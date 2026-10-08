r"""Preview or create Capital Markets mission agents from the adjacent cm_agents.md.

Copy the configured source agent's definition and governed tool connections:
fabric (Fabric IQ), kb (knowledge-base MCP), work (Work IQ), and web (web search
or Bing grounding). Only mission instructions and the selected tools change.

Required: FOUNDRY_PROJECT_ENDPOINT, FOUNDRY_SOURCE_AGENT_NAME, AZURE_AUTH_MODE,
and the selected mode's credential fields documented in portability.py.

    python agent\create_cm_agents.py           # dry run
    python -m agent.create_cm_agents --apply
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import re
from pathlib import Path
from urllib.parse import quote

if __package__:
    from .portability import (
        ConfigurationError, agent_url, compatible_tool_choice, foundry_token,
        load_foundry_config, require_file,
    )
else:
    from portability import (
        ConfigurationError, agent_url, compatible_tool_choice, foundry_token,
        load_foundry_config, require_file,
    )

API = "2025-05-15-preview"
SPEC = Path(__file__).parent / "cm_agents.md"
TOOL_KINDS = ("fabric", "kb", "work", "web")


def load_spec(path: Path) -> list[tuple[str, list[str], str]]:
    path = require_file(path, "mission agent specification")
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ConfigurationError(f"Cannot read mission agent specification {path}: {exc}") from exc

    header = re.compile(r"[ \t]*<!--[ \t]+AGENT[ \t]+([^\s<>]+)[ \t]+tools=(\S+)[ \t]+-->[ \t]*")
    ending = re.compile(r"[ \t]*<!--[ \t]+END[ \t]+-->[ \t]*")
    marker = re.compile(r"<!--\s*(?:AGENT|END)", re.IGNORECASE)
    agents = []
    names = set()
    current = None
    body = []
    for number, line in enumerate(text.splitlines(keepends=True), 1):
        content = line.rstrip("\r\n")
        if not marker.search(content):
            if current is not None:
                body.append(line)
            continue
        location = f"{path}:{number}"
        match = header.fullmatch(content)
        if match:
            if current is not None:
                raise ConfigurationError(f"{location}: nested AGENT before END for {current[0]}")
            name, requested = match.groups()
            if name in names:
                raise ConfigurationError(f"{location}: duplicate agent name {name}")
            kinds = requested.split(",")
            unknown = [kind or "(empty)" for kind in kinds if kind not in TOOL_KINDS]
            if unknown:
                raise ConfigurationError(
                    f"{location}: {name}: unrecognized tool categories {unknown}; "
                    f"expected {', '.join(TOOL_KINDS)}")
            if len(kinds) != len(set(kinds)):
                raise ConfigurationError(f"{location}: {name}: duplicate tool categories")
            names.add(name)
            current = (name, kinds)
            body = []
        elif ending.fullmatch(content):
            if current is None:
                raise ConfigurationError(f"{location}: END without an AGENT")
            instructions = "".join(body).strip()
            if not instructions:
                raise ConfigurationError(f"{location}: {current[0]}: empty instructions")
            agents.append((*current, instructions))
            current = None
        else:
            raise ConfigurationError(f"{location}: malformed AGENT or END marker")
    if current is not None:
        raise ConfigurationError(f"{path}: missing END for {current[0]}")
    if not agents:
        raise ConfigurationError(f"{path}: no AGENT blocks found; specification is empty or malformed")
    return agents


def latest(config: dict, h: dict, name: str, http) -> dict | None:
    url = agent_url(config, name)
    r = http.get(f"{url}?api-version={API}", headers=h, timeout=120)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    try:
        ver = r.json()["versions"]["latest"]["version"]
    except (KeyError, TypeError) as exc:
        raise ConfigurationError(f"{name}: source or target response has no latest version") from exc
    if not isinstance(ver, (str, int)) or isinstance(ver, bool) or not str(ver).strip():
        raise ConfigurationError(f"{name}: invalid latest version")
    v = http.get(
        f"{url}/versions/{quote(str(ver), safe='')}?api-version={API}", headers=h, timeout=120)
    v.raise_for_status()
    return v.json()


def mission_definitions(source: dict, source_name: str, agents: list) -> list[tuple[str, dict]]:
    if not isinstance(source, dict) or not isinstance(source.get("definition"), dict):
        raise ConfigurationError(f"{source_name}: missing or invalid source definition")
    definition = source["definition"]
    for field in ("kind", "model"):
        if not isinstance(definition.get(field), str) or not definition[field].strip():
            raise ConfigurationError(f"{source_name}: missing or invalid source definition {field}")
    tools = definition.get("tools")
    if not isinstance(tools, list) or any(
        not isinstance(tool, dict) or not isinstance(tool.get("type"), str)
        or not tool["type"].strip() for tool in tools
    ):
        raise ConfigurationError(f"{source_name}: missing or invalid source definition tools")
    pool = {
        "fabric": [t for t in tools if t["type"] == "fabric_iq_preview"],
        "kb": [t for t in tools if t["type"] == "mcp"
               and str(t.get("server_label", "")).startswith("kb-")],
        "work": [t for t in tools if str(t.get("server_label", "")).lower().startswith("workiq")],
        "web": [t for t in tools if t["type"] in (
            "web_search", "web_search_2025_08_26", "web_search_preview",
            "web_search_preview_2025_03_11", "bing_grounding",
        )],
    }
    missing = [
        f"{name}: no {kind} tool on {source_name}"
        for name, kinds, _ in agents for kind in kinds if not pool[kind]
    ]
    if missing:
        raise ConfigurationError("; ".join(missing))
    missions = []
    for name, kinds, instructions in agents:
        payload = deepcopy(definition)
        payload["instructions"] = instructions
        payload["tools"] = deepcopy([tool for kind in kinds for tool in pool[kind]])
        if not compatible_tool_choice(payload.get("tool_choice"), payload["tools"]):
            labels = [tool.get("server_label") or tool["type"] for tool in payload["tools"]]
            raise ConfigurationError(
                f"{name}: FOUNDRY_SOURCE_AGENT_NAME={source_name!r} has incompatible or "
                f"unrecognized tool_choice {payload['tool_choice']!r} for retained tools {labels}. "
                "Remove the source tool_choice, set it to 'auto', 'none', or 'required', "
                "or select a retained SDK-supported tool and an allowed tool name.")
        missions.append((name, payload))
    return missions


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args(argv)
    try:
        config = load_foundry_config("FOUNDRY_SOURCE_AGENT_NAME", require_agent=False)
        agents = load_spec(SPEC)
        source_name = config["FOUNDRY_SOURCE_AGENT_NAME"]
        if any(name == source_name for name, _, _ in agents):
            raise ConfigurationError(
                f"FOUNDRY_SOURCE_AGENT_NAME={source_name!r} must differ from every mission target; "
                "choose separate mission targets to avoid overwriting the source agent")
    except ConfigurationError as exc:
        ap.error(str(exc))

    import requests

    h = {"Authorization": f"Bearer {foundry_token(config)}", "Content-Type": "application/json"}
    try:
        src = latest(config, h, source_name, requests)
        if src is None:
            raise ConfigurationError(f"Source agent {source_name} not found")
        missions = mission_definitions(src, source_name, agents)
        current = {name: latest(config, h, name, requests) for name, _ in missions}
    except ConfigurationError as exc:
        ap.error(str(exc))
    for name, definition in missions:
        cur = current[name]
        print(f"{name:22} tools={[t.get('server_label') or t['type'] for t in definition['tools']]} "
              f"model={definition['model']} "
              f"{'new' if cur is None else 'v' + str(cur.get('version'))} "
              f"instructions={len(definition['instructions'])}")
        if not args.apply:
            continue
        r = requests.post(
            f"{agent_url(config, name)}/versions?api-version={API}", headers=h, timeout=180,
            json={"definition": definition, "description": f"Capital Markets - {name}"})
        if r.status_code >= 400:
            raise SystemExit(f"{name}: {r.status_code} {r.text[:400]}")
        print(f"  -> created version {r.json().get('version')}")
    if not args.apply:
        print("Dry run. Re-run with --apply.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
