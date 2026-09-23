"""Agent run telemetry, read from Foundry's own traces.

Feeds chapter 12 of the guided story ("What it costs to run").

WHERE THE NUMBERS COME FROM
---------------------------
Token counts, latency and success are **measured by Foundry**, not by this app.
The Foundry project writes OpenTelemetry gen-AI spans to the Application
Insights component connected to it (see
`infra/modules/foundry-appinsights-connection.bicep`), and this module reads
them back out of the Log Analytics workspace behind that component:

    invoke_agent <agent>:<version>   one user question - duration, success
      chat <model>                   the model call - gen_ai.usage.input_tokens
                                     and gen_ai.usage.output_tokens
      execute_tool <server>.<tool>   one grounding call - maps to an IQ layer

Spans are correlated by `OperationId`, so one row out of the query is one
question the agent was asked, with the tokens it actually burned.

Nothing is synthesised. If the workspace is unreachable or has no traces the
snapshot says so and the slide renders an empty state, because a demo slide that
invents plausible telemetry is worse than one that admits it has none.

THE ONE DERIVED FIGURE is cost. Foundry does not emit a price, so cost is
`tokens x list price` from the table below, and is labelled as an estimate
everywhere it appears. Override with TOKEN_PRICE_INPUT_PER_1K /
TOKEN_PRICE_OUTPUT_PER_1K where the tenant has negotiated rates.

INGESTION LAG. Application Insights takes a minute or two to make a span
queryable. The BFF therefore also counts the runs it has served in this process
and reports how many are not yet visible in the traces, so a question asked on
stage is acknowledged rather than appearing to have been lost.
"""

from __future__ import annotations

import asyncio
import json as _json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

import httpx

from .config import settings
from .cost import snapshot as billed_cost
from .iq import IQS, classify

logger = logging.getLogger("telemetry")

CURRENCY = "USD"

# Runs plotted on the per-run charts (the most recent N).
SERIES_POINTS = 24

# Recent runs listed in the table under the charts.
RECENT_RUNS = 6

# Trace queries are cached for this long. The slide polls every 15s and several
# people may have it open; the underlying data only changes when someone asks a
# question, so re-querying Log Analytics on every poll buys nothing.
CACHE_SECONDS = 25

LOG_ANALYTICS_SCOPE = "https://api.loganalytics.io/.default"
LOG_ANALYTICS_URL = "https://api.loganalytics.io/v1/workspaces/{ws}/query"

# Published Azure OpenAI global-standard list price per 1,000 tokens, in USD.
#
# USD deliberately: Cost Management bills this subscription in USD, and the
# slide shows estimated token cost beside actual billed cost. Converting one of
# them through an invented FX rate would make two numbers that must be compared
# incomparable.
#
# Matched by longest prefix, because deployments carry date and variant suffixes
# ("gpt-5.6-sol-2026-07-09").
_DEFAULT_PRICES: dict[str, tuple[float, float]] = {
    "gpt-5":        (0.00125, 0.01000),
    "gpt-5-mini":   (0.00025, 0.00200),
    "gpt-5-nano":   (0.00005, 0.00040),
    "gpt-4o":       (0.00250, 0.01000),
    "gpt-4o-mini":  (0.00015, 0.00060),
    "gpt-4.1":      (0.00200, 0.00800),
    "gpt-4.1-mini": (0.00040, 0.00160),
    "o4-mini":      (0.00110, 0.00440),
}
_FALLBACK_PRICE = (0.00125, 0.01000)


def _price_for(model: str) -> tuple[float, float]:
    """Input/output price per 1k tokens for a model name."""
    env_in = os.getenv("TOKEN_PRICE_INPUT_PER_1K")
    env_out = os.getenv("TOKEN_PRICE_OUTPUT_PER_1K")
    if env_in and env_out:
        try:
            return float(env_in), float(env_out)
        except ValueError:
            pass

    name = (model or "").lower().replace("_", "-")
    best = ""
    for key in _DEFAULT_PRICES:
        if name.startswith(key) and len(key) > len(best):
            best = key
    return _DEFAULT_PRICES.get(best, _FALLBACK_PRICE)


def _layer_for(tool_span: str) -> str | None:
    """Map an `execute_tool <server>.<tool>` span name onto an IQ layer."""
    name = tool_span.replace("execute_tool", "", 1).strip()
    if name.startswith("web.") or name == "web":
        return "web"
    return classify(name)


# --------------------------------------------------------------------------- #
# Session-local record of what this process has served. Used ONLY to report how
# many runs are still waiting on trace ingestion - never to fabricate a number.


@dataclass
class _SessionRun:
    ts: datetime
    ok: bool


_session: list[_SessionRun] = []
_session_lock = threading.Lock()


