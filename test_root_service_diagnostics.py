"""Offline native unittest coverage; all HTTP, SDK credentials and clocks are mocked.

Run from the project root: python -B -m unittest test_root_service_diagnostics -v
"""
from __future__ import annotations

import builtins
import importlib
import importlib.util
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import types
import unittest
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from unittest import mock


ROOT = Path(__file__).resolve().parent
TOOLS = ("diag_events", "diag_fabric", "diag_workiq")
TOKEN = "offline-test-access-token-not-a-real-credential"
TENANT = "11111111-1111-4111-8111-111111111111"
CLIENT = "22222222-2222-4222-8222-222222222222"
WORKSPACE = "33333333-3333-4333-8333-333333333333"
MODEL = "44444444-4444-4444-8444-444444444444"
SUBSCRIPTION = "55555555-5555-4555-8555-555555555555"
ENDPOINT = "https://foundry.invalid/api/projects/offline"
PROMPT = "Explicit offline diagnostic prompt."
QUERY = 'EVALUATE ROW("configured", 2)'
AUTH_FIELDS = {
    "azure_cli": ("AZURE_TENANT_ID", "AZURE_SUBSCRIPTION_ID"),
    "service_principal": ("AZURE_TENANT_ID", "AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET"),
    "managed_identity": ("AZURE_CLIENT_ID",),
}
AUTH_VALUES = {
    "AZURE_TENANT_ID": TENANT,
    "AZURE_SUBSCRIPTION_ID": SUBSCRIPTION,
    "AZURE_CLIENT_ID": CLIENT,
    "AZURE_CLIENT_SECRET": "offline-placeholder-not-a-secret",
}
REQUIRED = {
    "diag_events": ("FOUNDRY_PROJECT_ENDPOINT", "FOUNDRY_AGENT_NAME", "DIAG_PROMPT"),
    "diag_fabric": ("FABRIC_WORKSPACE_ID", "FABRIC_SEMANTIC_MODEL_ID", "DIAG_FABRIC_QUERY"),
    "diag_workiq": ("WORKIQ_TENANT_ID", "WORKIQ_CLIENT_ID", "DIAG_PROMPT"),
}


class FakeAzureError(Exception):
    pass


class FakeRequestError(Exception):
    pass


class Clock:
    def __init__(self):
        self.now = 0
        self.waits = []

    def monotonic(self):
        return self.now

    def sleep(self, duration):
        self.waits.append(duration)
        self.now += duration


def environment(tool: str, mode="azure_cli") -> dict[str, str]:
    values = {
        "FOUNDRY_PROJECT_ENDPOINT": ENDPOINT + "/",
        "FOUNDRY_AGENT_NAME": "offline-agent",
        "DIAG_PROMPT": PROMPT,
        "FABRIC_WORKSPACE_ID": WORKSPACE,
        "FABRIC_SEMANTIC_MODEL_ID": MODEL,
        "DIAG_FABRIC_QUERY": QUERY,
        "WORKIQ_TENANT_ID": TENANT,
        "WORKIQ_CLIENT_ID": CLIENT,
    }
    config = {name: values[name] for name in REQUIRED[tool]}
    if tool != "diag_workiq":
        config["AZURE_AUTH_MODE"] = mode
        config.update({name: AUTH_VALUES[name] for name in AUTH_FIELDS[mode]})
    return config


def response(body=None, status=200, lines=(), content_type="text/event-stream"):
    result = mock.MagicMock()
    result.status_code = status
    result.headers = {"Content-Type": content_type}
    result.json.return_value = body
    result.iter_lines.return_value = iter(lines)
    result.__enter__.return_value = result
    return result


def frames(*events):
    lines = []
    for event in events:
        data = event if isinstance(event, str) else json.dumps(event)
        lines.extend([f"data: {data}".encode("utf-8"), b""])
    return lines


def completed():
    return {"type": "response.completed", "response": {"status": "completed"}}


def rows(value):
    return {"results": [{"tables": [{"rows": value}]}]}


def device(**changes):
    return {
        "device_code": "offline-device-code",
        "user_code": "OFFLINE-CODE",
        "verification_uri": "https://microsoft.com/devicelogin",
        "expires_in": 60,
        "interval": 5,
        **changes,
    }


def bearer(**changes):
    return {"access_token": TOKEN, "token_type": "Bearer", **changes}


def message(**changes):
    return {
        "kind": "message", "role": "agent", "messageId": "offline-message",
        "parts": [{"kind": "text", "text": "Offline response."}], **changes,
    }


class OfflineDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(mock.patch.object(sys, "dont_write_bytecode", True))
        self.stack.enter_context(mock.patch.object(sys, "path", [str(ROOT), *sys.path]))
        self.stack.enter_context(mock.patch.dict(os.environ, {}, clear=True))
        self.stdout = self.stack.enter_context(redirect_stdout(io.StringIO()))
        self.stderr = self.stack.enter_context(redirect_stderr(io.StringIO()))
        self.forbidden = []
        for owner, name in (
            (socket, "socket"), (socket, "create_connection"), (socket, "getaddrinfo"),
            (subprocess, "run"), (subprocess, "Popen"), (os, "system"), (os, "popen"),
        ):
            guard = self.stack.enter_context(mock.patch.object(
                owner, name, side_effect=AssertionError(f"Forbidden offline operation: {name}")))
            self.forbidden.append(guard)

        self.http = types.ModuleType("requests")
        self.http.RequestException = FakeRequestError
        self.http.get = mock.Mock(side_effect=AssertionError("Unexpected HTTP GET"))
        self.http.post = mock.Mock(side_effect=AssertionError("Unexpected HTTP POST"))
        self.credential = mock.Mock()
        self.credential.get_token.return_value = types.SimpleNamespace(token=TOKEN)
        self.azure_identity = types.ModuleType("azure.identity")
        for name in ("AzureCliCredential", "ClientSecretCredential", "ManagedIdentityCredential"):
            setattr(self.azure_identity, name, mock.Mock(return_value=self.credential))
        azure = types.ModuleType("azure")
        azure.__path__ = []
        core = types.ModuleType("azure.core")
        core.__path__ = []
        exceptions = types.ModuleType("azure.core.exceptions")
        exceptions.AzureError = FakeAzureError
        self.stack.enter_context(mock.patch.dict(sys.modules, {
            "requests": self.http, "azure": azure, "azure.core": core,
            "azure.core.exceptions": exceptions, "azure.identity": self.azure_identity,
        }))
        self.forbid_external_imports = False
        original_import = builtins.__import__

        def guarded_import(name, *args, **kwargs):
            if name.split(".", 1)[0] in ("httpx", "msal", "dotenv"):
                raise AssertionError(f"Unexpected dependency import: {name}")
            if self.forbid_external_imports and name.split(".", 1)[0] in ("requests", "azure"):
                raise AssertionError(f"Dependency imported before configuration validation: {name}")
            return original_import(name, *args, **kwargs)

        self.stack.enter_context(mock.patch.object(builtins, "__import__", side_effect=guarded_import))
        self.portability = importlib.import_module("agent.portability")
        self.clock = Clock()
        self.tools = {name: self.load_tool(name) for name in TOOLS}
        for module in self.tools.values():
            self.stack.enter_context(mock.patch.object(module, "time", self.clock))

    def tearDown(self):
        for guard in self.forbidden:
            guard.assert_not_called()
        output = self.stdout.getvalue() + self.stderr.getvalue()
        self.assertNotIn(TOKEN, output)
        self.assertNotIn(AUTH_VALUES["AZURE_CLIENT_SECRET"], output)

    @staticmethod
    def load_tool(name):
        spec = importlib.util.spec_from_file_location(f"_offline_{name}", ROOT / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def clear_output(self):
        for output in (self.stdout, self.stderr):
            output.seek(0)
            output.truncate()

    def assert_no_external_calls(self):
        self.http.get.assert_not_called()
        self.http.post.assert_not_called()
        self.credential.get_token.assert_not_called()
        for name in ("AzureCliCredential", "ClientSecretCredential", "ManagedIdentityCredential"):
            getattr(self.azure_identity, name).assert_not_called()

    def main(self, tool, config=None):
        with mock.patch.dict(os.environ, environment(tool) if config is None else config, clear=True):
            return self.tools[tool].main()

    def events_main(self, lines, **kwargs):
        result = response(lines=lines, **kwargs)
        self.http.post.side_effect = None
        self.http.post.return_value = result
        code = self.main("diag_events")
        result.__exit__.assert_called_once()
        return code

    def fabric_responses(self, metadata=None, refresh=None, queries=None):
        self.http.get.side_effect = [
            metadata if metadata is not None else response({"id": MODEL, "name": "offline-model"}),
            refresh if refresh is not None else response({"value": []}),
        ]
        self.http.post.side_effect = queries if queries is not None else [
            response(rows([{"[ok]": 1}])), response(rows([{"[configured]": 2}])),
        ]

    def workiq_responses(self, result=None, rpc_error=None, a2a_status=200):
        def send(url, **kwargs):
            if url.endswith("/devicecode"):
                return response(device())
            if url.endswith("/token"):
                return response(bearer())
            payload = kwargs["json"]
            body = {"jsonrpc": "2.0", "id": payload["id"]}
            if rpc_error is not None:
                body["error"] = rpc_error
            else:
                body["result"] = result if result is not None else message()
            return response(body, a2a_status)
        self.http.post.side_effect = send

    def test_imports_have_no_configuration_file_auth_or_network_effects(self):
        prepared = [
            (name, compile((ROOT / f"{name}.py").read_text(encoding="utf-8"), f"{name}.py", "exec"))
            for name in TOOLS
        ]
        self.forbid_external_imports = True
        with ExitStack() as stack:
            for method in ("get", "__getitem__", "__iter__", "__contains__", "keys", "items", "values"):
                stack.enter_context(mock.patch.object(
                    type(os.environ), method, side_effect=AssertionError("Environment read on import")))
            stack.enter_context(mock.patch.object(
                os, "getenv", side_effect=AssertionError("getenv on import")))
            for owner, name in (
                (builtins, "open"), (io, "open"), (Path, "read_text"), (Path, "read_bytes"),
            ):
                stack.enter_context(mock.patch.object(
                    owner, name, side_effect=AssertionError("File read on import")))
            for name in ("require_environment", "require_https_url", "load_foundry_config",
                         "load_auth_config", "build_credential", "foundry_token"):
                stack.enter_context(mock.patch.object(
                    self.portability, name, side_effect=AssertionError(f"{name} on import")))
            for name, code in prepared:
                module = types.ModuleType(f"_import_check_{name}")
                exec(code, module.__dict__)
                self.assertTrue(callable(module.main))
                self.assertNotIn("requests", vars(module))
        self.assert_no_external_calls()

    def test_every_required_field_missing_or_blank_fails_before_external_imports(self):
        self.forbid_external_imports = True
        for tool in TOOLS:
            modes = ("device",) if tool == "diag_workiq" else tuple(AUTH_FIELDS)
            for mode in modes:
                config = environment(tool, mode)
                fields = list(REQUIRED[tool])
                if tool != "diag_workiq":
                    fields += ["AZURE_AUTH_MODE", *AUTH_FIELDS[mode]]
                for field in fields:
                    for value in (None, "", " \r\n\t "):
                        with self.subTest(tool=tool, mode=mode, field=field, value=value):
                            changed = dict(config)
                            if value is None:
                                changed.pop(field)
                            else:
                                changed[field] = value
                            self.clear_output()
                            self.assertEqual(self.main(tool, changed), 2)
                            self.assertIn(field, self.stderr.getvalue())
                            self.assert_no_external_calls()

    def test_invalid_auth_profiles_fail_locally(self):
        self.forbid_external_imports = True
        for tool in ("diag_events", "diag_fabric"):
            for mode in ("default", "auto", "cli", "admin_key", "Azure_Cli"):
                with self.subTest(tool=tool, mode=mode):
                    config = {**environment(tool), "AZURE_AUTH_MODE": mode}
                    self.assertEqual(self.main(tool, config), 2)
        self.assert_no_external_calls()

    def test_invalid_azure_auth_identifiers_fail_before_dependency_imports(self):
        self.forbid_external_imports = True
        for tool in ("diag_events", "diag_fabric"):
            for mode, fields in AUTH_FIELDS.items():
                for field in fields:
                    if not field.endswith("_ID"):
                        continue
                    for value in ("not-a-guid", "../tenant", TENANT.replace("-", "")):
                        with self.subTest(tool=tool, mode=mode, field=field, value=value):
                            config = {**environment(tool, mode), field: value}
                            self.clear_output()
                            self.assertEqual(self.main(tool, config), 2)
                            self.assertIn(field, self.stderr.getvalue())
        self.assert_no_external_calls()

    def test_invalid_foundry_urls_fail_locally(self):
        self.forbid_external_imports = True
        for url in (
            "http://foundry.invalid", "https://", "https://user:password@foundry.invalid",
            "https://foundry.invalid?token=hidden", "https://foundry.invalid#fragment",
            "https://foundry.invalid\\path", "https://foundry.invalid/bad path",
            "https://foundry.invalid:70000", "https://[broken",
        ):
            with self.subTest(url=url):
                config = {**environment("diag_events"), "FOUNDRY_PROJECT_ENDPOINT": url}
                self.assertEqual(self.main("diag_events", config), 2)
        self.assert_no_external_calls()

    def test_malformed_guid_fields_fail_before_auth_or_http(self):
        self.forbid_external_imports = True
        for tool, names in (
            ("diag_fabric", ("FABRIC_WORKSPACE_ID", "FABRIC_SEMANTIC_MODEL_ID")),
            ("diag_workiq", ("WORKIQ_TENANT_ID", "WORKIQ_CLIENT_ID")),
        ):
            for name in names:
                for value in ("not-a-guid", "../tenant", TENANT + "?query=1", TENANT.replace("-", "")):
                    with self.subTest(tool=tool, name=name, value=value):
                        self.clear_output()
                        self.assertEqual(self.main(tool, {**environment(tool), name: value}), 2)
                        self.assertIn(name, self.stderr.getvalue())
        self.assert_no_external_calls()

    def test_legacy_workiq_application_and_backend_fields_are_not_fallbacks(self):
        self.forbid_external_imports = True
        config = {
            "WORKIQ_TENANT_ID": TENANT, "WORKIQ_CONNECTOR_APP": CLIENT,
            "AZURE_CLIENT_ID": CLIENT, "WORKIQ_CONNECTOR_CLIENT_ID": CLIENT,
            "DIAG_PROMPT": PROMPT, "BANK_TENANT_ID": TENANT,
        }
        self.assertEqual(self.main("diag_workiq", config), 2)
        self.assertIn("WORKIQ_CLIENT_ID", self.stderr.getvalue())
        self.assert_no_external_calls()

    def test_explicit_azure_profiles_select_only_one_credential(self):
        expectations = {
            "azure_cli": ("AzureCliCredential", {"tenant_id": TENANT, "subscription": SUBSCRIPTION}),
            "service_principal": ("ClientSecretCredential", {
                "tenant_id": TENANT, "client_id": CLIENT,
                "client_secret": AUTH_VALUES["AZURE_CLIENT_SECRET"],
            }),
            "managed_identity": ("ManagedIdentityCredential", {"client_id": CLIENT}),
        }
        for tool in ("diag_events", "diag_fabric"):
            for mode, (constructor, kwargs) in expectations.items():
                with self.subTest(tool=tool, mode=mode):
                    for name in ("AzureCliCredential", "ClientSecretCredential", "ManagedIdentityCredential"):
                        getattr(self.azure_identity, name).reset_mock()
                    self.credential.reset_mock()
                    if tool == "diag_events":
                        self.http.post.side_effect = None
                        self.http.post.return_value = response(lines=frames(completed()))
                    else:
                        self.fabric_responses()
                    self.assertEqual(self.main(tool, environment(tool, mode)), 0)
                    getattr(self.azure_identity, constructor).assert_called_once_with(**kwargs)
                    for other in set(name for name, _ in expectations.values()) - {constructor}:
                        getattr(self.azure_identity, other).assert_not_called()
                    scope = "https://ai.azure.com/.default" if tool == "diag_events" else self.tools[tool].SCOPE
                    self.credential.get_token.assert_called_once_with(scope)
                    self.credential.close.assert_called_once()

    def test_auth_failure_closes_credential_without_http_or_token_output(self):
        for tool in ("diag_events", "diag_fabric"):
            with self.subTest(tool=tool):
                self.credential.reset_mock()
                self.credential.get_token.side_effect = FakeAzureError(TOKEN)
                self.assertEqual(self.main(tool), 1)
                self.credential.close.assert_called_once()
                self.http.get.assert_not_called()
                self.http.post.assert_not_called()

    def test_empty_azure_token_fails_without_http(self):
        self.credential.get_token.return_value = types.SimpleNamespace(token="")
        for tool in ("diag_events", "diag_fabric"):
            with self.subTest(tool=tool):
                self.assertEqual(self.main(tool), 1)
        self.http.get.assert_not_called()
        self.http.post.assert_not_called()

    def test_events_request_uses_only_explicit_endpoint_agent_and_prompt(self):
        self.assertEqual(self.events_main(frames(completed(), "[DONE]")), 0)
        self.http.post.assert_called_once_with(
            ENDPOINT + "/openai/responses?api-version=2025-05-15-preview",
            headers={"Authorization": f"Bearer {TOKEN}", "Accept": "text/event-stream"},
            json={"agent_reference": {"type": "agent_reference", "name": "offline-agent"},
                  "input": PROMPT, "stream": True},
            stream=True, timeout=(30, 300), allow_redirects=False,
        )
        self.assertIn("response completed", self.stdout.getvalue())

    def test_events_multiline_comments_bom_and_distinct_item_types(self):
        lines = [
            b"\xef\xbb\xbf: heartbeat", b"", b"id: 1", b"retry: 1000",
            b"event: response.output_item.added",
            b'data: {"type":"response.output_item.added",',
            b'data: "item":{"type":"mcp_call","id":"one"}}', b"",
            *frames({"type": "response.output_item.added", "item": {"type": "mcp_call", "id": "two"}}),
            *frames({"type": "response.output_item.added", "item": {"type": "mcp_list_tools"}}),
            *frames(completed()),
        ]
        self.assertEqual(self.events_main(lines), 0)
        self.assertIn("3 distinct", self.stdout.getvalue())
        self.assertNotIn('"two"', self.stdout.getvalue())

    def test_events_omit_content_and_redact_access_token_from_metadata(self):
        event = {
            "type": "response.output_item.added",
            "item": {"type": "mcp_call", "id": TOKEN, "arguments": "private arguments"},
            "delta": "private delta",
        }
        self.assertEqual(self.events_main(frames(event, completed())), 0)
        self.assertIn("[REDACTED]", self.stdout.getvalue())
        self.assertNotIn("private arguments", self.stdout.getvalue())
        self.assertNotIn("private delta", self.stdout.getvalue())

    def test_events_reject_http_failure_and_wrong_content_type(self):
        for status, content in ((401, "text/event-stream"), (302, "text/event-stream"), (200, "text/html")):
            with self.subTest(status=status, content=content):
                self.assertEqual(self.events_main([], status=status, content_type=content), 1)

    def test_events_reject_malformed_frames_and_json_even_before_completion(self):
        bad_streams = [
            [], [b"data: {bad}", b""], frames([]), frames({}),
            frames({"type": []}), frames({"type": "response.created", "item": []}),
            frames({"type": "response.created", "response": None}),
            frames({"type": "response.created", "item": {"type": []}}),
            [b"garbage", b""], [b"data: \xff", b""],
            [b"event: response.created", b""],
            [b"event: response.created", *frames(completed())],
            [b"retry: negative", *frames(completed())],
            [b"id: bad\x00id", *frames(completed())],
            [b"data:", b""], frames({"type": "response.created"}),
        ]
        for lines in bad_streams:
            with self.subTest(lines=lines):
                self.assertEqual(self.events_main(lines), 1)

    def test_events_failed_incomplete_and_error_payloads_fail(self):
        events = [
            {"type": "error", "error": {"message": TOKEN}},
            {"type": "response.error"},
            {"type": "response.failed", "response": {"status": "failed"}},
            {"type": "response.incomplete", "response": {"status": "incomplete"}},
            {"type": "response.completed", "response": {"status": "failed"}},
            {"type": "response.completed", "response": {}},
            {"type": "response.completed", "response": {"status": "completed", "error": {"message": TOKEN}}},
            {"type": "response.output_item.done", "item": {"status": "failed"}},
            {"type": "response.output_item.done", "item": {"error": TOKEN}},
        ]
        for event in events:
            with self.subTest(event_type=event["type"]):
                self.assertEqual(self.events_main(frames(event)), 1)

    def test_events_do_not_accept_premature_done_or_truncated_terminal_frames(self):
        streams = [
            frames("[DONE]"),
            frames(completed())[:-1],
            [*frames(completed()), b"data: [DONE]"],
            frames(completed(), "[DONE]", "[DONE]"),
            frames(completed(), {"type": "error"}),
            frames(completed(), "[DONE]", {"type": "response.created"}),
            frames(completed(), completed()),
        ]
        for lines in streams:
            with self.subTest(lines=lines):
                self.assertEqual(self.events_main(lines), 1)

    def test_events_transport_failure_during_iteration_is_failure(self):
        result = response()
        result.iter_lines.side_effect = FakeRequestError(TOKEN)
        self.http.post.side_effect = None
        self.http.post.return_value = result
        self.assertEqual(self.main("diag_events"), 1)
        result.__exit__.assert_called_once()

    def test_fabric_runs_generic_smoke_and_only_explicit_domain_query(self):
        self.fabric_responses()
        self.assertEqual(self.main("diag_fabric"), 0)
        expected_url = self.tools["diag_fabric"].API + f"/groups/{WORKSPACE}/datasets/{MODEL}"
        self.assertEqual([call.args[0] for call in self.http.get.call_args_list],
                         [expected_url, expected_url + "/refreshes?$top=3"])
        self.assertEqual([call.kwargs["json"]["queries"][0]["query"]
                          for call in self.http.post.call_args_list],
                         ['EVALUATE ROW("ok", 1)', QUERY])
        for call in [*self.http.get.call_args_list, *self.http.post.call_args_list]:
            self.assertEqual(call.kwargs["headers"]["Authorization"], "Bearer " + TOKEN)
            self.assertFalse(call.kwargs["allow_redirects"])
            self.assertIn("timeout", call.kwargs)

    def test_fabric_failed_metadata_or_refresh_call_cannot_be_masked_by_queries(self):
        for label in ("metadata", "refresh"):
            for status in (403, 404, 429, 503, 302):
                with self.subTest(label=label, status=status):
                    self.fabric_responses(**{label: response(status=status)})
                    self.assertEqual(self.main("diag_fabric"), 1)
                    self.assertIn("[configured] OK", self.stdout.getvalue())

    def test_fabric_rejects_malformed_metadata_and_refresh_responses(self):
        cases = [
            ("metadata", None), ("metadata", []), ("metadata", {}),
            ("metadata", {"id": WORKSPACE, "name": "wrong model"}),
            ("metadata", {"id": MODEL, "name": None}),
            ("metadata", {"error": {"message": TOKEN}}),
            ("refresh", {}), ("refresh", {"value": {}}),
            ("refresh", {"value": [None]}), ("refresh", {"value": [{"status": 123}]}),
            ("refresh", {"error": {"message": TOKEN}}),
        ]
        for label, body in cases:
            with self.subTest(label=label, body=body):
                self.fabric_responses(**{label: response(body)})
                self.assertEqual(self.main("diag_fabric"), 1)

    def test_fabric_malformed_json_fails_in_each_call(self):
        for label in ("metadata", "refresh", "query"):
            with self.subTest(label=label):
                bad = response()
                bad.json.side_effect = ValueError(TOKEN)
                if label == "query":
                    self.fabric_responses(queries=[bad, response(rows([]))])
                else:
                    self.fabric_responses(**{label: bad})
                self.assertEqual(self.main("diag_fabric"), 1)

    def test_fabric_http200_query_errors_at_every_level_fail(self):
        failures = [
            {"error": {"message": TOKEN}},
            {"results": [{"error": {"message": TOKEN}}]},
            {"results": [{"tables": [{"rows": [], "error": {"message": TOKEN}}]}]},
            {"results": [{"tables": [{"rows": []}, {"error": {"message": TOKEN}}]}]},
            {"results": []}, {"results": {}}, {"results": [None]},
            {"results": [{"tables": []}]}, {"results": [{"tables": [None]}]},
            {"results": [{"tables": [{"rows": {}}]}]}, rows([None]),
            {"results": [{"tables": [{"rows": []}]}, {"error": {"message": TOKEN}}]},
        ]
        for body in failures:
            with self.subTest(body=body):
                self.fabric_responses(queries=[response(rows([{"[ok]": 1}])), response(body)])
                self.assertEqual(self.main("diag_fabric"), 1)

    def test_fabric_empty_configured_rows_are_valid_but_wrong_smoke_is_not(self):
        self.fabric_responses(queries=[response(rows([{"[ok]": 1}])), response(rows([]))])
        self.assertEqual(self.main("diag_fabric"), 0)
        for wrong in ([], [{"[ok]": 0}], [{"unrelated": 1}]):
            with self.subTest(rows=wrong):
                self.fabric_responses(queries=[response(rows(wrong)), response(rows([]))])
                self.assertEqual(self.main("diag_fabric"), 1)

    def test_fabric_historical_refresh_failure_is_reported_not_a_failed_rest_call(self):
        self.fabric_responses(refresh=response({"value": [
            {"status": "Failed", "serviceExceptionJson": TOKEN}, {"status": "Completed"},
        ]}))
        self.assertEqual(self.main("diag_fabric"), 0)
        self.assertIn("refresh status: Failed", self.stdout.getvalue())

    def test_fabric_transient_retries_can_recover(self):
        self.fabric_responses(queries=[
            response(status=429), response(status=503), response(rows([{"[ok]": 1}])),
            response(rows([])),
        ])
        self.assertEqual(self.main("diag_fabric"), 0)
        self.assertEqual(self.http.post.call_count, 4)
        self.assertEqual(self.clock.waits, [5, 10])

    def test_fabric_exhausted_retries_fail_without_a_final_sleep(self):
        self.fabric_responses(queries=[response(status=429) for _ in range(3)] + [response(rows([]))])
        self.assertEqual(self.main("diag_fabric"), 1)
        self.assertEqual(self.http.post.call_count, 4)
        self.assertEqual(self.clock.waits, [5, 10])
        self.assertIn("retries exhausted", self.stderr.getvalue())

    def test_fabric_nontransient_query_error_does_not_retry(self):
        self.fabric_responses(queries=[response(status=403), response(rows([]))])
        self.assertEqual(self.main("diag_fabric"), 1)
        self.assertEqual(self.http.post.call_count, 2)
        self.assertEqual(self.clock.waits, [])

    def test_fabric_transport_failure_cannot_succeed(self):
        self.http.get.side_effect = FakeRequestError(TOKEN)
        self.assertEqual(self.main("diag_fabric"), 1)
        self.http.post.assert_not_called()

    def test_workiq_device_flow_uses_explicit_ids_scope_and_prompt_without_secret(self):
        self.workiq_responses(result=message(parts=[{"kind": "text", "text": TOKEN}]))
        self.assertEqual(self.main("diag_workiq"), 0)
        first, second, third = self.http.post.call_args_list
        self.assertEqual(first.args[0], f"https://login.microsoftonline.com/{TENANT}/oauth2/v2.0/devicecode")
        self.assertEqual(first.kwargs["data"], {"client_id": CLIENT, "scope": self.tools["diag_workiq"].SCOPE})
        self.assertEqual(second.args[0], f"https://login.microsoftonline.com/{TENANT}/oauth2/v2.0/token")
        self.assertEqual(second.kwargs["data"], {
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "client_id": CLIENT, "device_code": "offline-device-code",
        })
        self.assertEqual(third.args[0], self.tools["diag_workiq"].A2A)
        self.assertEqual(third.kwargs["headers"]["Authorization"], "Bearer " + TOKEN)
        self.assertEqual(third.kwargs["json"]["params"]["message"]["kind"], "message")
        self.assertEqual(third.kwargs["json"]["params"]["message"]["parts"], [{"kind": "text", "text": PROMPT}])
        for call in self.http.post.call_args_list:
            self.assertFalse(call.kwargs["allow_redirects"])
            self.assertNotIn("client_secret", call.kwargs.get("data", {}))
        self.credential.get_token.assert_not_called()
        self.assertIn("Code: OFFLINE-CODE", self.stdout.getvalue())

    def test_workiq_pending_and_slow_down_increase_all_subsequent_intervals(self):
        module = self.tools["diag_workiq"]
        self.http.post.side_effect = [
            response({"error": "authorization_pending"}, 400),
            response({"error": "slow_down"}, 400),
            response({"error": "authorization_pending"}, 400),
            response({"error": "slow_down"}, 429),
            response(bearer()),
        ]
        self.assertEqual(module.poll(self.http, environment("diag_workiq"), device(expires_in=120)), TOKEN)
        self.assertEqual(self.clock.waits, [5, 5, 10, 10, 15])
        self.assertEqual(self.http.post.call_count, 5)

    def test_workiq_poll_expiry_does_not_send_a_late_request(self):
        module = self.tools["diag_workiq"]
        self.http.post.side_effect = [response({"error": "authorization_pending"}, 400)]
        with self.assertRaisesRegex(module.DiagnosticError, "expired"):
            module.poll(self.http, environment("diag_workiq"), device(expires_in=7))
        self.assertEqual(self.clock.waits, [5, 2])
        self.assertEqual(self.http.post.call_count, 1)

    def test_workiq_missing_interval_uses_protocol_default(self):
        data = device()
        data.pop("interval")
        self.http.post.side_effect = [response(data), response(bearer())]
        module = self.tools["diag_workiq"]
        obtained = module.device_code(self.http, environment("diag_workiq"))
        self.assertEqual(module.poll(self.http, environment("diag_workiq"), obtained), TOKEN)
        self.assertEqual(self.clock.waits, [5])

    def test_workiq_malformed_device_response_never_polls(self):
        cases = [
            None, [], {}, device(device_code=""), device(user_code=None),
            device(verification_uri="http://login.invalid"),
            device(expires_in=0), device(expires_in="60"), device(interval=-1),
            device(interval=True), device(error={"message": TOKEN}),
        ]
        for body in cases:
            with self.subTest(body=body):
                self.http.post.reset_mock()
                self.http.post.side_effect = [response(body)]
                self.assertEqual(self.main("diag_workiq"), 1)
                self.assertEqual(self.http.post.call_count, 1)

    def test_workiq_failed_device_http_never_polls(self):
        self.http.post.side_effect = [response(status=401)]
        self.assertEqual(self.main("diag_workiq"), 1)
        self.assertEqual(self.http.post.call_count, 1)

    def test_workiq_terminal_oauth_errors_do_not_call_a2a(self):
        for error in ("access_denied", "authorization_declined", "expired_token",
                      "bad_verification_code", "invalid_client"):
            with self.subTest(error=error):
                self.http.post.reset_mock()
                self.http.post.side_effect = [
                    response(device()), response({"error": error, "error_description": TOKEN}, 400),
                ]
                self.assertEqual(self.main("diag_workiq"), 1)
                self.assertEqual(self.http.post.call_count, 2)

    def test_workiq_invalid_http200_token_payload_does_not_call_a2a(self):
        for body in (None, {}, bearer(access_token=""), bearer(access_token=None),
                     bearer(token_type="MAC"), bearer(error={"message": TOKEN})):
            with self.subTest(body=body):
                self.http.post.reset_mock()
                self.http.post.side_effect = [response(device()), response(body)]
                self.assertEqual(self.main("diag_workiq"), 1)
                self.assertEqual(self.http.post.call_count, 2)

    def test_workiq_malformed_json_fails_at_device_token_and_a2a(self):
        for phase in range(3):
            with self.subTest(phase=phase):
                bad = response()
                bad.json.side_effect = ValueError(TOKEN)
                self.http.post.side_effect = [response(device()), response(bearer())][:phase] + [bad]
                self.assertEqual(self.main("diag_workiq"), 1)

    def test_workiq_jsonrpc_error_in_http200_is_failure_and_not_dumped(self):
        self.workiq_responses(rpc_error={"code": -32001, "message": TOKEN})
        self.assertEqual(self.main("diag_workiq"), 1)
        self.assertIn("JSON-RPC error (code -32001)", self.stderr.getvalue())

    def test_workiq_non200_a2a_status_fails(self):
        for status in (401, 403, 429, 500, 302, 202):
            with self.subTest(status=status):
                self.workiq_responses(a2a_status=status)
                self.assertEqual(self.main("diag_workiq"), 1)

    def test_workiq_invalid_jsonrpc_envelopes_and_results_fail(self):
        module = self.tools["diag_workiq"]
        cases = [
            {}, {"jsonrpc": "1.0", "id": "request", "result": message()},
            {"jsonrpc": "2.0", "id": "different", "result": message()},
            {"jsonrpc": "2.0", "id": "request", "result": None},
            {"jsonrpc": "2.0", "id": "request", "result": {}},
            {"jsonrpc": "2.0", "id": "request", "error": None, "result": message()},
            {"jsonrpc": "2.0", "id": "request", "result": {"error": {"message": TOKEN}}},
        ]
        for body in cases:
            with self.subTest(body=body), self.assertRaises(module.DiagnosticError):
                module.check_a2a(body, "request")

    def test_workiq_failed_or_nonterminal_tasks_and_malformed_messages_fail(self):
        for state in ("failed", "canceled", "rejected", "working", "submitted", "input-required", "auth-required"):
            with self.subTest(state=state):
                self.workiq_responses(result={"kind": "task", "id": "offline-task", "status": {"state": state}})
                self.assertEqual(self.main("diag_workiq"), 1)
        for result in (message(role="user"), message(parts=[]), message(parts=[None]),
                       message(parts=[{"kind": "text"}]), message(messageId=""),
                       message(parts=[{"kind": "data", "data": []}]),
                       message(parts=[{"kind": "file"}]),
                       message(parts=[{"kind": "file", "file": {}}]),
                       message(parts=[{"kind": "file", "file": {"uri": "", "bytes": ""}}])):
            with self.subTest(result=result):
                self.workiq_responses(result=result)
                self.assertEqual(self.main("diag_workiq"), 1)

    def test_workiq_structured_and_file_messages_succeed_without_content_output(self):
        self.workiq_responses(result=message(parts=[
            {"kind": "data", "data": {"private": TOKEN}},
            {"kind": "file", "file": {"uri": "https://files.invalid/offline"}},
            {"kind": "file", "file": {"bytes": "b2ZmbGluZQ=="}},
        ]))
        self.assertEqual(self.main("diag_workiq"), 0)
        self.assertIn("3 parts", self.stdout.getvalue())
        self.assertNotIn("https://files.invalid/offline", self.stdout.getvalue())

    def test_workiq_completed_task_succeeds(self):
        self.workiq_responses(result={"kind": "task", "id": "offline-task", "status": {"state": "completed"}})
        self.assertEqual(self.main("diag_workiq"), 0)
        self.assertIn("completed task", self.stdout.getvalue())

    def test_workiq_transport_failure_is_nonzero_and_redacted(self):
        self.http.post.side_effect = FakeRequestError(TOKEN)
        self.assertEqual(self.main("diag_workiq"), 1)


if __name__ == "__main__":
    unittest.main()
