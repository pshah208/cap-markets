"""Local, side-effect-free configuration and Graph transport for infra scripts.

All entrypoints require AZURE_TENANT_ID (a nonzero tenant GUID). Authentication
uses only AzureCliCredential bound to that tenant; there is no credential chain.
azure-identity and requests are imported only after configuration validation.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from collections.abc import Mapping
from urllib.parse import quote, urlsplit

GRAPH = "https://graph.microsoft.com/v1.0"
GRAPH_SCOPE = "https://graph.microsoft.com/.default"


class ConfigurationError(ValueError):
    """A required setting is absent or unsafe."""


def environment(environ: Mapping[str, str] | None) -> Mapping[str, str]:
    return os.environ if environ is None else environ


def required(environ: Mapping[str, str], name: str) -> str:
    value = environ.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError(f"{name} is required and must not be blank.")
    return value.strip()


def guid(value: str, name: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(
        r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", value
    ) or uuid.UUID(value).int == 0:
        raise ConfigurationError(f"{name} must be a nonzero GUID.")
    return str(uuid.UUID(value))


def tenant_id(environ: Mapping[str, str]) -> str:
    return guid(required(environ, "AZURE_TENANT_ID"), "AZURE_TENANT_ID")


def app_name(environ: Mapping[str, str], name: str) -> str:
    value = required(environ, name)
    if len(value) > 256 or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ConfigurationError(f"{name} must be a display name of 1–256 characters without controls.")
    return value


def app_names(environ: Mapping[str, str]) -> tuple[str, str]:
    spa = app_name(environ, "INFRA_SPA_NAME")
    bff = app_name(environ, "INFRA_BFF_NAME")
    if spa.casefold() == bff.casefold():
        raise ConfigurationError("INFRA_SPA_NAME and INFRA_BFF_NAME must be distinct.")
    return spa, bff


def redirect_uri(value: str, name: str) -> str:
    """Allow Entra-compatible HTTPS and HTTP localhost redirects up to 256 characters."""
    if not isinstance(value, str) or not value or any(c.isspace() for c in value):
        raise ConfigurationError(f"{name} must be a nonblank redirect URI without whitespace.")
    if len(value) > 256:
        raise ConfigurationError(f"{name} must be at most 256 characters for an Entra redirect URI.")
    try:
        parsed = urlsplit(value)
        host = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be a valid redirect URI.") from exc
    if host and ":" in host:
        raise ConfigurationError(
            f"{name} must not use IPv6; Entra does not support IPv6 redirect URIs. "
            "Use localhost or 127.0.0.1 for loopback redirects."
        )
    if (
        parsed.scheme not in ("https", "http")
        or not host
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or "?" in value
        or "#" in value
        or "\\" in value
        or parsed.netloc.endswith(":")
        or any(c in value for c in '<>"^`{|}')
        or any(ord(c) < 32 or ord(c) == 127 for c in value)
        or (port is not None and port == 0)
        or (parsed.scheme == "http" and host not in ("localhost", "127.0.0.1"))
        or not valid_hostname(host)
        or re.search(r"%(?![0-9a-fA-F]{2})", value)
    ):
        raise ConfigurationError(
            f"{name} must be an absolute HTTPS URI (HTTP only for localhost, "
            "127.0.0.1), without userinfo, query or fragment."
        )
    return value


def valid_hostname(value: str) -> bool:
    return len(value) <= 253 and all(
        re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label)
        for label in value.split(".")
    )


def role_assignments(environ: Mapping[str, str], roles: set[str]) -> dict[str, str]:
    name = "INFRA_ROLE_ASSIGNMENTS"

    def unique(pairs):
        result = {}
        seen = set()
        for key, value in pairs:
            if key.casefold() in seen:
                raise ConfigurationError(f"{name} contains a duplicate UPN.")
            seen.add(key.casefold())
            result[key] = value
        return result

    try:
        assignments = json.loads(required(environ, name), object_pairs_hook=unique)
    except json.JSONDecodeError as exc:
        raise ConfigurationError(f"{name} must be a JSON object mapping full UPNs to app roles.") from exc
    if not isinstance(assignments, dict) or not assignments:
        raise ConfigurationError(f"{name} must be a nonempty JSON object mapping full UPNs to app roles.")
    for upn, role in assignments.items():
        local, separator, domain = upn.partition("@")
        if (
            not separator
            or not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+", local)
            or len(upn) > 254
            or "." not in domain
            or not valid_hostname(domain)
        ):
            raise ConfigurationError(f"{name} keys must be full, valid user principal names (not prefixes).")
        if not isinstance(role, str) or role not in roles:
            raise ConfigurationError(f"{name} values must be one of: {', '.join(sorted(roles))}.")
    return assignments


def eq_filter(field: str, value: str) -> str:
    """Escape OData string literals, then encode the complete query value."""
    return "$filter=" + quote(f"{field} eq '{value.replace(chr(39), chr(39) * 2)}'", safe="")


def single(items: list[dict], label: str) -> dict | None:
    if len(items) > 1:
        raise RuntimeError(f"Ambiguous {label}: more than one match; choose a unique configured identity.")
    return items[0] if items else None


def find_app(g: GraphClient, name: str) -> dict | None:
    return single(g.collection(f"/applications?{eq_filter('displayName', name)}"), "application display name")


def find_sp(g: GraphClient, app_id: str) -> dict | None:
    return single(g.collection(f"/servicePrincipals?{eq_filter('appId', app_id)}"), "service principal appId")


def tenant_grant(grants: list[dict], resource_id: str) -> dict | None:
    return single([
        grant for grant in grants
        if grant["resourceId"] == resource_id and grant.get("consentType") == "AllPrincipals"
    ], "tenant-wide delegated grant")


class GraphClient:
    def __init__(self, tenant: str) -> None:
        tenant = guid(tenant, "AZURE_TENANT_ID")
        from azure.identity import AzureCliCredential
        import requests

        self.credential = AzureCliCredential(tenant_id=tenant)
        self.requests = requests

    def call(self, method: str, path: str, body=None, ok=(200, 201, 204)):
        if not path.startswith("/") or path.startswith("//"):
            raise ValueError("Graph requests must use a relative /v1.0 resource path.")
        token = self.credential.get_token(GRAPH_SCOPE).token
        if not isinstance(token, str) or not token.strip():
            raise RuntimeError("AzureCliCredential returned an empty Microsoft Graph token.")
        response = self.requests.request(
            method, f"{GRAPH}{path}",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=body, timeout=90, allow_redirects=False,
        )
        if response.status_code not in ok:
            raise RuntimeError(f"{method} {path} -> {response.status_code}: {response.text[:600]}")
        if response.content and "json" in response.headers.get("Content-Type", "").lower():
            return response.json()
        return None

    def collection(self, path: str) -> list[dict]:
        items = []
        seen = set()
        while path:
            if path in seen:
                raise RuntimeError("Microsoft Graph returned a repeated pagination link.")
            seen.add(path)
            result = self.call("GET", path)
            items.extend(result["value"])
            link = result.get("@odata.nextLink")
            if link and (not isinstance(link, str) or not link.startswith(f"{GRAPH}/")):
                raise RuntimeError("Microsoft Graph returned a pagination link outside the public v1.0 API.")
            path = link[len(GRAPH):] if link else None
        return items
