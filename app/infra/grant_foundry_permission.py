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
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time

import requests

GRAPH = "https://graph.microsoft.com/v1.0"
BFF_NAME = "cm-client-intelligence-bff"

# The audience the Foundry Responses API demands is https://ai.azure.com. That URI
# is owned by "Azure Machine Learning Services" (18a66f5f-...), NOT by the
# similarly-named "Azure Machine Learning" (0736f41a-...), which exposes no scopes
# at all. Resolving it the reliable way:  az ad sp show --id https://ai.azure.com
CANDIDATES = [
    ("Azure Machine Learning Services", "18a66f5f-dbdf-4c17-9dd7-1634712a9cbe"),
]
WANT_SCOPE = "user_impersonation"


def token() -> str:
    o = subprocess.run(["az", "account", "get-access-token", "--resource",
                        "https://graph.microsoft.com", "--query", "accessToken",
                        "-o", "tsv"], capture_output=True, text=True, shell=True)
    if o.returncode != 0:
        sys.exit("run az login")
    return o.stdout.strip()


H = {"Authorization": f"Bearer {token()}", "Content-Type": "application/json"}


def call(method: str, path: str, body=None, ok=(200, 201, 204)):
    r = requests.request(method, f"{GRAPH}{path}", headers=H, json=body, timeout=90)
    if r.status_code not in ok:
        raise RuntimeError(f"{method} {path} -> {r.status_code}: {r.text[:500]}")
    if r.content and "json" in r.headers.get("Content-Type", ""):
        return r.json()
    return None


def find_sp(app_id: str):
    v = call("GET", f"/servicePrincipals?$filter=appId eq '{app_id}'"
                    "&$select=id,appId,displayName,oauth2PermissionScopes")["value"]
    return v[0] if v else None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--show", action="store_true")
    args = ap.parse_args()

    app = (call("GET", f"/applications?$filter=displayName eq '{BFF_NAME}'")
           .get("value") or [None])[0]
    if not app:
        sys.exit(f"{BFF_NAME} not found.")
    app = call("GET", f"/applications/{app['id']}")
    bff_sp = find_sp(app["appId"])

    # Locate (or provision) the resource service principal.
    resource = None
    for label, app_id in CANDIDATES:
        sp = find_sp(app_id)
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
            resource = find_sp(app_id)
            break
        except RuntimeError as exc:
            print(f"  could not provision {label}: {str(exc)[:160]}")

    if not resource:
        sys.exit("No suitable resource service principal found or created.")

    scopes = {s["value"]: s["id"] for s in resource.get("oauth2PermissionScopes", [])}
    if WANT_SCOPE not in scopes:
        print(f"  !! '{WANT_SCOPE}' not exposed by {resource['displayName']}. "
              f"Available: {', '.join(sorted(scopes)) or '(none)'}")
        sys.exit(1)
    scope_id = scopes[WANT_SCOPE]

    if args.show:
        blocks = app.get("requiredResourceAccess", [])
        has = any(b["resourceAppId"] == resource["appId"] for b in blocks)
        print(f"  BFF requests it in manifest : {has}")
        grants = call("GET", f"/oauth2PermissionGrants?$filter=clientId eq '{bff_sp['id']}'")["value"]
        g = next((x for x in grants if x["resourceId"] == resource["id"]), None)
        print(f"  BFF consented               : {bool(g)}"
              + (f" ({g['scope'].strip()})" if g else ""))
        return

    # 1. add to the manifest
    blocks = app.get("requiredResourceAccess", [])
    block = next((b for b in blocks if b["resourceAppId"] == resource["appId"]), None)
    if block:
        if not any(a["id"] == scope_id for a in block["resourceAccess"]):
            block["resourceAccess"].append({"id": scope_id, "type": "Scope"})
    else:
        blocks.append({"resourceAppId": resource["appId"],
                       "resourceAccess": [{"id": scope_id, "type": "Scope"}]})
    call("PATCH", f"/applications/{app['id']}",
         {"requiredResourceAccess": blocks}, ok=(204,))
    print(f"+ manifest: delegated {WANT_SCOPE} on {resource['displayName']}")

    # 2. admin-consent it
    grants = call("GET", f"/oauth2PermissionGrants?$filter=clientId eq '{bff_sp['id']}'")["value"]
    grant = next((x for x in grants if x["resourceId"] == resource["id"]), None)
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
