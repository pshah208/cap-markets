"""Offline configuration and fail-closed Graph support for root diagnostics.

Export WORKIQ_TENANT_ID, WORKIQ_CLIENT_ID, WORKIQ_CLIENT_SECRET.
User audits also require WORKIQ_USER_MAPPING_FILE: copy the tracked
data\\work-iq\\user_mapping.example.json to the ignored user_mapping.json,
replace the example accounts, then explicitly select that private path.
Team audits require WORKIQ_TEAM_ID. Leakage audits require
WORKIQ_FORBIDDEN_TERMS, a nonempty JSON array of literal cross-demo terms.
No tenant identities, ignored filenames, people or branding are built in.
No .env, credentials, mapping or service is accessed on import.
"""
from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, urlsplit
from uuid import UUID

WORKIQ_DIR = Path(__file__).resolve().parent / "data" / "work-iq"
if str(WORKIQ_DIR) not in sys.path:
    sys.path.insert(0, str(WORKIQ_DIR))
from workiq_config import ConfigurationError, load_config, read_object

GRAPH = "https://graph.microsoft.com/v1.0"


class AuditError(RuntimeError):
    """A read or mutation could not be verified; the result is inconclusive."""


def required_environment(*names: str) -> dict[str, str]:
    values = {name: os.environ.get(name, "").strip() for name in names}
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise ConfigurationError("Required environment variables: " + ", ".join(missing))
    return values


def guid(name: str, value: str) -> str:
    try:
        result = str(UUID(value))
    except (ValueError, AttributeError, TypeError):
        raise ConfigurationError(f"{name} must be a canonical GUID") from None
    if result != value.lower():
        raise ConfigurationError(f"{name} must be a canonical GUID")
    return result


def string_list(name: str, value: str) -> tuple[str, ...]:
    try:
        values = json.loads(value)
    except ValueError:
        raise ConfigurationError(f"{name} must be a nonempty JSON array of strings") from None
    if (not isinstance(values, list) or not values
            or any(not isinstance(item, str) or not item.strip()
                   or any(ord(char) < 32 for char in item) for item in values)):
        raise ConfigurationError(f"{name} must be a nonempty JSON array of nonblank strings")
    return tuple(dict.fromkeys(item.strip() for item in values))


@dataclass(frozen=True)
class AuditConfig:
    tenant_id: str
    client_id: str
    client_secret: str
    users: tuple[tuple[str, str], ...]
    team_id: str | None
    forbidden_terms: tuple[str, ...]


def load_audit_config(*, users: bool = True, team: bool = False,
                      forbidden: bool = True, extra: tuple[str, ...] = ()) -> AuditConfig:
    names = ["WORKIQ_TENANT_ID", "WORKIQ_CLIENT_ID", "WORKIQ_CLIENT_SECRET", *extra]
    if users:
        names.append("WORKIQ_USER_MAPPING_FILE")
    if team:
        names.append("WORKIQ_TEAM_ID")
    if forbidden:
        names.append("WORKIQ_FORBIDDEN_TERMS")
    values = required_environment(*names)
    tenant = guid("WORKIQ_TENANT_ID", values["WORKIQ_TENANT_ID"])
    client = guid("WORKIQ_CLIENT_ID", values["WORKIQ_CLIENT_ID"])
    team_id = guid("WORKIQ_TEAM_ID", values["WORKIQ_TEAM_ID"]) if team else None
    terms = string_list("WORKIQ_FORBIDDEN_TERMS", values["WORKIQ_FORBIDDEN_TERMS"]) if forbidden else ()
    accounts = []
    if users:
        config = load_config("app", actions=(), source_dir=WORKIQ_DIR)
        if config.mapping_file.name.endswith(".example.json"):
            raise ConfigurationError("WORKIQ_USER_MAPPING_FILE must select a private mapping, not the example")
        seen = set()
        for alias in config.accounts:
            upn = config.upn(alias)
            domain = upn.split("@")[1].casefold()
            if domain in ("example.com", "example.net", "example.org") or domain.endswith((".invalid", ".example")):
                raise ConfigurationError("WORKIQ_USER_MAPPING_FILE: replace every example UPN before use")
            if upn.casefold() not in seen:
                accounts.append((alias, upn))
                seen.add(upn.casefold())
    # Preserve the secret verbatim rather than stripping its significant bytes.
    return AuditConfig(tenant, client, os.environ["WORKIQ_CLIENT_SECRET"], tuple(accounts), team_id, terms)


def object_response(response, label: str, *, statuses: tuple[int, ...] = (200,)) -> dict:
    if response.status_code not in statuses:
        raise AuditError(f"{label}: HTTP {response.status_code}")
    try:
        body = response.json()
    except ValueError:
        raise AuditError(f"{label}: malformed JSON") from None
    if not isinstance(body, dict) or "error" in body:
        raise AuditError(f"{label}: expected a JSON object without a service error")
    return body


def identifier(item: dict, field: str, label: str) -> str:
    value = item.get(field)
    if not isinstance(value, str) or not value.strip():
        raise AuditError(f"{label}: missing or invalid {field}")
    return value


def body_text(item: dict, label: str) -> str:
    body = item.get("body")
    if not isinstance(body, dict) or not isinstance(body.get("content"), str):
        raise AuditError(f"{label}: missing or invalid body.content")
    subject = item.get("subject")
    if subject is not None and not isinstance(subject, str):
        raise AuditError(f"{label}: invalid subject")
    return (subject or "") + " " + body["content"]


