"""Configuration for the Bank's Capital Markets Client Intelligence BFF."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from urllib.parse import unquote, urlsplit


def _split(v: str) -> list[str]:
    return [x.strip() for x in v.split(",") if x.strip()]


def _env_days(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
        if value > 0:
            return value
    except ValueError:
        pass
    raise ValueError(f"{name} must be a positive integer.") from None


def _valid_https_endpoint(value: str) -> bool:
    if not value or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in value):
        return False
    if any(c in value for c in ("\\", "?", "#")):
        return False
    try:
        parsed = urlsplit(value)
        return bool(
            parsed.scheme == "https" and parsed.hostname and parsed.netloc
            and "%" not in parsed.netloc and not parsed.netloc.endswith(":")
            and parsed.username is None and parsed.password is None
            and (parsed.port is None or 0 < parsed.port <= 65535)
        )
    except ValueError:
        return False


def _valid_arm_path(value: str) -> bool:
    decoded = unquote(value)
    parts = decoded.split("/")[1:]
    return bool(
        re.fullmatch(r"/(?:subscriptions|providers)/[^?#\\\s]+", decoded, re.I)
        and len(parts) % 2 == 0
        and all(part not in ("", ".", "..") for part in parts)
    )


@dataclass(repr=False)
class Settings:
    # --- Entra / auth ---
    tenant_id: str = field(default_factory=lambda: os.getenv("AAD_TENANT_ID", ""))
    client_id: str = field(default_factory=lambda: os.getenv("AAD_CLIENT_ID", ""))
    client_secret: str = field(default_factory=lambda: os.getenv("AAD_CLIENT_SECRET", ""), repr=False)
    api_scope: str = field(default_factory=lambda: os.getenv("AAD_API_SCOPE", ""))

    # Downstream scope the OBO exchange targets. Foundry data plane.
    foundry_scope: str = field(default_factory=lambda: os.getenv(
        "FOUNDRY_SCOPE", "https://ai.azure.com/.default"
    ))

    # --- Foundry ---
    project_endpoint: str = field(default_factory=lambda: os.getenv("FOUNDRY_PROJECT_ENDPOINT", ""))
    agent_name: str = field(default_factory=lambda: os.getenv("FOUNDRY_AGENT_NAME", ""))
    scenario_agent_name: str = field(default_factory=lambda: os.getenv("SCENARIO_AGENT_NAME", ""))
    mission_agent_name: str = field(default_factory=lambda: os.getenv("MISSION_AGENT_NAME", ""))
    barrier_agent_name: str = field(default_factory=lambda: os.getenv("BARRIER_AGENT_NAME", ""))
    # Compatibility only: the Responses API selects agents by name, not ID.
    agent_id: str = field(default_factory=lambda: os.getenv("FOUNDRY_AGENT_ID", ""))

    # --- telemetry (chapter 12) ---
    # Customer id (GUID) of the Log Analytics workspace behind the Application
    # Insights component connected to the Foundry project. Empty disables the
    # agent-economics slide rather than letting it invent numbers.
    log_analytics_workspace_id: str = field(default_factory=lambda: os.getenv("LOG_ANALYTICS_WORKSPACE_ID", ""))
    telemetry_window_days: int = field(default_factory=lambda: _env_days("TELEMETRY_WINDOW_DAYS", 7))

    # ARM scope Cost Management is queried at, for the billed-cost panel.
    # Normally the resource group the demo runs in.
    cost_scope: str = field(default_factory=lambda: os.getenv("COST_SCOPE", ""))
    cost_window_days: int = field(default_factory=lambda: _env_days("COST_WINDOW_DAYS", 30))

    fabric_capacity_id: str = field(default_factory=lambda: os.getenv("FABRIC_CAPACITY_ID", "").strip())
    fabric_capacity_operators: set[str] = field(
        default_factory=lambda: {u.lower() for u in _split(os.getenv("FABRIC_CAPACITY_OPERATORS", ""))}
    )

    # --- behaviour ---
    # Compatibility setting only. Delegated agent calls never fall back to an
    # app identity, which cannot represent the user's Work IQ permissions.
    allow_app_identity_fallback: bool = field(default_factory=lambda:
        os.getenv("ALLOW_APP_IDENTITY_FALLBACK", "false").lower() == "true"
    )
    mock_mode: bool = field(default_factory=lambda: os.getenv("MOCK_MODE", "false").lower() == "true")

    cors_origins: list[str] = field(
        default_factory=lambda: _split(
            os.getenv("CORS_ORIGINS", "http://localhost:5173")
        )
    )

    @property
    def authority(self) -> str:
        return f"https://login.microsoftonline.com/{self.tenant_id}"

    @property
    def issuers(self) -> tuple[str, ...]:
        return (
            f"https://login.microsoftonline.com/{self.tenant_id}/v2.0",
            f"https://sts.windows.net/{self.tenant_id}/",
        )

    @property
    def jwks_uri(self) -> str:
        return f"{self.authority}/discovery/v2.0/keys"

    @property
    def audiences(self) -> tuple[str, ...]:
        # v2 tokens carry the bare client id; v1 tokens carry api://<client-id>.
        return (self.client_id, f"api://{self.client_id}")

    def configured(self) -> bool:
        """Whether delegated auth is configured; independent of mock mode."""
        return not self.auth_config_error()

    def auth_config_error(self, *, require_secret: bool = True) -> str:
        for name, value in (("AAD_TENANT_ID", self.tenant_id), ("AAD_CLIENT_ID", self.client_id)):
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", value) or value in (".", ".."):
                return f"Set {name} to a valid identifier, not a URL or path."
        if require_secret and not self.client_secret.strip():
            return "Set AAD_CLIENT_SECRET on the BFF."
        return ""

    def project_config_error(self) -> str:
        if not _valid_https_endpoint(self.project_endpoint):
            return ("Set FOUNDRY_PROJECT_ENDPOINT to an absolute HTTPS project URL "
                    "without userinfo, query or fragment.")
        return ""

    def agent_config_error(self, agent_name: str | None = None) -> str:
        name = self.agent_name if agent_name is None else agent_name
        if not name.strip():
            return ("Set FOUNDRY_AGENT_NAME or the explicitly selected "
                    "SCENARIO_AGENT_NAME, MISSION_AGENT_NAME or BARRIER_AGENT_NAME.")
        return self.project_config_error()

    def agent_configured(self, agent_name: str | None = None) -> bool:
        """Endpoint + selected name readiness; an explicit empty override fails."""
        return not self.agent_config_error(agent_name)

    def require_agent_configured(self, agent_name: str | None = None) -> str:
        error = self.agent_config_error(agent_name)
        if error:
            raise ValueError(error)
        return self.agent_name if agent_name is None else agent_name

    def cost_config_error(self) -> str:
        if not _valid_arm_path(self.cost_scope):
            return "Set COST_SCOPE to an ARM subscription, resource-group or billing scope path."
        if self.cost_window_days <= 0:
            return "COST_WINDOW_DAYS must be a positive integer."
        return ""

    def telemetry_config_error(self) -> str:
        if not re.fullmatch(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}",
                            self.log_analytics_workspace_id):
            return "Set LOG_ANALYTICS_WORKSPACE_ID to the workspace customer ID (GUID)."
        if self.telemetry_window_days <= 0:
            return "TELEMETRY_WINDOW_DAYS must be a positive integer."
        return ""

    def fabric_capacity_config_error(self) -> str:
        if not _valid_arm_path(self.fabric_capacity_id) or not re.fullmatch(
            r"/subscriptions/[^/]+/resourceGroups/[^/]+/providers/Microsoft\.Fabric/capacities/[^/]+",
            self.fabric_capacity_id, re.I,
        ):
            return "Set FABRIC_CAPACITY_ID to the ARM resource ID of a Microsoft.Fabric capacity."
        return ""


settings = Settings()
