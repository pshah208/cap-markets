"""Map an agent's tool calls onto the four Microsoft IQ layers.

An earlier version of this app emitted `iq_active` events from its *own* Python
function tools, so it always knew which layer was running. With native Foundry
connections the agent executes server-side and we never see the tool bodies - so
instead we poll run steps and infer the layer from each tool call's type and
payload.

Same SSE contract as before; different producer.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict
from typing import Any, Literal

from .bank_name import normalize_bank_text, normalize_citations

IQId = Literal["work", "fabric", "foundry", "web"]


@dataclass
class IQMeta:
    id: IQId
    name: str
    source: str
    blurb: str


IQS: dict[str, IQMeta] = {
    "work": IQMeta(
        "work", "Work IQ", "Microsoft 365 · Graph",
        "How the team works — email, Teams and coverage documents in context.",
    ),
    "fabric": IQMeta(
        "fabric", "Fabric IQ", "Microsoft Fabric · OneLake",
        "Governed business data — exposures, limits, covenants and concentration.",
    ),
    "foundry": IQMeta(
        "foundry", "Foundry IQ", "Azure AI Foundry · AI Search",
        "Reasoning grounded on the capital markets policy corpus.",
    ),
    "web": IQMeta(
        "web", "Web IQ", "Grounding with Bing",
        "Live external intelligence — news, ratings and market signal.",
    ),
}

# Classification is TWO-STAGE, and the order matters more than it looks.
#
# Stage 1 - the tool NAME alone, matched against unambiguous server labels. On
# the live agent every tool carries a `server_label` that identifies its layer
# exactly, so this is authoritative and the payload is never consulted.
#
# Stage 2 - name + payload, using the broader heuristics below. Only reached
# when the name is uninformative (a bare `mcp_call`, a function tool, an older
# agent build).
#
# WHY THE SPLIT EXISTS. The heuristics have to match on business vocabulary to
# be useful at all, but that vocabulary is shared across layers: a Work IQ mail
# search for "covenant pro-forma" contains "covenant", which is a Fabric term,
# and Fabric is tested first. Feeding the payload in unconditionally therefore
# lit the Fabric card for a Work IQ call. Anchoring on the label removes the
# ambiguity wherever a label exists - which, on this agent, is everywhere.
#
# Connection label conventions:
#   smclientintel               -> Fabric semantic model / data agent
#   kb-* / knowledgebase       -> Azure AI Search knowledge base
#   bing_grounding / web_search -> Grounding with Bing
#   WorkIQMail · WorkIQTeams · WorkIQSharePoint · WorkIQOneDrive ·
#   WorkIQWord · WorkIQCopilot  -> per-service managed MCP connections
#
# NOTE: Work IQ is wired as individual `agent365.svc.cloud.microsoft`
# connections rather than the single `workiq.svc` A2A tool. The A2A endpoint is
# metered against Copilot Credits and returns NoPolicy without a billing policy;
# the managed connections are not. All of them share the `WorkIQ` prefix, so one
# pattern covers them.
_LABEL_PATTERNS: list[tuple[re.Pattern[str], IQId]] = [
    # Work IQ first here: every one of its labels starts `WorkIQ`, and matching
    # it before the others means no Fabric or Foundry term in a mail body can
    # ever steal the attribution.
    # `_tool_label` prefixes the item type ("mcp_call WorkIQTeams"), so match the label as a word,
    # not only at the start - otherwise a Teams search mentioning "covenant" lights the Fabric card.
    (re.compile(r"(?:^|\s)workiq|agent365|mcp_(mail|teams|word|sharepoint|onedrive|m365copilot)",
                re.I), "work"),
    (re.compile(r"smclientintel|sm_client_intel|lh_client_intel|fabric_iq|fabricaihub"
                r"|ws-capital-markets-client-intel", re.I), "fabric"),
    (re.compile(r"\bkb-|knowledgebase|cm-client-policies|srch-cmintel|ai_search"
                r"|azure_ai_search|file_search", re.I), "foundry"),
    (re.compile(r"bing|web_search|grounding_web", re.I), "web"),
]

# Fallback heuristics - name AND payload. Broad by necessity, so only used when
# the label told us nothing.
_PATTERNS: list[tuple[re.Pattern[str], IQId]] = [
    # Fabric first. "cm-client-policies" and "sm_client_intel" both contain
    # "client", and the Work IQ patterns below are deliberately broad, so the
    # most specific match has to be tested first or the wrong card lights up.
    (re.compile(
        r"sm_client_intel|smclientintel|lh_client_intel|ws-capital-markets-client-intel"
        r"|fabric|onelake|lakehouse|semantic|dax|powerbi|power_bi|warehouse"
        r"|exposure|limits_utilization|credit_facilit|covenant|wallet_share"
        r"|risk_rating|revenue_by_product|client_360",
        re.I), "fabric"),
    (re.compile(
        r"workiq|work_iq|agent365|graph|outlook|mail|teams|chat|sharepoint"
        r"|onedrive|drive|m365|calendar|word",
        re.I), "work"),
    (re.compile(
        r"cm-client-policies|cm_client_policies|srch-cmintel|knowledgebase|knowledge_base"
        r"|azure_ai_search|ai_search|azure_search|file_search|policy|policies|retrieval|\bkb-|\bcp-\d",
        re.I), "foundry"),
    (re.compile(r"bing|web_search|grounding_web|bing-grounding|bing_grounding", re.I), "web"),
]

# Item types that are not evidence a layer was used.
#
# `mcp_list_tools` in particular is *discovery* - the service enumerates every
# connected MCP server at the start of a run whether or not it ends up being
# called. Lighting a card on that would make all four IQs glow on every single
# question, which destroys the whole point of the panel.
#
# `mcp_approval_request` is the opposite of evidence: it means the tool was
# BLOCKED pending a human approval that never comes over an API call. Counting
# it would light a card for a layer that produced nothing.
_IGNORED = re.compile(
    r"^(message|reasoning|mcp_list_tools|mcp_approval_request|"
    r"mcp_approval_response|function_call_output|"
    r"response\.(created|in_progress|completed|content_part|output_text))",
    re.I,
)


def is_invocation(item_type: str) -> bool:
    """True only for events that mean a tool actually ran."""
    return not _IGNORED.match(item_type.strip())

# Human-readable activity per layer, so the card says something meaningful.
_DETAIL = {
    "work": "Searching email, Teams and coverage records",
    "fabric": "Querying governed exposure and limit analytics",
    "foundry": "Retrieving global banking policy",
    "web": "Checking live external intelligence",
}


def classify(tool_name: str, payload: str = "") -> IQId | None:
    """Map a tool call to an IQ layer.

    The tool NAME is authoritative when it carries a recognised server label -
    the payload is not consulted at all in that case. Only an unlabelled call
    falls through to the broad name+payload heuristics, which can be fooled by
    shared business vocabulary (a Work IQ mail search that mentions "covenant"
    would otherwise light the Fabric card).
    """
    name = (tool_name or "").strip()
    for pattern, iq in _LABEL_PATTERNS:
        if pattern.search(name):
            return iq

    blob = f"{name} {payload}"
    for pattern, iq in _PATTERNS:
        if pattern.search(blob):
            return iq
    return None


def summarise_call(tool_name: str, payload: str) -> str:
    """A short, human phrase describing what the agent asked for."""
    q = ""
    if payload:
        try:
            data = json.loads(payload)
            if isinstance(data, dict):
                for k in ("query", "queryString", "question", "search", "input", "q"):
                    if data.get(k):
                        q = str(data[k])
                        break
                if not q:
                    q = json.dumps(data)[:160]
        except Exception:  # noqa: BLE001
            q = payload[:160]
    q = re.sub(r"\s+", " ", q).strip()
    return f'"{q[:120]}"' if q else tool_name


# --------------------------------------------------------------------------- #
# SSE frames
# --------------------------------------------------------------------------- #
def sse(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def iq_event(iq: IQId, status: str, detail: str = "") -> str:
    meta = IQS[iq]
    return sse("iq_active", {
        "iq": iq,
        "status": status,
        "detail": detail or _DETAIL.get(iq, ""),
        "source": meta.source,
        "name": meta.name,
    })


def token_event(text: str) -> str:
    # Deltas may split a label, URL or citation ID. Normalize the final message,
    # never isolated chunks, which have no sentence or Markdown context.
    return sse("token", {"text": text})


def message_event(text: str, citations: list[dict] | None = None) -> str:
    return sse("message", {"text": normalize_bank_text(text),
                           "citations": normalize_citations(citations)})


def status_event(text: str) -> str:
    return sse("status", {"text": text})


def error_event(text: str, detail: str = "") -> str:
    return sse("error", {"text": text, "detail": detail})


def done_event(**extra: Any) -> str:
    return sse("done", extra or {"ok": True})


def iq_catalogue() -> list[dict]:
    return [asdict(m) for m in IQS.values()]