def record_run(*, ok: bool = True, **_ignored) -> None:
    """Note that this process served a run. Never raises.

    Deliberately stores no tokens, cost or question content: Foundry's traces
    are the source for all of that, and a second, less accurate copy of the same
    figure is how a dashboard starts lying.
    """
    try:
        with _session_lock:
            _session.append(_SessionRun(datetime.now(timezone.utc), ok))
            if len(_session) > 500:
                del _session[: len(_session) - 500]
    except Exception:  # noqa: BLE001 - telemetry is best-effort by design
        pass


def estimate_tokens(text: str) -> int:
    """Kept for callers that pass an estimate; estimates are never stored."""
    return max(1, round(len(text or "") / 4))


def usage_from_payload(payload: dict) -> tuple[int, int, str]:
    """Pull (input_tokens, output_tokens, model) out of a Responses payload.

    Still parsed so the BFF can log what a run cost, but the slide reads the
    same figures from Foundry's traces rather than trusting this process.
    """
    usage = payload.get("usage") or {}
    if not isinstance(usage, dict):
        usage = {}
    inp = usage.get("input_tokens", usage.get("prompt_tokens", 0)) or 0
    out = usage.get("output_tokens", usage.get("completion_tokens", 0)) or 0
    model = payload.get("model") or ""
    return int(inp), int(out), model if isinstance(model, str) else ""


# --------------------------------------------------------------------------- #
# Log Analytics access.

_token: tuple[str, float] | None = None
_token_lock = asyncio.Lock()


async def _access_token() -> str:
    """Bearer token for the Log Analytics API, from the app's managed identity.

    The container app runs as the user-assigned identity `id-cmci`, which holds
    Monitoring Reader on the workspace. DefaultAzureCredential picks that up
    from AZURE_CLIENT_ID inside the container, and a developer's `az login`
    locally.

    The SYNCHRONOUS credential is used, off-thread. `azure.identity.aio`
    requires aiohttp, which this image deliberately does not carry (the rest of
    the BFF is httpx), and importing it fails at runtime with "aiohttp package
    is not installed" - which is silently swallowed as "could not read traces".
    """
    global _token
    async with _token_lock:
        if _token and _token[1] - 120 > time.time():
            return _token[0]

        def _fetch():
            from azure.identity import DefaultAzureCredential

            cred = DefaultAzureCredential()
            try:
                return cred.get_token(LOG_ANALYTICS_SCOPE)
            finally:
                cred.close()

        tok = await asyncio.to_thread(_fetch)
        _token = (tok.token, float(tok.expires_on))
        return tok.token


def _query(window_days: int, agent: str) -> str:
    """KQL: one row per question the agent was asked.

    `invoke_agent` is the unit of work; its `chat` child carries the token usage
    and its `execute_tool` children say which layers were reached. Runs with no
    usage AND no tools are dropped - those are aborted or no-op invocations that
    would otherwise show up as free questions and flatter the average.
    """
    agent_filter = (
        f"| where tostring(P['gen_ai.agent.name']) == '{agent}'" if agent else ""
    )
    return " ".join(f"""
        let win = {int(window_days)}d;
        let spans = AppDependencies
        | where TimeGenerated > ago(win)
        | extend P = parse_json(Properties);
        let runs = spans
        | where Name startswith 'invoke_agent'
        {agent_filter}
        | summarize ts = min(TimeGenerated), durationMs = sum(DurationMs),
                    fails = countif(Success == false) by OperationId;
        let usage = spans
        | where Name startswith 'chat '
        | summarize inTok = sum(toint(P['gen_ai.usage.input_tokens'])),
                    outTok = sum(toint(P['gen_ai.usage.output_tokens'])),
                    model = any(tostring(P['gen_ai.response.model'])),
                    calls = count() by OperationId;
        let tools = spans
        | where Name startswith 'execute_tool'
        | summarize tools = make_set(Name), toolCount = count() by OperationId;
        runs
        | join kind=leftouter usage on OperationId
        | join kind=leftouter tools on OperationId
        | where isnotnull(inTok) or isnotnull(toolCount)
        | project ts, durationMs, fails, inTok, outTok, model, calls, toolCount, tools
        | order by ts asc
    """.split())


@dataclass
class FoundryRun:
    """One question, as Foundry recorded it."""

    ts: datetime
    ok: bool
    latency_ms: float
    input_tokens: int
    output_tokens: int
    model: str
    layers: list[str] = field(default_factory=list)
    tool_calls: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def cost(self) -> float:
        pin, pout = _price_for(self.model)
        return (self.input_tokens / 1000) * pin + (self.output_tokens / 1000) * pout


