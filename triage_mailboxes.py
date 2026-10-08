"""Inventory mapped mailboxes; optionally move unmatched subjects to Deleted Items.

Requires WORKIQ_TENANT_ID/CLIENT_ID/CLIENT_SECRET, WORKIQ_USER_MAPPING_FILE
and WORKIQ_MAIL_SOURCE_FILES (a nonempty JSON array of explicit local JSON
paths, relative to the working directory). Include EVERY seed corpus in that
list, including mission mail if used. Each corpus must have a nonempty emails
array with nonblank subjects. There is no built-in author or subject allowlist.

Subject matching is a triage heuristic, not provenance verification. Review the
report before explicitly choosing --purge. Deleted Items and its descendants
are excluded. Inventory must complete for every user before any move occurs.
No POST is retried automatically; a failure may leave a partially moved batch.
"""
from __future__ import annotations

import argparse
import os
import re
from pathlib import Path
from urllib.parse import quote

from diagnostic_support import (
    AuditError, ConfigurationError, GraphClient, folder_ids, identifier,
    load_audit_config, read_object, report_error, string_list, user_url,
)


def norm(subject: str) -> str:
    subject = re.sub(r"^(?:(?:re|fw|fwd)\s*:\s*)+", "", subject.strip(), flags=re.I)
    return re.sub(r"\s+", " ", subject).strip().casefold()


def load_subjects() -> set[str]:
    sources = string_list("WORKIQ_MAIL_SOURCE_FILES", os.environ["WORKIQ_MAIL_SOURCE_FILES"])
    subjects = set()
    for source in sources:
        data = read_object(Path(source), "WORKIQ_MAIL_SOURCE_FILES")
        emails = data.get("emails")
        if not isinstance(emails, list) or not emails:
            raise ConfigurationError(f"WORKIQ_MAIL_SOURCE_FILES: {source} needs a nonempty emails array")
        for email in emails:
            if (not isinstance(email, dict) or not isinstance(email.get("subject"), str)
                    or not norm(email["subject"])):
                raise ConfigurationError(f"WORKIQ_MAIL_SOURCE_FILES: {source} has a missing/blank subject")
            subjects.add(norm(email["subject"]))
    return subjects


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--purge", action="store_true", help="move unmatched subjects to Deleted Items after full inventory")
    args = parser.parse_args(argv)
    try:
        config = load_audit_config(forbidden=False, extra=("WORKIQ_MAIL_SOURCE_FILES",))
        seeded = load_subjects()
        graph = GraphClient.authenticate(config)
        foreign = []
        print(f"{len(seeded)} distinct configured subjects; subject matching is only a triage heuristic")
        for alias, upn in config.users:
            base = user_url(upn)
            deleted = graph.get(f"{base}/mailFolders/deleteditems?$select=id", f"{alias} Deleted Items")
            destination = identifier(deleted, "id", f"{alias} Deleted Items")
            excluded = set(folder_ids(graph, base, destination))
            seen = set()
            total = unmatched = 0
            for message in graph.collection(
                f"{base}/messages?$top=200&$select=id,subject,parentFolderId,receivedDateTime",
                f"{alias} mailbox messages",
            ):
                mid = identifier(message, "id", f"{alias} message")
                parent = identifier(message, "parentFolderId", f"{alias} message")
                if mid in seen:
                    raise AuditError(f"{alias}: repeated message id; inventory is unstable")
                seen.add(mid)
                if parent in excluded:
                    continue
                subject = message.get("subject")
                if not isinstance(subject, str):
                    raise AuditError(f"{alias}: message has a missing/invalid subject")
                total += 1
                if norm(subject) not in seeded:
                    foreign.append((alias, base, mid, subject, destination))
                    unmatched += 1
            print(f"{alias}: {total} outside Deleted Items, {unmatched} unmatched subject(s)")

        if not foreign:
            print("No unmatched subjects outside Deleted Items in the inventoried mailboxes.")
            return 0
        for alias, _, _, subject, _ in foreign:
            print(f"  {alias}: {subject[:120]}")
        if not args.purge:
            print("Report only. Review all configured corpora before choosing --purge.")
            return 1
        moved = 0
        for alias, base, mid, _, destination in foreign:
            graph.move(f"{base}/messages/{quote(mid, safe='')}/move", destination, f"{alias} move")
            moved += 1
            print(f"Confirmed moves: {moved}/{len(foreign)}")
        print(f"Moved {moved} message(s) to Deleted Items.")
        return 0
    except (ConfigurationError, AuditError) as error:
        if args.purge:
            print("Purge did not complete. Previously confirmed moves may remain; re-run report-only before retrying.")
        return report_error(error)


if __name__ == "__main__":
    raise SystemExit(main())
