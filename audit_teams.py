"""Audit the Teams channels backing this demo for stray messages.

This demo deliberately posts no native channel messages, so any message here is
foreign - most likely left over from a previous demo that used the same team.
"""

from __future__ import annotations

import os
import re

import requests

G = "https://graph.microsoft.com/v1.0"
TEAM = "47b3de02-2462-443b-a8f5-a29d8d45acdd"
# "bmo" and "gibson" are THIS demo's own content - not leakage.
TOKENS = ["scotiabank", "scotia", "rbc", "royal bank", "contoso",
          "vale", "teck", "freeport",
          "mortgage", "renewal", "concierge", "heloc"]
RX = [(t, re.compile(r"\b" + re.escape(t), re.I)) for t in TOKENS]


def main() -> int:
    tid = os.environ["WORKIQ_TENANT_ID"]
    tok = requests.post(
        f"https://login.microsoftonline.com/{tid}/oauth2/v2.0/token",
        data={
            "client_id": os.environ["WORKIQ_CLIENT_ID"],
            "client_secret": os.environ["WORKIQ_CLIENT_SECRET"],
            "scope": "https://graph.microsoft.com/.default",
            "grant_type": "client_credentials",
        }, timeout=60).json()["access_token"]
    h = {"Authorization": "Bearer " + tok}

    r = requests.get(f"{G}/teams/{TEAM}/channels", headers=h, timeout=60)
    if r.status_code != 200:
        print(f"channels -> HTTP {r.status_code}: {r.text[:200]}")
        return 2

    total, leaks, errors = 0, [], []
    for c in r.json().get("value", []):
        m = requests.get(
            f"{G}/teams/{TEAM}/channels/{c['id']}/messages?$top=50",
            headers=h, timeout=60)
        if m.status_code != 200:
            errors.append(f"{c['displayName']} -> HTTP {m.status_code}")
            print(f"  {c['displayName']:<40} HTTP {m.status_code}")
            continue
        msgs = m.json().get("value", [])
        total += len(msgs)
        print(f"  {c['displayName']:<40} messages={len(msgs)}")
        for msg in msgs:
            body = (msg.get("body") or {}).get("content") or ""
            for t, rx in RX:
                if rx.search(body):
                    leaks.append((c["displayName"], t, body[:80]))

    print()
    if errors:
        print("REQUEST FAILURES - inconclusive:")
        for e in errors:
            print(f"  ! {e}")
        return 2
    if leaks:
        print(f"LEAKS ({len(leaks)}):")
        for ch, t, snip in leaks:
            print(f"  [{t}] {ch}: {snip}")
        return 1
    print(f"CLEAN - {total} channel message(s), none foreign.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
