"""Configuration and service boundaries; no live credentials or transports."""

import asyncio
import importlib
import json
import os
import time
from dataclasses import MISSING, fields, replace
from unittest.mock import AsyncMock, patch

from tests.offline import OfflineAsyncTestCase, OfflineTestCase


class SettingsTests(OfflineTestCase):
    def setUp(self):
        super().setUp()
        self.config = importlib.import_module("app.config")

    def test_clean_defaults_are_deployment_and_bank_neutral(self):
        with patch.dict(os.environ, {}, clear=True):
            cfg = self.config.Settings()
        for name in (
            "tenant_id", "client_id", "client_secret", "api_scope", "project_endpoint",
            "agent_name", "scenario_agent_name", "mission_agent_name", "barrier_agent_name",
            "agent_id", "log_analytics_workspace_id", "cost_scope", "fabric_capacity_id",
        ):
            self.assertEqual(getattr(cfg, name), "", name)
        self.assertFalse(cfg.configured())
        self.assertFalse(cfg.agent_configured())
        self.assertFalse(cfg.mock_mode)
        self.assertFalse(cfg.allow_app_identity_fallback)
        self.assertEqual(cfg.fabric_capacity_operators, set())
        self.assertEqual(cfg.foundry_scope, "https://ai.azure.com/.default")
        self.assertEqual(cfg.cors_origins, ["http://localhost:5173"])
        self.assertEqual((cfg.telemetry_window_days, cfg.cost_window_days), (7, 30))
        self.assertFalse(any("bank" in f.name.lower() for f in fields(cfg)))
        self.assertTrue(all(f.default_factory is not MISSING for f in fields(cfg)))

    def test_every_environment_default_is_read_for_each_instance(self):
        env = {
            "AAD_TENANT_ID": "tenant.example.invalid", "AAD_CLIENT_ID": "test-client",
            "AAD_CLIENT_SECRET": "test-secret", "AAD_API_SCOPE": "api://test/access_as_user",
            "FOUNDRY_SCOPE": "https://service.example.invalid/.default",
            "FOUNDRY_PROJECT_ENDPOINT": "https://project.example.invalid/custom/project/",
            "FOUNDRY_AGENT_NAME": "coverage", "SCENARIO_AGENT_NAME": "scenario",
            "MISSION_AGENT_NAME": "mission", "BARRIER_AGENT_NAME": "reviewer",
            "FOUNDRY_AGENT_ID": "compatibility-id", "LOG_ANALYTICS_WORKSPACE_ID": "workspace",
            "TELEMETRY_WINDOW_DAYS": "14", "COST_SCOPE": "/subscriptions/test-sub",
            "COST_WINDOW_DAYS": "60",
            "FABRIC_CAPACITY_ID": " /subscriptions/test-sub/resourceGroups/test-rg/providers/Microsoft.Fabric/capacities/test-capacity ",
            "FABRIC_CAPACITY_OPERATORS": " Demo.User@Example.Invalid, other@example.invalid ",
            "MOCK_MODE": "TRUE", "ALLOW_APP_IDENTITY_FALLBACK": "TRUE",
            "CORS_ORIGINS": "https://ui.example.invalid, http://localhost:5173",
        }
        with patch.dict(os.environ, {}, clear=True):
            before = self.config.Settings()
        with patch.dict(os.environ, env, clear=True):
            during = self.config.Settings()
        with patch.dict(os.environ, {}, clear=True):
            after = self.config.Settings()
        names = [
            "tenant_id", "client_id", "client_secret", "api_scope", "foundry_scope",
            "project_endpoint", "agent_name", "scenario_agent_name", "mission_agent_name",
            "barrier_agent_name", "agent_id", "log_analytics_workspace_id",
            "telemetry_window_days", "cost_scope", "cost_window_days", "fabric_capacity_id",
            "fabric_capacity_operators", "mock_mode", "allow_app_identity_fallback", "cors_origins",
        ]
        for name in names:
            self.assertNotEqual(getattr(before, name), getattr(during, name), name)
            self.assertEqual(getattr(before, name), getattr(after, name), name)
        self.assertEqual(during.fabric_capacity_operators,
                         {"demo.user@example.invalid", "other@example.invalid"})
        self.assertEqual(during.fabric_capacity_id, env["FABRIC_CAPACITY_ID"].strip())
        self.assertEqual((during.telemetry_window_days, during.cost_window_days), (14, 60))
        during.cors_origins.append("https://another.example.invalid")
        self.assertEqual(after.cors_origins, ["http://localhost:5173"])

    def test_auth_readiness_does_not_expose_values(self):
        with patch.dict(os.environ, {}, clear=True):
            cfg = self.config.Settings(tenant_id="tenant.example.invalid",
                                       client_id="client", client_secret="private-secret")
        self.assertTrue(cfg.configured())
        self.assertFalse(replace(cfg, tenant_id="").configured())
        self.assertFalse(replace(cfg, client_id=" ").configured())
        self.assertFalse(replace(cfg, client_secret=" ").configured())
        bad = replace(cfg, tenant_id="https://private-secret@example.invalid")
        self.assertFalse(bad.configured())
        self.assertNotIn("private-secret", bad.auth_config_error())
        self.assertNotIn("private-secret", repr(cfg))
        self.assertNotIn("private-secret", repr(bad))
        self.assertEqual(cfg.authority, "https://login.microsoftonline.com/tenant.example.invalid")
        self.assertEqual(cfg.audiences, ("client", "api://client"))

    def test_agent_requires_name_and_https_endpoint_not_legacy_id(self):
        with patch.dict(os.environ, {}, clear=True):
            cfg = self.config.Settings(project_endpoint="https://custom.example.invalid/any/project",
                                       agent_id="legacy-id")
        self.assertFalse(cfg.agent_configured())
        self.assertTrue(cfg.agent_configured("scenario"))
        cfg.agent_name = "coverage"
        self.assertTrue(cfg.agent_configured())
        self.assertEqual(cfg.require_agent_configured(), "coverage")
        self.assertEqual(cfg.require_agent_configured("mission"), "mission")
        for name in ("", " ", "\t"):
            with self.subTest(name=name):
                self.assertFalse(cfg.agent_configured(name))
                with self.assertRaises(ValueError):
                    cfg.require_agent_configured(name)

    def test_endpoint_validation_is_offline_and_does_not_leak_userinfo(self):
        with patch.dict(os.environ, {}, clear=True):
            cfg = self.config.Settings(agent_name="coverage")
        invalid = (
            "", " ", "/relative", "http://example.invalid/project",
            "https://", "https://:443/project", "https://host.invalid:bad/project",
            "https://host.invalid:/project", "https://host%40other.invalid/project",
            "https://host.invalid:99999/project", "https://host.invalid:0/project",
            "https://user:private-secret@host.invalid/project",
            "https://host.invalid/project?key=private-secret",
            "https://host.invalid/project#private-secret", "https://host.invalid/project?",
            "https://host.invalid/project#", "https://host.invalid\\project",
            "https://host.invalid/\nproject",
        )
        for endpoint in invalid:
            with self.subTest(endpoint=endpoint):
                cfg.project_endpoint = endpoint
                self.assertFalse(cfg.agent_configured())
                with self.assertRaises(ValueError) as exc:
                    cfg.require_agent_configured()
                self.assertNotIn("private-secret", str(exc.exception))
                self.assertNotIn("private-secret", repr(cfg))
        for endpoint in (
            "https://custom.example.invalid", "https://custom.example.invalid/arbitrary/path/",
            "https://custom.example.invalid:8443/project", "https://[::1]:8443/project",
        ):
            with self.subTest(endpoint=endpoint):
                cfg.project_endpoint = endpoint
                self.assertTrue(cfg.agent_configured())

    def test_bad_window_values_fail_without_echoing_environment(self):
        for variable in ("COST_WINDOW_DAYS", "TELEMETRY_WINDOW_DAYS"):
            for value in ("0", "-1", "private-secret"):
                with self.subTest(variable=variable, value=value):
                    with patch.dict(os.environ, {variable: value}, clear=True):
                        with self.assertRaises(ValueError) as exc:
                            self.config.Settings()
                    self.assertIn(variable, str(exc.exception))
                    self.assertNotIn("private-secret", str(exc.exception))

    def test_cost_scope_allows_subscription_resource_group_and_billing_scopes(self):
        with patch.dict(os.environ, {}, clear=True):
            cfg = self.config.Settings()
        for scope in (
            "/subscriptions/test-sub", "/subscriptions/test-sub/resourceGroups/test-rg",
            "/providers/Microsoft.Management/managementGroups/test-group",
            "/providers/Microsoft.Billing/billingAccounts/test-account",
            "/providers/Microsoft.Billing/billingAccounts/test-account/billingProfiles/test-profile",
        ):
            with self.subTest(scope=scope):
                cfg.cost_scope = scope
                self.assertEqual(cfg.cost_config_error(), "")
        for scope in (
            "", "/subscriptions/test-sub/resourceGroups", "https://example.invalid",
            "/subscriptions/test-sub/../other", "//subscriptions/test-sub",
            "/subscriptions/test-sub?secret=value", "/subscriptions/test-sub%23fragment",
        ):
            with self.subTest(scope=scope):
                cfg.cost_scope = scope
                self.assertTrue(cfg.cost_config_error())


