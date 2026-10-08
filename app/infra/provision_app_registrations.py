"""Provision the two Entra ID app registrations the web app needs.

WHY TWO APPS
------------
Work IQ is a *delegated* data source: it grounds on what the signed-in user can
see. If the web app called the Foundry agent using its own managed identity, Work
IQ would resolve against an identity that sits in no mailbox and no Teams channel,
and would return nothing. So the browser must sign the user in, and the backend
must exchange that user token for a downstream token **on behalf of** the user.

That requires the standard OBO pair:

  1. SPA (public client)  - signs the user in, requests a token for the BFF's own
                            API scope. No secret; PKCE only.
  2. BFF (confidential)   - exposes api://<app-id>/access_as_user, holds a client
                            secret, and performs the OBO exchange for downstream
                            tokens (Foundry, and Graph if needed).

    Browser --login--> Entra
       | token for api://<bff>/access_as_user
       v
    BFF --OBO exchange--> Entra --> token for Foundry, AS THE USER
       v
    Foundry agent -> Work IQ / Fabric / AI Search, all under the user's identity

USAGE
-----
    pip install azure-identity requests
    # Authenticate Azure CLI separately as an Application Administrator.

    python provision_app_registrations.py --spa-redirect http://localhost:5173
    python provision_app_registrations.py --show
    python provision_app_registrations.py --add-redirect https://<fqdn>
    python provision_app_registrations.py --delete

The BFF client secret is printed once and is never written to disk by this script.

Required environment in all modes: AZURE_TENANT_ID (tenant GUID), INFRA_SPA_NAME
and INFRA_BFF_NAME (distinct, unique app display names). No optional environment
settings. Provisioning requires one or more explicit --spa-redirect URIs.
--add-redirect only updates existing SPA redirects; it never provisions apps or
secrets. --show and --delete take no redirect arguments. --no-secret skips secret
creation on provisioning. HTTPS is required except for explicit HTTP localhost
development redirects. No endpoint or identity is inferred from the CLI session.
"""

from __future__ import annotations

import argparse
import time

if __package__:
    from .portability_config import (
        ConfigurationError, GraphClient, app_names, environment, eq_filter,
        find_app, find_sp, redirect_uri, tenant_grant, tenant_id,
    )
else:
    from portability_config import (
        ConfigurationError, GraphClient, app_names, environment, eq_filter,
        find_app, find_sp, redirect_uri, tenant_grant, tenant_id,
    )

GRAPH_APP_ID = "00000003-0000-0000-c000-000000000000"

SCOPE_NAME = "access_as_user"

# Delegated Graph scopes the BFF needs.
BFF_GRAPH_SCOPES = ["User.Read", "offline_access", "openid", "profile"]

# The Foundry data plane the OBO exchange targets. The scope
# https://ai.azure.com/.default resolves to the Azure Machine Learning Services
# resource - its `user_impersonation` scope.
#
# This scope MUST be pre-registered on the BFF's requiredResourceAccess and
# consented on the BFF's service principal, or the first OBO call fails with
#
#   AADSTS65001: The user or administrator has not consented to use the
#                application ... Send an interactive authorization request
#
# even though the SPA was consented. The tenant-wide grant on the resource is
# what tells Entra "the admin has agreed the BFF may exchange for this on
# behalf of any signed-in user".
AML_APP_ID = "18a66f5f-dbdf-4c17-9dd7-1634712a9cbe"
AML_USER_IMPERSONATION_SCOPE = "1a7925b5-f871-417a-9b8b-303f9f29fa10"


def ensure_sp(g: GraphClient, app_id: str) -> dict:
    sp = find_sp(g, app_id)
    if sp:
        return sp
    sp = g.call("POST", "/servicePrincipals", {"appId": app_id})
    time.sleep(5)
    return sp


