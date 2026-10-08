"""Audit the configured team's channel names, messages and replies.

Requires WORKIQ_TENANT_ID/CLIENT_ID/CLIENT_SECRET, WORKIQ_TEAM_ID and
WORKIQ_FORBIDDEN_TERMS (nonempty JSON string array). All pages are required;
missing/inaccessible channels or replies are inconclusive, never clean.
"""
from __future__ import annotations

from urllib.parse import quote

from diagnostic_support import (
    GRAPH, AuditError, ConfigurationError, GraphClient, LeakageScanner,
    body_text, identifier, load_audit_config, report_error,
)


def main() -> int:
    try:
        config = load_audit_config(users=False, team=True)
        scanner = LeakageScanner(config.forbidden_terms)
        graph = GraphClient.authenticate(config)
        total = 0
        base = f"{GRAPH}/teams/{config.team_id}/channels"
        for channel in graph.collection(base, "team channels"):
            channel_id = identifier(channel, "id", "team channel")
            name = identifier(channel, "displayName", "team channel")
            scanner.scan(f"channel {name}", name)
            messages = f"{base}/{quote(channel_id, safe='')}/messages"
            count = 0
            for message in graph.collection(f"{messages}?$top=50", f"{name} messages"):
                mid = identifier(message, "id", f"{name} message")
                scanner.scan(f"{name}/message/{mid}", body_text(message, f"{name} message"))
                count += 1
                for reply in graph.collection(
                    f"{messages}/{quote(mid, safe='')}/replies?$top=50", f"{name} replies",
                ):
                    rid = identifier(reply, "id", f"{name} reply")
                    scanner.scan(f"{name}/reply/{rid}", body_text(reply, f"{name} reply"))
                    count += 1
            print(f"{name}: {count} message(s), including replies")
            total += count
        print(f"{total} channel message(s), including replies")
        return scanner.report("configured team channels, messages and replies")
    except (ConfigurationError, AuditError) as error:
        return report_error(error)


if __name__ == "__main__":
    raise SystemExit(main())
