"""Let the BFF save follow-up emails as Outlook DRAFTS in the signed-in user's own mailbox.

The wrap-up step (the "Cowork" step) drafts a client follow-up email. Saving it to
Outlook needs Microsoft Graph POST /me/messages On-Behalf-Of the user, which needs
the *delegated* Mail.ReadWrite scope on the BFF app registration plus consent.

Least privilege:
  * Mail.ReadWrite only - the minimum Graph scope that can create a draft.
  * NOT Mail.Send - the app cannot send anything; a human sends from Outlook.
  * Delegated, so it only ever touches the signed-in user's own mailbox.

    python grant_mail_draft_permission.py          # apply
    python grant_mail_draft_permission.py --show   # report only

Required environment: AZURE_TENANT_ID and INFRA_BFF_CLIENT_ID (nonzero GUIDs).
No optional environment settings or implicit identity defaults.
"""

from __future__ import annotations

import argparse

if __package__:
    from .portability_config import (
        ConfigurationError, GraphClient, environment, eq_filter, find_sp,
        guid, required, single, tenant_grant, tenant_id,
    )
else:
    from portability_config import (
        ConfigurationError, GraphClient, environment, eq_filter, find_sp,
        guid, required, single, tenant_grant, tenant_id,
    )

GRAPH_APP_ID = "00000003-0000-0000-c000-000000000000"
SCOPE = "Mail.ReadWrite"


def main(argv=None, environ=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--show", action="store_true")
    args = ap.parse_args(argv)
    env = environment(environ)
    try:
        tenant = tenant_id(env)
        bff_app_id = guid(required(env, "INFRA_BFF_CLIENT_ID"), "INFRA_BFF_CLIENT_ID")
    except ConfigurationError as exc:
        ap.error(str(exc))

    g = GraphClient(tenant)
    graph_sp = find_sp(g, GRAPH_APP_ID)
    bff_sp = find_sp(g, bff_app_id)
    app = single(g.collection(f"/applications?{eq_filter('appId', bff_app_id)}"), "BFF appId")
    if not graph_sp or not bff_sp or not app:
        raise RuntimeError("The configured BFF application and both resource service principals must exist.")
    scope_id = next((
        s["id"] for s in graph_sp.get("oauth2PermissionScopes", [])
        if s["value"] == SCOPE and s.get("isEnabled", False)
    ), None)
    if not scope_id:
        raise RuntimeError(f"Microsoft Graph does not expose an enabled delegated {SCOPE} scope.")
    bff_sp_id = bff_sp["id"]
    grants = g.collection(f"/oauth2PermissionGrants?{eq_filter('clientId', bff_sp_id)}")

    declared = any(ra["resourceAppId"] == GRAPH_APP_ID and
                   any(a["id"] == scope_id and a["type"] == "Scope" for a in ra["resourceAccess"])
                   for ra in app.get("requiredResourceAccess", []))
    grant = tenant_grant(grants, graph_sp["id"])
    consented = bool(grant) and SCOPE in grant["scope"].split()
    print(f"declared on app : {declared}")
    print(f"admin consented : {consented}  ({grant['scope'] if grant else 'no grant'})")
    if args.show:
        return

    if not declared:
        rra = app.get("requiredResourceAccess", [])
        block = next((ra for ra in rra if ra["resourceAppId"] == GRAPH_APP_ID), None)
        if block is None:
            block = {"resourceAppId": GRAPH_APP_ID, "resourceAccess": []}
            rra.append(block)
        block["resourceAccess"].append({"id": scope_id, "type": "Scope"})
        g.call("PATCH", f"/applications/{app['id']}", {"requiredResourceAccess": rra}, ok=(204,))
        print(f"+ declared delegated {SCOPE}")

    if not consented:
        if grant:
            scopes = " ".join(sorted(set(grant["scope"].split()) | {SCOPE}))
            g.call("PATCH", f"/oauth2PermissionGrants/{grant['id']}", {"scope": scopes}, ok=(204,))
        else:
            g.call("POST", "/oauth2PermissionGrants", {
                "clientId": bff_sp_id, "consentType": "AllPrincipals",
                "resourceId": graph_sp["id"], "scope": SCOPE,
            })
        print(f"+ admin consent extended with {SCOPE}")
    print("done")


if __name__ == "__main__":
    main()
