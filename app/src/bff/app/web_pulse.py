"""Live Web IQ pulse for the guided story.

The four-layer comparison slide used to carry a hand-written Web IQ row, which
went stale the day it was written and - worse - quoted the internal rating
placeholder as if it came from the web. This asks the same Foundry agent a
web-only question and caches the answer, so the slide always shows what the
public web says today, with sources.

Public information only, identical for every user, so one cached answer is
shared. The run still goes through the signed-in user's identity (OBO) like
every other agent call.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any

from .agent_client import run_agent
from .auth import User

logger = logging.getLogger("bff.web_pulse")

TTL_SECONDS = int(os.getenv("WEB_PULSE_TTL_MIN", "360")) * 60
FAILURE_TTL_SECONDS = 5 * 60

PROMPT = (
    "Use ONLY the public web for this answer (Grounding with Bing / web search). "
    "Do not query Work IQ, Fabric IQ or Foundry IQ and do not mention any internal "
    "data. For Gibson Energy Inc. (TSX:GEI), give at most four short bullet points "
    "covering: the latest reported quarterly results, its current public credit "
    "ratings as published by the agencies, and any notable public news from the last "
    "30 days. Start each bullet with the date in YYYY-MM-DD form and cite a source. "
    "No preamble and no closing summary."
)

_cache: dict[str, Any] = {}
_lock = asyncio.Lock()


def _parse(frame: str) -> tuple[str, Any]:
    event, data = "", None
    for line in frame.splitlines():
        if line.startswith("event: "):
            event = line[7:].strip()
        elif line.startswith("data: "):
            try:
                data = json.loads(line[6:])
            except json.JSONDecodeError:
                data = None
    return event, data


async def _fetch(user: User) -> dict[str, Any]:
    text, citations, web_used, error = "", [], False, ""
    async for frame in run_agent(user, PROMPT):
        event, data = _parse(frame)
        if not isinstance(data, dict):
            continue
        if event == "iq_active" and data.get("iq") == "web":
            web_used = True
        elif event == "message":
            text = data.get("text") or ""
            citations = [c for c in data.get("citations") or [] if c.get("url")]
        elif event == "error":
            error = f"{data.get('text', '')} {data.get('detail', '')}".strip()

    if not text:
        return {"status": "unavailable", "detail": error[:300] or "No answer returned."}
    return {
        "status": "live",
        "text": text,
        "citations": citations[:6],
        "webUsed": web_used or bool(citations),
        "fetchedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


async def pulse(user: User, refresh: bool = False) -> dict[str, Any]:
    now = time.monotonic()
    hit = _cache.get("v")
    if hit and not refresh and now < hit["expires"]:
        return hit["value"]

    async with _lock:
        hit = _cache.get("v")
        if hit and not refresh and time.monotonic() < hit["expires"]:
            return hit["value"]
        try:
            value = await _fetch(user)
        except Exception as exc:  # noqa: BLE001
            logger.warning("web pulse failed: %s", str(exc)[:200])
            value = {"status": "unavailable", "detail": str(exc)[:300]}

        # Keep serving the last good answer if a refresh fails.
        if value["status"] != "live" and hit and hit["value"].get("status") == "live":
            value = {**hit["value"], "stale": True}
        ttl = TTL_SECONDS if value["status"] == "live" else FAILURE_TTL_SECONDS
        _cache["v"] = {"value": value, "expires": time.monotonic() + ttl}
        return value
