"""Provision the Entra application used by the Work IQ seeder.

Requires WORKIQ_TENANT_ID (tenant UUID) and WORKIQ_SEEDER_APP_NAME (exact display
name). Duplicate names fail closed, including on deletion. Uses the standard
library and an existing Azure CLI sign-in explicitly bound to that tenant.

    python provision_seeder_app.py                     # provision and issue secret
    python provision_seeder_app.py --no-secret          # provision without a secret
    python provision_seeder_app.py --show               # read-only state
    python provision_seeder_app.py --delete             # delete exact named app
    python provision_seeder_app.py --enable-device-code --no-secret

Public-client flows are enabled only with --enable-device-code. Device-code auth
does not need a redirect; optional public-client redirects must be passed using
repeatable --redirect-uri. The secret is printed once and never saved to disk.
Granting these permissions requires appropriate Entra administrative privileges.
"""

from __future__ import annotations

import argparse

from workiq_admin_config import (
    GRAPH_APP_ID,
    GraphClient,
    find_service_principal,
    find_tenant_grant,
    find_unique,
    load_config,
    merge_resource_access,
    odata_literal,
    permission_entries,
    validate_redirect_uris,
    write_tenant_grant,
)

REQUIRED = [
    ("User.Read.All", "resolve persona aliases to user ids"),
    ("User.ReadWrite.All", "--map-users renames"),
    ("Mail.ReadWrite", "import messages into mailboxes with original sender/date"),
    ("Group.ReadWrite.All", "create the team's group"),
    ("Team.Create", "create the team"),
    ("TeamMember.ReadWrite.All", "add personas to the team"),
    ("Channel.Create", "create channels"),
    ("Teamwork.Migrate.All", "post messages in migration-mode teams"),
    ("ChannelMessage.Read.All", "verify seeded channel messages"),
    ("Files.ReadWrite.All", "upload meeting notes"),
    ("Sites.ReadWrite.All", "upload to the team's SharePoint library"),
]
DEVICE_SCOPES = [
    "ChannelMessage.Send", "Group.ReadWrite.All", "Files.ReadWrite.All", "User.Read.All",
]

PROTECTED_NOTE = (
    "ChannelMessage.Send is delegated-only. App-only channel message import uses\n"
    "Teamwork.Migrate.All and requires a team created in migration mode.\n"
    "For delegated message posting, provision with --enable-device-code, then use:\n"
    "    python seed_work_iq.py --only teams --messages-only --auth device"
)


def find_app(g: GraphClient, name: str) -> dict | None:
    return find_unique(g, "/applications", f"displayName eq {odata_literal(name)}",
                       f"seeder application named {name!r}", required=False)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--show", action="store_true", help="report state, no changes")
    modes.add_argument("--delete", action="store_true", help="delete the exact named application")
    parser.add_argument("--no-secret", action="store_true", help="do not issue a new client secret")
    parser.add_argument("--enable-device-code", action="store_true", help="enable and consent delegated Teams auth")
    parser.add_argument("--redirect-uri", action="append", default=[], help="explicit public-client redirect; repeatable")
    args = parser.parse_args(argv)
    config = load_config("WORKIQ_SEEDER_APP_NAME")
    if args.redirect_uri and not args.enable_device_code:
        parser.error("--redirect-uri requires --enable-device-code")
    redirects = validate_redirect_uris(args.redirect_uri)
    g = GraphClient(config["WORKIQ_TENANT_ID"])
    name = config["WORKIQ_SEEDER_APP_NAME"]
    app = find_app(g, name)

    if args.delete:
        if app:
            g.call("DELETE", f"/applications/{app['id']}")
            print(f"Deleted {name} ({app['appId']})")
        else:
            print("Nothing to delete.")
        return 0
    if not app and args.show:
        print(f"Application {name}: NOT CREATED")
        return 0

    resource = find_service_principal(g, GRAPH_APP_ID)
    roles = permission_entries(resource, [value for value, _ in REQUIRED], application=True)
    delegated = permission_entries(resource, DEVICE_SCOPES) if args.enable_device_code else []
    merged = merge_resource_access(app or {}, GRAPH_APP_ID, roles + delegated)
    sp = find_service_principal(g, app["appId"], required=False) if app else None
    assignments = g.collection(f"/servicePrincipals/{sp['id']}/appRoleAssignments") if sp else []
    existing_roles = {a["appRoleId"] for a in assignments if a["resourceId"] == resource["id"]}
    grant = find_tenant_grant(g, sp["id"], resource["id"]) if sp and args.enable_device_code else None
    if grant and grant.get("consentType") != "AllPrincipals":
        raise RuntimeError("Expected an AllPrincipals consent grant; no changes made")

    print(f"Application: {name} ({app['appId'] if app else 'NOT CREATED'})")
    print(f"Service principal: {sp['id'] if sp else 'NOT CREATED'}")
    for (value, why), role in zip(REQUIRED, roles):
        print(f"  {'=' if role['id'] in existing_roles else '+'} {value}: {why}")
    if args.enable_device_code:
        print(f"Public-client enabled: {bool(app and app.get('isFallbackPublicClient'))}")
        print(f"Delegated scopes requested: {', '.join(DEVICE_SCOPES)}")
    if args.show:
        print("Read-only: no permissions, public-client flags, redirects, or secrets changed.")
        return 0

    import time

    updates = {}
    if merged != ((app or {}).get("requiredResourceAccess") or []):
        updates["requiredResourceAccess"] = merged
    if args.enable_device_code:
        if not app or not app.get("isFallbackPublicClient"):
            updates["isFallbackPublicClient"] = True
        if redirects:
            public = (app or {}).get("publicClient") or {}
            current = list(public.get("redirectUris") or [])
            combined = current + [uri for uri in redirects if uri not in current]
            if combined != current:
                updates["publicClient"] = {**public, "redirectUris": combined}

    if not app:
        app = g.call("POST", "/applications", {
            "displayName": name,
            "description": "Seeds synthetic Work IQ demo content. Demo tenant only.",
            "signInAudience": "AzureADMyOrg",
            **updates,
        })
        time.sleep(10)
    elif updates:
        g.call("PATCH", f"/applications/{app['id']}", updates)
    if not sp:
        sp = g.call("POST", "/servicePrincipals", {"appId": app["appId"]})
        time.sleep(10)
    for role in roles:
        if role["id"] not in existing_roles:
            g.call("POST", f"/servicePrincipals/{sp['id']}/appRoleAssignments", {
                "principalId": sp["id"], "resourceId": resource["id"], "appRoleId": role["id"],
            })
    if args.enable_device_code:
        write_tenant_grant(g, sp["id"], resource["id"], DEVICE_SCOPES, grant)
    if args.no_secret:
        print("Permissions up to date (no new secret issued).")
        return 0

    credential = g.call("POST", f"/applications/{app['id']}/addPassword", {
        "passwordCredential": {"displayName": f"seeder-{int(time.time())}"},
    })
    print("\nSet these before running the seeder. The secret is shown ONCE, not stored.")
    print(f'$env:WORKIQ_TENANT_ID     = "{config["WORKIQ_TENANT_ID"]}"')
    print(f'$env:WORKIQ_CLIENT_ID     = "{app["appId"]}"')
    print(f'$env:WORKIQ_CLIENT_SECRET = "{credential["secretText"]}"')
    print("\n" + PROTECTED_NOTE)
    print("\nWhen finished: python provision_seeder_app.py --delete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
