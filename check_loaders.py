"""Read-only loader/frontend checks using the existing deterministic generators.

Python, Node.js, and the installed web dependencies are required. Missing tools
or stale outputs fail the check; no dependency install, build, credential lookup,
tenant access, or regeneration is performed.
"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
GENERATORS = [
    ("Fabric tables", "data/fabric-iq/generate_fabric_data.py", ["--check"]),
    ("market scenarios", "data/market-scenario/generate_scenario_tables.py", ["--check"]),
    ("mission corpus", "data/mission_data.py", ["--data-only", "--check"]),
    ("dashboard snapshot", "data/generate_dashboard_snapshot.py", ["--check"]),
    ("BFF skills", "app/src/bff/generate_skill_data.py", ["--check"]),
    ("BFF market scenarios", "app/src/bff/generate_market_data.py", ["--check"]),
]


def commands() -> list[tuple[str, list[str], Path]]:
    checks = [
        (label, [sys.executable, "-B", str(HERE.joinpath(*relative.split("/"))), *args], HERE)
        for label, relative, args in GENERATORS
    ]
    checks.append(("offline agent tools",
                   [sys.executable, "-B", str(HERE / "agent" / "create_agent.py"),
                    "--local-smoke"], HERE))
    web = HERE / "app" / "src" / "web"
    checks.append(("frontend dashboard", ["node", "--test", "dashboard.test.mjs"], web))
    return checks


def main() -> int:
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"}
    failed = []
    for label, command, cwd in commands():
        print(f"\n{label}", flush=True)
        try:
            result = subprocess.run(command, cwd=cwd, env=env, check=False)
        except OSError as exc:
            print(f"FAIL {label}: required tool unavailable: {exc}")
            failed.append(label)
            continue
        if result.returncode:
            failed.append(label)
        print(f"{'FAIL' if result.returncode else 'PASS'} {label}", flush=True)
    if failed:
        print("\nFAILED: " + ", ".join(failed))
        return 1
    print("\nPASSED - all source loader and frontend checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
