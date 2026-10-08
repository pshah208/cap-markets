"""Validated configuration and tenant-bound Graph access for Work IQ admin tools.

Only the Python standard library is required. Importing this module does not
discover credentials, locate Azure CLI, authenticate, or contact any service.
"""

from __future__ import annotations

import copy
import json
import os
from uuid import UUID

GRAPH_RESOURCE = "https://graph.microsoft.com"
GRAPH = f"{GRAPH_RESOURCE}/v1.0"
GRAPH_APP_ID = "00000003-0000-0000-c000-000000000000"


def _uuid(name: str, value: str) -> str:
    try:
        return str(UUID(value))
    except (ValueError, AttributeError) as exc:
        raise ValueError(f"{name} must be an explicit tenant/application UUID") from exc


def load_config(*required: str, optional: tuple[str, ...] = ()) -> dict[str, str]:
    """Validate all settings before callers construct a client or perform I/O."""
    names = ("WORKIQ_TENANT_ID", *required)
    missing = [name for name in names if not os.environ.get(name, "").strip()]
    if missing:
        raise ValueError("Required environment variables: " + ", ".join(missing))
    config = {}
    for name in (*names, *optional):
        if name not in os.environ and name not in names:
            continue
        value = os.environ.get(name, "").strip()
        if not value:
            raise ValueError(f"{name} must not be empty")
        if name.endswith("_ID"):
            value = _uuid(name, value)
        elif len(value) > 256 or any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise ValueError(f"{name} must be a name of at most 256 characters without controls")
        config[name] = value
    return config


def validate_redirect_uris(uris: list[str]) -> list[str]:
    from urllib.parse import urlsplit

    result = []
    for uri in uris:
        if len(uri) > 256:
            raise ValueError(f"Invalid redirect URI: {uri!r}; must be at most 256 characters")
        try:
            parsed = urlsplit(uri)
            valid = (
                uri == uri.strip()
                and not any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in uri)
                and "\\" not in uri
                and bool(parsed.hostname)
                and ":" not in parsed.hostname
                and not parsed.username
                and not parsed.password
                and not parsed.fragment
                and (
                    parsed.scheme == "https"
                    or (parsed.scheme == "http" and parsed.hostname in ("localhost", "127.0.0.1"))
                )
            )
            parsed.port
        except ValueError:
            valid = False
        if not valid:
            raise ValueError(
                f"Invalid redirect URI: {uri!r}; use HTTPS or HTTP localhost/127.0.0.1 "
                "without a fragment; Entra does not support IPv6 redirects"
            )
        if uri not in result:
            result.append(uri)
    return result


def odata_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


