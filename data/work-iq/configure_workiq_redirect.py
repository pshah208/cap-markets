"""Register explicit web redirects and inspect the Work IQ resource scope.

Requires WORKIQ_TENANT_ID and WORKIQ_CONNECTOR_CLIENT_ID. Optional
WORKIQ_RESOURCE_APP_ID selects an exact resource application UUID; otherwise
the exact public Work IQ protocol resource URI is used, never a name heuristic.
Use grant_workiq_scope.py separately to register and consent WorkIQAgent.Ask.

    python configure_workiq_redirect.py --show
    python configure_workiq_redirect.py --redirect-uri "<uri>" --apply

--apply requires at least one explicit --redirect-uri unless --show is present.
No implicit redirects are added. All existing redirects and web settings remain.
"""

from __future__ import annotations

import argparse

from workiq_admin_config import (
    GraphClient,
    find_application,
    find_service_principal,
    find_unique,
    load_config,
    odata_literal,
    permission_entries,
    validate_redirect_uris,
)

WORKIQ_RESOURCE_URI = "api://workiq.svc.cloud.microsoft"
WORKIQ_SCOPE = "WorkIQAgent.Ask"


def find_workiq_sp(g: GraphClient, resource_app_id: str | None = None) -> dict | None:
    if resource_app_id:
        return find_service_principal(g, resource_app_id, required=False)
    return find_unique(
        g, "/servicePrincipals",
        f"servicePrincipalNames/any(n:n eq {odata_literal(WORKIQ_RESOURCE_URI)})",
        f"Work IQ service principal for exact URI {WORKIQ_RESOURCE_URI}", required=False,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--redirect-uri", action="append", default=[], help="explicit web redirect; repeatable")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--show", action="store_true", help="read-only, overrides --apply")
    args = parser.parse_args(argv)
    config = load_config("WORKIQ_CONNECTOR_CLIENT_ID", optional=("WORKIQ_RESOURCE_APP_ID",))
    if args.apply and not args.show and not args.redirect_uri:
        parser.error("--apply requires an explicit --redirect-uri unless --show is used")
    redirects = validate_redirect_uris(args.redirect_uri)
    g = GraphClient(config["WORKIQ_TENANT_ID"])
    app = find_application(g, config["WORKIQ_CONNECTOR_CLIENT_ID"])
    web = app.get("web") or {}
    current = list(web.get("redirectUris") or [])
    print(f"Application: {app.get('displayName', '')} ({app['appId']})")
    print(f"Web redirects: {current or '(none)'}")

    resource = find_workiq_sp(g, config.get("WORKIQ_RESOURCE_APP_ID"))
    if resource:
        permission_entries(resource, [WORKIQ_SCOPE])
        print(f"Work IQ resource: {resource.get('displayName', '')} ({resource['appId']}); {WORKIQ_SCOPE} enabled")
    else:
        print("Exact Work IQ resource service principal is not provisioned in this tenant.")
        # A fresh tenant provisions the public resource during first consent;
        # the callback must already be registered for that consent to complete.

    merged = current + [uri for uri in redirects if uri not in current]
    if args.show or not args.apply:
        print(f"Read-only: would add {len(merged) - len(current)} explicit web redirect(s).")
        return 0
    if merged != current:
        writable = {key: web[key] for key in ("homePageUrl", "logoutUrl", "implicitGrantSettings") if key in web}
        g.call("PATCH", f"/applications/{app['id']}", {"web": {**writable, "redirectUris": merged}})
    print("Web redirects are up to date.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
