"""Set `require_approval: never` on every MCP tool on the Foundry agent.

Connections added in the portal default to requiring interactive approval. In a
demo that is fatal: the run stops on `mcp_approval_request` and the answer never
arrives, with no obvious error - it simply looks like the agent hung.

Only the approval flag is changed; instructions, model and tool wiring are
preserved exactly.

    python set_tool_autoapprove.py            # dry run
    python set_tool_autoapprove.py --apply
"""

from __future__ import annotations

import argparse
import subprocess
import sys

import requests

ENDPOINT = ("https://cmintel-foundry.services.ai.azure.com"
            "/api/projects/proj-client-intelligence")
AGENT = "Agent-cap-market"
API = "2025-05-15-preview"

# Only MCP-style tools take require_approval. bing_grounding and web_search do
# not, and sending the field to them risks a 400.
APPROVABLE = {"mcp", "fabric_iq_preview", "work_iq_preview"}


def token() -> str:
    out = subprocess.run(
        ["az", "account", "get-access-token", "--resource",
         "https://ai.azure.com", "--query", "accessToken", "-o", "tsv"],
        capture_output=True, text=True, shell=True)
    if out.returncode != 0:
        sys.exit(f"az token failed: {out.stderr[:300]}")
    return out.stdout.strip()


def label(tool: dict) -> str:
    return (tool.get("server_label")
            or (tool.get("project_connection_id") or "").split("/")[-1]
            or tool.get("type", "?"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    h = {"Authorization": "Bearer " + token(),
         "Content-Type": "application/json"}

    r = requests.get(f"{ENDPOINT}/agents/{AGENT}?api-version={API}",
                     headers=h, timeout=60)
    r.raise_for_status()
    latest = r.json()["versions"]["latest"]
    definition = latest["definition"]
    print(f"current version : {latest['version']}")
    print(f"  instructions  : {len(definition.get('instructions') or '')} chars")

    tools = [dict(t) for t in definition.get("tools", [])]
    changed = []
    for t in tools:
        if t.get("type") not in APPROVABLE:
            continue
        if t.get("require_approval") != "never":
            changed.append(label(t))
            t["require_approval"] = "never"

    for t in tools:
        flag = t.get("require_approval", "-")
        mark = " <-- fixed" if label(t) in changed else ""
        print(f"  {label(t):<28} require_approval={flag}{mark}")

    if not changed:
        print("\nNothing to change - every MCP tool is already auto-approved.")
        return 0

    print(f"\n{len(changed)} tool(s) would change: {', '.join(changed)}")
    if not args.apply:
        print("Dry run. Re-run with --apply.")
        return 0

    new_def = dict(definition)
    new_def["tools"] = tools
    r = requests.post(f"{ENDPOINT}/agents/{AGENT}/versions?api-version={API}",
                      headers=h, json={"definition": new_def}, timeout=120)
    if r.status_code >= 400:
        print(f"\nFAILED {r.status_code}: {r.text[:800]}")
        return 1
    made = r.json()
    print(f"\ncreated version {made.get('version')} "
          f"({len(made['definition'].get('instructions') or '')} chars "
          f"instructions, {len(made['definition'].get('tools', []))} tools)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
