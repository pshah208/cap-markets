"""Actual Azure spend for the demo, from Cost Management.

Chapter 12 asks "what does it cost to run?". Tokens are only half of that
answer, and on this workload they are the *small* half: the Azure AI Search
service backing Foundry IQ is a provisioned Basic instance billed by the hour,
so it costs the same whether the agent is asked nine questions or nine thousand.
A slide that showed only the token bill would understate the real number by
roughly an order of magnitude, which is exactly the kind of plausible-but-wrong
figure this deck is about.

So this module reports **billed** cost - what Azure actually charged for the
resource group over the same window as the traces - grouped by resource, and
splits it into:

    metered    scales with questions asked (Foundry tokens, Log Analytics)
    fixed      provisioned capacity, charged whether or not anyone asks
               anything (AI Search, Container Apps, ACR)

Everything here is read-only, uses the app's managed identity (Cost Management
Reader on the resource group), and is cached hard: the Cost Management query API
is aggressively rate limited (HTTP 429) and billing data only settles every few
hours, so polling it on a 15-second slide refresh would be both rude and
pointless.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import date, timedelta

import httpx

from .config import settings

logger = logging.getLogger("cost")

ARM_SCOPE = "https://management.azure.com/.default"
QUERY_URL = (
    "https://management.azure.com{scope}/providers/Microsoft.CostManagement"
    "/query?api-version=2023-03-01"
)

# Billing data settles over hours, and the query API is rate limited. One hour
# of cache is far more than the data's own resolution.
CACHE_SECONDS = 3600

# Fallback cooldown after a 429 that carries no Retry-After header.
DEFAULT_BACKOFF_SECONDS = 300


# Cost Management meters one of its quota buckets per *client type*, keyed off
# the User-Agent. Callers that do not identify themselves all share one
# "DefaultQuota" bucket, which on a busy tenant is routinely exhausted by
# unrelated tools - the portal, the CLI, someone else's script. Sending a
# distinctive agent puts this app in its own bucket.
USER_AGENT = "cmci-client-intelligence/1.0 (chapter-12-agent-economics)"


class RateLimited(Exception):
    """Cost Management asked us to back off, and for how long."""

    def __init__(self, retry_after: int):
        super().__init__(f"rate limited, retry in {retry_after}s")
        self.retry_after = retry_after


def _retry_after(response: httpx.Response) -> int:
    """Seconds to wait, from whichever header the service populated.

    Cost Management spreads its cooldown across several headers depending on
    which quota bucket was exhausted - entity, tenant or client type - so any
    `costmanagement-*retry-after` is matched rather than a fixed list. Getting
    this wrong is not cosmetic: the client-type bucket asks for ~30 seconds,
    and defaulting to a flat five minutes turned a brief pause into a blank
    panel for ten times longer than the service actually wanted.
    """
    candidates = [response.headers.get("Retry-After")]
    candidates += [v for k, v in response.headers.items()
                   if "costmanagement" in k.lower() and k.lower().endswith("retry-after")]
    for raw in candidates:
        if not raw:
            continue
        try:
            return max(1, min(3600, int(float(raw))))
        except ValueError:
            continue
    return DEFAULT_BACKOFF_SECONDS

# Which resource types scale with usage. Everything else is provisioned capacity
# that is billed whether or not a single question is asked - which is the point
# the panel exists to make.
_METERED_TYPES = {
    "microsoft.cognitiveservices/accounts",       # Foundry - token consumption
    "microsoft.operationalinsights/workspaces",   # Log Analytics - ingestion
}

# Friendlier names than the raw resource id, and the role each plays in the
# architecture the previous slides described.
_ROLE = {
    "microsoft.search/searchservices": ("Azure AI Search", "Foundry IQ index"),
    "microsoft.cognitiveservices/accounts": ("Azure AI Foundry", "agent + models"),
    "microsoft.app/containerapps": ("Container Apps", "this app"),
    "microsoft.containerregistry/registries": ("Container Registry", "images"),
    "microsoft.operationalinsights/workspaces": ("Log Analytics", "traces + logs"),
    "microsoft.insights/components": ("Application Insights", "telemetry"),
}


def _describe(resource_id: str) -> tuple[str, str, str]:
    """(name, service, role) for a resource id, without an extra ARM call."""
    parts = resource_id.split("/")
    name = parts[-1] if parts else resource_id
    rtype = ""
    if "providers" in parts:
        i = parts.index("providers")
        if len(parts) > i + 2:
            rtype = f"{parts[i + 1]}/{parts[i + 2]}".lower()
    service, role = _ROLE.get(rtype, (rtype.split("/")[-1] or "Azure", ""))
    return name, service, role


def _is_metered(resource_id: str) -> bool:
    parts = resource_id.split("/")
    if "providers" not in parts:
        return False
    i = parts.index("providers")
    if len(parts) <= i + 2:
        return False
    return f"{parts[i + 1]}/{parts[i + 2]}".lower() in _METERED_TYPES


_token: tuple[str, float] | None = None
_token_lock = asyncio.Lock()


async def _access_token() -> str:
    """ARM token from the app's managed identity.

    Synchronous credential off-thread: `azure.identity.aio` needs aiohttp, which
    this image does not carry (see the same note in telemetry.py).
    """
    global _token
    async with _token_lock:
        if _token and _token[1] - 120 > time.time():
            return _token[0]

        def _fetch():
            from azure.identity import DefaultAzureCredential

            cred = DefaultAzureCredential()
            try:
                return cred.get_token(ARM_SCOPE)
            finally:
                cred.close()

        tok = await asyncio.to_thread(_fetch)
        _token = (tok.token, float(tok.expires_on))
        return tok.token


async def _fetch(window_days: int) -> dict:
    """Actual cost for the resource group, grouped by resource."""
    token = await _access_token()
    end = date.today()
    start = end - timedelta(days=window_days)
    body = {
        "type": "ActualCost",
        "timeframe": "Custom",
        "timePeriod": {"from": start.isoformat(), "to": end.isoformat()},
        "dataset": {
            "granularity": "None",
            "aggregation": {"totalCost": {"name": "Cost", "function": "Sum"}},
            "grouping": [{"type": "Dimension", "name": "ResourceId"}],
        },
    }
    url = QUERY_URL.format(scope=settings.cost_scope)

    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(url, json=body, headers={
            "Authorization": f"Bearer {token}",
            "User-Agent": USER_AGENT,
        })
    if r.status_code == 429:
        # Cost Management publishes its own cooldown. Honour it rather than
        # guessing: guessing low means hammering an API that is already telling
        # us to stop, and guessing high means a blank panel for longer than
        # necessary in front of an audience.
        raise RateLimited(_retry_after(r))
    if r.status_code >= 400:
        raise RuntimeError(f"Cost Management {r.status_code}: {r.text[:300]}")

    props = r.json().get("properties") or {}
    cols = [c["name"].lower() for c in props.get("columns") or []]
    rows = props.get("rows") or []

    items = []
    currency = "USD"
    for row in rows:
        rec = dict(zip(cols, row))
        rid = str(rec.get("resourceid") or "")
        if not rid:
            continue
        currency = str(rec.get("currency") or currency)
        name, service, role = _describe(rid)
        items.append({
            "name": name,
            "service": service,
            "role": role,
            "cost": round(float(rec.get("cost") or 0), 4),
            "metered": _is_metered(rid),
        })

    items.sort(key=lambda x: x["cost"], reverse=True)
    total = sum(i["cost"] for i in items)
    metered = sum(i["cost"] for i in items if i["metered"])
    for i in items:
        i["pct"] = round(100 * i["cost"] / total, 1) if total else 0.0

    return {
        "available": True,
        "detail": (
            f"Azure Cost Management · actual billed cost · "
            f"{start.isoformat()} to {end.isoformat()}"
        ),
        "error": "",
        "currency": currency,
        "windowDays": window_days,
        "from": start.isoformat(),
        "to": end.isoformat(),
        "total": round(total, 2),
        "metered": round(metered, 2),
        "fixed": round(total - metered, 2),
        "fixedPct": round(100 * (total - metered) / total, 1) if total else 0.0,
        "items": items,
    }


def _unavailable(reason: str, detail: str = "") -> dict:
    return {
        "available": False,
        "detail": reason,
        "error": detail,
        "currency": "USD",
        "windowDays": settings.cost_window_days,
        "from": "",
        "to": "",
        "total": 0.0,
        "metered": 0.0,
        "fixed": 0.0,
        "fixedPct": 0.0,
        "items": [],
    }


_cache: tuple[dict, float] | None = None
_cache_lock = asyncio.Lock()


async def snapshot() -> dict:
    """Billed Azure cost for the demo, cached. Never raises."""
    global _cache

    if not settings.cost_scope:
        return _unavailable(
            "Billed cost is not wired up here.",
            "Set COST_SCOPE to the resource group the demo runs in.")

    async with _cache_lock:
        if _cache and time.time() - _cache[1] < CACHE_SECONDS:
            return dict(_cache[0])
        try:
            snap = await _fetch(settings.cost_window_days)
            _cache = (snap, time.time())
            return dict(snap)
        except Exception as exc:  # noqa: BLE001
            limited = isinstance(exc, RateLimited)
            backoff = exc.retry_after if limited else DEFAULT_BACKOFF_SECONDS
            logger.warning("cost query failed (%s), backing off %ss",
                           str(exc)[:200], backoff)
            # Serve stale rather than blanking the panel: an hour-old billing
            # figure is still true, and a 429 is the most likely failure.
            if _cache:
                stale = dict(_cache[0])
                stale["detail"] += " · showing last successful read"
                _cache = (_cache[0], time.time() - CACHE_SECONDS + backoff)
                return stale
            out = _unavailable(
                "Billed cost is temporarily rate limited by Azure."
                if limited else "Could not read billed cost.",
                f"Azure Cost Management asked us to retry in {backoff}s."
                if limited else str(exc)[:300])
            _cache = (out, time.time() - CACHE_SECONDS + backoff)
            return out
