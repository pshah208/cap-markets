"""Diagnose Work IQ with explicit delegated device authentication and A2A.

Requires WORKIQ_TENANT_ID and WORKIQ_CLIENT_ID (canonical GUIDs), plus
DIAG_PROMPT. No client secret, backend bank configuration, default application,
Azure auth profile or .env is used. Imports never read configuration or connect.
Only status/structural summaries are printed, never tokens or raw service bodies.
"""
from __future__ import annotations

import sys
import time
import uuid

from agent.portability import ConfigurationError, require_environment, require_https_url


SCOPE = "api://workiq.svc.cloud.microsoft/WorkIQAgent.Ask offline_access"
A2A = "https://workiq.svc.cloud.microsoft/a2a/"


class DiagnosticError(RuntimeError):
    """Device authorization or the A2A protocol failed."""


def load_config() -> dict[str, str]:
    config = require_environment("WORKIQ_TENANT_ID", "WORKIQ_CLIENT_ID", "DIAG_PROMPT")
    for name in ("WORKIQ_TENANT_ID", "WORKIQ_CLIENT_ID"):
        try:
            valid = str(uuid.UUID(config[name])) == config[name].lower()
        except ValueError:
            valid = False
        if not valid:
            raise ConfigurationError(f"{name} must be a canonical GUID")
    return config


def read_object(response, label: str) -> dict:
    try:
        body = response.json()
    except ValueError:
        raise DiagnosticError(f"{label}: malformed JSON") from None
    if not isinstance(body, dict):
        raise DiagnosticError(f"{label}: expected a JSON object")
    return body


def device_code(http, config: dict[str, str]) -> dict:
    with http.post(
        f"https://login.microsoftonline.com/{config['WORKIQ_TENANT_ID']}/oauth2/v2.0/devicecode",
        data={"client_id": config["WORKIQ_CLIENT_ID"], "scope": SCOPE},
        timeout=(30, 60), allow_redirects=False,
    ) as response:
        if response.status_code != 200:
            raise DiagnosticError(f"devicecode: HTTP {response.status_code}")
        body = read_object(response, "devicecode")
    if "error" in body:
        raise DiagnosticError("devicecode: OAuth error")
    for name in ("device_code", "user_code", "verification_uri"):
        if not isinstance(body.get(name), str) or not body[name].strip():
            raise DiagnosticError(f"devicecode: missing {name}")
    try:
        require_https_url("verification_uri", body["verification_uri"])
    except ConfigurationError:
        raise DiagnosticError("devicecode: invalid HTTPS verification_uri") from None
    for name, value in (("expires_in", body.get("expires_in")), ("interval", body.get("interval", 5))):
        if type(value) is not int or value <= 0:
            raise DiagnosticError(f"devicecode: {name} must be a positive integer")
    return body


def poll(http, config: dict[str, str], device: dict) -> str:
    deadline = time.monotonic() + device["expires_in"]
    interval = device.get("interval", 5)
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise DiagnosticError("Device code expired")
        time.sleep(min(interval, remaining))
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise DiagnosticError("Device code expired")
        with http.post(
            f"https://login.microsoftonline.com/{config['WORKIQ_TENANT_ID']}/oauth2/v2.0/token",
            data={"grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                  "client_id": config["WORKIQ_CLIENT_ID"], "device_code": device["device_code"]},
            timeout=min(60, remaining), allow_redirects=False,
        ) as response:
            status = response.status_code
            body = read_object(response, "token")
        if status == 200:
            token = body.get("access_token")
            if ("error" in body or not isinstance(token, str) or not token.strip()
                    or not isinstance(body.get("token_type"), str)
                    or body["token_type"].lower() != "bearer"):
                raise DiagnosticError("token: missing bearer access token or OAuth error")
            return token
        error = body.get("error")
        if status in (400, 429) and error == "authorization_pending":
            continue
        if status in (400, 429) and error == "slow_down":
            interval += 5
            continue
        if error in ("access_denied", "authorization_declined", "expired_token", "bad_verification_code"):
            raise DiagnosticError(f"Device authorization failed: {error}")
        raise DiagnosticError(f"token: OAuth request failed (HTTP {status})")


def check_a2a(body: dict, request_id: str) -> None:
    if body.get("jsonrpc") != "2.0" or body.get("id") != request_id:
        raise DiagnosticError("A2A: invalid JSON-RPC version or response id")
    if "error" in body:
        error = body["error"]
        code = error.get("code") if isinstance(error, dict) else None
        suffix = f" (code {code})" if type(code) is int else ""
        raise DiagnosticError(f"A2A: JSON-RPC error{suffix}")
    result = body.get("result")
    if not isinstance(result, dict) or "error" in result:
        raise DiagnosticError("A2A: missing result or result-level error")
    if result.get("kind") == "message":
        parts = result.get("parts")
        if (result.get("role") != "agent"
                or not isinstance(result.get("messageId"), str) or not result["messageId"].strip()
                or not isinstance(parts, list) or not parts):
            raise DiagnosticError("A2A: malformed agent message")
        for part in parts:
            if not isinstance(part, dict) or part.get("kind") not in ("text", "file", "data"):
                raise DiagnosticError("A2A: malformed message part")
            if part["kind"] == "text" and not isinstance(part.get("text"), str):
                raise DiagnosticError("A2A: malformed text part")
            if part["kind"] == "data" and not isinstance(part.get("data"), dict):
                raise DiagnosticError("A2A: malformed data part")
            if part["kind"] == "file":
                file = part.get("file")
                if not isinstance(file, dict):
                    raise DiagnosticError("A2A: malformed file part")
                content = [name for name in ("uri", "bytes") if name in file]
                if len(content) != 1 or not isinstance(file[content[0]], str) or not file[content[0]]:
                    raise DiagnosticError("A2A: malformed file content")
        print(f"A2A: OK, agent message ({len(parts)} parts)")
    elif result.get("kind") == "task":
        status = result.get("status")
        if (not isinstance(result.get("id"), str) or not result["id"].strip()
                or not isinstance(status, dict) or status.get("state") != "completed"):
            raise DiagnosticError("A2A: task failed or is not completed")
        print("A2A: OK, completed task")
    else:
        raise DiagnosticError("A2A: expected an agent message or completed task")


def main() -> int:
    try:
        config = load_config()
    except ConfigurationError as error:
        print(f"Configuration error: {error}", file=sys.stderr)
        return 2

    import requests

    try:
        device = device_code(requests, config)
        print(f"Open: {device['verification_uri']}")
        print(f"Code: {device['user_code']}")
        print("Sign in with the intended user in the explicitly configured Work IQ tenant.")
        access_token = poll(requests, config, device)
        print("Bearer token acquired (not displayed)")
        request_id = str(uuid.uuid4())
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "message/send",
            "params": {"message": {
                "kind": "message",
                "role": "user",
                "parts": [{"kind": "text", "text": config["DIAG_PROMPT"]}],
                "messageId": str(uuid.uuid4()),
            }},
        }
        with requests.post(
            A2A, headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
            json=payload, timeout=(30, 180), allow_redirects=False,
        ) as response:
            print(f"A2A HTTP {response.status_code}")
            if response.status_code != 200:
                raise DiagnosticError(f"A2A: HTTP {response.status_code}")
            check_a2a(read_object(response, "A2A"), request_id)
        return 0
    except DiagnosticError as error:
        print(f"Work IQ diagnostic failed: {error}", file=sys.stderr)
    except requests.RequestException as error:
        print(f"Work IQ transport failed ({type(error).__name__})", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
