"""Configure RBAC for the Bank's Capital Markets Client Intelligence web app.

WHAT THIS DOES
--------------
1. Defines five **app roles** on the SPA app registration, one per function:

       Coverage            MD Corporate Coverage - Energy - the demo driver
       CorporateBanking    lending, DCM origination and the balance sheet
       GlobalMarkets       commodity and FX derivatives, pre-settlement exposure
       CreditRisk          limits, covenants and the annual review
       Research            publishing analyst - public side, behind the wall

   The roles land in the `roles` claim of the user's token, so the BFF and the UI
   can read them. The SPA uses the role to pick a `personaByRole` entry from
   story.json, so the guided narrative is framed from the signed-in banker's own
   point of view rather than always Coverage's.

2. Sets **appRoleAssignmentRequired** on the SPA's service principal, so only
   explicitly assigned users can sign in at all. Without this, any member of the
   tenant can open the app.

3. Assigns explicitly configured user principal names to app roles.

Note this is *application* RBAC - who may use the app. It sits on top of, and
does not replace, the data-plane authorisation that already happens downstream:
Work IQ, Fabric and AI Search each evaluate the signed-in user's own permissions
because every call is made On-Behalf-Of that user.

    python configure_rbac.py            # apply
    python configure_rbac.py --show     # report only
    python configure_rbac.py --open     # turn OFF assignment-required (open to tenant)

Required environment in every mode: AZURE_TENANT_ID (tenant GUID),
INFRA_SPA_NAME (unique app display name). Apply also requires
INFRA_ROLE_ASSIGNMENTS: a nonempty JSON object mapping full UPNs to Coverage,
CorporateBanking, GlobalMarkets, CreditRisk or Research. --show and --open do not
read INFRA_ROLE_ASSIGNMENTS. No inferred domain, users or optional defaults.
"""

from __future__ import annotations

import argparse
import sys
import time
import uuid
from urllib.parse import quote

if __package__:
    from .portability_config import (
        ConfigurationError, GraphClient, app_name, environment, find_app, find_sp,
        role_assignments, tenant_id,
    )
else:
    from portability_config import (
        ConfigurationError, GraphClient, app_name, environment, find_app, find_sp,
        role_assignments, tenant_id,
    )

ROLES = [
    {
        "value": "Coverage",
        "displayName": "Corporate Coverage - Energy",
        "description": "Relationship owner. Sees the whole client across business lines.",
    },
    {
        "value": "CorporateBanking",
        "displayName": "Corporate Banking & DCM",
        "description": "Lending, hold sizing, covenants and the balance sheet.",
    },
    {
        "value": "GlobalMarkets",
        "displayName": "Global Markets",
        "description": "Derivatives, hedging structures and pre-settlement exposure.",
    },
    {
        "value": "CreditRisk",
        "displayName": "Credit Risk Management",
        "description": "Limits, covenant testing, watchlist and annual review.",
    },
    {
        "value": "Research",
        "displayName": "Equity Research",
        "description": "Publishing analyst. Public side, subject to the information barrier.",
    },
]


def main(argv=None, environ=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--show", action="store_true")
    mode.add_argument("--open", action="store_true",
                      help="allow any tenant user to sign in (turns off assignment-required)")
    args = ap.parse_args(argv)
    env = environment(environ)
    try:
        tenant = tenant_id(env)
        spa_name = app_name(env, "INFRA_SPA_NAME")
        assignments = (
            role_assignments(env, {role["value"] for role in ROLES})
            if not args.show and not args.open else {}
        )
    except ConfigurationError as exc:
        ap.error(str(exc))

    g = GraphClient(tenant)
    app = find_app(g, spa_name)
    if not app:
        sys.exit(f"{spa_name} not found. Run provision_app_registrations.py first.")
    sp = find_sp(g, app["appId"])
    if not sp:
        sys.exit("Service principal not found for the SPA.")

    if args.show:
        print(f"{spa_name}  appId={app['appId']}")
        print(f"  assignment required : {sp.get('appRoleAssignmentRequired')}")
        print("  roles defined       :",
              ", ".join(r["value"] for r in app.get("appRoles", [])) or "none")
        assigned = g.collection(f"/servicePrincipals/{sp['id']}/appRoleAssignedTo")
        print(f"  users assigned      : {len(assigned)}")
        role_by_id = {r["id"]: r["value"] for r in app.get("appRoles", [])}
        for a in assigned:
            print(f"     {a.get('principalDisplayName'):<22} "
                  f"{role_by_id.get(a.get('appRoleId'), '(default)')}")
        return

    if args.open:
        g.call("PATCH", f"/servicePrincipals/{sp['id']}",
               {"appRoleAssignmentRequired": False}, ok=(204,))
        print("= sign-in OPEN to all tenant users")
        return

    # Resolve all configured users before changing any roles or sign-in policy.
    users = {
        upn: g.call("GET", f"/users/{quote(upn, safe='')}?$select=id,displayName")
        for upn in assignments
    }

    # ---- 1. app roles ----
    existing = {r["value"]: r for r in app.get("appRoles", [])}
    roles = list(app.get("appRoles", []))
    added = 0
    for spec in ROLES:
        if spec["value"] in existing:
            continue
        roles.append({
            "id": str(uuid.uuid4()),
            "allowedMemberTypes": ["User"],
            "description": spec["description"],
            "displayName": spec["displayName"],
            "isEnabled": True,
            "value": spec["value"],
        })
        added += 1
    if added:
        g.call("PATCH", f"/applications/{app['id']}", {"appRoles": roles}, ok=(204,))
        print(f"+ defined {added} app role(s)")
        time.sleep(15)
    else:
        print("= app roles already defined")

    app = g.call("GET", f"/applications/{app['id']}")
    role_id = {r["value"]: r["id"] for r in app["appRoles"]}

    # ---- 2. require assignment ----
    g.call("PATCH", f"/servicePrincipals/{sp['id']}",
           {"appRoleAssignmentRequired": True}, ok=(204,))
    print("+ user assignment REQUIRED - only assigned users can sign in")

    # ---- 3. assign the configured users ----
    current = {
        (a.get("principalId"), a.get("appRoleId"))
        for a in g.collection(f"/servicePrincipals/{sp['id']}/appRoleAssignedTo")
    }

    for upn, role in assignments.items():
        user = users[upn]
        rid = role_id[role]
        if (user["id"], rid) in current:
            print(f"  = {user['displayName']:<20} {role}")
            continue
        g.call("POST", f"/users/{user['id']}/appRoleAssignments", {
            "principalId": user["id"],
            "resourceId": sp["id"],
            "appRoleId": rid,
        })
        print(f"  + {user['displayName']:<20} {role}")

    print("\nOnly users with an app role assignment can sign in; existing assignments are retained.")
    print("Assign more in the portal: Entra ID > Enterprise applications > "
          f"{spa_name} > Users and groups.")
    print("To open it up again:  python configure_rbac.py --open")


if __name__ == "__main__":
    main()
