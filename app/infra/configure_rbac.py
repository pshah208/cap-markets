"""Configure RBAC for the BMO Capital Markets Client Intelligence web app.

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

3. Assigns the demo personas to sensible roles.

Note this is *application* RBAC - who may use the app. It sits on top of, and
does not replace, the data-plane authorisation that already happens downstream:
Work IQ, Fabric and AI Search each evaluate the signed-in user's own permissions
because every call is made On-Behalf-Of that user.

    python configure_rbac.py            # apply
    python configure_rbac.py --show     # report only
    python configure_rbac.py --open     # turn OFF assignment-required (open to tenant)
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
import uuid
from typing import Any

import requests

GRAPH = "https://graph.microsoft.com/v1.0"
SPA_NAME = "cm-client-intelligence-spa"

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

# Persona UPN prefix -> role. These five accounts belong to THIS demo.
#
# Every other account in the tenant is load-bearing for another demo - do not
# add them here. In particular the Scotia mortgage-renewal demo owns LisaT,
# MarioR, MonicaT, SEdemo, KaiC, AdilE, AmberR, BillieV, CoraT, CoreyG, DaichiM,
# DakotaS, EkaS and HadarC. The role value must match a key in story.json's
# personaByRole, or the SPA silently falls back to the default Coverage framing.
ASSIGNMENTS = {
    "SydneyM": "Coverage",          # Sydney Mattos  - MD, Corporate Coverage - Energy (driver)
    "SashaO": "CorporateBanking",   # Sasha Ouellet  - Director, Corporate Banking & DCM
    "QuinnC": "GlobalMarkets",      # Quinn Campbell - Director, Commodities & FX Sales
    "VanceD": "CreditRisk",         # Vance DeLeon   - Director, Credit Risk - Energy
    "RobinK": "Research",           # Robin Kline    - ED, Equity Research
}

DOMAIN = "M365CPI65678641.OnMicrosoft.com"


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
            raise RuntimeError(f"{method} {path} -> {r.status_code}: {r.text[:600]}")
        if r.content and "json" in r.headers.get("Content-Type", ""):
            return r.json()
        return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--open", action="store_true",
                    help="allow any tenant user to sign in (turns off assignment-required)")
    args = ap.parse_args()

    g = G()

    app = (g.call("GET", f"/applications?$filter=displayName eq '{SPA_NAME}'")
           .get("value") or [None])[0]
    if not app:
        sys.exit(f"{SPA_NAME} not found. Run provision_app_registrations.py first.")
    sp = (g.call("GET", f"/servicePrincipals?$filter=appId eq '{app['appId']}'")
          .get("value") or [None])[0]
    if not sp:
        sys.exit("Service principal not found for the SPA.")

    if args.show:
        print(f"{SPA_NAME}  appId={app['appId']}")
        print(f"  assignment required : {sp.get('appRoleAssignmentRequired')}")
        print("  roles defined       :",
              ", ".join(r["value"] for r in app.get("appRoles", [])) or "none")
        assigned = g.call("GET", f"/servicePrincipals/{sp['id']}/appRoleAssignedTo")
        print(f"  users assigned      : {len(assigned.get('value', []))}")
        role_by_id = {r["id"]: r["value"] for r in app.get("appRoles", [])}
        for a in assigned.get("value", []):
            print(f"     {a.get('principalDisplayName'):<22} "
                  f"{role_by_id.get(a.get('appRoleId'), '(default)')}")
        return

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
    if args.open:
        g.call("PATCH", f"/servicePrincipals/{sp['id']}",
               {"appRoleAssignmentRequired": False}, ok=(204,))
        print("= sign-in OPEN to all tenant users")
        return

    g.call("PATCH", f"/servicePrincipals/{sp['id']}",
           {"appRoleAssignmentRequired": True}, ok=(204,))
    print("+ user assignment REQUIRED - only assigned users can sign in")

    # ---- 3. assign the personas ----
    current = {
        (a.get("principalId"), a.get("appRoleId"))
        for a in g.call("GET", f"/servicePrincipals/{sp['id']}/appRoleAssignedTo")
                  .get("value", [])
    }

    for prefix, role in ASSIGNMENTS.items():
        upn = f"{prefix}@{DOMAIN}"
        try:
            user = g.call("GET", f"/users/{upn}?$select=id,displayName")
        except RuntimeError:
            print(f"  !! not found: {upn}")
            continue
        rid = role_id[role]
        if (user["id"], rid) in current:
            print(f"  = {user['displayName']:<20} {role}")
            continue
        try:
            g.call("POST", f"/users/{user['id']}/appRoleAssignments", {
                "principalId": user["id"],
                "resourceId": sp["id"],
                "appRoleId": rid,
            })
            print(f"  + {user['displayName']:<20} {role}")
        except RuntimeError as exc:
            print(f"  !! {user['displayName']}: {str(exc)[:120]}")

    print("\nUsers not assigned above will be blocked at sign-in.")
    print("Assign more in the portal: Entra ID > Enterprise applications > "
          f"{SPA_NAME} > Users and groups.")
    print("To open it up again:  python configure_rbac.py --open")


if __name__ == "__main__":
    main()
