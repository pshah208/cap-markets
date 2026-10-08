"""Merge read-only Microsoft Graph delegated permissions and admin consent.

Requires WORKIQ_TENANT_ID and WORKIQ_CONNECTOR_CLIENT_ID (application UUIDs,
not display names). Azure CLI must already be signed in to the specified tenant.

    python configure_workiq_connector.py            # read-only plan
    python configure_workiq_connector.py --show     # read-only, even with --apply
    python configure_workiq_connector.py --apply    # merge permissions and consent

Delegated permissions preserve the signed-in user's access boundaries. Existing
permissions and grants, including those on the Work IQ resource, are preserved.
"""

from __future__ import annotations

import argparse

from workiq_admin_config import (
    GRAPH_APP_ID,
    GraphClient,
    configure_delegated_permissions,
    find_application,
    find_service_principal,
    load_config,
)

REQUIRED = [
    ("User.Read", "sign the user in and read their own profile"),
    ("offline_access", "refresh tokens"),
    ("Mail.Read", "read the signed-in user's mail"),
    ("Files.Read.All", "read files the user can access"),
    ("Sites.Read.All", "read SharePoint sites the user can access"),
    ("ChannelMessage.Read.All", "read Teams channel messages the user can access"),
    ("Chat.Read", "read the user's Teams chats"),
    ("Calendars.Read", "read the user's calendar"),
    ("People.Read", "resolve colleagues named in the corpus"),
    ("Group.Read.All", "resolve team membership"),
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--show", action="store_true", help="read-only, overrides --apply")
    args = parser.parse_args(argv)
    config = load_config("WORKIQ_CONNECTOR_CLIENT_ID")
    g = GraphClient(config["WORKIQ_TENANT_ID"])
    app = find_application(g, config["WORKIQ_CONNECTOR_CLIENT_ID"])
    resource = find_service_principal(g, GRAPH_APP_ID)
    print(f"Application: {app.get('displayName', '')} ({app['appId']})")
    configure_delegated_permissions(
        g, app, resource, [name for name, _ in REQUIRED], apply=args.apply and not args.show,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