# --------------------------------------------------------------------------- #
def ensure_bff(g: GraphClient, name: str) -> dict:
    """Confidential client that exposes the API scope and performs OBO."""
    app = find_app(g, name)
    if app:
        print(f"= {name} ({app['appId']})")
    else:
        app = g.call("POST", "/applications", {
            "displayName": name,
            "description": "The Bank's Capital Markets Client Intelligence BFF. Exchanges the signed-in "
                           "user's token for downstream tokens (On-Behalf-Of) so the "
                           "Foundry agent grounds Work IQ under the user's identity.",
            "signInAudience": "AzureADMyOrg",
            "requiredResourceAccess": [],
        })
        print(f"+ {name} ({app['appId']})")
        time.sleep(10)

    app_id = app["appId"]
    obj_id = app["id"]

    # Identifier URI + the access_as_user delegated scope.
    current = g.call("GET", f"/applications/{obj_id}")
    scopes = current.get("api", {}).get("oauth2PermissionScopes", [])
    have = next((s for s in scopes if s["value"] == SCOPE_NAME), None)

    if not have:
        import uuid

        scopes.append({
            "id": str(uuid.uuid4()),
            "value": SCOPE_NAME,
            "type": "User",
            "isEnabled": True,
            "adminConsentDisplayName": "Access the Bank's Capital Markets Client Intelligence as you",
            "adminConsentDescription": "Allows the app to call the Foundry agent and "
                                       "its grounded data sources on behalf of the "
                                       "signed-in user.",
            "userConsentDisplayName": "Access the Bank's Capital Markets Client Intelligence as you",
            "userConsentDescription": "Allows the app to retrieve your client "
                                      "coverage email, Teams and document context.",
        })
        api = dict(current.get("api", {}))
        api.update({"oauth2PermissionScopes": scopes, "requestedAccessTokenVersion": 2})
        g.call("PATCH", f"/applications/{obj_id}", {
            "identifierUris": sorted(set(current.get("identifierUris", []) + [f"api://{app_id}"])),
            "api": api,
        }, ok=(204,))
        print(f"  + exposed api://{app_id}/{SCOPE_NAME}")
    else:
        print(f"  = api://{app_id}/{SCOPE_NAME} already exposed")

    # Delegated permissions the BFF needs on downstream APIs.
    gsp = find_sp(g, GRAPH_APP_ID)
    if not gsp:
        raise RuntimeError("The Microsoft Graph service principal must exist in the configured tenant.")
    ids = {s["value"]: s["id"] for s in gsp["oauth2PermissionScopes"] if s.get("isEnabled", False)}
    missing = set(BFF_GRAPH_SCOPES) - ids.keys()
    if missing:
        raise RuntimeError(f"Microsoft Graph is missing enabled delegated scopes: {', '.join(sorted(missing))}")
    graph_access = [{"id": ids[s], "type": "Scope"} for s in BFF_GRAPH_SCOPES]

    aml_sp = ensure_sp(g, AML_APP_ID)
    aml_access = [{"id": AML_USER_IMPERSONATION_SCOPE, "type": "Scope"}]

    blocks = current.get("requiredResourceAccess", [])
    for resource_id, access in ((GRAPH_APP_ID, graph_access), (AML_APP_ID, aml_access)):
        block = next((b for b in blocks if b["resourceAppId"] == resource_id), None)
        if block is None:
            blocks.append({"resourceAppId": resource_id, "resourceAccess": access})
        else:
            for permission in access:
                if permission not in block["resourceAccess"]:
                    block["resourceAccess"].append(permission)
    g.call("PATCH", f"/applications/{obj_id}", {
        "requiredResourceAccess": blocks,
        "web": {"implicitGrantSettings": {"enableIdTokenIssuance": False,
                                          "enableAccessTokenIssuance": False}},
    }, ok=(204,))

    sp = ensure_sp(g, app_id)

    # Pre-consent the delegated Graph scopes so users are not prompted.
    grants = g.collection(f"/oauth2PermissionGrants?{eq_filter('clientId', sp['id'])}")
    grant = tenant_grant(grants, gsp["id"])
    if grant:
        merged = " ".join(sorted(set(grant["scope"].split()) | set(BFF_GRAPH_SCOPES)))
        g.call("PATCH", f"/oauth2PermissionGrants/{grant['id']}", {"scope": merged},
               ok=(204,))
    else:
        g.call("POST", "/oauth2PermissionGrants", {
            "clientId": sp["id"], "consentType": "AllPrincipals",
            "resourceId": gsp["id"], "scope": " ".join(BFF_GRAPH_SCOPES),
        })
    print(f"  + delegated Graph scopes consented: {' '.join(BFF_GRAPH_SCOPES)}")

    # Pre-consent user_impersonation on Azure Machine Learning Services. Without
    # this, the OBO exchange for https://ai.azure.com/.default returns
    # AADSTS65001, no matter what the SPA has consented.
    aml_grant = tenant_grant(grants, aml_sp["id"])
    if aml_grant:
        merged = " ".join(sorted(set(aml_grant["scope"].split())
                                 | {"user_impersonation"}))
        g.call("PATCH", f"/oauth2PermissionGrants/{aml_grant['id']}",
               {"scope": merged}, ok=(204,))
    else:
        g.call("POST", "/oauth2PermissionGrants", {
            "clientId": sp["id"], "consentType": "AllPrincipals",
            "resourceId": aml_sp["id"], "scope": "user_impersonation",
        })
    print("  + Azure Machine Learning user_impersonation consented (for OBO)")
    return {"appId": app_id, "objectId": obj_id, "spId": sp["id"]}


