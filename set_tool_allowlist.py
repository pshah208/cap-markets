"""Restrict each MCP connection to the tools this demo actually needs.

TWO PROBLEMS, ONE FIX
---------------------
1. **Latency.** Foundry injects the full JSON schema of every tool on every
   connected MCP server into *every* request, before the question is read. With
   all five Work IQ servers attached that is 124 tools and roughly 44,000 input
   tokens per turn - more than 90% of it Work IQ, and most of that write tools
   the demo never calls. A trivial question like "what is the internal risk
   rating" was costing ~44k input tokens and ~44 seconds.

2. **Safety.** The unfiltered surface includes `DeleteMessage`,
   `deleteFileOrFolder`, `deleteList`, `SendMessageToChannel` and
    `setSensitivityLabelOnFile`. A read-only agent has no business holding a
    delete tool, and an allowlist is a far stronger control than an instruction
    asking it not to.

The allowlist below is therefore **read-only by construction**. Adding a write
tool here is a deliberate act, not an accident of connecting a server.

Requires FOUNDRY_PROJECT_ENDPOINT, FOUNDRY_AGENT_NAME and AZURE_AUTH_MODE, plus
the selected mode's Azure identity environment fields.

    python set_tool_allowlist.py            # dry run - show the saving
    python set_tool_allowlist.py --apply
    python set_tool_allowlist.py --clear    # remove filters, restore everything
"""

from __future__ import annotations

import argparse

from agent.portability import (
    ConfigurationError,
    agent_url,
    foundry_token,
    load_foundry_config,
)

API = "2025-05-15-preview"

# Read-only. Every entry is a search, list or read.
#
# The demo asks four kinds of Work IQ question: "what did the team discuss"
# (search mail + Teams), "what is reference CR-YYYY-NNNN" (search all three),
# "what is in the brief" (read a SharePoint file) and "who said what" (read a
# message). Nothing else is needed, and nothing that writes is included.
ALLOWLIST: dict[str, list[str]] = {
    "WorkIQMail": [
        # The service's own guidance: prefer the deterministic query-parameter
        # form, which is faster and has no indexing delay. Omitting it in the
        # first cut of this allowlist left the agent with only the relevance
        # search and GetMessage, so it leaned on GetMessage - which fails on any
        # Graph message id containing "/" ("Message ID cannot contain forward
        # slashes"). Graph ids are base64 and routinely contain one, so that
        # tool is unusable here by construction and is deliberately excluded.
        "SearchMessagesQueryParameters",
        "SearchMessages",
    ],
    "WorkIQTeams": [
        "SearchTeamMessagesQueryParameters",
        "SearchTeamsMessages",
        "ListChannels",
        "ListChannelMessages",
        "ListChats",
        "ListChatMessages",
    ],
    "WorkIQSharePoint": [
        "findSite",
        "findFileOrFolder",
        "getFileOrFolderMetadata",
        "listDocumentLibrariesInSite",
        "readSmallTextFile",
    ],
    "WorkIQOneDrive": [
        "findFileOrFolderInMyDrive",
        "readSmallTextFileFromMyOnedrive",
    ],
    "WorkIQWord": [
        "GetDocumentContent",
    ],
    # The Fabric data agent and the AI Search knowledge base expose
    # a handful of tools each and are all read paths, so they are left whole.
}


def token(config: dict[str, str]) -> str:
    return foundry_token(config)


def label(tool: dict) -> str:
    return (tool.get("server_label")
            or (tool.get("project_connection_id") or "").split("/")[-1]
            or tool.get("type", "?"))


def current_allowed(tool: dict) -> list[str] | None:
    """Tool names currently allowed, normalised.

    The service does not echo back what you send. `allowed_tools` goes up as a
    flat list and comes back as `{"tool_names": [...]}`, so a naive
    `!= wanted` comparison never matches and every dry run reports work to do -
    and every --apply cuts a pointless new agent version. Both shapes are
    accepted here so the script is honestly idempotent.
    """
    raw = tool.get("allowed_tools")
    if raw is None:
        return None
    if isinstance(raw, dict):
        names = raw.get("tool_names")
        return list(names) if names is not None else None
    if isinstance(raw, list):
        return list(raw)
    return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--clear", action="store_true",
                    help="remove every allowed_tools filter")
    args = ap.parse_args(argv)

    try:
        config = load_foundry_config()
    except ConfigurationError as exc:
        ap.error(str(exc))

    import requests

    h = {"Authorization": "Bearer " + token(config), "Content-Type": "application/json"}

    r = requests.get(f"{agent_url(config)}?api-version={API}",
                     headers=h, timeout=60)
    r.raise_for_status()
    latest = r.json()["versions"]["latest"]
    definition = latest["definition"]
    print(f"current version : {latest['version']}")

    tools = [dict(t) for t in definition.get("tools", [])]
    changed: list[str] = []

    for t in tools:
        name = label(t)
        if args.clear:
            if "allowed_tools" in t:
                t.pop("allowed_tools")
                changed.append(name)
            continue
        wanted = ALLOWLIST.get(name)
        if wanted is None:
            continue
        if current_allowed(t) != wanted:
            t["allowed_tools"] = wanted
            changed.append(name)

    for t in tools:
        name = label(t)
        allowed = current_allowed(t)
        shown = f"{len(allowed)} allowed" if allowed else "all tools"
        mark = "  <-- changed" if name in changed else ""
        print(f"  {name:<28} {shown}{mark}")

    if not changed:
        print("\nNothing to change.")
        return 0

    if not args.clear:
        kept = sum(len(v) for v in ALLOWLIST.values())
        print(f"\nWork IQ surface: 117 tools -> {kept}. "
              f"Roughly 40k input tokens per turn removed, and every write "
              f"tool (delete, send, upload, relabel) is dropped.")

    print(f"\n{len(changed)} connection(s) would change: {', '.join(changed)}")
    if not args.apply:
        print("Dry run. Re-run with --apply.")
        return 0

    new_def = dict(definition)
    new_def["tools"] = tools
    r = requests.post(f"{agent_url(config)}/versions?api-version={API}",
                      headers=h, json={"definition": new_def}, timeout=120)
    if r.status_code >= 400:
        print(f"\nFAILED {r.status_code}: {r.text[:800]}")
        return 1
    made = r.json()
    print(f"\ncreated version {made.get('version')} "
          f"({len(made['definition'].get('tools', []))} tools)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