async def _fetch_runs() -> list[FoundryRun]:
    """Run the trace query. Raises on failure so the caller can report why."""
    token = await _access_token()
    body = {"query": _query(settings.telemetry_window_days, settings.agent_name)}
    url = LOG_ANALYTICS_URL.format(ws=settings.log_analytics_workspace_id)

    async with httpx.AsyncClient(timeout=45) as client:
        r = await client.post(url, json=body,
                              headers={"Authorization": f"Bearer {token}"})
    if r.status_code >= 400:
        raise RuntimeError(f"Log Analytics {r.status_code}: {r.text[:300]}")

    tables = r.json().get("tables") or []
    if not tables:
        return []
    cols = [c["name"] for c in tables[0]["columns"]]
    out: list[FoundryRun] = []
    for row in tables[0]["rows"]:
        rec = dict(zip(cols, row))
        raw_tools = rec.get("tools") or []
        if isinstance(raw_tools, str):
            try:
                raw_tools = _json.loads(raw_tools)
            except ValueError:
                raw_tools = []
        layers = sorted({iq for iq in (_layer_for(str(t)) for t in raw_tools) if iq})
        try:
            when = datetime.fromisoformat(str(rec.get("ts") or "").replace("Z", "+00:00"))
        except ValueError:
            continue
        out.append(FoundryRun(
            ts=when,
            ok=not int(rec.get("fails") or 0),
            latency_ms=float(rec.get("durationMs") or 0),
            input_tokens=int(rec.get("inTok") or 0),
            output_tokens=int(rec.get("outTok") or 0),
            model=str(rec.get("model") or ""),
            layers=layers,
            tool_calls=int(rec.get("toolCount") or 0),
        ))
    out.sort(key=lambda r: r.ts)
    return out


_cache: tuple[dict, float] | None = None
_cache_lock = asyncio.Lock()


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, round((pct / 100) * (len(ordered) - 1))))
    return ordered[idx]


def _pending(newest: datetime | None) -> int:
    """Runs this process served that the traces have not caught up with yet."""
    with _session_lock:
        if newest is None:
            return len(_session)
        return sum(1 for s in _session if s.ts > newest)


def _empty(reason: str, detail: str = "") -> dict:
    return {
        "asOf": datetime.now(timezone.utc).isoformat(),
        "source": "unavailable",
        "sourceDetail": reason,
        "sourceError": detail,
        "currency": CURRENCY,
        "model": "",
        "windowDays": settings.telemetry_window_days,
        "pendingRuns": _pending(None),
        "pricing": {"model": "", "inputPer1k": 0.0, "outputPer1k": 0.0,
                    "currency": CURRENCY, "basis": "list price estimate"},
        "totals": {k: 0 for k in (
            "runs", "okRuns", "failedRuns", "successPct", "inputTokens",
            "outputTokens", "totalTokens", "cost", "costPerRun", "tokensPerRun",
            "avgLatencyMs", "p95LatencyMs", "avgToolCalls")},
        "series": [],
        "byLayer": [],
        "recent": [],
        "billed": None,
        "allIn": None,
    }


