"""Explicit configuration and lazy authentication shared by the agent scripts.

AZURE_AUTH_MODE selects exactly one credential, never a credential chain:
azure_cli: AZURE_TENANT_ID, AZURE_SUBSCRIPTION_ID
service_principal: AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET
managed_identity: AZURE_CLIENT_ID (user-assigned managed identity)
"""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import quote, urlsplit


class ConfigurationError(ValueError):
    """Configuration must be corrected before any external action."""


AUTH_FIELDS = {
    "azure_cli": ("AZURE_TENANT_ID", "AZURE_SUBSCRIPTION_ID"),
    "service_principal": ("AZURE_TENANT_ID", "AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET"),
    "managed_identity": ("AZURE_CLIENT_ID",),
}


def compatible_tool_choice(choice: object, tools: list[dict]) -> bool:
    if choice is None or (isinstance(choice, str) and choice in ("auto", "none", "required")):
        return True

    def retained_selection(selection: object) -> bool:
        if not isinstance(selection, dict):
            return False
        kind = selection.get("type")
        # Only these web types have SDK tool-choice shapes; Bing and GA web tools do not.
        if kind in ("web_search_preview", "web_search_preview_2025_03_11"):
            return selection.keys() == {"type"} and any(t.get("type") == kind for t in tools)
        if kind != "mcp" or selection.keys() - {"type", "server_label", "name"}:
            return False
        label, name = selection.get("server_label"), selection.get("name")
        if (not isinstance(label, str) or not label.strip()
                or (name is not None and (not isinstance(name, str) or not name.strip()))):
            return False
        tool = next((t for t in tools
                     if t.get("type") == "mcp" and t.get("server_label") == label), None)
        if tool is None:
            return False
        allowed = tool.get("allowed_tools")
        if isinstance(allowed, dict):
            allowed = allowed.get("tool_names")
        return name is None or allowed is None or (isinstance(allowed, list) and name in allowed)

    if isinstance(choice, dict) and choice.get("type") == "allowed_tools":
        selections = choice.get("tools")
        return (not (choice.keys() - {"type", "mode", "tools"})
                and choice.get("mode") in ("auto", "required")
                and isinstance(selections, list) and bool(selections)
                and all(retained_selection(selection) for selection in selections))
    return retained_selection(choice)


def require_environment(*names: str) -> dict[str, str]:
    values = {name: os.environ.get(name, "").strip() for name in names}
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise ConfigurationError("Missing required environment variables: " + ", ".join(missing))
    return values


def require_values(values: dict[str, str], *names: str) -> None:
    missing = [name for name in names
               if not isinstance(values.get(name), str) or not values[name].strip()]
    if missing:
        raise ConfigurationError("Missing required configuration: " + ", ".join(missing))


def require_https_url(name: str, value: str) -> str:
    try:
        parts = urlsplit(value)
        valid = (parts.scheme == "https" and parts.hostname and not parts.username
                 and not parts.password and not parts.query and not parts.fragment
                 and not any(c.isspace() or c in "<>\\?#" for c in value))
        parts.port
    except ValueError:
        valid = False
    if not valid:
        raise ConfigurationError(f"{name} must be an HTTPS URL without credentials, query or fragment")
    return value.rstrip("/")


def require_file(path: str | Path, description: str) -> Path:
    path = Path(path)
    if not path.is_file():
        raise ConfigurationError(f"Missing {description} file: {path}")
    return path


def validate_auth(config: dict[str, str]) -> None:
    require_values(config, "AZURE_AUTH_MODE")
    mode = config["AZURE_AUTH_MODE"]
    if mode not in AUTH_FIELDS:
        raise ConfigurationError("AZURE_AUTH_MODE must be one of: " + ", ".join(AUTH_FIELDS))
    require_values(config, *AUTH_FIELDS[mode])


def load_auth_config() -> dict[str, str]:
    config = require_environment("AZURE_AUTH_MODE")
    mode = config["AZURE_AUTH_MODE"]
    if mode not in AUTH_FIELDS:
        raise ConfigurationError("AZURE_AUTH_MODE must be one of: " + ", ".join(AUTH_FIELDS))
    config.update(require_environment(*AUTH_FIELDS[mode]))
    return config


def load_foundry_config(*extra_names: str, require_agent: bool = True) -> dict[str, str]:
    names = ["FOUNDRY_PROJECT_ENDPOINT", *extra_names]
    if require_agent:
        names.append("FOUNDRY_AGENT_NAME")
    config = require_environment(*names)
    config["FOUNDRY_PROJECT_ENDPOINT"] = require_https_url(
        "FOUNDRY_PROJECT_ENDPOINT", config["FOUNDRY_PROJECT_ENDPOINT"])
    config.update(load_auth_config())
    return config


def build_credential(config: dict[str, str]):
    validate_auth(config)
    mode = config["AZURE_AUTH_MODE"]
    if mode == "azure_cli":
        from azure.identity import AzureCliCredential

        return AzureCliCredential(
            tenant_id=config["AZURE_TENANT_ID"], subscription=config["AZURE_SUBSCRIPTION_ID"])
    if mode == "service_principal":
        from azure.identity import ClientSecretCredential

        return ClientSecretCredential(
            tenant_id=config["AZURE_TENANT_ID"], client_id=config["AZURE_CLIENT_ID"],
            client_secret=config["AZURE_CLIENT_SECRET"])
    from azure.identity import ManagedIdentityCredential

    return ManagedIdentityCredential(client_id=config["AZURE_CLIENT_ID"])


def foundry_token(config: dict[str, str]) -> str:
    require_values(config, "FOUNDRY_PROJECT_ENDPOINT")
    require_https_url("FOUNDRY_PROJECT_ENDPOINT", config["FOUNDRY_PROJECT_ENDPOINT"])
    credential = build_credential(config)
    try:
        token = credential.get_token("https://ai.azure.com/.default").token
        if not token:
            raise RuntimeError("The selected Azure credential returned an empty Foundry token")
        return token
    finally:
        credential.close()


def agent_url(config: dict[str, str], name: str | None = None) -> str:
    require_values(config, "FOUNDRY_PROJECT_ENDPOINT")
    if name is None:
        require_values(config, "FOUNDRY_AGENT_NAME")
        name = config["FOUNDRY_AGENT_NAME"]
    if not name.strip():
        raise ConfigurationError("Agent name must not be blank")
    endpoint = require_https_url("FOUNDRY_PROJECT_ENDPOINT", config["FOUNDRY_PROJECT_ENDPOINT"])
    return f"{endpoint}/agents/{quote(name, safe='')}"
