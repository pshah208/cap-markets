"""Register the Work IQ delegated permission on the connector app and consent it.

The authorize request asks for:

    scope = offline_access api://workiq.svc.cloud.microsoft/WorkIQAgent.Ask

`WorkIQAgent.Ask` is a scope on the **Work IQ** resource, not on Microsoft Graph.
Registering it on the app (rather than relying on dynamic consent at the prompt)
means the permission is visible in the portal, can be admin-consented once for the
whole tenant, and does not surprise each persona with a consent dialog.

    python grant_workiq_scope.py            # show
    python grant_workiq_scope.py --apply    # register + admin consent
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys

APP_NAME = "cm-capmarket-workiq-foundry-connector"
WORKIQ_APP_ID = "fdcc1f02-fc51-4226-8753-f668596af7f7"   # resolved from the tenant
WANTED = ["WorkIQAgent.Ask"]                              # least privilege - Ask only
AZ = shutil.which("az") or "az"


def az(*args: str) -> str:
    out = subprocess.run([AZ, *args], capture_output=True, text=True,
                         encoding="utf-8", errors="replace")
    if out.returncode != 0:
        raise RuntimeError(f"az {' '.join(args[:4])}... failed:\n{(out.stderr or '')[:600]}")
    return (out.stdout or "").strip()


def graph(method: str, url: str, body: dict | None = None):
    args = ["rest", "--method", method, "--resource", "https://graph.microsoft.com", "--url", url]
    if body is not None:
        args += ["--headers", "Content-Type=application/json", "--body", json.dumps(body)]
    out = az(*args)
    return json.loads(out) if out else None


def main() -> int:
    apply = "--apply" in sys.argv

    app = graph("get", f"https://graph.microsoft.com/v1.0/applications"
                       f"?$filter=displayName eq '{APP_NAME}'")["value"][0]
    obj_id, app_id = app["id"], app["appId"]

    wiq = graph("get", f"https://graph.microsoft.com/v1.0/servicePrincipals"
                       f"?$filter=appId eq '{WORKIQ_APP_ID}'"
                       f"&$select=id,appId,displayName,oauth2PermissionScopes")["value"][0]
    wiq_sp_id = wiq["id"]
    scopes = {s["value"]: s["id"] for s in wiq["oauth2PermissionScopes"]}

    print(f"connector app : {APP_NAME}  ({app_id})")
    print(f"resource      : {wiq['displayName']}  ({wiq['appId']})")
    print(f"available     : {sorted(scopes)}")
    print(f"registering   : {WANTED}  (least privilege - Ask only, not the Settings scopes)")

    rra = [r for r in app.get("requiredResourceAccess", [])
           if r["resourceAppId"] != WORKIQ_APP_ID]
    rra.append({
        "resourceAppId": WORKIQ_APP_ID,
        "resourceAccess": [{"id": scopes[s], "type": "Scope"} for s in WANTED if s in scopes],
    })

    if not apply:
        print("\nWould write requiredResourceAccess for the Work IQ resource and grant "
              "tenant-wide admin consent.\nRe-run with --apply.")
        return 0

    graph("patch", f"https://graph.microsoft.com/v1.0/applications/{obj_id}",
          {"requiredResourceAccess": rra})
    print("\n+ Work IQ permission registered on the app")

    sps = graph("get", f"https://graph.microsoft.com/v1.0/servicePrincipals"
                       f"?$filter=appId eq '{app_id}'&$select=id")
    client_sp = sps["value"][0]["id"]

    scope_str = " ".join(WANTED)
    existing = graph("get", f"https://graph.microsoft.com/v1.0/oauth2PermissionGrants"
                            f"?$filter=clientId eq '{client_sp}' and resourceId eq '{wiq_sp_id}'")
    if existing and existing.get("value"):
        gid = existing["value"][0]["id"]
        graph("patch", f"https://graph.microsoft.com/v1.0/oauth2PermissionGrants/{gid}",
              {"scope": scope_str})
        print(f"= admin consent updated: {scope_str}")
    else:
        graph("post", "https://graph.microsoft.com/v1.0/oauth2PermissionGrants",
              {"clientId": client_sp, "consentType": "AllPrincipals",
               "resourceId": wiq_sp_id, "scope": scope_str})
        print(f"+ admin consent granted (AllPrincipals): {scope_str}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
