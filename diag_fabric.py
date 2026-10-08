"""Read semantic-model metadata/history and execute two Power BI REST queries.

Requires FABRIC_WORKSPACE_ID and FABRIC_SEMANTIC_MODEL_ID (canonical GUIDs),
DIAG_FABRIC_QUERY (a nonblank, explicitly selected DAX query), and the
AZURE_AUTH_MODE profile from agent.portability. Always runs a generic ROW smoke
query followed by DIAG_FABRIC_QUERY; DAX syntax is validated by the service.
No .env is loaded. No configuration, authentication or I/O occurs on import.
Success checks only these calls, not the health of every model/capacity workload.
"""
from __future__ import annotations

import sys
import time
import uuid

from agent.portability import ConfigurationError, build_credential, load_auth_config, require_environment
from diagnostic_auth import validate_auth_identifiers


API = "https://api.powerbi.com/v1.0/myorg"
SCOPE = "https://analysis.windows.net/powerbi/api/.default"
SMOKE_QUERY = 'EVALUATE ROW("ok", 1)'


class DiagnosticError(RuntimeError):
    """A REST call or query result failed validation."""


def load_config() -> dict[str, str]:
    config = require_environment("FABRIC_WORKSPACE_ID", "FABRIC_SEMANTIC_MODEL_ID", "DIAG_FABRIC_QUERY")
    for name in ("FABRIC_WORKSPACE_ID", "FABRIC_SEMANTIC_MODEL_ID"):
        try:
            valid = str(uuid.UUID(config[name])) == config[name].lower()
        except ValueError:
            valid = False
        if not valid:
            raise ConfigurationError(f"{name} must be a canonical GUID")
    config.update(load_auth_config())
    validate_auth_identifiers(config)
    return config


def token(config: dict[str, str]) -> str:
    credential = build_credential(config)
    try:
        value = credential.get_token(SCOPE).token
        if not value:
            raise DiagnosticError("The selected Azure credential returned an empty Power BI token")
        return value
    finally:
        credential.close()


def read_object(response, label: str) -> dict:
    if response.status_code != 200:
        raise DiagnosticError(f"{label}: HTTP {response.status_code}")
    try:
        body = response.json()
    except ValueError:
        raise DiagnosticError(f"{label}: malformed JSON") from None
    if not isinstance(body, dict) or "error" in body:
        raise DiagnosticError(f"{label}: service error or malformed object")
    return body


def query_rows(body: dict) -> list[dict]:
    results = body.get("results")
    if not isinstance(results, list) or len(results) != 1:
        raise DiagnosticError("executeQueries: expected exactly one result")
    rows = []
    for result in results:
        if not isinstance(result, dict) or "error" in result:
            raise DiagnosticError("executeQueries: result-level error or malformed result")
        tables = result.get("tables")
        if not isinstance(tables, list) or not tables:
            raise DiagnosticError("executeQueries: missing tables")
        for table in tables:
            if not isinstance(table, dict) or "error" in table:
                raise DiagnosticError("executeQueries: table-level error or malformed table")
            table_rows = table.get("rows")
            if not isinstance(table_rows, list) or any(not isinstance(row, dict) for row in table_rows):
                raise DiagnosticError("executeQueries: malformed rows")
            rows.extend(table_rows)
    return rows


def execute_query(http, url: str, headers: dict, label: str, dax: str) -> None:
    body = {"queries": [{"query": dax}], "serializerSettings": {"includeNulls": True}}
    for attempt in range(3):
        with http.post(
            f"{url}/executeQueries", headers=headers, json=body,
            timeout=(30, 180), allow_redirects=False,
        ) as response:
            status = response.status_code
            if status not in (429, 503):
                rows = query_rows(read_object(response, "executeQueries"))
                if label == "smoke" and rows != [{"[ok]": 1}]:
                    raise DiagnosticError("smoke: expected exactly one [ok]=1 row")
                print(f"[{label}] OK: {len(rows)} row(s)")
                return
        if attempt == 2:
            raise DiagnosticError(f"{label}: HTTP {status}; retries exhausted")
        wait = 5 * (attempt + 1)
        print(f"[{label}] HTTP {status}; retry in {wait}s")
        time.sleep(wait)


def run_checks(http, config: dict[str, str], access_token: str) -> int:
    url = f"{API}/groups/{config['FABRIC_WORKSPACE_ID']}/datasets/{config['FABRIC_SEMANTIC_MODEL_ID']}"
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    failures = 0
    for label, suffix in (("metadata", ""), ("refresh history", "/refreshes?$top=3")):
        try:
            with http.get(
                url + suffix, headers=headers, timeout=(30, 90), allow_redirects=False,
            ) as response:
                body = read_object(response, label)
            if label == "metadata":
                if (not isinstance(body.get("id"), str)
                        or body["id"].lower() != config["FABRIC_SEMANTIC_MODEL_ID"].lower()
                        or not isinstance(body.get("name"), str) or not body["name"].strip()):
                    raise DiagnosticError("metadata: missing name or mismatched dataset id")
                print("Dataset metadata: OK")
            else:
                history = body.get("value")
                if (not isinstance(history, list)
                        or any(not isinstance(entry, dict) or "error" in entry
                               or not isinstance(entry.get("status"), str) for entry in history)):
                    raise DiagnosticError("refresh history: malformed entries")
                print(f"Refresh history: OK ({len(history)} entries)")
                # Historical refresh failures are reported, not confused with a failed REST call.
                for entry in history:
                    status = entry["status"]
                    print("  refresh status: " + (
                        status if status in ("Completed", "Failed", "Cancelled", "Disabled", "Unknown")
                        else "other"
                    ))
        except DiagnosticError as error:
            print(f"FAIL: {error}", file=sys.stderr)
            failures += 1

    for label, dax in (("smoke", SMOKE_QUERY), ("configured", config["DIAG_FABRIC_QUERY"])):
        try:
            execute_query(http, url, headers, label, dax)
        except DiagnosticError as error:
            print(f"[{label}] FAIL: {error}", file=sys.stderr)
            failures += 1
    return 1 if failures else 0


def main() -> int:
    try:
        config = load_config()
    except ConfigurationError as error:
        print(f"Configuration error: {error}", file=sys.stderr)
        return 2

    import requests
    from azure.core.exceptions import AzureError

    try:
        access_token = token(config)
    except DiagnosticError as error:
        print(f"Fabric authentication failed: {error}", file=sys.stderr)
        return 1
    except AzureError as error:
        print(f"Fabric authentication failed ({type(error).__name__})", file=sys.stderr)
        return 1
    try:
        return run_checks(requests, config, access_token)
    except requests.RequestException as error:
        print(f"Fabric transport failed ({type(error).__name__})", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
