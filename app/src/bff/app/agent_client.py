"""Runs the Foundry agent as the signed-in user and streams progress as SSE.

WHY THIS TARGETS THE RESPONSES API
----------------------------------
Foundry has two agent surfaces. The older *assistants* API (threads / runs /
run-steps, exposed by the `azure-ai-agents` SDK) and the newer **prompt agent**
surface invoked through the OpenAI-compatible **Responses API**. An agent built
in the Foundry portal today is the latter, and it is invisible to the assistants
API - `list_agents()` returns an empty list even though the agent plainly exists.

So we call:

    POST {project}/openai/responses?api-version=2025-05-15-preview
    { "agent_reference": {"name": "<agent>"}, "input": "<question>", "stream": true }

Note `agent_reference`, not `agent` - the latter is deprecated and returns 400.

Streaming is a genuine win here: tool calls arrive as events, so the IQ cards
light up from the agent's real activity as it happens, with no polling.

TWO THINGS THIS DELIBERATELY DOES
---------------------------------
1. **On-Behalf-Of.** The call carries a token exchanged for the signed-in user, so
   Work IQ grounds on that user's mailbox, Teams and files - never the app identity.

2. **Citations kept separate from prose.** The Foundry playground splices citation
   markers in by character offset, which corrupts digits inside numbers and
   identifiers (`180 days` -> `[14]80 days`, `BR-202` -> `BR-[12]0[12]`). We return
   the answer text and its citations as separate fields and let the client render
   them, so numbers cannot be mangled.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, AsyncGenerator

import httpx

from . import telemetry
from .auth import User, exchange_obo
from .config import settings
from .iq import (
    classify,
    done_event,
    error_event,
    iq_event,
    is_invocation,
    message_event,
    status_event,
    summarise_call,
    token_event,
)

logger = logging.getLogger("agent")

API_VERSION = "2025-05-15-preview"


def responses_url() -> str:
    base = settings.project_endpoint.rstrip("/")
    return f"{base}/openai/responses?api-version={API_VERSION}"


def _strip_markers(text: str) -> str:
    """Remove citation placeholders and per-layer prose narration.

    Two categories of noise are removed:

    * Citation markers the service embeds mid-sentence (%%CITATION_N%%, and the
      Chinese-brackets form 【...】). These belong in the citation list, not in
      the prose.

    * Layer narration - the agent has a strong habit of prefixing sentences with
      "**Work IQ:**", "Fabric IQ says ...", "From Foundry IQ ...", "Web IQ
      confirms ...". The active-card animation in the left panel already tells
      the user which layer produced what, so the prose repetition is clutter and
      obscures the answer. The BFF strips it defensively - instructions alone
      only reduce the frequency, they never eliminate it.

    Runs on every streamed chunk, so patterns are tightly anchored to avoid
    eating real prose that happens to mention a layer.
    """
    text = re.sub(r"%%CITATION_\d+%%", "", text)
    text = re.sub(r"【[^】]*】", "", text)

    # Strip layer narration at the start of a line or bullet:
    #
    #   "**Fabric IQ:** foo"          -> "foo"
    #   "**Foundry IQ**: foo"         -> "foo"
    #   "**Foundry IQ context:** foo" -> "foo"
    #   "- **Work IQ:** foo"          -> "- foo"
    #   "**Fabric IQ** shows the ..." -> "shows the ..."
    #   "From Fabric IQ, foo"         -> "foo"
    #   "Web IQ result: foo"          -> "foo"
    #
    # Anchored to line start so mid-sentence mentions ("the Fabric IQ layer is
    # ...") are left alone. Handles the optional leading bullet by rewriting
    # rather than deleting it, so list structure survives.
    #
    # The `\*{0,2}` blocks are sprinkled to tolerate boldface markers in any of
    # the three positions Foundry produces: `**Layer:**`, `**Layer**:`, and
    # `**Layer:** **X**` context prefixes.
    layer = r"(?:Work|Fabric|Foundry|Web)\s+IQ"
    narrator = (r"(?:says|shows|reports|confirms|context|result|response"
                r"|only|note|indicates)")

    def _keep_bullet(m: "re.Match[str]") -> str:
        return m.group("bullet") or ""

    # Pattern A: [Layer][ narrator][:-,]  (colon can be inside or outside **)
    text = re.sub(
        rf"""(?imx)
            ^(?P<bullet>[-*]\s+)?
            \*{{0,2}}
            (?:from\s+|per\s+|according\s+to\s+)?
            {layer}
            \*{{0,2}}
            (?:\s+{narrator})?
            \*{{0,2}}
            \s*[:\-\u2014,]
            \*{{0,2}}
            \s+
        """,
        _keep_bullet,
        text,
    )

    # Pattern B: **Layer** shows ...   (boldfaced tag directly followed by verb,
    # no colon). "Fabric IQ shows" without ** is left alone - too likely to be
    # real prose.
    text = re.sub(
        rf"(?im)^(?P<bullet>[-*]\s+)?"
        rf"\*{{1,2}}{layer}\*{{1,2}}\s+(?={narrator}\b)",
        _keep_bullet,
        text,
    )

    # Standalone "Fabric IQ." on its own bullet line, no content.
    text = re.sub(
        rf"(?im)^\s*[-*]?\s*\*{{0,2}}{layer}\*{{0,2}}\s*[.!:]?\s*$\n?",
        "",
        text,
    )

    return text


def _tool_label(item: dict) -> tuple[str, str]:
    """Best-effort (name, payload) for an output item representing a tool call."""
    kind = item.get("type", "") or ""
    name = (
        item.get("server_label")
        or item.get("name")
        or item.get("tool_name")
        or kind
    )
    payload = ""
    for key in ("arguments", "query", "input", "queries"):
        val = item.get(key)
        if val:
            payload = val if isinstance(val, str) else json.dumps(val)
            break
    return f"{kind} {name}".strip(), payload


def _item_error(item: dict) -> str:
    """Return a human-readable error for a tool call item, or '' if it succeeded.

    A failed MCP call still arrives as a normal output item - the only signal is
    a populated `error`. Foundry sometimes reports it as a bare string
    ("MCP tool call failed") and sometimes as an object, so both are handled.
    """
    err = item.get("error")
    if not err:
        return ""
    label = item.get("server_label") or item.get("name") or item.get("type") or "tool"
    if isinstance(err, dict):
        text = err.get("message") or err.get("code") or json.dumps(err)
    else:
        text = str(err)
    return f"{label}: {text}"


def _collect_tool_errors(payload: dict) -> list[str]:
    """Every tool failure in a completed response, in call order."""
    out: list[str] = []
    for item in payload.get("output", []) or []:
        if isinstance(item, dict):
            msg = _item_error(item)
            if msg and msg not in out:
                out.append(msg)
    return out


def _empty_answer_detail(tool_errors: list[str], status: str) -> str:
    """Explain an empty answer using whatever the run actually told us."""
    if tool_errors:
        return ("A grounding tool failed, so the agent had nothing to answer from: "
                + "; ".join(tool_errors))
    return (
        f"The agent completed (status={status or 'unknown'}) but produced no text, "
        "and no tool reported an error. The grounding tools most likely returned "
        "zero results for your identity - Work IQ and Fabric IQ are security "
        "trimmed, so check that this user has a provisioned mailbox, Teams "
        "membership and Fabric workspace access."
    )


def _collect_citations(payload: dict) -> list[dict]:
    """Pull url/file citation annotations out of a completed response."""
    out: list[dict] = []
    seen: set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if node.get("type") in ("url_citation", "file_citation"):
                key = node.get("url") or node.get("file_id") or node.get("title", "")
                if key and key not in seen:
                    seen.add(key)
                    out.append({
                        "kind": "url" if node.get("type") == "url_citation" else "file",
                        "title": node.get("title") or node.get("filename") or "",
                        "url": node.get("url", ""),
                        "fileId": node.get("file_id", ""),
                    })
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(payload)
    return out


def _extract_text(payload: dict) -> str:
    """Concatenate the assistant's output text from a completed response."""
    if isinstance(payload.get("output_text"), str) and payload["output_text"]:
        return payload["output_text"]
    parts: list[str] = []
    for item in payload.get("output", []) or []:
        if item.get("type") != "message":
            continue
        for c in item.get("content", []) or []:
            if c.get("type") in ("output_text", "text") and c.get("text"):
                parts.append(c["text"])
    return "".join(parts)


