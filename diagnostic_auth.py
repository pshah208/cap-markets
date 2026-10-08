"""Local identifier validation layered over the shared explicit Azure profile."""
from __future__ import annotations

from uuid import UUID

from agent.portability import AUTH_FIELDS, ConfigurationError, validate_auth


def validate_auth_identifiers(config: dict[str, str]) -> None:
    validate_auth(config)
    for name in AUTH_FIELDS[config["AZURE_AUTH_MODE"]]:
        if not name.endswith("_ID"):
            continue
        try:
            valid = str(UUID(config[name])) == config[name].lower()
        except (ValueError, AttributeError, TypeError):
            valid = False
        if not valid:
            raise ConfigurationError(f"{name} must be a canonical GUID")
