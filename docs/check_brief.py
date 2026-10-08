"""Extract a selected briefing document and validate current synthetic facts."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from xml.etree import ElementTree
import zipfile

DATA = Path(__file__).resolve().parents[1] / "data"
if str(DATA) not in sys.path:
    sys.path.insert(0, str(DATA))
from scenario_facts import FACTS

NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}


def check_document(path: Path) -> int:
    with zipfile.ZipFile(path) as archive:
        root = ElementTree.fromstring(archive.read("word/document.xml"))
    paragraphs = [
        "".join(node.text or "" for node in paragraph.findall(".//w:t", NS)).strip()
        for paragraph in root.findall(".//w:p", NS)
    ]
    paragraphs = [text for text in paragraphs if text]
    print(f"paragraphs with text : {len(paragraphs)}")
    print(f"tables               : {len(root.findall('.//w:tbl', NS))}")
    print(f"page breaks          : {len(root.findall('.//w:br[@w:type=\"page\"]', NS))}")
    print("\nDEMO QUESTIONS:")
    for text in paragraphs:
        if text.startswith("\u201c"):
            print(f"  - {text[:110]}")
    print("\nHEADINGS:")
    for paragraph in root.findall(".//w:p", NS):
        style = paragraph.find("w:pPr/w:pStyle", NS)
        level = style.get(f"{{{NS['w']}}}val", "") if style is not None else ""
        if level in ("Heading1", "Heading2", "Heading3"):
            heading = "".join(node.text or "" for node in paragraph.findall(".//w:t", NS))
            print(f"  {'  ' * (int(level[-1]) - 1)}{level[-1]}. {heading}")
    text = " ".join(paragraphs)
    hero = FACTS["hero_metrics"]
    expected = [
        ("single-name limit", f"{hero['single_name_limit_m']:,.0f}"),
        ("total exposure", f"{hero['total_exposure_m']:,.1f}"),
        ("limit utilisation", f"{hero['limit_utilisation_pct']}%"),
        ("wallet share", f"{hero['wallet_share_pct']}%"),
        ("internal risk rating", hero["internal_risk_rating"]),
        ("covenant actual", f"{FACTS['covenant_tension']['actual']:.2f}"),
        ("covenant threshold", f"{FACTS['covenant_tension']['threshold']:.2f}"),
        ("disclaimer", "Synthetic demonstration data"),
    ]
    failed = []
    print("\nFACT CHECK:")
    for label, needle in expected:
        present = needle.casefold() in text.casefold()
        print(f"  {'OK' if present else 'MISSING'} {label}: {needle}")
        if not present:
            failed.append(label)
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("document", type=Path, help="local .docx brief to inspect")
    args = parser.parse_args(argv)
    if not args.document.is_file():
        parser.error(f"brief not found: {args.document}")
    try:
        return check_document(args.document)
    except (OSError, zipfile.BadZipFile, KeyError, ElementTree.ParseError) as exc:
        print(f"Cannot check brief: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
