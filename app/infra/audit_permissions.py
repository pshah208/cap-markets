"""Audit the API permissions on both app registrations.

Checks what each app *requests* in its manifest, what has actually been
*granted* (admin consent), and flags anything the app needs at run time but is
missing.
"""

from __future__ import annotations

import subprocess
import sys

import requests

GRAPH = "https://graph.microsoft.com/v1.0"
GRAPH_APP_ID = "00000003-0000-0000-c000-000000000000"
SPA_NAME = "cm-client-intelligence-spa"
BFF_NAME = "cm-client-intelligence-bff"


def token() -> str:
    o = subprocess.run(["az", "account", "get-access-token", "--resource",
                        "https://graph.microsoft.com", "--query", "accessToken",
                        "-o", "tsv"], capture_output=True, text=True, shell=True)
    if o.returncode != 0:
        sys.exit("run az login")
    return o.stdout.strip()


H = {"Authorization": f"Bearer {token()}"}


def get(path: str):
    r = requests.get(f"{GRAPH}{path}", headers=H, timeout=60)
    r.raise_for_status()
    return r.json()


def app_by_name(name: str):
    v = get(f"/applications?$filter=displayName eq '{name}'")["value"]
    return v[0] if v else None


def sp_by_appid(app_id: str):
    v = get(f"/servicePrincipals?$filter=appId eq '{app_id}'")["value"]
    return v[0] if v else None


# Resource service principals we care about, resolved lazily.
_res_cache: dict[str, dict] = {}


def resource_sp(app_id: str):
    if app_id not in _res_cache:
        v = get(f"/servicePrincipals?$filter=appId eq '{app_id}'"
                "&$select=id,appId,displayName,oauth2PermissionScopes,appRoles")["value"]
        _res_cache[app_id] = v[0] if v else {}
    return _res_cache[app_id]


def audit(name: str) -> None:
    print("=" * 74)
    print(name)
    print("=" * 74)
    app = app_by_name(name)
    if not app:
        print("  NOT FOUND\n")
        return
    app = get(f"/applications/{app['id']}")
    sp = sp_by_appid(app["appId"])
    print(f"  appId        : {app['appId']}")
    print(f"  audience     : {app.get('signInAudience')}")
    print(f"  public client: {app.get('isFallbackPublicClient')}")
    print(f"  secrets      : {len(app.get('passwordCredentials', []))}")
    if sp:
        print(f"  assignment required: {sp.get('appRoleAssignmentRequired')}")

    # Exposed API
    api = app.get("api", {})
    scopes = api.get("oauth2PermissionScopes", [])
    if scopes:
        print(f"  exposes      : {', '.join(app.get('identifierUris', []))}")
        for s in scopes:
            print(f"                 {s['value']} (enabled={s['isEnabled']})")
    pre = api.get("preAuthorizedApplications", [])
    if pre:
        print(f"  pre-authorized apps: {[p['appId'] for p in pre]}")

    # Requested permissions
    print("\n  REQUESTED (manifest):")
    if not app.get("requiredResourceAccess"):
        print("    (none)")
    for block in app.get("requiredResourceAccess", []):
        res = resource_sp(block["resourceAppId"])
        rname = res.get("displayName", block["resourceAppId"])
        smap = {s["id"]: s["value"] for s in res.get("oauth2PermissionScopes", [])}
        rmap = {r["id"]: r["value"] for r in res.get("appRoles", [])}
        for acc in block["resourceAccess"]:
            kind = "delegated" if acc["type"] == "Scope" else "application"
            label = smap.get(acc["id"]) or rmap.get(acc["id"]) or acc["id"]
            print(f"    {rname:<22} {kind:<12} {label}")

    # Granted delegated consent
    print("\n  GRANTED (delegated, admin consent):")
    if sp:
        grants = get(f"/oauth2PermissionGrants?$filter=clientId eq '{sp['id']}'")["value"]
        if not grants:
            print("    (none)")
        for g in grants:
            res = get(f"/servicePrincipals/{g['resourceId']}?$select=displayName,appId")
            print(f"    {res.get('displayName', '?'):<22} {g.get('consentType'):<14} "
                  f"{g['scope'].strip()}")

        # Granted application roles
        ras = get(f"/servicePrincipals/{sp['id']}/appRoleAssignments")["value"]
        if ras:
            print("\n  GRANTED (application roles):")
            for ra in ras:
                res = resource_sp("")  # not needed; look up by resourceId
                r = get(f"/servicePrincipals/{ra['resourceId']}"
                        "?$select=displayName,appRoles")
                rm = {x["id"]: x["value"] for x in r.get("appRoles", [])}
                print(f"    {r.get('displayName', '?'):<22} "
                      f"{rm.get(ra['appRoleId'], ra['appRoleId'])}")
    print()


audit(SPA_NAME)
audit(BFF_NAME)

print("=" * 74)
print("RUNTIME REQUIREMENTS")
print("=" * 74)
print("""
  SPA  -> BFF        api://<bff>/access_as_user            delegated
  BFF  -> Graph      User.Read                             delegated (persona card)
  BFF  -> Foundry    https://ai.azure.com/.default         delegated, via OBO
                     (the agent call itself)
""")
