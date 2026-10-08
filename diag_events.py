"""Inspect distinct Foundry SSE event/item types without printing response content.

Requires FOUNDRY_PROJECT_ENDPOINT (HTTPS), FOUNDRY_AGENT_NAME, DIAG_PROMPT,
and the explicit AZURE_AUTH_MODE profile documented in agent.portability.
No configuration or authentication is performed on import; no .env is loaded.
"""
from __future__ import annotations

import json
import sys
import time

from agent.portability import ConfigurationError, foundry_token, load_foundry_config
from diagnostic_auth import validate_auth_identifiers


API_VERSION = "2025-05-15-preview"


class DiagnosticError(RuntimeError):
    """A service response did not satisfy the diagnostic."""


def sse_events(response):
    """Parse complete SSE frames, including multiline data and UTF-8 decoding."""
    data = []
    event_name = ""
    first_line = True
    for raw_line in response.iter_lines():
        try:
            line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line
        except UnicodeDecodeError:
            raise DiagnosticError("SSE contains invalid UTF-8") from None
        if not isinstance(line, str):
            raise DiagnosticError("SSE contains an invalid line")
        if first_line:
            line = line.removeprefix("\ufeff")
            first_line = False
        if not line:
            if data:
                yield event_name, "\n".join(data)
            elif event_name:
                raise DiagnosticError("SSE event is missing data")
            data = []
            event_name = ""
            continue
        if line.startswith(":"):
            continue
        field, _, value = line.partition(":")
        value = value.removeprefix(" ")
        if field == "data":
            data.append(value)
        elif field == "event":
            event_name = value
        elif field == "id":
            if "\0" in value:
                raise DiagnosticError("SSE contains an invalid id")
        elif field == "retry":
            if not value.isascii() or not value.isdecimal():
                raise DiagnosticError("SSE contains an invalid retry interval")
        else:
            raise DiagnosticError("SSE contains an unrecognized field")
    if data or event_name:
        raise DiagnosticError("SSE ended with an unterminated event")


def inspect_stream(response, access_token: str) -> int:
    if response.status_code != 200:
        raise DiagnosticError(f"Foundry HTTP {response.status_code}")
    content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
    if content_type != "text/event-stream":
        raise DiagnosticError("Foundry did not return text/event-stream")

    seen = set()
    completed = False
    done = False
    start = time.monotonic()
    for event_name, data in sse_events(response):
        if done:
            raise DiagnosticError("SSE contains data after [DONE]")
        if data == "[DONE]":
            if not completed:
                raise DiagnosticError("SSE ended before response.completed")
            done = True
            continue
        try:
            event = json.loads(data)
        except json.JSONDecodeError:
            raise DiagnosticError("SSE contains malformed JSON") from None
        if not isinstance(event, dict):
            raise DiagnosticError("SSE data must be a JSON object")
        event_type = event.get("type")
        if not isinstance(event_type, str) or not event_type.strip():
            raise DiagnosticError("SSE data is missing its event type")
        if event_name not in ("", "message", event_type):
            raise DiagnosticError("SSE event name disagrees with its data type")
        item = event.get("item", {})
        result = event.get("response", {})
        if not isinstance(item, dict) or not isinstance(result, dict):
            raise DiagnosticError("SSE contains malformed item/response data")
        if (event_type == "error" or event_type.endswith((".error", ".failed", ".incomplete"))
                or any(value.get("error") is not None for value in (event, item, result))
                or any(value.get("status") in ("failed", "incomplete", "cancelled", "canceled")
                       for value in (item, result))):
            raise DiagnosticError("Foundry reported an error, failed or incomplete response")
        if completed:
            raise DiagnosticError("SSE contains an event after response.completed")
        if event_type == "response.completed":
            if result.get("status") != "completed":
                raise DiagnosticError("response.completed has no completed response status")
            completed = True
        item_type = item.get("type", "")
        if not isinstance(item_type, str):
            raise DiagnosticError("SSE item type must be a string")
        key = (event_type, item_type)
        if key in seen:
            continue
        seen.add(key)
        # Only structural metadata is useful here; prompts, arguments and deltas may be sensitive.
        summary = {"type": event_type}
        for name in ("output_index", "item_id"):
            if name in event:
                summary[name] = event[name]
        if item:
            summary["item"] = {
                name: item[name] for name in ("id", "type", "status", "server_label", "name")
                if name in item
            }
        safe_summary = json.dumps(summary, ensure_ascii=True).replace(access_token, "[REDACTED]")
        print(f"{time.monotonic() - start:6.1f}s {safe_summary[:500]}")
    if not completed:
        raise DiagnosticError("SSE ended without response.completed")
    print(f"{len(seen)} distinct (event, item_type) combinations; response completed")
    return 0


def main() -> int:
    try:
        config = load_foundry_config("DIAG_PROMPT")
        validate_auth_identifiers(config)
    except ConfigurationError as error:
        print(f"Configuration error: {error}", file=sys.stderr)
        return 2

    import requests
    from azure.core.exceptions import AzureError

    try:
        access_token = foundry_token(config)
    except (AzureError, RuntimeError) as error:
        print(f"Foundry authentication failed ({type(error).__name__})", file=sys.stderr)
        return 1
    body = {
        "agent_reference": {"type": "agent_reference", "name": config["FOUNDRY_AGENT_NAME"]},
        "input": config["DIAG_PROMPT"],
        "stream": True,
    }
    url = f"{config['FOUNDRY_PROJECT_ENDPOINT']}/openai/responses?api-version={API_VERSION}"
    try:
        with requests.post(
            url, headers={"Authorization": f"Bearer {access_token}", "Accept": "text/event-stream"},
            json=body, stream=True, timeout=(30, 300), allow_redirects=False,
        ) as response:
            return inspect_stream(response, access_token)
    except DiagnosticError as error:
        print(f"Foundry diagnostic failed: {error}", file=sys.stderr)
    except requests.RequestException as error:
        print(f"Foundry transport failed ({type(error).__name__})", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
