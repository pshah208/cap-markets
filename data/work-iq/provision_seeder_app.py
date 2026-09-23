"""Provision the Entra ID app registration used by seed_work_iq.py.

Creates the application, its service principal, grants the required Microsoft
Graph **application** permissions (admin consent applied directly via
appRoleAssignments), and issues a client secret.

Idempotent: re-running reuses the existing app and only adds missing grants.
Requires the signed-in `az login` account to be Global Administrator (or
Privileged Role Administrator + Application Administrator).

    pip install azure-identity requests
    az login
    python provision_seeder_app.py
    python provision_seeder_app.py --show          # no secret rotation
    python provision_seeder_app.py --delete        # tear down

The client secret is printed once and never stored by this script.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from typing import Any

import requests

GRAPH = "https://graph.microsoft.com/v1.0"
GRAPH_APP_ID = "00000003-0000-0000-c000-000000000000"
APP_NAME = "workiq-cmintel-seeder"

# Application (app-only) permissions the seeder needs.
REQUIRED = [
    ("User.Read.All", "resolve persona aliases to user ids"),
    ("User.ReadWrite.All", "--map-users renames"),
    ("Mail.ReadWrite", "import messages into mailboxes with original sender/date"),
    ("Group.ReadWrite.All", "create the team's group"),
    ("Team.Create", "create the team"),
    ("TeamMember.ReadWrite.All", "add the 13 other personas to the team"),
    ("Channel.Create", "create channels"),
    ("Teamwork.Migrate.All", "post channel messages (PROTECTED API - see below)"),
    ("ChannelMessage.Read.All", "verify seeded channel messages"),
    ("Files.ReadWrite.All", "upload meeting notes"),
    ("Sites.ReadWrite.All", "upload to the team's SharePoint library"),
]

PROTECTED_NOTE = (
    "Channel message posting: 'ChannelMessage.Send' does NOT exist as an\n"
    "application permission - it is delegated-only. App-only posting instead\n"
    "requires 'Teamwork.Migrate.All', which is a Microsoft protected API and only\n"
    "works against a team created in *migration mode*. For a demo the simpler path\n"
    "is delegated device-code auth:\n"
    "    python seed_work_iq.py --only teams --messages-only --auth device\n"
    "Every post is prefixed with the original author, so the narrative survives."
)


def token() -> str:
    out = subprocess.run(
        ["az", "account", "get-access-token", "--resource",
         "https://graph.microsoft.com", "--query", "accessToken", "-o", "tsv"],
        capture_output=True, text=True, shell=True,
    )
    if out.returncode != 0:
        sys.exit(f"az token failed - run `az login`: {out.stderr}")
    return out.stdout.strip()


class G:
    def __init__(self) -> None:
        self.h = {"Authorization": f"Bearer {token()}",
                  "Content-Type": "application/json"}

    def call(self, method: str, path: str, body: Any = None,
             ok: tuple[int, ...] = (200, 201, 204)) -> Any:
        r = requests.request(method, f"{GRAPH}{path}", headers=self.h,
                             json=body, timeout=90)
        if r.status_code not in ok:
            raise RuntimeError(f"{method} {path} -> {r.status_code}: {r.text[:700]}")
        return r.json() if r.content and "json" in r.headers.get("Content-Type", "") else None


def find_app(g: G) -> dict | None:
    r = g.call("GET", f"/applications?$filter=displayName eq '{APP_NAME}'")
    return (r.get("value") or [None])[0]


def find_sp(g: G, app_id: str) -> dict | None:
    r = g.call("GET", f"/servicePrincipals?$filter=appId eq '{app_id}'")
    return (r.get("value") or [None])[0]


def graph_sp(g: G) -> dict:
    r = g.call("GET", f"/servicePrincipals?$filter=appId eq '{GRAPH_APP_ID}'"
                      "&$select=id,appId,appRoles,oauth2PermissionScopes")
    return r["value"][0]


def enable_device_code(g: G, app: dict, sp: dict, gsp: dict) -> None:
    """Make the app usable for delegated device-code auth.

    Channel message posting cannot be done app-only (Graph allows it only in
    migration mode), so the Teams step falls back to delegated auth. That needs
    the app marked as a public client and the delegated scope pre-consented.
    """
    scopes = ["ChannelMessage.Send", "Group.ReadWrite.All", "User.Read"]
    ids = {s["value"]: s["id"] for s in gsp["oauth2PermissionScopes"]}
    delegated = [{"id": ids[s], "type": "Scope"} for s in scopes if s in ids]

    existing = app.get("requiredResourceAccess", [])
    graph_block = next((b for b in existing if b["resourceAppId"] == GRAPH_APP_ID), None)
    have = {a["id"] for a in (graph_block or {}).get("resourceAccess", [])}
    merged = (graph_block or {}).get("resourceAccess", []) + [
        d for d in delegated if d["id"] not in have
    ]

    g.call("PATCH", f"/applications/{app['id']}", {
        "isFallbackPublicClient": True,
        "requiredResourceAccess": [
            {"resourceAppId": GRAPH_APP_ID, "resourceAccess": merged}
        ],
    }, ok=(204,))
    print("  + public client enabled (device code flow)")

    grants = g.call("GET", f"/oauth2PermissionGrants?$filter=clientId eq '{sp['id']}'")
    grant = next((x for x in grants["value"] if x["resourceId"] == gsp["id"]), None)
    want = " ".join(scopes)
    if grant:
        merged_scope = " ".join(sorted(set(grant["scope"].split()) | set(scopes)))
        g.call("PATCH", f"/oauth2PermissionGrants/{grant['id']}",
               {"scope": merged_scope}, ok=(204,))
    else:
        g.call("POST", "/oauth2PermissionGrants", {
            "clientId": sp["id"], "consentType": "AllPrincipals",
            "resourceId": gsp["id"], "scope": want,
        })
    print(f"  + delegated scopes consented: {want}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--show", action="store_true", help="report state, no changes")
    ap.add_argument("--no-secret", action="store_true",
                    help="grant permissions but do not issue a new client secret")
    ap.add_argument("--enable-device-code", action="store_true",
                    help="also configure delegated auth for the Teams messages step")
    ap.add_argument("--delete", action="store_true")
    args = ap.parse_args()

    g = G()
    gsp = graph_sp(g)
    roles = {r["value"]: r["id"] for r in gsp["appRoles"] if "Application" in r["allowedMemberTypes"]}

    app = find_app(g)

    if args.delete:
        if not app:
            print("nothing to delete")
            return
        g.call("DELETE", f"/applications/{app['id']}", ok=(204,))
        print(f"deleted {APP_NAME}")
        return

    # ---- application ----
    resource_access = [
        {"id": roles[v], "type": "Role"} for v, _ in REQUIRED if v in roles
    ]
    missing_roles = [v for v, _ in REQUIRED if v not in roles]

    if app:
        print(f"= application {APP_NAME} ({app['appId']})")
        # Idempotently repair an app created before the public-client fix. Without
        # this an existing app keeps failing device-code auth with AADSTS7000218.
        if not app.get("isFallbackPublicClient"):
            g.call("PATCH", f"/applications/{app['id']}", {
                "isFallbackPublicClient": True,
                "publicClient": {
                    "redirectUris": ["https://login.microsoftonline.com/common/oauth2/nativeclient"]
                },
            })
            print("  + enabled public-client flows (required for device-code auth)")
    elif args.show:
        print(f"application {APP_NAME}: NOT CREATED")
        return
    else:
        app = g.call("POST", "/applications", {
            "displayName": APP_NAME,
            "description": "Seeds synthetic Work IQ demo content (Capital Markets "
                           "Client Intelligence). Demo tenant only.",
            "signInAudience": "AzureADMyOrg",
            # Teams channel messages cannot be posted with application permissions
            # (ChannelMessage.Send is delegated-only), so the same app has to
            # support the device-code flow. Device code is a PUBLIC client flow:
            # without isFallbackPublicClient the token request is rejected with
            # AADSTS7000218 "must contain client_assertion or client_secret",
            # which reads like a secret problem but is actually a client-type one.
            "isFallbackPublicClient": True,
            "publicClient": {
                "redirectUris": ["https://login.microsoftonline.com/common/oauth2/nativeclient"]
            },
            "requiredResourceAccess": [{
                "resourceAppId": GRAPH_APP_ID,
                "resourceAccess": resource_access,
            }],
        })
        print(f"+ application {APP_NAME} ({app['appId']})")
        time.sleep(10)

    # ---- service principal ----
    sp = find_sp(g, app["appId"])
    if sp:
        print(f"= service principal ({sp['id']})")
    elif args.show:
        print("service principal: NOT CREATED")
        return
    else:
        sp = g.call("POST", "/servicePrincipals", {"appId": app["appId"]})
        print(f"+ service principal ({sp['id']})")
        time.sleep(10)

    # ---- app role assignments == admin consent ----
    existing = {
        a["appRoleId"]
        for a in g.call("GET", f"/servicePrincipals/{sp['id']}/appRoleAssignments")["value"]
    }
    for value, why in REQUIRED:
        rid = roles.get(value)
        if not rid:
            print(f"  !! {value:<22} no application role of that name on Microsoft Graph")
            continue
        if rid in existing:
            print(f"  = {value:<22} already granted  ({why})")
            continue
        if args.show:
            print(f"  ? {value:<22} MISSING          ({why})")
            continue
        try:
            g.call("POST", f"/servicePrincipals/{sp['id']}/appRoleAssignments", {
                "principalId": sp["id"], "resourceId": gsp["id"], "appRoleId": rid,
            })
            print(f"  + {value:<22} granted          ({why})")
        except RuntimeError as exc:
            print(f"  !! {value:<22} FAILED: {exc}")

    if args.show:
        return

    if args.enable_device_code:
        app = g.call("GET", f"/applications/{app['id']}")
        enable_device_code(g, app, sp, gsp)

    if args.no_secret:
        print("\npermissions up to date (no new secret issued)")
        return

    # ---- client secret ----
    cred = g.call("POST", f"/applications/{app['id']}/addPassword", {
        "passwordCredential": {"displayName": f"seeder-{int(time.time())}"}
    })

    tenant = g.call("GET", "/organization?$select=id")["value"][0]["id"]

    print("\n" + "=" * 72)
    print("Set these, then run seed_work_iq.py. The secret is shown ONCE.")
    print("=" * 72)
    print(f'$env:WORKIQ_TENANT_ID     = "{tenant}"')
    print(f'$env:WORKIQ_CLIENT_ID     = "{app["appId"]}"')
    print(f'$env:WORKIQ_CLIENT_SECRET = "{cred["secretText"]}"')
    print("\n" + PROTECTED_NOTE)
    if missing_roles:
        print(f"\nNot available as application roles: {', '.join(missing_roles)}")
    print("\nWhen the demo is finished, tear the app down:")
    print("    python provision_seeder_app.py --delete")


if __name__ == "__main__":
    main()