def _build(runs: list[FoundryRun]) -> dict:
    now = datetime.now(timezone.utc)
    model = next((r.model for r in reversed(runs) if r.model), "")
    pin, pout = _price_for(model)

    total_in = sum(r.input_tokens for r in runs)
    total_out = sum(r.output_tokens for r in runs)
    total_cost = sum(r.cost for r in runs)
    ok_runs = sum(1 for r in runs if r.ok)
    latencies = [r.latency_ms for r in runs]

    tail = runs[-SERIES_POINTS:]
    running = sum(r.cost for r in runs[: max(0, len(runs) - SERIES_POINTS)])
    series = []
    for r in tail:
        running += r.cost
        series.append({
            "t": r.ts.isoformat(),
            "label": r.ts.astimezone().strftime("%d %b %H:%M"),
            "inputTokens": r.input_tokens,
            "outputTokens": r.output_tokens,
            "totalTokens": r.total_tokens,
            "cost": round(r.cost, 4),
            "cumulativeCost": round(running, 4),
            "latencyMs": round(r.latency_ms),
            "ok": r.ok,
            "layers": r.layers,
        })

    by_layer = []
    for iq_id, meta in IQS.items():
        hits = [r for r in runs if iq_id in r.layers]
        if not hits:
            continue
        # A run that reached three layers spread its tokens across those three:
        # the context is shared, so charging the whole run to each layer would
        # treble the bill.
        tokens = sum(r.total_tokens / max(1, len(r.layers)) for r in hits)
        cost = sum(r.cost / max(1, len(r.layers)) for r in hits)
        by_layer.append({"id": iq_id, "name": meta.name, "runs": len(hits),
                         "tokens": round(tokens), "cost": round(cost, 4)})
    layer_total = sum(x["tokens"] for x in by_layer) or 1
    for x in by_layer:
        x["pct"] = round(100 * x["tokens"] / layer_total, 1)
    by_layer.sort(key=lambda x: x["tokens"], reverse=True)

    recent = [{
        "t": r.ts.isoformat(),
        "label": r.ts.astimezone().strftime("%d %b %H:%M"),
        "ok": r.ok,
        "latencyMs": round(r.latency_ms),
        "totalTokens": r.total_tokens,
        "cost": round(r.cost, 4),
        "layers": r.layers,
        "toolCalls": r.tool_calls,
        "model": r.model,
    } for r in reversed(runs[-RECENT_RUNS:])]

    return {
        "asOf": now.isoformat(),
        "source": "foundry",
        "sourceDetail": (
            f"Foundry agent traces · Application Insights · last "
            f"{settings.telemetry_window_days} days"
        ),
        "sourceError": "",
        "currency": CURRENCY,
        "model": model,
        "windowDays": settings.telemetry_window_days,
        "pendingRuns": _pending(runs[-1].ts if runs else None),
        "pricing": {
            "model": model,
            "inputPer1k": pin,
            "outputPer1k": pout,
            "currency": CURRENCY,
            "basis": "list-price estimate — Foundry does not emit a price",
        },
        "totals": {
            "runs": len(runs),
            "okRuns": ok_runs,
            "failedRuns": len(runs) - ok_runs,
            "successPct": round(100 * ok_runs / len(runs), 1) if runs else 0.0,
            "inputTokens": total_in,
            "outputTokens": total_out,
            "totalTokens": total_in + total_out,
            "cost": round(total_cost, 4),
            "costPerRun": round(total_cost / len(runs), 4) if runs else 0.0,
            "tokensPerRun": round((total_in + total_out) / len(runs)) if runs else 0,
            "avgLatencyMs": round(sum(latencies) / len(latencies)) if latencies else 0,
            "p95LatencyMs": round(_percentile(latencies, 95)),
            "avgToolCalls": (
                round(sum(r.tool_calls for r in runs) / len(runs), 1) if runs else 0.0
            ),
        },
        "series": series,
        "byLayer": by_layer,
        "recent": recent,
        "billed": None,
        "allIn": None,
    }


async def snapshot() -> dict:
    """Everything chapter 12 renders: Foundry traces plus billed Azure cost."""
    global _cache

    if not settings.log_analytics_workspace_id:
        snap = _empty(
            "Foundry tracing is not wired up here.",
            "Set LOG_ANALYTICS_WORKSPACE_ID to the workspace behind the "
            "project's Application Insights connection.")
        snap["billed"] = await billed_cost()
        return snap

    async with _cache_lock:
        fresh = _cache and time.time() - _cache[1] < CACHE_SECONDS
        if not fresh:
            try:
                runs = await _fetch_runs()
                _cache = ((_build(runs) if runs else _empty(
                    "No agent traces in the window yet.",
                    "Ask the agent a question — traces appear a minute or two "
                    "later.")), time.time())
            except Exception as exc:  # noqa: BLE001
                logger.warning("foundry telemetry query failed: %s", str(exc)[:400])
                snap = _empty("Could not read Foundry traces.", str(exc)[:400])
                snap["billed"] = await billed_cost()
                return snap

        snap = dict(_cache[0])

    # Pending is cheap, changes between polls, and must not be served stale -
    # it is the only acknowledgement a presenter gets that the question they
    # just asked has been served but not yet ingested.
    newest = snap["series"][-1]["t"] if snap["series"] else None
    snap["pendingRuns"] = _pending(
        datetime.fromisoformat(newest) if newest else None)

    # Billed cost is cached on its own much longer clock, so it is attached
    # here rather than baked into the trace snapshot.
    billed = await billed_cost()
    snap["billed"] = billed

    # The number the panel exists to produce: what a question really costs once
    # the provisioned services it depends on are counted, not just its tokens.
    #
    # Deliberately computed here rather than in the browser, and deliberately
    # NOT shown unless both windows are known - dividing a 30-day bill by 7 days
    # of questions would be a fabricated ratio, which is the exact failure this
    # slide was rebuilt to avoid.
    runs_n = snap["totals"]["runs"]
    if billed.get("available") and runs_n and billed.get("windowDays"):
        scale = snap["windowDays"] / billed["windowDays"]
        platform_in_window = billed["total"] * scale
        snap["allIn"] = {
            "platformCost": round(platform_in_window, 2),
            "costPerQuestion": round(platform_in_window / runs_n, 3),
            "tokenCostPerQuestion": snap["totals"]["costPerRun"],
            "multiple": (
                round(platform_in_window / snap["totals"]["cost"], 1)
                if snap["totals"]["cost"] else 0.0
            ),
            "basis": (
                f"{billed['windowDays']}-day bill scaled to the "
                f"{snap['windowDays']}-day trace window, over {runs_n} question"
                f"{'' if runs_n == 1 else 's'}"
            ),
        }
    else:
        snap["allIn"] = None

    return snap