def is_transient(detail: str) -> bool:
    """True when a failure is worth retrying rather than reporting.

    Fabric IQ on a small capacity (F4) intermittently rejects its schema call
    with "Power BI couldn't process that request right now" or a 429. The
    semantic model itself is healthy - direct DAX against it succeeds - so this
    is throttling, not a broken model or a bad question.
    """
    low = (detail or "").lower()
    return any(m in low for m in (
        "couldn't process that request right now",
        "could not process that request right now",
        "mcpprotocolexception",
        "getsemanticmodelschema",
        "too many requests",
        "429",
        "503",
        "service unavailable",
        "temporarily unavailable",
    ))


_MAX_TRANSIENT_RETRIES = 2
_RETRY_BACKOFF_SECONDS = 6


async def run_agent(user: User, question: str,
                    thread_id: str | None = None) -> AsyncGenerator[str, None]:
    """Yield SSE frames for one question, retrying transient tool failures.

    A single failing tool aborts the WHOLE response rather than degrading to the
    other three layers. In front of an audience that is the worst possible
    failure mode, so a throttled data layer is retried silently instead of being
    reported as an error.

    Frames are buffered per attempt: a retry must not leave half an answer and a
    set of lit IQ cards on screen from the attempt that failed.
    """
    if settings.mock_mode:
        async for frame in _mock(question):
            yield frame
        return

    for attempt in range(1, _MAX_TRANSIENT_RETRIES + 2):
        # Buffer only while we haven't yielded anything the browser can act on
        # yet. Once the first status / iq_active / message / text delta lands,
        # we stream through - so the IQ cards can light up in real time.
        #
        # If a transient tool failure lands DURING those first few frames (the
        # common F4 throttling case), we can still safely retry, because the
        # browser has seen at most an "Authenticating..." status.
        buffer: list[str] = []
        streaming = False
        failed_transiently = False

        async for frame in _run_agent_once(user, question, thread_id):
            if streaming:
                yield frame
                continue

            # Still in the pre-content phase. Anything that isn't a plain
            # status update is user-visible progress and flips us into
            # streaming mode.
            if not frame.startswith("event: status"):
                # Flush what we buffered, then let the frame through.
                for pending in buffer:
                    yield pending
                buffer = []
                streaming = True
                yield frame
                continue

            buffer.append(frame)
            if '"event": "error"' in frame or frame.startswith("event: error"):
                if is_transient(frame):
                    failed_transiently = True
                    break

        if streaming or not failed_transiently or attempt > _MAX_TRANSIENT_RETRIES:
            # Either we already streamed everything, or the failure isn't
            # worth retrying, or we've exhausted retries. Flush anything
            # still buffered and stop.
            for pending in buffer:
                yield pending
            return

        logger.warning("transient tool failure before content, retry %d", attempt)
        yield status_event(
            f"The data layer is busy — retrying ({attempt} of "
            f"{_MAX_TRANSIENT_RETRIES})…")
        await asyncio.sleep(_RETRY_BACKOFF_SECONDS * attempt)