def ensure_spa(g: GraphClient, name: str, bff: dict, redirects: list[str]) -> dict:
    """Public client the browser uses. PKCE, no secret."""
    app = find_app(g, name)
    if app:
        print(f"= {name} ({app['appId']})")
        existing = g.call("GET", f"/applications/{app['id']}")
        uris = sorted(set(existing.get("spa", {}).get("redirectUris", []) + redirects))
    else:
        app = g.call("POST", "/applications", {
            "displayName": name,
            "description": "The Bank's Capital Markets Client Intelligence single-page app. Signs the "
                           "user in and calls the BFF.",
            "signInAudience": "AzureADMyOrg",
        })
        print(f"+ {name} ({app['appId']})")
        time.sleep(10)
        uris = sorted(set(redirects))
        existing = app

    scope_id = next(
        s["id"] for s in
        g.call("GET", f"/applications/{bff['objectId']}")["api"]["oauth2PermissionScopes"]
        if s["value"] == SCOPE_NAME
    )

    blocks = existing.get("requiredResourceAccess", [])
    block = next((b for b in blocks if b["resourceAppId"] == bff["appId"]), None)
    permission = {"id": scope_id, "type": "Scope"}
    if block is None:
        blocks.append({"resourceAppId": bff["appId"], "resourceAccess": [permission]})
    elif permission not in block["resourceAccess"]:
        block["resourceAccess"].append(permission)
    g.call("PATCH", f"/applications/{app['id']}", {
        "spa": {"redirectUris": uris},
        "requiredResourceAccess": blocks,
    }, ok=(204,))
    print(f"  + redirect URIs: {', '.join(uris)}")

    sp = ensure_sp(g, app["appId"])

    # Pre-consent the SPA -> BFF scope so the user sees no prompt.
    grants = g.collection(f"/oauth2PermissionGrants?{eq_filter('clientId', sp['id'])}")
    grant = tenant_grant(grants, bff["spId"])
    if grant:
        if SCOPE_NAME not in grant["scope"].split():
            merged = " ".join(sorted(set(grant["scope"].split()) | {SCOPE_NAME}))
            g.call("PATCH", f"/oauth2PermissionGrants/{grant['id']}", {"scope": merged}, ok=(204,))
    else:
        g.call("POST", "/oauth2PermissionGrants", {
            "clientId": sp["id"], "consentType": "AllPrincipals",
            "resourceId": bff["spId"], "scope": SCOPE_NAME,
        })
    print(f"  + consented {name} -> api://{bff['appId']}/{SCOPE_NAME}")

    # Let the BFF accept tokens from the SPA without a second consent prompt.
    cur = g.call("GET", f"/applications/{bff['objectId']}")
    pre = cur.get("api", {}).get("preAuthorizedApplications", [])
    authorized = next((p for p in pre if p["appId"] == app["appId"]), None)
    if authorized is None or scope_id not in authorized.get("delegatedPermissionIds", []):
        if authorized is None:
            pre.append({"appId": app["appId"], "delegatedPermissionIds": [scope_id]})
        else:
            authorized.setdefault("delegatedPermissionIds", []).append(scope_id)
        api = dict(cur["api"])
        api["preAuthorizedApplications"] = pre
        g.call("PATCH", f"/applications/{bff['objectId']}", {"api": api}, ok=(204,))
        print("  + SPA pre-authorized on the BFF API")

    return {"appId": app["appId"], "objectId": app["id"]}


