"""Call the Work IQ A2A endpoint directly to see the real error.

The Foundry portal wraps every failure in the same generic "Access denied ...
verify (1)(2)(3)" message, which does not distinguish between:

  * no token at all              (connection never authorized)
  * token with the wrong audience
  * valid token, identity not entitled
  * valid token, tenant not enrolled in the preview

This performs the delegated device-code flow against the SAME app registration
and scope the Foundry connection uses, then calls the endpoint and prints the
raw status and body.

    python diag_workiq.py
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid

import requests

TENANT = os.getenv("WORKIQ_TENANT_ID", "cf54b15b-1866-486f-88d6-7ba81bf35aa1")
CLIENT = os.getenv("WORKIQ_CONNECTOR_APP", "f940a69d-32ec-4865-ab13-452cb8164771")
SCOPE = "api://workiq.svc.cloud.microsoft/WorkIQAgent.Ask offline_access"
A2A = "https://workiq.svc.cloud.microsoft/a2a/"


def device_code() -> dict:
    r = requests.post(
        f"https://login.microsoftonline.com/{TENANT}/oauth2/v2.0/devicecode",
        data={"client_id": CLIENT, "scope": SCOPE}, timeout=60)
    if r.status_code != 200:
        sys.exit(f"devicecode failed {r.status_code}: {r.text[:600]}")
    return r.json()


def poll(dc: dict) -> dict:
    deadline = time.time() + dc.get("expires_in", 900)
    while time.time() < deadline:
        time.sleep(dc.get("interval", 5))
        r = requests.post(
            f"https://login.microsoftonline.com/{TENANT}/oauth2/v2.0/token",
            data={"grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                  "client_id": CLIENT, "device_code": dc["device_code"]},
            timeout=60)
        if r.status_code == 200:
            return r.json()
        err = r.json().get("error", "")
        if err in ("authorization_pending", "slow_down"):
            continue
        sys.exit(f"token failed: {r.text[:800]}")
    sys.exit("device code expired")


def claims(tok: str) -> dict:
    import base64
    body = tok.split(".")[1]
    body += "=" * (-len(body) % 4)
    return json.loads(base64.urlsafe_b64decode(body))


def main() -> int:
    dc = device_code()
    print("\n" + "=" * 68)
    print(f"  Open: {dc['verification_uri']}")
    print(f"  Code: {dc['user_code']}")
    print("  Sign in as the user you want to test (e.g. SydneyM).")
    print("=" * 68 + "\n")

    tok = poll(dc)["access_token"]
    c = claims(tok)
    print("token acquired")
    print(f"  aud : {c.get('aud')}")
    print(f"  upn : {c.get('upn') or c.get('preferred_username')}")
    print(f"  scp : {c.get('scp')}")
    print(f"  appid: {c.get('appid')}")

    # Minimal A2A message/send, mirroring what Foundry's SendMessage does.
    payload = {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": "message/send",
        "params": {
            "message": {
                "role": "user",
                "parts": [{"kind": "text",
                           "text": "What is reference CR-2026-0184?"}],
                "messageId": str(uuid.uuid4()),
            }
        },
    }
    r = requests.post(A2A, headers={"Authorization": f"Bearer {tok}",
                                    "Content-Type": "application/json"},
                      json=payload, timeout=180)
    print(f"\nA2A POST {A2A}")
    print(f"  status: {r.status_code}")
    for k in ("x-ms-diagnostics", "www-authenticate", "x-ms-request-id",
              "request-id", "x-ms-correlation-id"):
        if k in r.headers:
            print(f"  {k}: {r.headers[k][:300]}")
    print(f"  body  : {r.text[:1500]}")
    return 0 if r.status_code < 400 else 1


if __name__ == "__main__":
    raise SystemExit(main())
