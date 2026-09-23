"""Configure the Work IQ Foundry connector app registration.

Adds what the observed authorize request actually needs:

  1. the REDIRECT URI the Azure API Management consent broker sends the code to;
  2. the delegated permission on the Work IQ resource itself.

WHAT THE AUTHORIZE URL TOLD US

    redirect_uri = https://global.consent.azure-apim.net/redirect/<conn-guid>-workiq
    scope        = offline_access api://workiq.svc.cloud.microsoft/WorkIQAgent.Ask
    response_type= code   (+ PKCE)

Two corrections to the earlier assumption fall out of that:

  * The connector does NOT call Microsoft Graph directly with Graph scopes. It
    calls the Work IQ service (`api://workiq.svc.cloud.microsoft`) and asks for
    `WorkIQAgent.Ask`. Work IQ then does the per-user retrieval itself. The Graph
    scopes already granted are harmless and useful if anything ever calls Graph
    directly, but they are not what this flow needs.
  * It is an authorization-code flow through the Azure API Management consent
    broker, so the redirect URI must be registered as a WEB redirect. Without it
    the sign-in fails with AADSTS50011 before any consent prompt appears.

    python configure_workiq_connector.py --show
    python configure_workiq_connector.py --redirect-uri "<uri>" --apply
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys

APP_NAME = "cm-capmarket-workiq-foundry-connector"
WORKIQ_RESOURCE_URI = "api://workiq.svc.cloud.microsoft"
WORKIQ_SCOPE = "WorkIQAgent.Ask"

AZ = shutil.which("az") or "az"


def az(*args: str) -> str:
    """shell=False so that & and $ in URLs are not eaten by cmd.exe."""
    out = subprocess.run([AZ, *args], capture_output=True, text=True,
                         encoding="utf-8", errors="replace")
    if out.returncode != 0:
        raise RuntimeError(f"az {' '.join(args[:3])}... failed:\n{(out.stderr or '')[:600]}")
    return (out.stdout or "").strip()


def graph(method: str, url: str, body: dict | None = None):
    args = ["rest", "--method", method, "--resource", "https://graph.microsoft.com", "--url", url]
    if body is not None:
        args += ["--headers", "Content-Type=application/json", "--body", json.dumps(body)]
    out = az(*args)
    return json.loads(out) if out else None


def get_app() -> dict:
    r = graph("get", "https://graph.microsoft.com/v1.0/applications"
                     f"?$filter=displayName eq '{APP_NAME}'")
    if not r or not r.get("value"):
        sys.exit(f"application '{APP_NAME}' not found")
    return r["value"][0]


def find_workiq_sp() -> dict | None:
    """The Work IQ resource SP may not exist until first consent provisions it."""
    for flt in (f"$filter=servicePrincipalNames/any(n:n eq '{WORKIQ_RESOURCE_URI}')",
                "$search=\"displayName:Work IQ\""):
        try:
            headers = ["--headers", "ConsistencyLevel=eventual"] if "search" in flt else []
            args = ["rest", "--method", "get", "--resource", "https://graph.microsoft.com",
                    "--url", f"https://graph.microsoft.com/v1.0/servicePrincipals?{flt}"
                             "&$select=id,appId,displayName,servicePrincipalNames,oauth2PermissionScopes",
                    *headers]
            out = az(*args)
            data = json.loads(out or "{}")
            for sp in data.get("value", []):
                names = sp.get("servicePrincipalNames") or []
                if WORKIQ_RESOURCE_URI in names or "workiq" in " ".join(names).lower():
                    return sp
        except RuntimeError:
            continue
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--redirect-uri", action="append", default=[],
                    help="web redirect URI to register; repeatable")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--show", action="store_true")
    args = ap.parse_args()

    app = get_app()
    obj_id, app_id = app["id"], app["appId"]
    web = app.get("web") or {}
    current = list(web.get("redirectUris") or [])

    print(f"application  : {APP_NAME}")
    print(f"appId        : {app_id}")
    print(f"web redirects: {current or '(none)'}")

    sp = find_workiq_sp()
    if sp:
        print(f"\nWork IQ resource SP found:")
        print(f"  displayName : {sp['displayName']}")
        print(f"  appId       : {sp['appId']}")
        scopes = {s['value']: s['id'] for s in sp.get('oauth2PermissionScopes', [])}
        print(f"  scopes      : {sorted(scopes)}")
    else:
        print(f"\nWork IQ resource SP ({WORKIQ_RESOURCE_URI}) is NOT provisioned in this")
        print("tenant yet. That is expected before the first successful consent - Entra")
        print(f"creates it when '{WORKIQ_SCOPE}' is first consented. Because the scope is")
        print("requested dynamically in the authorize URL, it does NOT need to be")
        print("pre-registered on the app; it will be presented at the consent prompt.")

    if args.show or not args.apply:
        if args.redirect_uri:
            new = [u for u in args.redirect_uri if u not in current]
            print(f"\nWould add {len(new)} redirect URI(s):")
            for u in new:
                print(f"  + {u}")
            print("\nRe-run with --apply.")
        return 0

    if args.redirect_uri:
        merged = current + [u for u in args.redirect_uri if u not in current]
        graph("patch", f"https://graph.microsoft.com/v1.0/applications/{obj_id}",
              {"web": {"redirectUris": merged,
                       "implicitGrantSettings": {"enableIdTokenIssuance": False,
                                                 "enableAccessTokenIssuance": False}}})
        print("\n+ redirect URIs written:")
        for u in merged:
            print(f"    {u}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
