"""Pause / resume the Fabric capacity behind Fabric IQ, from the top bar.

An F-SKU bills by the hour whether or not anyone is querying it, so the demo
needs an off switch that does not require the Azure portal. Calls go to ARM with
the app's managed identity, which holds a custom role scoped to this one
capacity that can only read, suspend and resume it (see
infra/modules/fabric-capacity-control.bicep).

Pausing takes Fabric IQ offline for every user, so every state change is logged
with the signed-in user's UPN, and FABRIC_CAPACITY_OPERATORS can restrict who
may change it (comma-separated UPNs; empty = any signed-in user, which is fine
because sign-in already requires an app-role assignment).
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

from .config import settings

logger = logging.getLogger("bff.fabric_capacity")

ARM = "https://management.azure.com"
ARM_SCOPE = "https://management.azure.com/.default"
API = "2023-11-01"

# ARM states, mapped to what the UI shows.
_STEADY = {"Active": "active", "Paused": "paused"}
_TRANSIENT = {"Resuming": "resuming", "Pausing": "pausing", "Provisioning": "resuming",
              "Updating": "resuming", "Deleting": "pausing"}

_token: tuple[str, float] | None = None
_lock = asyncio.Lock()


async def _access_token() -> str:
    global _token
    if settings.mock_mode:
        raise PermissionError("Fabric capacity access is disabled in MOCK_MODE.")
    error = settings.fabric_capacity_config_error()
    if error:
        raise PermissionError(error)
    async with _lock:
        if _token and _token[1] - 120 > time.time():
            return _token[0]

        def fetch():
            from azure.identity import DefaultAzureCredential
            cred = DefaultAzureCredential()
            try:
                return cred.get_token(ARM_SCOPE)
            finally:
                cred.close()

        tok = await asyncio.to_thread(fetch)
        _token = (tok.token, float(tok.expires_on))
        return tok.token


def can_operate(upn: str) -> bool:
    if settings.mock_mode or settings.fabric_capacity_config_error() or not (upn or "").strip():
        return False
    operators = settings.fabric_capacity_operators
    return not operators or upn.strip().lower() in operators


def _shape(body: dict[str, Any], upn: str) -> dict[str, Any]:
    raw = (body.get("properties") or {}).get("state", "Unknown")
    return {
        "configured": True,
        "name": body.get("name") or settings.fabric_capacity_id.rsplit("/", 1)[-1],
        "sku": (body.get("sku") or {}).get("name", ""),
        "region": body.get("location", ""),
        "rawState": raw,
        "state": _STEADY.get(raw) or _TRANSIENT.get(raw) or "unknown",
        "canOperate": can_operate(upn),
    }


async def status(upn: str) -> dict[str, Any]:
    error = ("Fabric capacity access is disabled in MOCK_MODE." if settings.mock_mode
             else settings.fabric_capacity_config_error())
    if error:
        return {"configured": False, "state": "unknown", "canOperate": False, "error": error}
    try:
        token = await _access_token()
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(f"{ARM}{settings.fabric_capacity_id}?api-version={API}",
                                 headers={"Authorization": f"Bearer {token}"})
        if r.status_code != 200:
            logger.warning("capacity status %s: %s", r.status_code, r.text[:300])
            return {"configured": True, "state": "unknown", "canOperate": False,
                    "error": f"ARM {r.status_code}"}
        return _shape(r.json(), upn)
    except Exception as exc:  # noqa: BLE001
        logger.warning("capacity status failed: %s", str(exc)[:300])
        return {"configured": True, "state": "unknown", "canOperate": False,
                "error": "Capacity status unavailable"}


async def change(action: str, upn: str) -> dict[str, Any]:
    """Start a suspend or resume. ARM returns 202 and completes asynchronously."""
    if action not in ("suspend", "resume"):
        raise ValueError("action must be suspend or resume")
    if settings.mock_mode:
        raise PermissionError("Fabric capacity changes are disabled in MOCK_MODE.")
    error = settings.fabric_capacity_config_error()
    if error:
        raise PermissionError(error)
    if not can_operate(upn):
        raise PermissionError("You are not permitted to change the Fabric capacity.")

    token = await _access_token()
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(f"{ARM}{settings.fabric_capacity_id}/{action}?api-version={API}",
                              headers={"Authorization": f"Bearer {token}"})
    logger.info("fabric capacity %s requested by %s -> %s", action, upn, r.status_code)
    if r.status_code not in (200, 202):
        # A suspend on an already-paused capacity (or the reverse) is a 400 from
        # ARM; report the real state rather than an error.
        if r.status_code == 400:
            current = await status(upn)
            desired = "paused" if action == "suspend" else "active"
            if current.get("state") == desired:
                return {**current, "note": r.text[:200]}
        raise RuntimeError(f"ARM {r.status_code}: {r.text[:300]}")

    current = await status(upn)
    # ARM can report the old steady state for a moment after accepting; show the
    # transition the user asked for so the UI does not appear to ignore the click.
    if current.get("state") in ("active", "paused"):
        current["state"] = "pausing" if action == "suspend" else "resuming"
    return current
