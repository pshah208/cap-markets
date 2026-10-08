"""Explicit, side-effect-free configuration for the Work IQ seeders.

Required: WORKIQ_TENANT_ID and WORKIQ_USER_MAPPING_FILE.
App/device auth also requires WORKIQ_CLIENT_ID; app auth requires
WORKIQ_CLIENT_SECRET. Mapping/restore operations require WORKIQ_RESTORE_FILE.
The mapping JSON must explicitly identify driver_alias and every used account.
Relative configuration paths are resolved against the caller's working directory.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID


class ConfigurationError(ValueError):
    """Configuration must be corrected before authentication or writes."""


def read_object(path: Path, setting: str) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ConfigurationError(f"{setting}: supply a readable JSON object at {path}") from exc
    if not isinstance(data, dict):
        raise ConfigurationError(f"{setting}: expected a JSON object at {path}")
    return data


def _uuid(name: str, value: str) -> str:
    try:
        return str(UUID(value))
    except (ValueError, AttributeError, TypeError) as exc:
        raise ConfigurationError(f"{name} must be a tenant/application UUID") from exc


def _upn(value: object) -> bool:
    if not isinstance(value, str) or value.count("@") != 1:
        return False
    local, domain = value.split("@")
    return bool(local and "." in domain and not any(
        c.isspace() or c in "/\\?#'\"" for c in value
    ))


@dataclass(frozen=True)
class SeederConfig:
    tenant_id: str
    client_id: str | None
    client_secret: str | None
    mapping_file: Path
    accounts: dict
    driver_alias: str | None
    restore_file: Path | None
    snapshot: dict

    def upn(self, alias: str) -> str:
        if alias not in self.accounts:
            raise ConfigurationError(
                f"WORKIQ_USER_MAPPING_FILE: missing mapping for alias {alias!r}; "
                "add an explicit upn (no tenant-domain fallback)"
            )
        return self.accounts[alias]["upn"]


def load_config(mode: str, *, actions: tuple[str, ...],
                onedrive_alias: str | None = None,
                mail_source: str = "emails.json",
                source_dir: Path) -> SeederConfig:
    if mode not in ("app", "device", "cli"):
        raise ConfigurationError("auth must be app, device, or cli")
    required = ["WORKIQ_TENANT_ID", "WORKIQ_USER_MAPPING_FILE"]
    if mode != "cli":
        required.append("WORKIQ_CLIENT_ID")
    if mode == "app":
        required.append("WORKIQ_CLIENT_SECRET")
    if any(action in actions for action in ("map", "restore")):
        required.append("WORKIQ_RESTORE_FILE")
    missing = [name for name in required if not os.environ.get(name, "").strip()]
    if missing:
        raise ConfigurationError("Required environment variables: " + ", ".join(missing))
    tenant = _uuid("WORKIQ_TENANT_ID", os.environ["WORKIQ_TENANT_ID"].strip())
    client = _uuid("WORKIQ_CLIENT_ID", os.environ["WORKIQ_CLIENT_ID"].strip()) if mode != "cli" else None
    secret = os.environ["WORKIQ_CLIENT_SECRET"] if mode == "app" else None
    path = Path(os.environ["WORKIQ_USER_MAPPING_FILE"].strip()).resolve()
    document = read_object(path, "WORKIQ_USER_MAPPING_FILE")
    # Existing private mappings may declare their tenant. Never use it as an
    # implicit credential default, and refuse a conflicting explicit tenant.
    if "tenant_id" in document and _uuid("mapping tenant_id", document["tenant_id"]) != tenant:
        raise ConfigurationError("WORKIQ_TENANT_ID conflicts with the mapping tenant_id")
    accounts = document.get("mapping")
    if not isinstance(accounts, dict) or not accounts:
        raise ConfigurationError("WORKIQ_USER_MAPPING_FILE must contain a nonempty mapping object")
    for alias, entry in accounts.items():
        if not alias or not isinstance(entry, dict) or not _upn(entry.get("upn")):
            raise ConfigurationError(f"WORKIQ_USER_MAPPING_FILE: {alias!r} needs an explicit valid upn")
        if "map" in actions:
            for field in ("displayName", "jobTitle", "department"):
                if not isinstance(entry.get(field), str) or not entry[field].strip():
                    raise ConfigurationError(f"Mapping alias {alias!r} requires {field} for --map-users")
    driver = document.get("driver_alias")
    if driver is not None and (not isinstance(driver, str) or not driver.strip()):
        raise ConfigurationError("WORKIQ_USER_MAPPING_FILE: driver_alias must be a nonempty alias")
    if driver and driver not in accounts:
        raise ConfigurationError("WORKIQ_USER_MAPPING_FILE: driver_alias requires an explicit upn mapping")
    if "mail" in actions and (not isinstance(driver, str) or not driver.strip()):
        raise ConfigurationError("WORKIQ_USER_MAPPING_FILE requires an explicit driver_alias for mail")
    required_aliases = set()
    if any(action in actions for action in ("mail", "teams", "check")):
        mail = read_object(source_dir / mail_source, mail_source)
        required_aliases.update(person["alias"] for person in mail["people"])
        if "mail" in actions:
            required_aliases.add(driver)
            for message in mail["emails"]:
                required_aliases.update([message["from"], *message["to"], *message.get("cc", [])])
            people = {person["alias"] for person in mail["people"]}
            for message in mail["emails"]:
                unknown = {message["from"], *message["to"], *message.get("cc", [])} - people
                if unknown:
                    raise ConfigurationError(f"{mail_source}: unknown persona aliases {sorted(unknown)}")
            if driver not in people and not (
                isinstance(accounts.get(driver, {}).get("displayName"), str)
                and accounts[driver]["displayName"].strip()
            ):
                raise ConfigurationError("The configured driver requires a mapping displayName")
    if "teams" in actions:
        teams = read_object(source_dir / "teams_messages.json", "teams_messages.json")
        owners = teams["team"]["ownerAliases"]
        if not owners:
            raise ConfigurationError("teams_messages.json requires an explicit team ownerAliases entry")
        required_aliases.update([*owners, *teams["team"]["memberAliases"]])
        authors = set()
        for channel in teams["channels"]:
            for message in channel["conversations"]:
                authors.update([message["from"], *(reply["from"] for reply in message.get("replies", []))])
        unknown = authors - {person["alias"] for person in mail["people"]}
        if unknown:
            raise ConfigurationError(f"teams_messages.json: unknown author aliases {sorted(unknown)}")
        required_aliases.update(authors)
    if onedrive_alias is not None:
        if not onedrive_alias.strip():
            raise ConfigurationError("--onedrive-alias must name an explicitly mapped user")
        required_aliases.add(onedrive_alias)
    missing_aliases = required_aliases - accounts.keys()
    if missing_aliases:
        raise ConfigurationError(
            "WORKIQ_USER_MAPPING_FILE: missing explicit upn mappings for " + ", ".join(sorted(missing_aliases))
        )
    if "map" in actions:
        targets = [entry["upn"].casefold() for entry in accounts.values()]
        if len(targets) != len(set(targets)):
            raise ConfigurationError("--map-users requires a different account for each persona")
    restore = None
    snapshot = {}
    if any(action in actions for action in ("map", "restore")):
        restore = Path(os.environ["WORKIQ_RESTORE_FILE"].strip()).resolve()
        if restore == path or restore.suffix != ".json" or not restore.parent.is_dir():
            raise ConfigurationError("WORKIQ_RESTORE_FILE must be a separate JSON path in an existing directory")
        if "restore" in actions or restore.exists():
            snapshot = read_object(restore, "WORKIQ_RESTORE_FILE")
            if not snapshot:
                raise ConfigurationError("WORKIQ_RESTORE_FILE must contain the original account properties")
            mapped_upns = {entry["upn"].casefold() for entry in accounts.values()}
            for target, original in snapshot.items():
                if not _upn(target) or target.casefold() not in mapped_upns:
                    raise ConfigurationError("WORKIQ_RESTORE_FILE contains an account absent from the mapping")
                if not isinstance(original, dict) or set(original) != {"displayName", "jobTitle", "department"}:
                    raise ConfigurationError("WORKIQ_RESTORE_FILE must contain only displayName, jobTitle, department")
                if any(value is not None and not isinstance(value, str) for value in original.values()):
                    raise ConfigurationError("WORKIQ_RESTORE_FILE account properties must be strings or null")
    return SeederConfig(tenant, client, secret, path, accounts, driver, restore, snapshot)
