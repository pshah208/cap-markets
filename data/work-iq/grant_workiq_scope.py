"""Register and consent the Work IQ delegated permission on an exact connector.

Requires WORKIQ_TENANT_ID, WORKIQ_CONNECTOR_CLIENT_ID and WORKIQ_RESOURCE_APP_ID.
All are explicit UUIDs; no tenant, client, or resource identity is inferred.

    python grant_workiq_scope.py            # read-only plan
    python grant_workiq_scope.py --show     # read-only, even with --apply
    python grant_workiq_scope.py --apply    # merge permissions and admin consent

WorkIQAgent.Ask belongs to the Work IQ resource, not to Microsoft Graph.
Existing permissions and tenant-wide consent scopes are preserved.
"""

from __future__ import annotations

import argparse

from workiq_admin_config import (
    GraphClient,
    configure_delegated_permissions,
    find_application,
    find_service_principal,
    load_config,
)

WANTED = ["WorkIQAgent.Ask"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--show", action="store_true", help="read-only, overrides --apply")
    args = parser.parse_args(argv)
    config = load_config("WORKIQ_CONNECTOR_CLIENT_ID", "WORKIQ_RESOURCE_APP_ID")
    g = GraphClient(config["WORKIQ_TENANT_ID"])
    app = find_application(g, config["WORKIQ_CONNECTOR_CLIENT_ID"])
    resource = find_service_principal(g, config["WORKIQ_RESOURCE_APP_ID"])
    print(f"Connector: {app.get('displayName', '')} ({app['appId']})")
    print(f"Resource: {resource.get('displayName', '')} ({resource['appId']})")
    configure_delegated_permissions(g, app, resource, WANTED, apply=args.apply and not args.show)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
