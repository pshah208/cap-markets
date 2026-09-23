"""Push the portal instructions onto the Foundry prompt agent.

The agent was built by hand in the portal with all five tools wired but an EMPTY
instructions field, so it answered the capacity question from arithmetic alone
and never called a knowledge source. That is precisely the failure the demo is
built to expose - so it must not be the demo's own behaviour.

Creates a new agent version, preserving the existing tool wiring verbatim.

    python push_agent_instructions.py            # show what would change
    python push_agent_instructions.py --apply
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import requests

HERE = Path(__file__).parent
ENDPOINT = ("https://cmintel-foundry.services.ai.azure.com"
            "/api/projects/proj-client-intelligence")
AGENT = "Agent-cap-market"
API = "2025-05-15-preview"
INSTRUCTIONS = HERE / "agent" / "agent_instructions.portal.md"


def token() -> str:
    out = subprocess.run(
        ["az", "account", "get-access-token", "--resource",
         "https://ai.azure.com", "--query", "accessToken", "-o", "tsv"],
        capture_output=True, text=True, shell=True)
    if out.returncode != 0:
        sys.exit(f"az token failed: {out.stderr[:300]}")
    return out.stdout.strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--effort", default="medium",
                    choices=["low", "medium", "high"])
    args = ap.parse_args()

    body = INSTRUCTIONS.read_text(encoding="utf-8")

    # The file is a document *about* the instructions; only the fenced region is
    # the prompt itself. The preamble explains to a human why this variant
    # exists and must not be sent to the model.
    START, END = "<!-- INSTRUCTIONS-START -->", "<!-- INSTRUCTIONS-END -->"
    if START not in body:
        sys.exit(f"{INSTRUCTIONS.name} is missing {START}")
    body = body.split(START, 1)[1]
    if END in body:
        body = body.split(END, 1)[0]
    body = body.strip()
    print(f"instructions: {len(body)} chars, starts: {body[:70]!r}\n")

    h = {"Authorization": "Bearer " + token(),
         "Content-Type": "application/json"}

    r = requests.get(f"{ENDPOINT}/agents/{AGENT}/versions?api-version={API}",
                     headers=h, timeout=60)
    r.raise_for_status()
    versions = r.json()["data"]
    latest = max(versions, key=lambda v: int(v["version"]))
    definition = latest["definition"]

    print(f"latest version : {latest['version']}")
    print(f"  instructions : {len(definition.get('instructions') or '')} chars")
    print(f"  tools        : "
          f"{[t.get('type') for t in definition.get('tools', [])]}")
    print(f"  effort       : {(definition.get('reasoning') or {}).get('effort')}")

    new_def = dict(definition)
    new_def["instructions"] = body
    new_def["reasoning"] = {"effort": args.effort}

    print(f"\nwould create a new version with "
          f"{len(body)} chars of instructions and effort={args.effort}, "
          f"preserving {len(new_def.get('tools', []))} tools.")

    if not args.apply:
        print("\nDry run. Re-run with --apply.")
        return 0

    r = requests.post(
        f"{ENDPOINT}/agents/{AGENT}/versions?api-version={API}",
        headers=h, json={"definition": new_def}, timeout=120)
    if r.status_code >= 400:
        print(f"\nFAILED {r.status_code}: {r.text[:900]}")
        return 1

    made = r.json()
    print(f"\ncreated version {made.get('version')} "
          f"({len(made.get('definition', {}).get('instructions') or '')} chars)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
