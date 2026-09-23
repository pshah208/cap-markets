"""Add the Microsoft Graph permissions a Work IQ / Microsoft 365 grounding
connector needs, and grant admin consent.

    python configure_workiq_connector.py            # show what would change
    python configure_workiq_connector.py --apply    # apply and consent

DESIGN NOTE - why DELEGATED and not APPLICATION permissions.

Work IQ grounds on content the SIGNED-IN USER can access. That is the whole point:
the demo driver sees her own mail, her team's channels and her SharePoint library,
and a different persona would legitimately see something different. Delegated
permissions preserve that.

Application permissions would let the connector read EVERY mailbox and EVERY site
in the tenant regardless of who is asking. That is a large, permanent privilege
escalation, it breaks the per-user grounding model the demo is built on, and it is
not needed. Everything here is delegated and READ-ONLY - a grounding connector
never writes.
"""

from __future__ import annotations

import json
import subprocess
import sys

GRAPH_APP_ID = "00000003-0000-0000-c000-000000000000"
APP_NAME = "cm-capmarket-workiq-foundry-connector"

# Delegated, read-only. Each entry says why it is needed, so the set can be
# defended or trimmed rather than copied blindly.
REQUIRED = [
    ("User.Read",               "sign the user in and read their own profile"),
    ("offline_access",          "refresh tokens, so the connection does not expire mid-demo"),
    ("Mail.Read",               "read the signed-in user's mail - the 18 seeded emails"),
    ("Files.Read.All",          "read files the user can access - meeting records and client docs"),
    ("Sites.Read.All",          "read SharePoint sites - the team's 'Client Files' library"),
    ("ChannelMessage.Read.All", "read Teams channel messages the user can access"),
    ("Chat.Read",               "read the user's Teams chats"),
    ("Calendars.Read",          "read the user's calendar - meeting context"),
    ("People.Read",             "resolve colleagues named in the corpus"),
    ("Group.Read.All",          "resolve team membership so channel content is reachable"),
]


def az(*args: str) -> str:
    # errors="replace": the Graph service principal's permission descriptions
    # contain non-UTF-8 bytes (curly apostrophes in a legacy code page), which
    # otherwise kills the reader thread and surfaces as a bare None.
    out = subprocess.run(["az", *args], capture_output=True, text=True, shell=True,
                         encoding="utf-8", errors="replace")
    if out.returncode != 0:
        raise RuntimeError(f"az {' '.join(args)} failed:\n{(out.stderr or '')[:800]}")
    return (out.stdout or "").strip()


def main() -> int:
    apply = "--apply" in sys.argv

    app = json.loads(az("rest", "--method", "get", "--resource", "https://graph.microsoft.com",
                        "--url", f"https://graph.microsoft.com/v1.0/applications?$filter=displayName eq '{APP_NAME}'"))
    if not app.get("value"):
        sys.exit(f"application '{APP_NAME}' not found")
    a = app["value"][0]
    obj_id, app_id = a["id"], a["appId"]
    print(f"application : {APP_NAME}")
    print(f"appId       : {app_id}")
    print(f"objectId    : {obj_id}\n")

    graph_sp = json.loads(az("rest", "--method", "get", "--resource", "https://graph.microsoft.com",
                             "--url", f"https://graph.microsoft.com/v1.0/servicePrincipals?"
                                      f"$filter=appId eq '{GRAPH_APP_ID}'&$select=id,oauth2PermissionScopes"))
    sp = graph_sp["value"][0]
    graph_sp_id = sp["id"]
    scopes = {s["value"]: s["id"] for s in sp["oauth2PermissionScopes"]}

    existing = set()
    for rra in a.get("requiredResourceAccess", []):
        if rra["resourceAppId"] == GRAPH_APP_ID:
            existing = {ra["id"] for ra in rra["resourceAccess"] if ra["type"] == "Scope"}

    by_id = {v: k for k, v in scopes.items()}
    print("Current delegated scopes:")
    for sid in sorted(existing):
        print(f"  = {by_id.get(sid, sid)}")
    if not existing:
        print("  (none)")

    print("\nRequired:")
    resource_access, missing = [], []
    for name, why in REQUIRED:
        sid = scopes.get(name)
        if not sid:
            print(f"  ! {name:<24} NOT FOUND on the Graph service principal")
            continue
        resource_access.append({"id": sid, "type": "Scope"})
        mark = "=" if sid in existing else "+"
        if sid not in existing:
            missing.append(name)
        print(f"  {mark} {name:<24} {why}")

    if not missing:
        print("\nNothing to add.")
    elif not apply:
        print(f"\n{len(missing)} to add. Re-run with --apply.")
        return 0

    if apply:
        body = {"requiredResourceAccess": [{
            "resourceAppId": GRAPH_APP_ID, "resourceAccess": resource_access}]}
        az("rest", "--method", "patch", "--resource", "https://graph.microsoft.com",
           "--url", f"https://graph.microsoft.com/v1.0/applications/{obj_id}",
           "--headers", "Content-Type=application/json", "--body", json.dumps(body))
        print("\n+ permissions written to the application")

        # A service principal must exist in this tenant before consent can be granted.
        sps = json.loads(az("rest", "--method", "get", "--resource", "https://graph.microsoft.com",
                            "--url", f"https://graph.microsoft.com/v1.0/servicePrincipals?"
                                     f"$filter=appId eq '{app_id}'&$select=id"))
        if sps.get("value"):
            client_sp = sps["value"][0]["id"]
            print(f"= service principal {client_sp}")
        else:
            created = json.loads(az("rest", "--method", "post", "--resource", "https://graph.microsoft.com",
                                    "--url", "https://graph.microsoft.com/v1.0/servicePrincipals",
                                    "--headers", "Content-Type=application/json",
                                    "--body", json.dumps({"appId": app_id})))
            client_sp = created["id"]
            print(f"+ service principal {client_sp}")

        # Tenant-wide admin consent for the delegated scopes.
        grant = {
            "clientId": client_sp,
            "consentType": "AllPrincipals",
            "resourceId": graph_sp_id,
            "scope": " ".join(n for n, _ in REQUIRED if n in scopes),
        }
        existing_grants = json.loads(az(
            "rest", "--method", "get", "--resource", "https://graph.microsoft.com",
            "--url", f"https://graph.microsoft.com/v1.0/oauth2PermissionGrants?"
                     f"$filter=clientId eq '{client_sp}' and resourceId eq '{graph_sp_id}'"))
        if existing_grants.get("value"):
            gid = existing_grants["value"][0]["id"]
            az("rest", "--method", "patch", "--resource", "https://graph.microsoft.com",
               "--url", f"https://graph.microsoft.com/v1.0/oauth2PermissionGrants/{gid}",
               "--headers", "Content-Type=application/json",
               "--body", json.dumps({"scope": grant["scope"]}))
            print("= admin consent updated (AllPrincipals)")
        else:
            az("rest", "--method", "post", "--resource", "https://graph.microsoft.com",
               "--url", "https://graph.microsoft.com/v1.0/oauth2PermissionGrants",
               "--headers", "Content-Type=application/json", "--body", json.dumps(grant))
            print("+ admin consent granted (AllPrincipals)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