async def _run_agent_once(user: User, question: str,
                          thread_id: str | None = None) -> AsyncGenerator[str, None]:
    """One attempt at answering. See run_agent for the retry policy."""
    try:
        yield status_event("Authenticating on your behalf…")
        token = await exchange_obo(user)
    except Exception as exc:  # noqa: BLE001
        telemetry.record_run(ok=False)
        yield error_event("Could not authenticate to the agent.",
                          str(getattr(exc, "detail", exc))[:600])
        yield done_event(ok=False)
        return

    body: dict[str, Any] = {
        # Both keys are required. `agent_reference` replaces the deprecated
        # `agent` property, and the nested object must carry its own "type" -
        # omitting it returns 400 invalid_payload.
        "agent_reference": {
            "type": "agent_reference",
            "name": settings.agent_name,
        },
        "input": question,
        "stream": True,
    }
    # Continue the conversation when we have a prior response id.
    if thread_id:
        body["previous_response_id"] = thread_id

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    active: set[str] = set()
    seen_calls: set[str] = set()
    # item_id -> (name, payload). Populated when a tool is first announced via
    # response.output_item.added; consulted when a subsequent .in_progress event
    # tells us that same tool has actually started running. Without this map,
    # the .in_progress event arrives with only an item_id and we would not know
    # which IQ layer to light up.
    item_labels: dict[str, tuple[str, str]] = {}
    text_acc = ""
    citations: list[dict] = []
    response_id = thread_id
    tool_errors: list[str] = []
    final_status = ""
    # Token accounting for chapter 12. `usage` only arrives on the terminal
    # response event, so it is captured there and read back by _finish.
    usage_in = 0
    usage_out = 0
    usage_model = ""

    def _finish(ok: bool) -> None:
        """Note the run for the ingestion-lag counter.

        Token and latency figures for the slide come from Foundry's own traces,
        so nothing measured here is stored - only that a run happened, and when.
        """
        if usage_in or usage_out:
            logger.info("run tokens in=%s out=%s model=%s",
                        usage_in, usage_out, usage_model or "?")
        telemetry.record_run(ok=ok)

    yield status_event("Thinking…")

    # Watchdog: if the server goes silent for this long between events, treat
    # the stream as stalled. The Foundry service does keep sending progress
    # events (`response.mcp_call.in_progress`, `.completed`, etc.) throughout a
    # normal run, so 90 seconds of dead air really does mean it is stuck.
    IDLE_WATCHDOG_S = 90

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=30.0)) as client:
            async with client.stream("POST", responses_url(),
                                     headers=headers, json=body) as resp:
                if resp.status_code >= 400:
                    raw = (await resp.aread()).decode("utf-8", "replace")
                    async for frame in _fallback_nonstreaming(
                        client, headers, body, active, raw
                    ):
                        yield frame
                    return

                line_iter = resp.aiter_lines()
                while True:
                    try:
                        line = await asyncio.wait_for(
                            line_iter.__anext__(), timeout=IDLE_WATCHDOG_S)
                    except StopAsyncIteration:
                        break
                    except asyncio.TimeoutError:
                        logger.warning(
                            "SSE idle for %ss, aborting run for %s",
                            IDLE_WATCHDOG_S, user.upn)
                        for iq in list(active):
                            yield iq_event(iq, "done", "stopped")
                        _finish(ok=False)
                        yield error_event(
                            "The agent went quiet.",
                            f"No progress event for {IDLE_WATCHDOG_S} seconds. "
                            "The upstream service may be stalled - "
                            "please try again in a moment.")
                        yield done_event(ok=False, layers=sorted(active))
                        return

                    if not line or not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if not data or data == "[DONE]":
                        continue
                    try:
                        evt = json.loads(data)
                    except json.JSONDecodeError:
                        continue

                    etype = evt.get("type", "")

                    # Streamed prose. Forwarded to the browser as it arrives, not
                    # just accumulated: a grounded answer on this book takes 30s
                    # to three minutes, almost all of it tool latency, and
                    # holding the text back turns that into a blank spinner.
                    # Streaming does not make the answer faster - it makes the
                    # wait legible, which is the part the audience feels.
                    #
                    # `text_acc` is still maintained because the final `message`
                    # event carries the whole answer plus its citations, and the
                    # client replaces the streamed text with it. That keeps the
                    # citation-separation guarantee intact: nothing is ever
                    # spliced into a partial string.
                    if etype.endswith("output_text.delta"):
                        delta = evt.get("delta", "") or ""
                        if delta:
                            text_acc += delta
                            yield token_event(delta)
                        continue

                    # A tool actually ran -> light up its IQ layer. There are
                    # two signals to catch:
                    #
                    #   1) `response.output_item.added` (and .done) - carries the
                    #      full item, including server_label. Populates our
                    #      id -> (name, payload) lookup so a later .in_progress
                    #      event can identify its tool.
                    #
                    #   2) `response.mcp_call.in_progress`,
                    #      `response.web_search_call.in_progress` etc. - these
                    #      fire the MOMENT the tool starts running, which is
                    #      often several seconds before .completed. The item is
                    #      identified only by item_id, so we look it up.
                    #
                    # Discovery events (mcp_list_tools) are filtered out by
                    # is_invocation, otherwise every layer would glow on every
                    # question. mcp_approval_request would falsely light up a
                    # layer whose tool is BLOCKED - also filtered.
                    if "output_item" in etype or "tool" in etype:
                        item = evt.get("item") or evt.get("output_item") or {}
                        if isinstance(item, dict) and item:
                            item_type = item.get("type", "")
                            if not is_invocation(item_type):
                                continue
                            # A failed tool is the single most useful thing we
                            # can report, so capture it even if we cannot map
                            # the call onto an IQ layer.
                            err = _item_error(item)
                            if err and err not in tool_errors:
                                tool_errors.append(err)
                                logger.warning("tool failed for %s: %s", user.upn, err)
                            key = item.get("id") or json.dumps(item)[:80]
                            name, payload = _tool_label(item)
                            if item.get("id"):
                                # Cache before the corresponding .in_progress
                                # event might land.
                                item_labels[item["id"]] = (name, payload)
                            if key not in seen_calls:
                                seen_calls.add(key)
                                iq = classify(name, payload)
                                if iq and iq not in active:
                                    active.add(iq)
                                    yield iq_event(iq, "active",
                                                   summarise_call(name, payload))

                    # Tool actually starting to run - fire "active" now, not on
                    # completion.
                    elif ".in_progress" in etype and etype != "response.in_progress":
                        item_id = evt.get("item_id") or ""
                        name, payload = item_labels.get(item_id, ("", ""))
                        # Fall back to the event type if we haven't seen an
                        # output_item.added yet (event ordering can jitter).
                        if not name:
                            if "web_search" in etype:
                                name = "web_search"
                            elif "fabric_iq" in etype:
                                name = "fabric_iq_preview"
                            elif "bing_grounding" in etype:
                                name = "bing_grounding"
                            elif "mcp_list_tools" in etype:
                                # Discovery, not a real invocation.
                                continue
                            elif "mcp_call" in etype:
                                # Generic MCP call with no server_label context.
                                # Cannot classify - skip rather than light up
                                # a random layer.
                                continue
                            else:
                                continue
                        iq = classify(name, payload)
                        if iq and iq not in active:
                            active.add(iq)
                            yield iq_event(iq, "active",
                                           summarise_call(name, payload))

                    if etype.endswith("response.completed"):
                        payload = evt.get("response", evt)
                        response_id = payload.get("id", response_id)
                        final_status = payload.get("status", "") or final_status
                        usage_in, usage_out, model = telemetry.usage_from_payload(payload)
                        usage_model = model or usage_model
                        citations = _collect_citations(payload)
                        for err in _collect_tool_errors(payload):
                            if err not in tool_errors:
                                tool_errors.append(err)
                        full = _extract_text(payload)
                        if full:
                            text_acc = full

                    # Terminal failure events. Without this the stream stays
                    # open, the client waits forever, and the spinner never
                    # turns into anything actionable.
                    elif etype.endswith(("response.failed", "response.incomplete",
                                         "response.cancelled", "response.error")):
                        payload = evt.get("response", evt)
                        response_id = payload.get("id", response_id)
                        final_status = payload.get("status", "") or final_status
                        usage_in, usage_out, model = telemetry.usage_from_payload(payload)
                        usage_model = model or usage_model
                        err_obj = payload.get("error") or evt.get("error") or {}
                        if isinstance(err_obj, dict):
                            err_msg = (err_obj.get("message")
                                       or err_obj.get("code")
                                       or "The agent terminated the run.")
                        else:
                            err_msg = str(err_obj) or "The agent terminated the run."
                        reason = (payload.get("incomplete_details") or {}).get("reason", "")
                        detail = f"{final_status or etype}: {err_msg}"
                        if reason:
                            detail += f" ({reason})"
                        logger.warning("run %s for %s: %s", etype, user.upn, detail)
                        # Salvage any partial text before bailing.
                        salvage = _extract_text(payload) or text_acc
                        for iq in list(active):
                            yield iq_event(iq, "done", "stopped")
                        _finish(ok=False)
                        if salvage.strip():
                            yield message_event(
                                _strip_markers(salvage).strip() +
                                f"\n\n> _The agent stopped before finishing._",
                                _collect_citations(payload))
                            yield done_event(ok=False, threadId=response_id,
                                             layers=sorted(active),
                                             toolErrors=tool_errors,
                                             failed=detail)
                        else:
                            yield error_event(
                                "The agent did not finish this request.",
                                detail[:900])
                            yield done_event(ok=False, threadId=response_id,
                                             layers=sorted(active),
                                             toolErrors=tool_errors,
                                             failed=detail)
                        return
    except Exception as exc:  # noqa: BLE001
        logger.exception("agent stream failed")
        for iq in list(active):
            yield iq_event(iq, "done", "stopped")
        _finish(ok=False)
        yield error_event("The agent could not complete this request.", str(exc)[:600])
        yield done_event(ok=False)
        return

    for iq in active:
        yield iq_event(iq, "done", "complete")

    text = _strip_markers(text_acc).strip()

    # An empty answer used to render as silence, which looks like the app is
    # broken rather than the grounding being empty or failing. Say so instead.
    if not text:
        logger.warning("empty answer for %s (status=%s, tool_errors=%s)",
                       user.upn, final_status or "?", tool_errors or "none")
        _finish(ok=False)
        yield error_event(
            "The agent ran but returned no answer.",
            _empty_answer_detail(tool_errors, final_status)[:900],
        )
        yield done_event(ok=False, threadId=response_id, layers=sorted(active),
                         toolErrors=tool_errors)
        return

    if tool_errors:
        logger.warning("partial answer for %s, tool errors: %s", user.upn, tool_errors)

    _finish(ok=True)
    yield message_event(text, citations)
    yield done_event(ok=True, threadId=response_id, layers=sorted(active),
                     toolErrors=tool_errors)


