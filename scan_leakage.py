"""Pre-deployment sweep: prove no other demo's identity leaks into this one.

Deliberately over-broad, then narrowed by an explicit allowlist. Every accepted
hit is recorded below with a reason - "it's probably fine" is not a result.

Run before every deployment:

    python scan_leakage.py
    python scan_leakage.py --all    # show accepted hits too
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).parent
SKIP_DIRS = {"node_modules", "dist", ".venv", "__pycache__", ".vite", ".git"}
SKIP_FILES = {"package-lock.json"}
TEXT_SUFFIXES = {
    ".py", ".ts", ".tsx", ".js", ".json", ".md", ".css", ".html", ".ps1",
    ".bicep", ".txt", ".yml", ".yaml", ".csv", ".conf", ".template", ".sql",
    ".ipynb",
}

# Matched with a leading word boundary, so plurals and possessives are caught
# ("renewal" finds "renewals") but substrings are not ("heloc" no longer fires
# inside "cacheLocation").
#
# A trailing boundary is added only where a longer legitimate word would
# otherwise collide - "advisor" must not match "M&A Advisory", which is ordinary
# investment-banking vocabulary in this demo.
TOKENS = [
    # other banks
    "scotiabank", "scotia", "rbc", "royal bank", "nesbitt",
    # other demos' clients
    "vale", "teck", "freeport", "contoso",
    # other demos' domain language
    "mortgage", "renewal", "concierge", "heloc", "branch manager",
    r"advisor\b",
    # other demos' infrastructure
    "rbcintel", "rbcci", "rbccap", "mtgrenewal", "mortgage-iqs", "rg-scotia",
    "ws-mortgage", "sm_mortgage", "proj-conceirge", "ws-rbc-client-intel",
    # other demos' people
    "Raj Balakrishnan", "Diane Lafleur", "Karen Whitfield", "Derek Fontaine",
    "Helena Vasquez", "Liam O'Connor", "Camille Fortin", "Jonas Berg",
    "Marcus Delaney", "Sophie Tremblay", "Nadia Osei", "Priya Raghavan",
    "Wei Zhang", "Fatima Haddad",
]

# (file suffix or name, token, reason). A hit matching an entry is accepted.
#
# These are the ONLY permitted appearances. Anything else fails the sweep.
ALLOW: list[tuple[str, str, str]] = [
    # The checkers necessarily contain the words they ban.
    ("check_loaders.py", "*", "banned-word list lives in the checker"),
    ("validate_dataset.py", "*", "banned-word list lives in the checker"),
    ("check_corpus.py", "*", "banned-word list lives in the checker"),
    ("audit_tenant_leakage.py", "*", "banned-word list lives in the checker"),
    ("audit_files.py", "*", "banned-word list lives in the checker"),
    ("audit_teams.py", "*", "banned-word list lives in the checker"),
    ("triage_mailboxes.py", "*", "mailbox triage tooling"),
    # The live Foundry agent is genuinely called this.
    ("*", "concierge", "the portal agent is named Agent-cap-market"),
    # Protective annotation naming the accounts this demo must not touch.
    ("user_mapping.json", "mortgage", "do-not-touch list for other demos"),
    ("user_mapping.json", "renewal", "do-not-touch list for other demos"),
    ("user_mapping.json", "scotia", "do-not-touch list for other demos"),
    ("configure_rbac.py", "scotia", "do-not-touch list for other demos"),
    ("configure_rbac.py", "mortgage", "do-not-touch list for other demos"),
    ("configure_rbac.py", "renewal", "do-not-touch list for other demos"),
    ("README.md", "scotia", "documents the account split between demos"),
    ("README.md", "renewal", "documents the account split between demos"),
    ("README.md", "mortgage", "documents the account split between demos"),
    # "renewal" is ordinary credit vocabulary here - facilities renew.
    ("cm_policies.json", "renewal", "facility renewal, not the mortgage demo"),
    ("emails.json", "renewal", "facility renewal, not the mortgage demo"),
    # RBC is named as the reference implementation this demo was ported from.
    ("make_brand.py", "rbc", "explains how this differs from the RBC variant"),
    ("foundry-appinsights-connection.bicep", "rbc", "cites the RBC parity target"),
    # The chat skills cite the Scotia Flyer as the pattern they were modelled on.
    ("generate_skill_data.py", "scotia", "cites the Scotia data-transcription pattern"),
    ("SkillBar.tsx", "scotia", "cites the Scotia Flyer as the design precedent"),
    ("set_tool_allowlist.py", "scotia", "names the co-tenant demo the allowlist protects"),
    ("set_tool_allowlist.py", "mortgage", "names the co-tenant demo the allowlist protects"),
    ("styles.css", "scotia", "cites the Scotia Flyer as the design precedent"),
    ("scan_leakage.py", "*", "banned-word list lives in the checker"),
]

PATTERNS = [(t, re.compile(r"\b" + t if t.startswith("advisor") else
                           r"\b" + re.escape(t), re.I)) for t in TOKENS]


def allowed(rel: str, token: str) -> str | None:
    name = Path(rel).name
    for pat, tok, reason in ALLOW:
        if pat not in ("*", name):
            continue
        if tok not in ("*", token.lower()):
            continue
        return reason
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true",
                    help="also list accepted hits")
    args = ap.parse_args()

    failures: dict[str, list[tuple[str, int, str]]] = {}
    accepted: dict[str, int] = {}
    scanned = 0

    for p in sorted(ROOT.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(ROOT)
        if set(rel.parts) & SKIP_DIRS or p.name in SKIP_FILES:
            continue
        if p.suffix.lower() not in TEXT_SUFFIXES:
            continue
        if p.name == Path(__file__).name:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        scanned += 1
        for t, rx in PATTERNS:
            if not rx.search(text):
                continue
            reason = allowed(str(rel), t.lower())
            for i, line in enumerate(text.splitlines(), 1):
                if not rx.search(line):
                    continue
                if reason:
                    key = f"{t} :: {reason}"
                    accepted[key] = accepted.get(key, 0) + 1
                else:
                    failures.setdefault(t, []).append(
                        (str(rel), i, line.strip()[:150]))

    print(f"scanned {scanned} files")

    if args.all and accepted:
        print("\nAccepted (allowlisted):")
        for k, n in sorted(accepted.items()):
            print(f"  {n:>3}x  {k}")

    if not failures:
        print(f"\nCLEAN - no unexpected cross-demo references. "
              f"({sum(accepted.values())} allowlisted)")
        return 0

    print(f"\nFAILED - {len(failures)} token(s) leaked:\n")
    for t, rows in sorted(failures.items()):
        print(f"### {t}  ({len(rows)})")
        for f, i, line in rows[:20]:
            print(f"   {f}:{i}  {line}")
        if len(rows) > 20:
            print(f"   ... +{len(rows) - 20} more")
        print()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
