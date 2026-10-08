"""Create or update the configured Foundry scenario prompt agent.

The agent reuses the project's EXISTING connections - it does not create new ones:
  * Fabric IQ   - exactly one `fabric_iq_preview` tool
  * Foundry IQ  - exactly one MCP knowledge base with a `kb-` server label
Both are copied verbatim from FOUNDRY_SOURCE_AGENT_NAME to FOUNDRY_AGENT_NAME so
the two agents point at the same governed sources. Work IQ (mail / Teams) and
web search are deliberately NOT given to this agent.

Requires FOUNDRY_PROJECT_ENDPOINT, FOUNDRY_AGENT_NAME, FOUNDRY_SOURCE_AGENT_NAME
and AZURE_AUTH_MODE, plus the selected mode's Azure identity environment fields.

    python create_scenario_agent.py           # dry run
    python create_scenario_agent.py --apply
"""

from __future__ import annotations

import argparse
from pathlib import Path

from agent.portability import (
    ConfigurationError,
    agent_url,
    compatible_tool_choice,
    foundry_token,
    load_foundry_config,
    require_file,
)

HERE = Path(__file__).parent
API = "2025-05-15-preview"
INSTRUCTIONS = HERE / "agent" / "scenario_analyst_instructions.md"


def token(config: dict[str, str]) -> str:
    return foundry_token(config)


def latest(config: dict[str, str], h: dict, name: str, http) -> dict | None:
    url = agent_url(config, name)
    r = http.get(f"{url}?api-version={API}", headers=h, timeout=60)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    ver = r.json()["versions"]["latest"]["version"]
    v = http.get(f"{url}/versions/{ver}?api-version={API}", headers=h, timeout=60)
    v.raise_for_status()
    return v.json()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args(argv)

    try:
        config = load_foundry_config("FOUNDRY_SOURCE_AGENT_NAME")
        if config["FOUNDRY_SOURCE_AGENT_NAME"] == config["FOUNDRY_AGENT_NAME"]:
            raise ConfigurationError(
                "FOUNDRY_SOURCE_AGENT_NAME and FOUNDRY_AGENT_NAME must differ; "
                "choose a separate scenario target to avoid overwriting the source agent")
        path = require_file(INSTRUCTIONS, "scenario instructions")
        body = path.read_text(encoding="utf-8")
        start, end = "<!-- INSTRUCTIONS-START -->", "<!-- INSTRUCTIONS-END -->"
        if body.count(start) != 1 or body.count(end) != 1 or body.index(start) >= body.index(end):
            raise ConfigurationError(f"{path} must contain one ordered pair of {start} and {end}")
        body = body.split(start, 1)[1].split(end, 1)[0].strip()
        if not body:
            raise ConfigurationError(f"{path} contains empty scenario instructions")
    except (ConfigurationError, OSError, UnicodeError) as exc:
        ap.error(str(exc))

    import requests

    h = {"Authorization": f"Bearer {token(config)}", "Content-Type": "application/json"}
    source = config["FOUNDRY_SOURCE_AGENT_NAME"]
    target = config["FOUNDRY_AGENT_NAME"]

    src = latest(config, h, source, requests)
    if not src:
        ap.error(f"FOUNDRY_SOURCE_AGENT_NAME={source!r} not found")
    sdef = src["definition"]
    tools = [t for t in sdef["tools"]
             if t.get("type") == "fabric_iq_preview"
             or (t.get("type") == "mcp" and str(t.get("server_label", "")).startswith("kb-"))]
    labels = [t.get("server_label") or t.get("type") for t in tools]
    if (sum(t.get("type") == "fabric_iq_preview" for t in tools) != 1
            or sum(t.get("type") == "mcp" for t in tools) != 1):
        ap.error(f"expected exactly one Fabric IQ and one kb- MCP tool on "
                 f"FOUNDRY_SOURCE_AGENT_NAME={source!r}, found {labels}")
    if not compatible_tool_choice(sdef.get("tool_choice"), tools):
        ap.error(f"FOUNDRY_SOURCE_AGENT_NAME={source!r} has incompatible or unrecognized "
                 f"tool_choice {sdef['tool_choice']!r} for retained tools {labels}. "
                 "Remove the source tool_choice, set it to 'auto', 'none', or 'required', "
                 "or select the retained kb- MCP server and an allowed tool name.")

    new_def = dict(sdef)
    new_def.setdefault("kind", "prompt")
    new_def["instructions"] = body
    new_def["reasoning"] = {**(sdef.get("reasoning") or {}), "effort": "low"}
    new_def["tools"] = tools
    cur = latest(config, h, target, requests)
    print(f"source       : {source} v{src.get('version')} model {sdef['model']}")
    print(f"tools copied : {labels}")
    print(f"target       : {target} ({'new' if not cur else 'v' + str(cur.get('version'))})")
    print(f"instructions : {len(body)} chars")
    if not args.apply:
        print("Dry run. Re-run with --apply.")
        return 0
    r = requests.post(f"{agent_url(config)}/versions?api-version={API}",
                      headers=h, json={"definition": new_def,
                                       "description": "Scenario Analyst - Fabric IQ + Foundry IQ only"},
                      timeout=120)
    if r.status_code >= 400:
        raise SystemExit(f"create failed {r.status_code}: {r.text[:500]}")
    print(f"created {target} version {r.json().get('version')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