async def _fallback_nonstreaming(client: httpx.AsyncClient, headers: dict,
                                 body: dict, active: set[str],
                                 stream_error: str) -> AsyncGenerator[str, None]:
    """If streaming is rejected, retry once without it before giving up."""
    logger.warning("stream rejected, retrying without stream: %s", stream_error[:300])
    payload = dict(body)
    payload.pop("stream", None)
    try:
        r = await client.post(responses_url(), headers=headers, json=payload)
        if r.status_code >= 400:
            telemetry.record_run(ok=False)
            yield error_event("The agent rejected the request.",
                              f"{r.status_code}: {r.text[:500]}")
            yield done_event(ok=False)
            return
        data = r.json()
    except Exception as exc:  # noqa: BLE001
        telemetry.record_run(ok=False)
        yield error_event("The agent could not be reached.", str(exc)[:500])
        yield done_event(ok=False)
        return

    # No streamed events, so derive the layers from the tools the response used.
    tool_errors = _collect_tool_errors(data)
    for item in data.get("output", []) or []:
        if not isinstance(item, dict) or not is_invocation(item.get("type", "")):
            continue
        name, arg = _tool_label(item)
        iq = classify(name, arg)
        if iq and iq not in active:
            active.add(iq)
            yield iq_event(iq, "active", summarise_call(name, arg))

    for iq in active:
        yield iq_event(iq, "done", "complete")

    text = _strip_markers(_extract_text(data)).strip()
    u_in, u_out, u_model = telemetry.usage_from_payload(data)
    if u_in or u_out:
        logger.info("run tokens in=%s out=%s model=%s", u_in, u_out, u_model or "?")
    telemetry.record_run(ok=bool(text))
    if not text:
        logger.warning("empty answer (non-streaming), tool_errors=%s",
                       tool_errors or "none")
        yield error_event(
            "The agent ran but returned no answer.",
            _empty_answer_detail(tool_errors, data.get("status", ""))[:900],
        )
        yield done_event(ok=False, threadId=data.get("id"),
                         layers=sorted(active), toolErrors=tool_errors)
        return

    yield message_event(text, _collect_citations(data))
    yield done_event(ok=True, threadId=data.get("id"), layers=sorted(active),
                     toolErrors=tool_errors)


