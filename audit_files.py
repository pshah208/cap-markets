"""Enumerate OneDrive and SharePoint content for the demo, recursively.

A search(q='') returns nothing on OneDrive, which looks identical to "clean".
This walks children instead, so an empty result means empty, not mistyped.
"""

from __future__ import annotations

import os
import re

import requests

G = "https://graph.microsoft.com/v1.0"
D = "M365CPI65678641.OnMicrosoft.com"
USERS = ["SydneyM", "SashaO", "QuinnC", "VanceD", "RobinK"]
TEAM_ID = "47b3de02-2462-443b-a8f5-a29d8d45acdd"

# NOTE: this is the CAPITAL MARKETS demo, so "bmo" and "gibson" are OUR OWN
# content and must NOT be treated as leakage. What would be foreign here is the
# Scotia mortgage demo and the RBC metals demo.
TOKENS = ["scotiabank", "scotia", "rbc", "royal bank", "contoso",
          "vale", "teck", "freeport",
          "mortgage", "renewal", "concierge", "heloc"]
RX = [(t, re.compile(r"\b" + re.escape(t), re.I)) for t in TOKENS]

# Stock Microsoft demo-tenant files that ship on every mailbox in this tenant.
# They predate every demo here and the tenant owner has chosen to keep them, so
# they are reported as context but do not fail the audit.
TENANT_SAMPLE = {
    "Contoso Marketing Plan.docx",
    "Contoso Purchasing Data - Q1.xlsx",
    "eBike Inventory.xlsx",
    "Project Falcon - Launch Readiness review.pptx",
    "Proposed_agenda_topics.docx",
    "Resume - Daichi Maruyama.docx",
    "Thunderbolt 2024 - Presentation v2.0.pptx",
    "Thunderbolt Specifications v1.0.docx",
}

leaks: list[tuple[str, str]] = []
errors: list[str] = []


def token() -> str:
    tid = os.environ["WORKIQ_TENANT_ID"]
    return requests.post(
        f"https://login.microsoftonline.com/{tid}/oauth2/v2.0/token",
        data={
            "client_id": os.environ["WORKIQ_CLIENT_ID"],
            "client_secret": os.environ["WORKIQ_CLIENT_SECRET"],
            "scope": "https://graph.microsoft.com/.default",
            "grant_type": "client_credentials",
        }, timeout=60).json()["access_token"]


def walk(h: dict, base: str, item_id: str, path: str, out: list[str]) -> None:
    r = requests.get(f"{base}/items/{item_id}/children?$top=200",
                     headers=h, timeout=90)
    if r.status_code != 200:
        errors.append(f"{path} -> HTTP {r.status_code} {r.text[:140]}")
        return
    for it in r.json().get("value", []):
        p = f"{path}/{it['name']}"
        if "folder" in it:
            walk(h, base, it["id"], p, out)
        else:
            out.append(p)


def main() -> int:
    h = {"Authorization": "Bearer " + token()}

    for u in USERS:
        r = requests.get(f"{G}/users/{u}@{D}/drive/root", headers=h, timeout=60)
        if r.status_code != 200:
            errors.append(f"{u} drive -> HTTP {r.status_code} {r.text[:140]}")
            continue
        root = r.json()["id"]
        files: list[str] = []
        walk(h, f"{G}/users/{u}@{D}/drive", root, "", files)
        ours = [f for f in files if f.strip("/") not in TENANT_SAMPLE]
        stock = len(files) - len(ours)
        print(f"{u:9} {len(ours):>3} demo files  ({stock} tenant sample, ignored)")
        for f in ours:
            print(f"            {f}")
            for t, rx in RX:
                if rx.search(f):
                    leaks.append((f"{u}/OneDrive", f"{t} in {f}"))

    r = requests.get(f"{G}/groups/{TEAM_ID}/drive/root", headers=h, timeout=60)
    if r.status_code != 200:
        errors.append(f"team drive -> HTTP {r.status_code} {r.text[:200]}")
    else:
        root = r.json()["id"]
        files = []
        walk(h, f"{G}/groups/{TEAM_ID}/drive", root, "", files)
        print(f"\nteam SharePoint  {len(files)} files")
        for f in files:
            print(f"            {f}")
            for t, rx in RX:
                if rx.search(f):
                    leaks.append(("team/SharePoint", f"{t} in {f}"))

    print()
    if errors:
        print("REQUEST FAILURES - inconclusive:")
        for e in errors:
            print(f"  ! {e}")
    if leaks:
        print(f"LEAKS ({len(leaks)}):")
        for where, what in leaks:
            print(f"  {where}: {what}")
        return 1
    if errors:
        return 2
    print("CLEAN - no cross-demo filenames in OneDrive or SharePoint.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