class GraphClient:
    def __init__(self, tenant_id: str) -> None:
        self.tenant_id = _uuid("WORKIQ_TENANT_ID", tenant_id)
        self._access_token = None

    def _token(self) -> str:
        import shutil
        import subprocess

        executable = shutil.which("az")
        if not executable:
            raise RuntimeError("Azure CLI is required; install it and sign in to the configured tenant")
        result = subprocess.run(
            [executable, "account", "get-access-token", "--tenant", self.tenant_id,
             "--resource", GRAPH_RESOURCE, "--output", "json"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            shell=False, timeout=90,
        )
        if result.returncode:
            raise RuntimeError(
                f"Azure CLI could not obtain a Graph token for tenant {self.tenant_id}; "
                "sign in to that tenant and verify admin permissions"
            )
        try:
            payload = json.loads(result.stdout)
            tenant = _uuid("token tenant", payload.get("tenant", ""))
            access_token = payload["accessToken"]
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            raise RuntimeError("Azure CLI returned an invalid tenant-bound token response") from exc
        if tenant != self.tenant_id or not isinstance(access_token, str) or not access_token.strip():
            raise RuntimeError("Azure CLI token is empty or belongs to a different tenant")
        return access_token

    def _url(self, path: str) -> str:
        from urllib.parse import urlsplit

        url = f"{GRAPH}{path}" if path.startswith("/") else path
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or parsed.netloc != "graph.microsoft.com"
            or not parsed.path.startswith("/v1.0/")
            or parsed.fragment
        ):
            raise ValueError("Graph requests and pagination must stay on https://graph.microsoft.com/v1.0/")
        return url

    def call(self, method: str, path: str, body: dict | None = None,
             ok: tuple[int, ...] = (200, 201, 204)):
        from urllib.error import HTTPError, URLError
        from urllib.request import HTTPRedirectHandler, Request, build_opener

        url = self._url(path)
        data = json.dumps(body).encode("utf-8") if body is not None else None
        if self._access_token is None:
            self._access_token = self._token()

        class NoRedirect(HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                raise RuntimeError("Graph HTTP redirects are refused to protect the bearer token")

        request = Request(
            url, data=data, method=method.upper(),
            headers={"Authorization": f"Bearer {self._access_token}",
                     "Content-Type": "application/json", "Accept": "application/json"},
        )
        try:
            with build_opener(NoRedirect()).open(request, timeout=90) as response:
                if response.status not in ok:
                    raise RuntimeError(f"Graph {method.upper()} failed with HTTP {response.status}")
                content = response.read()
                return json.loads(content) if content else None
        except HTTPError as exc:
            raise RuntimeError(f"Graph {method.upper()} failed with HTTP {exc.code}") from exc
        except URLError as exc:
            raise RuntimeError(f"Graph {method.upper()} could not reach the service") from exc

    def collection(self, path: str, filter_expr: str | None = None,
                   select: str | None = None) -> list[dict]:
        from urllib.parse import urlencode

        query = {}
        if filter_expr is not None:
            query["$filter"] = filter_expr
        if select is not None:
            query["$select"] = select
        if query:
            path += ("&" if "?" in path else "?") + urlencode(query)
        values, seen = [], set()
        while path:
            url = self._url(path)
            if url in seen:
                raise RuntimeError("Graph returned a repeated pagination link")
            seen.add(url)
            page = self.call("GET", path)
            if not isinstance(page, dict) or not isinstance(page.get("value"), list):
                raise RuntimeError("Graph returned an invalid collection")
            values.extend(page["value"])
            path = page.get("@odata.nextLink")
        return values


def find_unique(g: GraphClient, path: str, filter_expr: str, description: str,
                *, required: bool = True, select: str | None = None) -> dict | None:
    matches = g.collection(path, filter_expr, select)
    if len(matches) > 1:
        raise RuntimeError(f"Ambiguous {description}: found {len(matches)} exact matches; resolve duplicates")
    if not matches:
        if required:
            raise RuntimeError(f"{description} not found in the configured tenant")
        return None
    return matches[0]


def find_application(g: GraphClient, app_id: str) -> dict:
    return find_unique(g, "/applications", f"appId eq {odata_literal(app_id)}",
                       f"application with appId {app_id}")


def find_service_principal(g: GraphClient, app_id: str, *, required: bool = True) -> dict | None:
    return find_unique(g, "/servicePrincipals", f"appId eq {odata_literal(app_id)}",
                       f"service principal with appId {app_id}", required=required)


def permission_entries(resource: dict, names: list[str], *, application: bool = False) -> list[dict]:
    key = "appRoles" if application else "oauth2PermissionScopes"
    available = {}
    for entry in resource.get(key, []):
        if entry.get("isEnabled") is not True:
            continue
        if application and "Application" not in entry.get("allowedMemberTypes", []):
            continue
        available.setdefault(entry.get("value"), []).append(entry.get("id"))
    missing = [name for name in names if not available.get(name)]
    ambiguous = [name for name in names if len(available.get(name, [])) > 1]
    if missing or ambiguous:
        raise RuntimeError(
            f"Required {'application roles' if application else 'delegated scopes'} "
            f"on {resource.get('displayName', resource.get('appId', 'resource'))} "
            f"are missing/disabled: {', '.join(missing) or '(none)'}; "
            f"ambiguous: {', '.join(ambiguous) or '(none)'}. No changes made."
        )
    if any(not available[name][0] for name in names):
        raise RuntimeError("Required permission has no ID; no changes made")
    return [{"id": available[name][0], "type": "Role" if application else "Scope"} for name in names]


def merge_resource_access(app: dict, resource_app_id: str, additions: list[dict]) -> list[dict]:
    blocks = copy.deepcopy(app.get("requiredResourceAccess") or [])
    matching = [b for b in blocks if b["resourceAppId"].lower() == resource_app_id.lower()]
    if not matching:
        block = {"resourceAppId": resource_app_id, "resourceAccess": []}
        blocks.append(block)
        matching = [block]
    have = {(a["id"], a["type"]) for b in matching for a in b.get("resourceAccess", [])}
    for addition in additions:
        identity = (addition["id"], addition["type"])
        if identity not in have:
            matching[0].setdefault("resourceAccess", []).append(copy.deepcopy(addition))
            have.add(identity)
    return blocks


def find_tenant_grant(g: GraphClient, client_sp_id: str, resource_sp_id: str) -> dict | None:
    # Graph supports clientId filtering here, but not resourceId filtering.
    grants = g.collection("/oauth2PermissionGrants", f"clientId eq {odata_literal(client_sp_id)}")
    matches = [
        grant for grant in grants
        if grant.get("clientId") == client_sp_id and grant.get("resourceId") == resource_sp_id
        and grant.get("consentType") == "AllPrincipals"
    ]
    if len(matches) > 1:
        raise RuntimeError("Ambiguous AllPrincipals delegated consent grant; resolve duplicates")
    return matches[0] if matches else None


def write_tenant_grant(g: GraphClient, client_sp_id: str, resource_sp_id: str,
                       names: list[str], existing: dict | None) -> None:
    wanted = set(names)
    if existing:
        if existing.get("consentType") != "AllPrincipals":
            raise RuntimeError("Refusing to modify a per-user consent grant")
        current = set(existing.get("scope", "").split())
        if not wanted.issubset(current):
            g.call("PATCH", f"/oauth2PermissionGrants/{existing['id']}",
                   {"scope": " ".join(sorted(current | wanted))})
    else:
        g.call("POST", "/oauth2PermissionGrants", {
            "clientId": client_sp_id, "consentType": "AllPrincipals",
            "resourceId": resource_sp_id, "scope": " ".join(names),
        })


def configure_delegated_permissions(g: GraphClient, app: dict, resource: dict,
                                    names: list[str], *, apply: bool) -> None:
    additions = permission_entries(resource, names)
    merged = merge_resource_access(app, resource["appId"], additions)
    client_sp = find_service_principal(g, app["appId"], required=False)
    grant = find_tenant_grant(g, client_sp["id"], resource["id"]) if client_sp else None
    if grant and grant.get("consentType") != "AllPrincipals":
        raise RuntimeError("Expected an AllPrincipals consent grant; no changes made")
    print(f"Delegated scopes: {', '.join(names)}")
    if not apply:
        print("Read-only: would merge application permissions and tenant-wide admin consent. Use --apply.")
        return
    if merged != (app.get("requiredResourceAccess") or []):
        g.call("PATCH", f"/applications/{app['id']}", {"requiredResourceAccess": merged})
    if not client_sp:
        client_sp = g.call("POST", "/servicePrincipals", {"appId": app["appId"]})
    write_tenant_grant(g, client_sp["id"], resource["id"], names, grant)
    print("Application permissions and AllPrincipals admin consent are up to date.")