# --------------------------------------------------------------------------- #
def main(argv=None, environ=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--spa-redirect", action="append", default=[],
                    help="SPA redirect URI; repeatable")
    ap.add_argument("--add-redirect", action="append", default=[],
                    help="add a redirect URI to the existing SPA (e.g. the deployed FQDN)")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--show", action="store_true")
    mode.add_argument("--delete", action="store_true")
    ap.add_argument("--no-secret", action="store_true")
    args = ap.parse_args(argv)
    env = environment(environ)
    try:
        tenant = tenant_id(env)
        spa_name, bff_name = app_names(env)
        if args.spa_redirect and args.add_redirect:
            raise ConfigurationError("Use either --spa-redirect or --add-redirect, not both.")
        if (args.show or args.delete) and (args.spa_redirect or args.add_redirect or args.no_secret):
            raise ConfigurationError("--show and --delete cannot be combined with redirects or --no-secret.")
        if args.add_redirect and args.no_secret:
            raise ConfigurationError("--add-redirect never creates a secret; omit --no-secret.")
        redirects = [
            redirect_uri(value, "--spa-redirect" if args.spa_redirect else "--add-redirect")
            for value in args.spa_redirect + args.add_redirect
        ]
        if not args.show and not args.delete and not redirects:
            raise ConfigurationError("Explicit --spa-redirect URI(s) are required to provision; no localhost default.")
    except ConfigurationError as exc:
        ap.error(str(exc))

    g = GraphClient(tenant)

    if args.delete:
        apps = [(name, find_app(g, name)) for name in (spa_name, bff_name)]
        for n, a in apps:
            if a:
                g.call("DELETE", f"/applications/{a['id']}", ok=(204,))
                print(f"deleted {n}")
        return

    if args.show:
        for n in (spa_name, bff_name):
            a = find_app(g, n)
            print(f"{n}: {a['appId'] if a else 'NOT CREATED'}")
            if a and n == spa_name:
                cur = g.call("GET", f"/applications/{a['id']}")
                print(f"   redirects: {cur.get('spa', {}).get('redirectUris', [])}")
        return

    if args.add_redirect:
        app = find_app(g, spa_name)
        if not app:
            raise RuntimeError(f"{spa_name} not found; provision it before adding redirect URIs.")
        current = g.call("GET", f"/applications/{app['id']}")
        uris = sorted(set(current.get("spa", {}).get("redirectUris", []) + redirects))
        g.call("PATCH", f"/applications/{app['id']}", {"spa": {"redirectUris": uris}}, ok=(204,))
        print(f"+ redirect URIs: {', '.join(uris)}")
        return

    print("== BFF (confidential client, performs OBO) ==")
    bff = ensure_bff(g, bff_name)
    print("\n== SPA (public client, PKCE) ==")
    spa = ensure_spa(g, spa_name, bff, redirects)

    secret = None
    if not args.no_secret:
        cred = g.call("POST", f"/applications/{bff['objectId']}/addPassword", {
            "passwordCredential": {"displayName": f"bff-{int(time.time())}"}
        })
        secret = cred["secretText"]

    print("\n" + "=" * 74)
    print("Configuration. The BFF secret is shown ONCE.")
    print("=" * 74)
    print("# --- BFF (Container App env vars / .env) ---")
    print(f'AAD_TENANT_ID   = "{tenant}"')
    print(f'AAD_CLIENT_ID   = "{bff["appId"]}"')
    if secret:
        print(f'AAD_CLIENT_SECRET = "{secret}"')
    print(f'AAD_API_SCOPE   = "api://{bff["appId"]}/{SCOPE_NAME}"')
    print()
    print("# --- SPA (src/web/.env) ---")
    print(f'VITE_AAD_TENANT_ID = "{tenant}"')
    print(f'VITE_AAD_CLIENT_ID = "{spa["appId"]}"')
    print(f'VITE_API_SCOPE     = "api://{bff["appId"]}/{SCOPE_NAME}"')
    print()
    print("After deploying, add the Container App FQDN as a redirect URI:")
    print("    python provision_app_registrations.py --add-redirect https://<web-fqdn>")
    print("\nTear down when the demo is over:")
    print("    python provision_app_registrations.py --delete")


if __name__ == "__main__":
    main()
