"""Check publishable source for cross-demo content without reading private files.

Uses Git's tracked files plus nonignored new files, not a recursive tenant/config
scan. Additional institution or tenant-specific terms can be supplied explicitly
with repeated --forbid arguments; no institution identifiers are shipped.
"""

from __future__ import annotations

import argparse
from fnmatch import fnmatchcase
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SKIP_DIRS = {"node_modules", "dist", ".venv", "__pycache__", ".vite", ".git"}
SKIP_FILES = {"package-lock.json"}
TEXT_SUFFIXES = {
    ".py", ".ts", ".tsx", ".js", ".mjs", ".json", ".md", ".css", ".html",
    ".ps1", ".bicep", ".txt", ".yml", ".yaml", ".csv", ".conf", ".template",
    ".sql", ".ipynb", ".tmdl",
}

# Leading boundaries catch plurals without matching the middle of a word.
# Investment advisory and facility renewal are legitimate scenario vocabulary.
TOKENS = [
    "vale", "teck", "freeport", "contoso", "mortgage", "concierge", "heloc",
    "branch manager", "mtgrenewal", "mortgage-iqs", "ws-mortgage",
    "sm_mortgage", "proj-conceirge",
]
PATTERNS = [(token, re.compile(r"\b" + re.escape(token), re.I)) for token in TOKENS]
PATTERNS.append(("advisor", re.compile(r"\badvisor\b", re.I)))
ALLOW = {
    ("scan_leakage.py", "*"): "source checker contains its own banned terms",
    ("test_source_checks.py", "*"): "negative fixtures exercise the source checker",
    ("cm_agents.md", "advisor"): "internal advisor brief, not retail advice",
}


def publishable_files(root: Path) -> list[Path]:
    """Include tracked ignored files so accidental publication still fails."""
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "--cached", "--others",
         "--exclude-standard", "-z", "--", "."],
        capture_output=True, check=True,
    )
    paths = {Path(item.decode("utf-8")) for item in result.stdout.split(b"\0") if item}
    return [root / rel for rel in sorted(paths)
            if not set(rel.parts) & SKIP_DIRS and rel.name not in SKIP_FILES]


def private_artifact(path: Path) -> bool:
    name = path.name.lower()
    parts = tuple(part.lower() for part in path.parts)
    brand = parts[:5] == ("app", "src", "web", "public", "brand")
    return (
        any(fnmatchcase(name, pattern) for pattern in (
            "*.local.*", "*.restore.json", "*.restore-state.*",
            "*token_cache*", "*token-cache*", "*token.cache*", ".tokens*",
            "*deploy*output*.json",
        ))
        or (name.startswith("user_mapping") and name.endswith(".json")
            and name != "user_mapping.example.json")
        or (name.startswith(".env") and name not in {".env.example", ".env.template"}
            and not name.endswith(".example"))
        or ("deployment" in name and name.endswith(".json"))
        or bool(set(parts) & {".azure", ".identity", ".local", "restore-state",
                              "deployment-outputs", "deploy-outputs"})
        or any(part.startswith(".deployment-checks") for part in parts)
        or ("infra" in parts and name in {"main.parameters.json", "main.json"})
        or ("brand" in parts and "generated" in parts)
        or (brand and (name in {"bank.json", "logo.png"} or "uploads" in parts
                       or any(fnmatchcase(name, pattern)
                              for pattern in ("user-logo.*", "bank-logo.*", "logo.local.*"))))
    )


def scan(root: Path, extra_terms: tuple[str, ...] = ()):
    failures: dict[str, list[tuple[str, int, str]]] = {}
    accepted: dict[str, int] = {}
    scanned = 0
    patterns = PATTERNS + [
        (term, re.compile(r"\b" + re.escape(term), re.I)) for term in extra_terms
    ]
    for path in publishable_files(root):
        rel = str(path.relative_to(root))
        if private_artifact(path.relative_to(root)):
            failures.setdefault("private artifact", []).append((rel, 0, "must be untracked"))
            continue
        # Private files still in the index are rejected even if removed locally.
        # Other checks validate required sources; this sweep inspects remaining
        # working-tree content, including intended deletions by other owners.
        if not path.exists():
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8-sig")
        scanned += 1
        for token, rx in patterns:
            reason = ALLOW.get((path.name, token)) or ALLOW.get((path.name, "*"))
            for line_number, line in enumerate(text.splitlines(), 1):
                if not rx.search(line):
                    continue
                if reason and token not in extra_terms:
                    key = f"{token} :: {reason}"
                    accepted[key] = accepted.get(key, 0) + 1
                else:
                    failures.setdefault(token, []).append((rel, line_number, line.strip()[:150]))
    return scanned, accepted, failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all", action="store_true", help="also list accepted hits")
    parser.add_argument("--forbid", action="append", default=[], metavar="TERM",
                        help="additional literal institution or tenant term to reject")
    args = parser.parse_args(argv)
    if any(not term.strip() for term in args.forbid):
        parser.error("--forbid terms must be nonblank")
    try:
        scanned, accepted, failures = scan(ROOT, tuple(term.strip() for term in args.forbid))
    except (OSError, UnicodeError, subprocess.CalledProcessError) as exc:
        print(f"FAILED - source inventory or read was incomplete: {exc}")
        return 2
    print(f"scanned {scanned} publishable files")
    if args.all and accepted:
        print("\nAccepted (allowlisted):")
        for key, count in sorted(accepted.items()):
            print(f"  {count:>3}x  {key}")
    if not failures:
        print(f"\nCLEAN - no unexpected cross-demo references. "
              f"({sum(accepted.values())} allowlisted)")
        return 0
    print(f"\nFAILED - {len(failures)} source issue(s):")
    for token, rows in sorted(failures.items()):
        print(f"\n### {token} ({len(rows)})")
        for filename, line, text in rows[:20]:
            print(f"   {filename}:{line}  {text}")
        if len(rows) > 20:
            print(f"   {len(rows) - 20} additional matches")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
