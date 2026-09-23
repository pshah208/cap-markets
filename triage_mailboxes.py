"""Inventory every message in this demo's mailboxes and classify it.

Anything not seeded by THIS demo is foreign. These accounts were reused from an
earlier demo, so their mailboxes still contain that demo's mail - which Work IQ
will happily retrieve mid-presentation.

    python triage_mailboxes.py            # report only
    python triage_mailboxes.py --purge    # move foreign mail to Deleted Items
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import requests

G = "https://graph.microsoft.com/v1.0"
DOMAIN = "M365CPI65678641.OnMicrosoft.com"
HERE = Path(__file__).parent
USERS = ["SydneyM", "SashaO", "QuinnC", "VanceD", "RobinK"]


def rq(method: str, url: str, **kw):
    """Graph occasionally drops a connection outright. Retry, or a purge stops
    half-finished and the next run sees an inconsistent mailbox."""
    last = None
    for attempt in range(4):
        try:
            return requests.request(method, url, timeout=90, **kw)
        except requests.exceptions.RequestException as e:  # noqa: PERF203
            last = e
            time.sleep(2 * (attempt + 1))
    raise last  # type: ignore[misc]


def norm(s: str) -> str:
    """Compare subjects ignoring case, Re:/Fw: prefixes and whitespace."""
    s = re.sub(r"^(re|fw|fwd)\s*:\s*", "", (s or "").strip(), flags=re.I)
    return re.sub(r"\s+", " ", s).strip().lower()


def token() -> str:
    tid = os.environ["WORKIQ_TENANT_ID"]
    r = requests.post(
        f"https://login.microsoftonline.com/{tid}/oauth2/v2.0/token",
        data={
            "client_id": os.environ["WORKIQ_CLIENT_ID"],
            "client_secret": os.environ["WORKIQ_CLIENT_SECRET"],
            "scope": "https://graph.microsoft.com/.default",
            "grant_type": "client_credentials",
        }, timeout=60)
    r.raise_for_status()
    return r.json()["access_token"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--purge", action="store_true",
                    help="move foreign messages to Deleted Items")
    args = ap.parse_args()

    emails = json.loads((HERE / "data" / "work-iq" / "emails.json")
                        .read_text(encoding="utf-8"))
    seeded = {norm(e["subject"]) for e in emails["emails"]}
    print(f"this demo seeded {len(seeded)} distinct subjects\n")

    h = {"Authorization": "Bearer " + token()}
    foreign: list[tuple[str, str, str, str]] = []
    errors: list[str] = []

    for u in USERS:
        upn = f"{u}@{DOMAIN}"
        r = rq("GET",
               f"{G}/users/{upn}/messages"
               f"?$top=300&$select=id,subject,receivedDateTime,from",
               headers=h)
        if r.status_code != 200:
            errors.append(f"{u}: HTTP {r.status_code} {r.text[:160]}")
            continue
        msgs = r.json().get("value", [])
        mine = [m for m in msgs if norm(m.get("subject", "")) in seeded]
        alien = [m for m in msgs if norm(m.get("subject", "")) not in seeded]
        print(f"{u:9} {len(msgs):>3} total  "
              f"{len(mine):>3} this demo  {len(alien):>3} FOREIGN")
        for m in alien:
            foreign.append((u, m["id"], m.get("subject", ""),
                            (m.get("receivedDateTime") or "")[:10]))

    if errors:
        print("\nrequest failures (inventory incomplete):")
        for e in errors:
            print(f"  ! {e}")

    if not foreign:
        print("\nNo foreign mail. Mailboxes contain only this demo's content.")
        return 0

    print(f"\n{len(foreign)} foreign message(s):\n")
    by_user: dict[str, list] = {}
    for u, _id, subj, date in foreign:
        by_user.setdefault(u, []).append((date, subj))
    for u, rows in by_user.items():
        print(f"  {u}")
        for date, subj in sorted(rows):
            print(f"    {date}  {subj[:96]}")
        print()

    if not args.purge:
        print("Report only. Re-run with --purge to move these to Deleted Items.")
        return 1

    print("Purging...")
    moved = failed = 0
    for u, mid, subj, _date in foreign:
        r = rq("POST",
               f"{G}/users/{u}@{DOMAIN}/messages/{mid}/move",
               headers={**h, "Content-Type": "application/json"},
               json={"destinationId": "deleteditems"})
        if r.status_code in (200, 201):
            moved += 1
        else:
            failed += 1
            print(f"  ! {u}: {r.status_code} {subj[:60]}")
    print(f"\nmoved {moved}, failed {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
