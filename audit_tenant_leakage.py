"""Audit the LIVE tenant for cross-demo content in this demo's accounts.

Source files being clean is not sufficient. These four accounts were previously
used by another demo, and mail seeded by that demo would still be sitting in the
mailboxes - where Work IQ would happily ground on it mid-presentation.

Reads only. Never reports "clean" on a request that failed.

    $env:WORKIQ_CLIENT_ID / WORKIQ_CLIENT_SECRET / WORKIQ_TENANT_ID
    python audit_tenant_leakage.py
"""

from __future__ import annotations

import os
import re
import sys

import requests

G = "https://graph.microsoft.com/v1.0"
DOMAIN = "M365CPI65678641.OnMicrosoft.com"
USERS = ["SydneyM", "SashaO", "QuinnC", "VanceD", "RobinK"]

TOKENS = [
    # other banks / other demos' branding
    "scotiabank", "scotia", "royal bank", "rbc", "nesbitt", "contoso",
    # other demos' clients
    "vale", "teck", "freeport",
    # other demos' domain language
    "mortgage", "renewal", "heloc", "concierge", "country envelope",
    "Raj Balakrishnan", "Diane Lafleur", "Karen Whitfield", "Derek Fontaine",
    "Helena Vasquez", "Marcus Delaney", "Sophie Tremblay", "Nadia Osei",
    "Cora Thomas", "Kai Carter", "Hadar Caspit", "Dakota Sanchez",
]
RX = [(t, re.compile(r"\b" + re.escape(t), re.I)) for t in TOKENS]

errors: list[str] = []
leaks: list[tuple[str, str, str]] = []


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


def scan(where: str, label: str, text: str) -> None:
    for t, rx in RX:
        if rx.search(text or ""):
            leaks.append((where, label, t))


def get(h: dict, url: str, what: str):
    r = requests.get(url, headers=h, timeout=90)
    if r.status_code == 404:
        return {"value": []}          # optional folder (e.g. archive) absent
    if r.status_code != 200:
        errors.append(f"{what} -> HTTP {r.status_code}: {r.text[:200]}")
        return None
    return r.json()


def main() -> int:
    h = {"Authorization": "Bearer " + token()}

    # Deliberately NOT /users/{id}/messages - that returns every folder,
    # including Deleted Items, so it can never show a purge succeeded. Work IQ
    # grounds on live mail, so audit the live folders.
    FOLDERS = ["inbox", "sentitems", "drafts", "archive"]

    for u in USERS:
        upn = f"{u}@{DOMAIN}"

        total = 0
        for folder in FOLDERS:
            data = get(h, f"{G}/users/{upn}/mailFolders/{folder}/messages"
                          f"?$top=200&$select=subject,receivedDateTime,body",
                       f"{u} {folder}")
            if data is None:
                continue
            msgs = data.get("value", [])
            total += len(msgs)
            for m in msgs:
                body = (m.get("body") or {}).get("content") or ""
                scan(f"mail/{folder}", f"{u}: {m.get('subject','')[:70]}",
                     (m.get("subject") or "") + " " + body)
        print(f"  {u:9} {total:>3} live messages")

    # OneDrive and SharePoint are audited by audit_files.py, which walks
    # children. A drive search(q='') returns nothing here and would look
    # identical to "clean" - exactly the false negative this script exists to
    # avoid - so it is deliberately not used.

    print()
    if errors:
        print("REQUESTS FAILED - this audit is INCONCLUSIVE, not clean:")
        for e in errors:
            print(f"  ! {e}")
        print()

    if leaks:
        print(f"LEAKS FOUND ({len(leaks)}):")
        seen = set()
        for where, label, t in leaks:
            k = (where, label, t)
            if k in seen:
                continue
            seen.add(k)
            print(f"  [{t}] {where}  {label}")
        return 1

    if errors:
        return 2

    print("CLEAN - no cross-demo content in any audited surface.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
