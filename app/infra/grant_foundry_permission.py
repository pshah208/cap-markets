"""Grant the BFF delegated access to the Foundry data plane (https://ai.azure.com).

WHY THIS IS NEEDED
------------------
The BFF calls the agent On-Behalf-Of the signed-in user, exchanging the user's
token for one scoped to `https://ai.azure.com`. For that exchange to succeed the
BFF app registration must hold a *delegated* permission on that resource, and the
resource's service principal must exist in the tenant.

Neither was true after the initial provisioning - the BFF only had Microsoft
Graph permissions - so the agent call would have failed with AADSTS65001 at run
time, after the user had already signed in.

    python grant_foundry_permission.py
    python grant_foundry_permission.py --show

Required environment: AZURE_TENANT_ID (tenant GUID), INFRA_BFF_NAME (unique app
display name). No optional environment settings or implicit identity defaults.
"""

from __future__ import annotations

import argparse
import sys
import time

if __package__:
    from .portability_config import (
        ConfigurationError, GraphClient, app_name, environment, eq_filter,
        find_app, find_sp, tenant_grant, tenant_id,
    )
else:
    from portability_config import (
        ConfigurationError, GraphClient, app_name, environment, eq_filter,
        find_app, find_sp, tenant_grant, tenant_id,
    )

# The audience the Foundry Responses API demands is https://ai.azure.com. That URI
# is owned by "Azure Machine Learning Services" (18a66f5f-...), NOT by the
# similarly-named "Azure Machine Learning" (0736f41a-...), which exposes no scopes
# at all. This is the first-party resource app ID for that audience.
CANDIDATES = [
    ("Azure Machine Learning Services", "18a66f5f-dbdf-4c17-9dd7-1634712a9cbe"),
]
WANT_SCOPE = "user_impersonation"


def main(argv=None, environ=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--show", action="store_true")
    args = ap.parse_args(argv)
    env = environment(environ)
    try:
        tenant = tenant_id(env)
        bff_name = app_name(env, "INFRA_BFF_NAME")
    except ConfigurationError as exc:
        ap.error(str(exc))

    g = GraphClient(tenant)
    call = g.call
    app = find_app(g, bff_name)
    if not app:
        sys.exit(f"{bff_name} not found.")
    app = call("GET", f"/applications/{app['id']}")
    bff_sp = find_sp(g, app["appId"])
    if not bff_sp:
        sys.exit("Service principal not found for the configured BFF.")

    # Locate (or provision) the resource service principal.
    resource = None
    for label, app_id in CANDIDATES:
        sp = find_sp(g, app_id)
        if sp:
            print(f"= resource SP present: {sp['displayName']} ({app_id})")
            resource = sp
            break
        if args.show:
            print(f"? resource SP missing: {label} ({app_id})")
            continue
        try:
            sp = call("POST", "/servicePrincipals", {"appId": app_id})
            print(f"+ provisioned resource SP: {label} ({app_id})")
            time.sleep(10)
            resource = find_sp(g, app_id)
            break
        except RuntimeError as exc:
            print(f"  could not provision {label}: {str(exc)[:160]}")

    if not resource:
        sys.exit("No suitable resource service principal found or created.")

    scopes = {s["value"]: s["id"] for s in resource.get("oauth2PermissionScopes", [])
              if s.get("isEnabled", False)}
    if WANT_SCOPE not in scopes:
        print(f"  !! '{WANT_SCOPE}' not exposed by {resource['displayName']}. "
              f"Available: {', '.join(sorted(scopes)) or '(none)'}")
        sys.exit(1)
    scope_id = scopes[WANT_SCOPE]

    if args.show:
        blocks = app.get("requiredResourceAccess", [])
        has = any(b["resourceAppId"] == resource["appId"] and
                  any(a["id"] == scope_id and a["type"] == "Scope" for a in b["resourceAccess"])
                  for b in blocks)
        print(f"  BFF requests it in manifest : {has}")
        grants = g.collection(f"/oauth2PermissionGrants?{eq_filter('clientId', bff_sp['id'])}")
        grant = tenant_grant(grants, resource["id"])
        print(f"  BFF consented               : {bool(grant) and WANT_SCOPE in grant['scope'].split()}"
              + (f" ({grant['scope'].strip()})" if grant else ""))
        return

    # 1. add to the manifest
    blocks = app.get("requiredResourceAccess", [])
    block = next((b for b in blocks if b["resourceAppId"] == resource["appId"]), None)
    if block:
        if not any(a["id"] == scope_id and a["type"] == "Scope" for a in block["resourceAccess"]):
            block["resourceAccess"].append({"id": scope_id, "type": "Scope"})
    else:
        blocks.append({"resourceAppId": resource["appId"],
                       "resourceAccess": [{"id": scope_id, "type": "Scope"}]})
    call("PATCH", f"/applications/{app['id']}",
         {"requiredResourceAccess": blocks}, ok=(204,))
    print(f"+ manifest: delegated {WANT_SCOPE} on {resource['displayName']}")

    # 2. admin-consent it
    grants = g.collection(f"/oauth2PermissionGrants?{eq_filter('clientId', bff_sp['id'])}")
    grant = tenant_grant(grants, resource["id"])
    if grant:
        merged = " ".join(sorted(set(grant["scope"].split()) | {WANT_SCOPE}))
        call("PATCH", f"/oauth2PermissionGrants/{grant['id']}",
             {"scope": merged}, ok=(204,))
        print(f"= consent updated: {merged}")
    else:
        call("POST", "/oauth2PermissionGrants", {
            "clientId": bff_sp["id"], "consentType": "AllPrincipals",
            "resourceId": resource["id"], "scope": WANT_SCOPE,
        })
        print(f"+ admin consent granted: {WANT_SCOPE}")

    print("\nThe On-Behalf-Of exchange to https://ai.azure.com should now succeed.")
    print("Verify from the app: sign in, Explore tab, Connection diagnostics.")


if __name__ == "__main__":
    main()