def graph_url(url: str) -> str:
    if not isinstance(url, str) or any(char.isspace() or char == "\\" for char in url):
        raise AuditError("Graph returned an invalid request/pagination URL")
    try:
        parts = urlsplit(url)
        valid = (parts.scheme == "https" and parts.netloc == "graph.microsoft.com"
                 and parts.path.startswith("/v1.0/") and not parts.fragment
                 and not parts.username and not parts.password)
    except ValueError:
        valid = False
    if not valid:
        raise AuditError("Refusing a request/pagination URL outside the Microsoft Graph v1.0 endpoint")
    return url


class GraphClient:
    def __init__(self, http, token: str):
        self.http = http
        self.headers = {"Authorization": f"Bearer {token}"}

    @classmethod
    def authenticate(cls, config: AuditConfig):
        import requests

        try:
            with requests.post(
                f"https://login.microsoftonline.com/{config.tenant_id}/oauth2/v2.0/token",
                data={"client_id": config.client_id, "client_secret": config.client_secret,
                      "scope": "https://graph.microsoft.com/.default", "grant_type": "client_credentials"},
                timeout=(30, 60), allow_redirects=False,
            ) as response:
                body = object_response(response, "Graph authentication")
        except requests.RequestException as error:
            raise AuditError(f"Graph authentication transport failed ({type(error).__name__})") from None
        token = identifier(body, "access_token", "Graph authentication")
        if str(body.get("token_type", "")).casefold() != "bearer":
            raise AuditError("Graph authentication: missing bearer token_type")
        return cls(requests, token)

    def get(self, url: str, label: str, *, optional_folder: bool = False) -> dict | None:
        import requests

        url = graph_url(url)
        # Only the archive folder metadata probe may interpret 404 as absence.
        if optional_folder and not urlsplit(url).path.endswith("/mailFolders/archive"):
            raise AuditError("Only archive folder metadata can be optional")
        try:
            with self.http.get(url, headers=self.headers, timeout=(30, 90),
                               allow_redirects=False) as response:
                if optional_folder and response.status_code == 404:
                    return None
                return object_response(response, label)
        except requests.RequestException as error:
            raise AuditError(f"{label}: transport failed ({type(error).__name__})") from None

    def collection(self, url: str, label: str):
        seen = set()
        while url is not None:
            url = graph_url(url)
            if url in seen:
                raise AuditError(f"{label}: pagination cycle")
            seen.add(url)
            body = self.get(url, label)
            rows = body.get("value")
            if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
                raise AuditError(f"{label}: missing or malformed collection value")
            yield from rows
            if "@odata.nextLink" in body:
                url = graph_url(body["@odata.nextLink"])
            else:
                url = None

    def move(self, url: str, destination: str, label: str) -> None:
        import requests

        url = graph_url(url)
        # Never retry an ambiguous POST: the first move may already have succeeded.
        try:
            with self.http.post(
                url, headers=self.headers, json={"destinationId": destination},
                timeout=(30, 90), allow_redirects=False,
            ) as response:
                result = object_response(response, label, statuses=(200, 201))
        except requests.RequestException as error:
            raise AuditError(f"{label}: move outcome unknown ({type(error).__name__}); re-inventory before retrying") from None
        identifier(result, "id", label)
        if result.get("parentFolderId") != destination:
            raise AuditError(f"{label}: move response did not confirm the destination folder")


def user_url(upn: str) -> str:
    return f"{GRAPH}/users/{quote(upn, safe='')}"


def folder_ids(graph: GraphClient, base: str, root: str):
    """Traverse a folder subtree without silently accepting a cycle."""
    pending = [root]
    seen = set()
    while pending:
        folder = pending.pop()
        if folder in seen:
            raise AuditError("Mail folder hierarchy contains a repeated folder id")
        seen.add(folder)
        yield folder
        for child in graph.collection(
            f"{base}/mailFolders/{quote(folder, safe='')}/childFolders?$top=100&includeHiddenFolders=true",
            "mail child folders",
        ):
            pending.append(identifier(child, "id", "mail child folder"))


def live_messages(graph: GraphClient, upn: str):
    """Audit selected live folders and descendants, never Deleted Items."""
    base = user_url(upn)
    seen = set()
    for name in ("inbox", "sentitems", "drafts", "archive"):
        metadata = graph.get(f"{base}/mailFolders/{name}?$select=id", f"{upn} {name}",
                             optional_folder=name == "archive")
        if metadata is None:
            continue
        root = identifier(metadata, "id", f"{upn} {name}")
        for folder in folder_ids(graph, base, root):
            if folder in seen:
                continue
            seen.add(folder)
            for message in graph.collection(
                f"{base}/mailFolders/{quote(folder, safe='')}/messages?$top=200&$select=id,subject,body",
                f"{upn} {name} messages",
            ):
                yield name, message


class LeakageScanner:
    def __init__(self, terms: tuple[str, ...]):
        self.patterns = [(term, re.compile(r"(?<!\w)" + re.escape(term), re.I)) for term in terms]
        self.hits: list[tuple[str, str]] = []

    def scan(self, location: str, text: str) -> None:
        for term, pattern in self.patterns:
            if pattern.search(text):
                self.hits.append((location, term))

    def report(self, scope: str) -> int:
        if self.hits:
            print(f"CROSS-DEMO MATCHES ({len(self.hits)}):")
            for location, term in self.hits:
                print(f"  [{term}] {location}")
            return 1
        print(f"CLEAN - no configured cross-demo terms in {scope}.")
        return 0


def report_error(error: ConfigurationError | AuditError) -> int:
    kind = "Configuration error" if isinstance(error, ConfigurationError) else "INCONCLUSIVE"
    print(f"{kind}: {error}", file=sys.stderr)
    return 2