# --------------------------------------------------------------------------- #
async def _mock(question: str) -> AsyncGenerator[str, None]:
    """Offline path so the UI can be built without Azure."""
    q = question.lower()
    layers = []
    if any(w in q for w in ("said", "discussion", "concern", "escalat", "feedback",
                            "email", "teams", "meeting", "raised", "committee",
                            "crc-", "commit", "who")):
        layers.append("work")
    if any(w in q for w in ("how much", "how many", "exposure", "limit", "headroom",
                            "utilis", "utiliz", "revenue", "wallet", "covenant",
                            "rating", "facility", "hold", "notional", "lend")):
        layers.append("fabric")
    if any(w in q for w in ("polic", "approv", "guardrail", "osfi", "allowed",
                            "evidence", "booking", "entity", "gp-", "suitab",
                            "may we", "can we book")):
        layers.append("foundry")
    if any(w in q for w in ("news", "public", "market", "rating agency", "moody",
                            "s&p", "fitch", "external", "announce", "press",
                            "web", "latest")):
        layers.append("web")
    layers = layers or ["fabric"]

    yield status_event("Thinking…")
    for iq in layers:
        await asyncio.sleep(0.7)
        yield iq_event(iq, "active")
    await asyncio.sleep(0.7)
    for iq in layers:
        yield iq_event(iq, "done", "complete")

    yield message_event(
        "**Mock mode.** The BFF is running without Azure credentials, so this is a "
        "canned answer.\n\nLayers that would have been used: "
        + ", ".join(layers)
        + ".\n\nSet `MOCK_MODE=false` and configure the Entra and Foundry settings "
          "to get grounded answers.",
        [],
    )
    # Mock runs are NOT recorded: they never reach Foundry, so counting them
    # would make the slide claim traces exist that never will.
    yield done_event(ok=True, layers=layers)
