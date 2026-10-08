"""Audit all mapped users' OneDrive and the configured team's SharePoint names.

Requires WORKIQ_TENANT_ID/CLIENT_ID/CLIENT_SECRET, WORKIQ_USER_MAPPING_FILE,
WORKIQ_TEAM_ID and WORKIQ_FORBIDDEN_TERMS (JSON string array). No stock tenant
file allowlist is applied. This audits names/paths, not binary file contents.
Every folder and collection page must be read before a clean result is possible.
"""
from __future__ import annotations

from urllib.parse import quote

from diagnostic_support import (
    GRAPH, AuditError, ConfigurationError, GraphClient, LeakageScanner,
    identifier, load_audit_config, report_error, user_url,
)


def walk(graph: GraphClient, base: str, root: str) -> list[str]:
    paths = []
    pending = [(root, "")]
    seen = set()
    while pending:
        item_id, parent = pending.pop()
        if item_id in seen:
            raise AuditError("Drive hierarchy contains a repeated folder id")
        seen.add(item_id)
        for item in graph.collection(
            f"{base}/items/{quote(item_id, safe='')}/children?$top=200", "drive children",
        ):
            name = identifier(item, "name", "drive item")
            child_id = identifier(item, "id", "drive item")
            path = f"{parent}/{name}"
            if "remoteItem" in item:
                raise AuditError(f"Drive shortcut cannot be fully audited: {path}")
            paths.append(path)
            if "folder" in item:
                if not isinstance(item["folder"], dict):
                    raise AuditError(f"Invalid folder metadata: {path}")
                pending.append((child_id, path))
    return paths


def main() -> int:
    try:
        config = load_audit_config(team=True)
        scanner = LeakageScanner(config.forbidden_terms)
        graph = GraphClient.authenticate(config)
        drives = [(alias, f"{user_url(upn)}/drive") for alias, upn in config.users]
        drives.append(("team SharePoint", f"{GRAPH}/groups/{config.team_id}/drive"))
        for label, base in drives:
            root = graph.get(f"{base}/root", f"{label} drive root")
            paths = walk(graph, base, identifier(root, "id", f"{label} drive root"))
            print(f"{label}: {len(paths)} file/folder name(s)")
            for path in paths:
                print(f"  {path}")
                scanner.scan(f"{label}{path}", path)
        return scanner.report("mapped OneDrive and configured team SharePoint names")
    except (ConfigurationError, AuditError) as error:
        return report_error(error)


if __name__ == "__main__":
    raise SystemExit(main())