class ServiceConfigurationTests(OfflineAsyncTestCase):
    def setUp(self):
        super().setUp()
        self.config = importlib.import_module("app.config")
        self.auth = importlib.import_module("app.auth")
        self.agent = importlib.import_module("app.agent_client")
        self.cost = importlib.import_module("app.cost")
        self.telemetry = importlib.import_module("app.telemetry")
        self.fabric = importlib.import_module("app.fabric_capacity")
        with patch.dict(os.environ, {}, clear=True):
            self.cfg = self.config.Settings()
        for module in (self.auth, self.agent, self.cost, self.telemetry, self.fabric):
            p = patch.object(module, "settings", self.cfg)
            p.start()
            self.addCleanup(p.stop)
        for module, name, value in (
            (self.auth, "_jwk_client", None), (self.auth, "_obo_cache", {}),
            (self.cost, "_cache", None), (self.cost, "_token", None),
            (self.cost, "_token_lock", asyncio.Lock()), (self.cost, "_cache_lock", asyncio.Lock()),
            (self.telemetry, "_cache", None), (self.telemetry, "_token", None),
            (self.telemetry, "_session", []), (self.telemetry, "_token_lock", asyncio.Lock()),
            (self.telemetry, "_cache_lock", asyncio.Lock()),
            (self.fabric, "_token", None), (self.fabric, "_lock", asyncio.Lock()),
        ):
            p = patch.object(module, name, value)
            p.start()
            self.addCleanup(p.stop)
        self.user = self.auth.User(
            {"oid": "test-user", "preferred_username": "demo.user@example.invalid"}, "user-assertion")

    async def test_missing_configuration_stays_offline(self):
        from fastapi import HTTPException

        self.assertFalse((await self.cost.snapshot())["available"])
        telemetry = await self.telemetry.snapshot()
        self.assertEqual(telemetry["source"], "unavailable")
        self.assertFalse(telemetry["billed"]["available"])
        self.assertFalse((await self.fabric.status(self.user.upn))["configured"])
        self.assertFalse(self.fabric.can_operate(self.user.upn))
        for operation in (self.cost._access_token, self.telemetry._access_token,
                          self.telemetry._fetch_runs):
            with self.subTest(operation=operation.__name__):
                with self.assertRaises(ValueError):
                    await operation()
        with self.assertRaises(ValueError):
            await self.cost._fetch(30)
        with self.assertRaises(PermissionError):
            await self.fabric._access_token()
        for action in ("suspend", "resume"):
            with self.assertRaises(PermissionError):
                await self.fabric.change(action, self.user.upn)
        with self.assertRaises(HTTPException) as exc:
            self.auth.validate_token("not-a-token")
        self.assertEqual(exc.exception.status_code, 500)
        with self.assertRaises(HTTPException) as exc:
            await self.auth.exchange_obo(self.user)
        self.assertEqual(exc.exception.status_code, 500)

    async def test_agent_configuration_fails_before_authentication(self):
        endpoint = "https://custom.example.invalid/project"
        cases = (
            (endpoint, "", None), (endpoint, "coverage", ""), (endpoint, "coverage", " "),
            ("", "coverage", None),
            ("https://user:private-secret@custom.example.invalid/project", "coverage", None),
        )
        for project, main_name, override in cases:
            with self.subTest(project=project, override=override):
                self.cfg.project_endpoint = project
                self.cfg.agent_name = main_name
                with patch.object(self.agent, "exchange_obo", new_callable=AsyncMock) as exchange:
                    frames = [frame async for frame in
                              self.agent.run_agent(self.user, "Question", agent_name=override)]
                exchange.assert_not_awaited()
                self.assertTrue(any(frame.startswith("event: error") for frame in frames))
                self.assertIn('"ok": false', "".join(frames))
                self.assertNotIn("Authenticating", "".join(frames))
                self.assertNotIn("private-secret", "".join(frames))

    async def test_configured_agent_preserves_explicit_override_and_main_selection(self):
        import httpx

        self.cfg.project_endpoint = "https://custom.example.invalid/arbitrary/project/"
        self.cfg.agent_name = "coverage"
        for override, expected in ((None, "coverage"), ("scenario", "scenario"), ("mission", "mission")):
            requests = []

            def respond(request):
                requests.append(request)
                event = {
                    "type": "response.completed",
                    "response": {"id": "response-id", "status": "completed",
                                 "output_text": "Grounded test response", "output": []},
                }
                return httpx.Response(200, content=f"data: {json.dumps(event)}\n\n".encode(),
                                      headers={"Content-Type": "text/event-stream"})

            with self.subTest(override=override):
                client = httpx.AsyncClient(transport=httpx.MockTransport(respond), trust_env=False)
                with patch.object(self.agent, "exchange_obo", new_callable=AsyncMock,
                                  return_value="delegated-test-token") as exchange, \
                     patch.object(self.agent.httpx, "AsyncClient", return_value=client):
                    frames = [frame async for frame in self.agent.run_agent(
                        self.user, "Question", "previous-response", override)]
                exchange.assert_awaited_once_with(self.user)
                self.assertEqual(len(requests), 1)
                self.assertEqual(
                    str(requests[0].url),
                    "https://custom.example.invalid/arbitrary/project/openai/responses?api-version=2025-05-15-preview")
                body = json.loads(requests[0].content)
                self.assertEqual(body["agent_reference"]["name"], expected)
                self.assertEqual(body["previous_response_id"], "previous-response")
                self.assertEqual(body["input"], "Question")
                self.assertTrue(body["stream"])
                self.assertIn('"ok": true', "".join(frames))
                self.assertNotIn("delegated-test-token", "".join(frames))

    async def test_mock_services_ignore_populated_environment_and_live_caches(self):
        from fastapi import HTTPException
        from starlette.requests import Request

        env = {
            "MOCK_MODE": "true", "AAD_TENANT_ID": "tenant", "AAD_CLIENT_ID": "client",
            "AAD_CLIENT_SECRET": "private-secret", "AZURE_CLIENT_ID": "ambient-client",
            "AZURE_TENANT_ID": "ambient-tenant", "AZURE_CLIENT_SECRET": "ambient-secret",
            "FOUNDRY_PROJECT_ENDPOINT": "https://project.example.invalid/project",
            "FOUNDRY_AGENT_NAME": "coverage",
            "LOG_ANALYTICS_WORKSPACE_ID": "00000000-0000-0000-0000-000000000001",
            "COST_SCOPE": "/subscriptions/test-sub",
            "FABRIC_CAPACITY_ID": "/subscriptions/test-sub/resourceGroups/test-rg/providers/Microsoft.Fabric/capacities/test-capacity",
        }
        with patch.dict(os.environ, env, clear=True):
            cfg = self.config.Settings()
            with patch.object(self.auth, "settings", cfg), patch.object(self.agent, "settings", cfg), \
                 patch.object(self.cost, "settings", cfg), patch.object(self.telemetry, "settings", cfg), \
                 patch.object(self.fabric, "settings", cfg):
                self.cost._cache = ({"available": True, "total": 123}, time.time())
                self.telemetry._cache = ({"source": "foundry"}, time.time())
                for module in (self.cost, self.telemetry, self.fabric):
                    module._token = ("cached-secret", time.time() + 3600)
                self.auth._obo_cache[f"{self.user.oid}:{cfg.foundry_scope}"] = (
                    "cached-secret", time.time() + 3600)
                user = await self.auth.current_user(Request({"type": "http", "headers": []}))
                self.assertEqual(user.upn, "demo.user@example.invalid")
                self.assertEqual(user.name, "Demo User (mock)")
                self.assertEqual(user.claims["roles"], ["Coverage"])
                self.assertEqual(user.raw_token, "")
                billed = await self.cost.snapshot()
                traces = await self.telemetry.snapshot()
                capacity = await self.fabric.status(user.upn)
                self.assertFalse(billed["available"])
                self.assertEqual(traces["source"], "unavailable")
                self.assertEqual(traces["totals"]["runs"], 0)
                self.assertIsNone(traces["billed"])
                self.assertFalse(capacity["configured"])
                self.assertEqual(capacity["state"], "unknown")
                self.assertFalse(self.fabric.can_operate(user.upn))
                for result in (billed, traces, capacity):
                    self.assertIn("MOCK_MODE", json.dumps(result))
                    self.assertNotIn("cached-secret", json.dumps(result))
                for operation in (self.cost._access_token, self.telemetry._access_token,
                                  self.telemetry._fetch_runs):
                    with self.assertRaises(RuntimeError):
                        await operation()
                with self.assertRaises(RuntimeError):
                    await self.cost._fetch(30)
                with self.assertRaises(PermissionError):
                    await self.fabric._access_token()
                for action in ("suspend", "resume"):
                    with self.assertRaises(PermissionError):
                        await self.fabric.change(action, user.upn)
                with self.assertRaises(HTTPException) as exc:
                    await self.auth.exchange_obo(self.user)
                self.assertEqual(exc.exception.status_code, 503)
                with self.assertRaises(HTTPException):
                    self.auth.validate_token("not-a-token")
                self.telemetry.record_run()
                self.assertEqual(self.telemetry._session, [])
                with patch.object(self.agent.asyncio, "sleep", new_callable=AsyncMock):
                    frames = [frame async for frame in self.agent.run_agent(user, "Question")]
                self.assertIn("Mock mode", "".join(frames))

    async def test_bad_service_configuration_is_not_hidden_by_cached_success(self):
        self.cost._cache = ({"available": True}, time.time())
        self.telemetry._cache = ({"source": "foundry"}, time.time())
        for module in (self.cost, self.telemetry, self.fabric):
            module._token = ("cached-secret", time.time() + 3600)
        self.cfg.cost_scope = "/subscriptions/test-sub?key=private-secret"
        self.cfg.log_analytics_workspace_id = "private-secret/../../other"
        self.cfg.fabric_capacity_id = "/subscriptions/test-sub?key=private-secret"
        for result in (await self.cost.snapshot(), await self.telemetry.snapshot(),
                       await self.fabric.status(self.user.upn)):
            self.assertNotIn("private-secret", json.dumps(result))
            self.assertNotIn("cached-secret", json.dumps(result))
        self.assertFalse((await self.cost.snapshot())["available"])
        self.assertEqual((await self.telemetry.snapshot())["source"], "unavailable")
        self.assertFalse((await self.fabric.status(self.user.upn))["configured"])
        for operation in (self.cost._access_token, self.telemetry._access_token):
            with self.assertRaises(ValueError):
                await operation()
        with self.assertRaises(PermissionError):
            await self.fabric.change("suspend", self.user.upn)

    async def test_unconfigured_traces_preserve_independent_billing(self):
        for workspace, agent in (("invalid", "coverage"),
                                 ("00000000-0000-0000-0000-000000000001", "")):
            with self.subTest(workspace=workspace, agent=agent):
                self.cfg.log_analytics_workspace_id = workspace
                self.cfg.agent_name = agent
                billed = {"available": True, "total": 12.0}
                with patch.object(self.telemetry, "billed_cost", AsyncMock(return_value=billed)) as billing, \
                     patch.object(self.telemetry, "_fetch_runs", AsyncMock()) as traces:
                    result = await self.telemetry.snapshot()
                self.assertEqual(result["source"], "unavailable")
                self.assertEqual(result["billed"], billed)
                billing.assert_awaited_once()
                traces.assert_not_awaited()

    async def test_auth_checks_configuration_and_assertion_before_cache(self):
        from fastapi import HTTPException

        self.auth._obo_cache[f"{self.user.oid}:{self.cfg.foundry_scope}"] = (
            "cached-secret", time.time() + 3600)
        self.cfg.allow_app_identity_fallback = True
        with self.assertRaises(HTTPException) as exc:
            await self.auth.exchange_obo(self.user)
        self.assertEqual(exc.exception.status_code, 500)
        self.cfg.tenant_id = "tenant"
        self.cfg.client_id = "client"
        self.cfg.client_secret = "private-secret"
        with self.assertRaises(HTTPException) as exc:
            await self.auth.exchange_obo(self.auth.User(self.user.claims, ""))
        self.assertEqual(exc.exception.status_code, 401)
        with self.assertRaises(HTTPException) as exc:
            await self.auth.exchange_obo(self.user, "")
        self.assertEqual(exc.exception.status_code, 500)
        self.assertNotIn("private-secret", exc.exception.detail)

    async def test_capacity_operator_policy_requires_identity_and_preserves_allowlist(self):
        self.cfg.fabric_capacity_id = (
            "/subscriptions/test-sub/resourceGroups/test-rg/providers/Microsoft.Fabric/capacities/test-capacity")
        self.assertFalse(self.fabric.can_operate(""))
        self.assertFalse(self.fabric.can_operate(" "))
        self.assertTrue(self.fabric.can_operate(self.user.upn))
        self.cfg.fabric_capacity_operators = {self.user.upn}
        self.assertTrue(self.fabric.can_operate(self.user.upn.upper()))
        self.assertFalse(self.fabric.can_operate("other@example.invalid"))
        with self.assertRaises(PermissionError):
            await self.fabric.change("resume", "other@example.invalid")
        with self.assertRaises(ValueError):
            await self.fabric.change("delete", self.user.upn)

    async def test_capacity_errors_cannot_masquerade_as_success(self):
        import httpx

        self.cfg.fabric_capacity_id = (
            "/subscriptions/test-sub/resourceGroups/test-rg/providers/Microsoft.Fabric/capacities/test-capacity")
        client = AsyncMock()
        client.__aenter__.return_value = client
        for code, state in ((403, "paused"), (500, "paused"), (400, "active")):
            with self.subTest(code=code, state=state):
                client.post.return_value = httpx.Response(code, text="ARM rejected request")
                with patch.object(self.fabric, "_access_token", new_callable=AsyncMock,
                                  return_value="test-token"), \
                     patch.object(self.fabric, "status", new_callable=AsyncMock,
                                  return_value={"state": state}), \
                     patch.object(self.fabric.httpx, "AsyncClient", return_value=client):
                    with self.assertRaises(RuntimeError):
                        await self.fabric.change("suspend", self.user.upn)
        client.post.return_value = httpx.Response(400, text="Already paused")
        with patch.object(self.fabric, "_access_token", new_callable=AsyncMock, return_value="test-token"), \
             patch.object(self.fabric, "status", new_callable=AsyncMock, return_value={"state": "paused"}), \
             patch.object(self.fabric.httpx, "AsyncClient", return_value=client):
            result = await self.fabric.change("suspend", self.user.upn)
        self.assertEqual(result["state"], "paused")
        client.post.return_value = httpx.Response(202)
        with patch.object(self.fabric, "_access_token", new_callable=AsyncMock, return_value="test-token"), \
             patch.object(self.fabric, "status", new_callable=AsyncMock, return_value={"state": "paused"}), \
             patch.object(self.fabric.httpx, "AsyncClient", return_value=client):
            result = await self.fabric.change("resume", self.user.upn)
        self.assertEqual(result["state"], "resuming")

    async def test_obo_error_does_not_echo_credentials_or_assertion(self):
        import httpx
        from fastapi import HTTPException

        self.cfg.tenant_id = "tenant"
        self.cfg.client_id = "client"
        self.cfg.client_secret = "private-secret"
        response = httpx.Response(
            400, text="AADSTS65001 private-secret user-assertion cached-secret")
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.post.return_value = response
        with patch.object(self.auth.httpx, "AsyncClient", return_value=client):
            with self.assertLogs("auth", level="ERROR") as logs:
                with self.assertRaises(HTTPException) as exc:
                    await self.auth.exchange_obo(self.user)
        self.assertEqual(exc.exception.status_code, 502)
        self.assertIn("consent", exc.exception.detail)
        for secret in ("private-secret", "user-assertion", "cached-secret"):
            self.assertNotIn(secret, exc.exception.detail)
            self.assertNotIn(secret, "".join(logs.output))
