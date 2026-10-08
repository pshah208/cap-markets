"""Run every pre-deployment audit, source and live tenant, in one command.

Source checks need Python, Node.js and installed web dependencies, but no tenant
configuration. The tenant checks need explicit credentials and audit scope:

    $env:WORKIQ_TENANT_ID     = "<tenant-guid>"
    $env:WORKIQ_CLIENT_ID     = "<workiq-cmintel-seeder appId>"
    $env:WORKIQ_CLIENT_SECRET = "<a freshly minted secret>"
    $env:WORKIQ_USER_MAPPING_FILE = "<private mapping JSON path>"
    $env:WORKIQ_TEAM_ID = "<team-guid>"
    $env:WORKIQ_FORBIDDEN_TERMS = '["foreign demo phrase"]'

    python preflight.py            # source only
    python preflight.py --tenant   # source + live tenant

NOTE: `az ad app credential reset` REPLACES every existing secret on the app.
Use `--append` if the seeder's own secret must survive.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent

SOURCE = [
    ("dataset", [sys.executable, str(HERE / "data" / "validate_dataset.py")]),
    ("policy corpus", [sys.executable,
                       str(HERE / "data" / "foundry-iq" / "check_corpus.py")]),
    ("loaders + frontend", [sys.executable, str(HERE / "check_loaders.py")]),
    ("cross-demo leakage", [sys.executable, str(HERE / "scan_leakage.py")]),
]

TENANT = [
    ("mailboxes", [sys.executable, str(HERE / "audit_tenant_leakage.py")]),
    ("OneDrive + SharePoint", [sys.executable, str(HERE / "audit_files.py")]),
    ("Teams channels", [sys.executable, str(HERE / "audit_teams.py")]),
]


def run(label: str, cmd: list[str]) -> bool:
    print(f"\n{'=' * 70}\n  {label}\n{'=' * 70}")
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"}
    p = subprocess.run(cmd, env=env, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    out = (p.stdout or "") + (p.stderr or "")
    tail = out.strip().splitlines()
    for line in tail[-14:]:
        print(f"  {line}")
    ok = p.returncode == 0
    print(f"  --> {'PASS' if ok else 'FAIL'}")
    return ok


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--tenant", action="store_true",
                    help="also audit the live tenant (needs WORKIQ_* env vars)")
    args = ap.parse_args()

    checks = list(SOURCE)
    if args.tenant:
        from diagnostic_support import ConfigurationError, load_audit_config
        try:
            load_audit_config(users=True, team=True)
        except ConfigurationError as exc:
            print(f"--tenant configuration invalid: {exc}")
            return 2
        checks += TENANT

    results = [(label, run(label, cmd)) for label, cmd in checks]

    print(f"\n{'=' * 70}\n  SUMMARY\n{'=' * 70}")
    for label, ok in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {label}")
    failed = [l for l, ok in results if not ok]
    if failed:
        print(f"\n{len(failed)} check(s) FAILED - do not deploy.")
        return 1
    print("\nAll selected checks passed. "
          + ("Live audit scope was verified." if args.tenant else
             "Source only; tenant policy, permissions and connectivity are not verified."))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
