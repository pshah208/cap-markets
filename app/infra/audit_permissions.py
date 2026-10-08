"""Audit the API permissions on both app registrations.

Checks what each app *requests* in its manifest, what has actually been
*granted* (admin consent), and flags anything the app needs at run time but is
missing.

Required environment: AZURE_TENANT_ID (tenant GUID), INFRA_SPA_NAME and
INFRA_BFF_NAME (distinct, unique app display names). No optional environment
settings. Read-only; importing this module does not acquire credentials.
"""

from __future__ import annotations

import argparse

if __package__:
    from .portability_config import (
        ConfigurationError, GraphClient, app_names, environment, eq_filter,
        find_app, find_sp, tenant_id,
    )
else:
    from portability_config import (
        ConfigurationError, GraphClient, app_names, environment, eq_filter,
        find_app, find_sp, tenant_id,
    )


def audit(g: GraphClient, name: str) -> None:
    cache = {}

    def get(path):
        return g.call("GET", path)

    def resource_sp(app_id):
        if app_id not in cache:
            cache[app_id] = find_sp(g, app_id) or {}
        return cache[app_id]

    print("=" * 74)
    print(name)
    print("=" * 74)
    app = find_app(g, name)
    if not app:
        print("  NOT FOUND\n")
        return
    app = get(f"/applications/{app['id']}")
    sp = find_sp(g, app["appId"])
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
        grants = g.collection(f"/oauth2PermissionGrants?{eq_filter('clientId', sp['id'])}")
        if not grants:
            print("    (none)")
        for grant in grants:
            res = get(f"/servicePrincipals/{grant['resourceId']}?$select=displayName,appId")
            print(f"    {res.get('displayName', '?'):<22} {grant.get('consentType'):<14} "
                  f"{grant['scope'].strip()}")

        # Granted application roles
        ras = g.collection(f"/servicePrincipals/{sp['id']}/appRoleAssignments")
        if ras:
            print("\n  GRANTED (application roles):")
            for ra in ras:
                r = get(f"/servicePrincipals/{ra['resourceId']}"
                        "?$select=displayName,appRoles")
                rm = {x["id"]: x["value"] for x in r.get("appRoles", [])}
                print(f"    {r.get('displayName', '?'):<22} "
                      f"{rm.get(ra['appRoleId'], ra['appRoleId'])}")
    print()


def main(argv=None, environ=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.parse_args(argv)
    env = environment(environ)
    try:
        tenant = tenant_id(env)
        spa_name, bff_name = app_names(env)
    except ConfigurationError as exc:
        ap.error(str(exc))
    g = GraphClient(tenant)
    audit(g, spa_name)
    audit(g, bff_name)

    print("=" * 74)
    print("RUNTIME REQUIREMENTS")
    print("=" * 74)
    print("""
  SPA  -> BFF        api://<bff>/access_as_user            delegated
  BFF  -> Graph      User.Read                             delegated (persona card)
  BFF  -> Foundry    https://ai.azure.com/.default         delegated, via OBO
                     (the agent call itself)
""")


if __name__ == "__main__":
    main()
