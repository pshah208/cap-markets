"""Read-only cross-demo audit of explicitly mapped users' live mail.

Requires WORKIQ_TENANT_ID/CLIENT_ID/CLIENT_SECRET, WORKIQ_USER_MAPPING_FILE
and WORKIQ_FORBIDDEN_TERMS (nonempty JSON string array).
Scope: Inbox, Sent Items, Drafts, optional Archive and their descendants.
Other top-level folders, Deleted Items and file contents are not audited.
An absent Archive metadata probe is optional; failed message reads never are.
"""
from __future__ import annotations

from diagnostic_support import (
    AuditError, ConfigurationError, GraphClient, LeakageScanner, body_text,
    identifier, live_messages, load_audit_config, report_error,
)


def main() -> int:
    try:
        config = load_audit_config()
        scanner = LeakageScanner(config.forbidden_terms)
        graph = GraphClient.authenticate(config)
        for alias, upn in config.users:
            total = 0
            for folder, message in live_messages(graph, upn):
                mid = identifier(message, "id", f"{alias} message")
                scanner.scan(f"{alias}/{folder}/{mid}", body_text(message, f"{alias} message"))
                total += 1
            print(f"{alias}: {total} message(s) in selected live folders and descendants")
        return scanner.report("mapped users' selected live mail folders and descendants")
    except (ConfigurationError, AuditError) as error:
        return report_error(error)


if __name__ == "__main__":
    raise SystemExit(main())
