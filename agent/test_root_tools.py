"""Offline regression tests for the four portable root maintenance tools."""

from __future__ import annotations

import builtins
import copy
import importlib
import importlib.util
import io
import os
import socket
import subprocess
import sys
import types
import unittest
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
TOOL_NAMES = (
    "create_scenario_agent",
    "push_agent_instructions",
    "set_tool_allowlist",
    "set_tool_autoapprove",
)
INSTRUCTION_TOOLS = TOOL_NAMES[:2]
API = "2025-05-15-preview"
ENDPOINT = "https://foundry.invalid/api/projects/test-project"
AGENT = "target / agent"
SOURCE = "source / agent"
TARGET_URL = ENDPOINT + "/agents/target%20%2F%20agent"
SOURCE_URL = ENDPOINT + "/agents/source%20%2F%20agent"
AUTH_FIELDS = {
    "azure_cli": ("AZURE_TENANT_ID", "AZURE_SUBSCRIPTION_ID"),
    "service_principal": ("AZURE_TENANT_ID", "AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET"),
    "managed_identity": ("AZURE_CLIENT_ID",),
}
FAKE_AUTH = {
    "AZURE_TENANT_ID": "11111111-1111-4111-8111-111111111111",
    "AZURE_SUBSCRIPTION_ID": "22222222-2222-4222-8222-222222222222",
    "AZURE_CLIENT_ID": "33333333-3333-4333-8333-333333333333",
    "AZURE_CLIENT_SECRET": "fake-unit-test-value-not-a-secret",
}
START = "<!-- INSTRUCTIONS-START -->"
END = "<!-- INSTRUCTIONS-END -->"
DOCUMENT = f"Human preamble\n{START}\nUse governed sources.\n{END}\nHuman appendix"


def environment(mode="azure_cli"):
    return {
        "FOUNDRY_PROJECT_ENDPOINT": ENDPOINT + "/",
        "FOUNDRY_AGENT_NAME": AGENT,
        "FOUNDRY_SOURCE_AGENT_NAME": SOURCE,
        "AZURE_AUTH_MODE": mode,
        **{name: FAKE_AUTH[name] for name in AUTH_FIELDS[mode]},
    }


def load_tool(name):
    spec = importlib.util.spec_from_file_location(f"_root_test_{name}", ROOT / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def response(body=None, status=200):
    result = mock.Mock()
    result.status_code = status
    result.json.return_value = body
    result.text = "mock service error"
    return result


def definition(tools=None):
    return {
        "kind": "prompt",
        "model": "test-model",
        "instructions": "Existing instructions",
        "reasoning": {"effort": "high", "summary": "auto", "additional": {"keep": True}},
        "temperature": 0.2,
        "metadata": {"preserve": ["custom", "properties"]},
        "tools": tools if tools is not None else [
            {
                "type": "fabric_iq_preview",
                "project_connection_id": "connections/fabric-test",
                "require_approval": "always",
                "extra": {"keep": [1, 2]},
            },
            {
                "type": "mcp",
                "server_label": "kb-policy",
                "server_url": "https://knowledge.invalid/mcp",
                "allowed_tools": {"tool_names": ["search"], "read_only": True},
                "require_approval": {"always": {"tool_names": ["search"]}},
                "extra": {"keep": True},
            },
            {"type": "work_iq_preview", "server_label": "WorkIQMail", "extra": "keep"},
            {"type": "web_search", "filters": {"allowed_domains": ["example.invalid"]}},
            {"type": "mcp", "server_label": "unrelated", "require_approval": "always"},
        ],
    }


class RootToolsTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(mock.patch.object(sys, "dont_write_bytecode", True))
        self.stack.enter_context(mock.patch.object(sys, "path", [str(ROOT), *sys.path]))
        self.stack.enter_context(mock.patch.dict(os.environ, environment(), clear=True))
        self.stdout = self.stack.enter_context(redirect_stdout(io.StringIO()))
        self.stderr = self.stack.enter_context(redirect_stderr(io.StringIO()))
        self.forbid_requests_import = False
        original_import = builtins.__import__

        def guarded_import(name, *args, **kwargs):
            if name == "azure" or name.startswith("azure."):
                raise ModuleNotFoundError("Azure SDK is deliberately unavailable in root tool tests")
            if name == "requests" and self.forbid_requests_import:
                raise AssertionError("requests imported before local validation completed")
            return original_import(name, *args, **kwargs)

        self.stack.enter_context(mock.patch("builtins.__import__", side_effect=guarded_import))
        self.stack.enter_context(mock.patch.object(
            subprocess, "run", side_effect=AssertionError("No subprocesses in offline tests")))
        self.stack.enter_context(mock.patch.object(
            socket, "socket", side_effect=AssertionError("No sockets in offline tests")))
        self.write_text = self.stack.enter_context(mock.patch.object(
            Path, "write_text", side_effect=AssertionError("No file writes in root tools")))
        self.write_bytes = self.stack.enter_context(mock.patch.object(
            Path, "write_bytes", side_effect=AssertionError("No file writes in root tools")))
        self.http = types.ModuleType("requests")
        self.http.get = mock.Mock()
        self.http.post = mock.Mock(return_value=response({
            "version": "12", "definition": {"tools": [], "instructions": "Saved"},
        }))
        self.stack.enter_context(mock.patch.dict(sys.modules, {"requests": self.http}))
        self.portability = importlib.import_module("agent.portability")
        self.credentials = self.stack.enter_context(mock.patch.object(
            self.portability, "build_credential",
            side_effect=AssertionError("No real credentials in offline tests")))

    def tool(self, name):
        module = load_tool(name)
        module._test_token = self.stack.enter_context(
            mock.patch.object(module, "foundry_token", return_value="offline-test-token"))
        return module

    def instructions(self, value=DOCUMENT):
        return mock.patch.object(Path, "read_text", return_value=value)

    def configure_get(self, name, data):
        if name == "create_scenario_agent":
            self.http.get.side_effect = [
                response({"versions": {"latest": {"version": "3"}}}),
                response({"version": "3", "definition": data}),
                response(status=404),
            ]
        elif name == "push_agent_instructions":
            self.http.get.side_effect = None
            self.http.get.return_value = response({"data": [
                {"version": "2", "definition": definition([])},
                {"version": "10", "definition": data},
                {"version": "9", "definition": definition([])},
            ]})
        else:
            self.http.get.side_effect = None
            self.http.get.return_value = response({
                "versions": {"latest": {"version": "3", "definition": data}},
            })

    def assert_config_error(self, module, message, argv=None):
        self.forbid_requests_import = True
        try:
            with self.assertRaises(SystemExit) as caught:
                module.main(["--apply"] if argv is None else argv)
        finally:
            self.forbid_requests_import = False
        self.assertEqual(caught.exception.code, 2)
        self.assertIn(message, self.stderr.getvalue())
        module._test_token.assert_not_called()
        self.credentials.assert_not_called()
        self.http.get.assert_not_called()
        self.http.post.assert_not_called()
        self.write_text.assert_not_called()
        self.write_bytes.assert_not_called()
        self.stderr.seek(0)
        self.stderr.truncate()

    def assert_reads(self):
        self.assertTrue(self.http.get.called)
        for call in self.http.get.call_args_list:
            self.assertEqual(call.kwargs, {
                "headers": {
                    "Authorization": "Bearer offline-test-token",
                    "Content-Type": "application/json",
                },
                "timeout": 60,
            })
            self.assertTrue(call.args[0].endswith(f"?api-version={API}"))

    def assert_post(self, data, **extra):
        self.http.post.assert_called_once_with(
            f"{TARGET_URL}/versions?api-version={API}",
            headers={
                "Authorization": "Bearer offline-test-token",
                "Content-Type": "application/json",
            },
            json={"definition": data, **extra},
            timeout=120,
        )

    def test_imports_have_no_environment_credentials_http_or_instruction_effects(self):
        self.forbid_requests_import = True
        for name in TOOL_NAMES:
            with self.subTest(tool=name), ExitStack() as stack:
                for function in ("load_foundry_config", "foundry_token", "require_file"):
                    stack.enter_context(mock.patch.object(
                        self.portability, function,
                        side_effect=AssertionError(f"{function} called at import")))
                stack.enter_context(mock.patch.object(
                    os, "getenv", side_effect=AssertionError("getenv at import")))
                for method in ("__getitem__", "__iter__", "__contains__"):
                    stack.enter_context(mock.patch.object(
                        type(os.environ), method,
                        side_effect=AssertionError("environment access at import")))
                stack.enter_context(mock.patch.object(
                    Path, "read_text", side_effect=AssertionError("instructions read at import")))
                module = load_tool(name)
                self.assertEqual(module.API, API)
                self.assertTrue(callable(module.main))
                self.assertNotIn("requests", vars(module))
        self.credentials.assert_not_called()
        self.http.get.assert_not_called()
        self.http.post.assert_not_called()

    def test_each_missing_or_blank_required_variable_fails_before_side_effects(self):
        for mode, fields in AUTH_FIELDS.items():
            for name in TOOL_NAMES:
                required = ("FOUNDRY_PROJECT_ENDPOINT", "FOUNDRY_AGENT_NAME", "AZURE_AUTH_MODE", *fields)
                if name == "create_scenario_agent":
                    required += ("FOUNDRY_SOURCE_AGENT_NAME",)
                for variable in required:
                    for value in (None, "", " \t "):
                        with self.subTest(mode=mode, tool=name, variable=variable, value=value):
                            env = environment(mode)
                            if value is None:
                                del env[variable]
                            else:
                                env[variable] = value
                            with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(
                                Path, "read_text", side_effect=AssertionError("read before config validation")
                            ):
                                self.assert_config_error(self.tool(name), variable)

    def test_invalid_endpoints_fail_before_side_effects(self):
        for name in TOOL_NAMES:
            for endpoint in (
                "http://foundry.invalid/project",
                "https:///project",
                "https://foundry.invalid/project?query=value",
                "https://foundry.invalid/project#fragment",
                "https://foundry.invalid/project?",
                "https://foundry.invalid/project#",
                "https://user@foundry.invalid/project",
                "https://user:fake@foundry.invalid/project",
            ):
                with self.subTest(tool=name, endpoint=endpoint), mock.patch.dict(
                    os.environ, {"FOUNDRY_PROJECT_ENDPOINT": endpoint}
                ):
                    self.assert_config_error(self.tool(name), "FOUNDRY_PROJECT_ENDPOINT")

    def test_unknown_auth_mode_does_not_fall_back(self):
        for name in TOOL_NAMES:
            with self.subTest(tool=name), mock.patch.dict(os.environ, {"AZURE_AUTH_MODE": "default"}):
                self.assert_config_error(self.tool(name), "AZURE_AUTH_MODE")

    def test_only_selected_auth_fields_and_scenario_source_are_required(self):
        for mode in AUTH_FIELDS:
            for name in TOOL_NAMES:
                with self.subTest(mode=mode, tool=name):
                    env = environment(mode)
                    if name != "create_scenario_agent":
                        del env["FOUNDRY_SOURCE_AGENT_NAME"]
                    with mock.patch.dict(os.environ, env, clear=True), self.instructions():
                        module = self.tool(name)
                        self.configure_get(name, definition())
                        self.assertEqual(module.main([]), 0)
                    config = module._test_token.call_args.args[0]
                    self.assertEqual(config["AZURE_AUTH_MODE"], mode)
                    self.assertEqual(config["FOUNDRY_PROJECT_ENDPOINT"], ENDPOINT)
                    for field in AUTH_FIELDS[mode]:
                        self.assertEqual(config[field], FAKE_AUTH[field])
                    self.http.post.assert_not_called()

    def test_missing_instruction_files_or_directories_fail_before_side_effects(self):
        for name in INSTRUCTION_TOOLS:
            for path in (ROOT / "agent" / "__missing_root_tool_instructions__.md", ROOT / "agent"):
                with self.subTest(tool=name, path=path):
                    module = self.tool(name)
                    with mock.patch.object(module, "INSTRUCTIONS", path):
                        self.assert_config_error(module, "instructions")

    def test_malformed_or_empty_instructions_fail_before_side_effects(self):
        for name in INSTRUCTION_TOOLS:
            for text in (
                "No markers",
                f"{START} text",
                f"text {END}",
                f"{END} text {START}",
                f"{START} text {START} {END}",
                f"{START} text {END} {END}",
                f"{START} \n\t {END}",
            ):
                with self.subTest(tool=name, text=text), self.instructions(text):
                    self.assert_config_error(self.tool(name), "instructions")

    def test_instruction_read_errors_fail_before_side_effects(self):
        for name in INSTRUCTION_TOOLS:
            for error in (OSError("instructions cannot be read"),
                          UnicodeError("instructions are not valid UTF-8")):
                with self.subTest(tool=name, error=error), mock.patch.object(
                    Path, "read_text", side_effect=error
                ):
                    self.assert_config_error(self.tool(name), "instructions")

    def test_invalid_arguments_and_help_do_not_authenticate(self):
        for name in TOOL_NAMES:
            with self.subTest(tool=name):
                module = self.tool(name)
                self.assert_config_error(module, "unrecognized arguments", ["--unknown"])
                self.forbid_requests_import = True
                with self.assertRaises(SystemExit) as caught:
                    module.main(["--help"])
                self.forbid_requests_import = False
                self.assertEqual(caught.exception.code, 0)
                module._test_token.assert_not_called()
        self.assert_config_error(self.tool("push_agent_instructions"), "--effort", ["--effort", "invalid"])

    def test_token_wrappers_delegate_config_unchanged(self):
        config = environment()
        for name in TOOL_NAMES:
            with self.subTest(tool=name):
                module = self.tool(name)
                self.assertEqual(module.token(config), "offline-test-token")
                module._test_token.assert_called_once_with(config)

    def test_all_dry_runs_authenticate_and_read_but_never_post(self):
        for name in TOOL_NAMES:
            with self.subTest(tool=name), self.instructions():
                self.http.get.reset_mock()
                module = self.tool(name)
                data = definition()
                before = copy.deepcopy(data)
                self.configure_get(name, data)
                self.assertEqual(module.main([]), 0)
                module._test_token.assert_called_once()
                self.assert_reads()
                self.http.post.assert_not_called()
                self.assertEqual(data, before)

    def test_scenario_copies_only_one_fabric_and_one_kb_preserving_properties(self):
        module = self.tool("create_scenario_agent")
        data = definition()
        before = copy.deepcopy(data)
        self.configure_get("create_scenario_agent", data)
        with self.instructions():
            self.assertEqual(module.main(["--apply"]), 0)
        expected = copy.deepcopy(before)
        expected["instructions"] = "Use governed sources."
        expected["reasoning"]["effort"] = "low"
        expected["tools"] = before["tools"][:2]
        self.assert_post(expected, description="Scenario Analyst - Fabric IQ + Foundry IQ only")
        self.assertEqual(data, before)
        self.assertEqual([call.args[0] for call in self.http.get.call_args_list], [
            f"{SOURCE_URL}?api-version={API}",
            f"{SOURCE_URL}/versions/3?api-version={API}",
            f"{TARGET_URL}?api-version={API}",
        ])
        self.assert_reads()

    def test_scenario_preserves_compatible_tool_choice(self):
        for choice in (
            None, "auto", "none", "required",
            {"type": "mcp", "server_label": "kb-policy"},
            {"type": "mcp", "server_label": "kb-policy", "name": None},
            {"type": "mcp", "server_label": "kb-policy", "name": "search"},
            *({"type": "allowed_tools", "mode": mode, "tools": [
                {"type": "mcp", "server_label": "kb-policy", "name": "search"},
            ]} for mode in ("auto", "required")),
        ):
            with self.subTest(choice=choice), self.instructions():
                self.http.post.reset_mock()
                module = self.tool("create_scenario_agent")
                data = definition()
                data["tool_choice"] = choice
                before = copy.deepcopy(data)
                self.configure_get("create_scenario_agent", data)
                self.assertEqual(module.main(["--apply"]), 0)
                expected = copy.deepcopy(before)
                expected["instructions"] = "Use governed sources."
                expected["reasoning"]["effort"] = "low"
                expected["tools"] = before["tools"][:2]
                self.assert_post(expected, description="Scenario Analyst - Fabric IQ + Foundry IQ only")
                self.assertEqual(data, before)

    def test_scenario_rejects_incompatible_or_unrecognized_tool_choice_before_post(self):
        choices = (
            {"type": "mcp", "server_label": "unrelated"},
            {"type": "mcp", "server_label": "kb-excluded", "name": "search"},
            {"type": "function", "name": "lookup_account"},
            {"type": "function", "function": {"name": "lookup_account"}},
            {"type": "web_search"},
            {"type": "work_iq_preview"},
            {"type": "code_interpreter"},
            {"type": "fabric_iq_preview"},
            "unknown", "", False, 1, [], {},
            {"type": "unknown"},
            {"type": "mcp"},
            {"type": "mcp", "server_label": ""},
            {"type": "mcp", "server_label": ["kb-policy"]},
            {"type": "mcp", "server_label": "kb-policy", "name": ""},
            {"type": "mcp", "server_label": "kb-policy", "name": ["search"]},
            {"type": "mcp", "server_label": "kb-policy", "name": "excluded"},
            {"type": "mcp", "server_label": "kb-policy", "unknown": True},
            {"type": "allowed_tools", "mode": "required", "tools": [
                {"type": "mcp", "server_label": "kb-policy"},
                {"type": "mcp", "server_label": "unrelated"},
            ]},
            {"type": "allowed_tools", "mode": "auto", "tools": [
                {"type": "function", "name": "lookup_account"},
            ]},
            {"type": "allowed_tools", "mode": "none", "tools": [
                {"type": "mcp", "server_label": "kb-policy"},
            ]},
            {"type": "allowed_tools", "mode": "auto", "tools": []},
            {"type": "allowed_tools", "mode": "auto", "tools": ["auto"]},
            {"type": "allowed_tools", "mode": "auto", "tools": [None]},
            {"type": "allowed_tools", "mode": "auto"},
        )
        for choice in choices:
            for argv in ([], ["--apply"]):
                with self.subTest(choice=choice, argv=argv), self.instructions():
                    self.http.get.reset_mock()
                    self.stderr.seek(0)
                    self.stderr.truncate()
                    module = self.tool("create_scenario_agent")
                    data = definition()
                    data["tools"].extend([
                        {"type": "function", "name": "lookup_account", "parameters": {}},
                        {"type": "code_interpreter", "container": {"type": "auto"}},
                    ])
                    data["tool_choice"] = choice
                    before = copy.deepcopy(data)
                    self.configure_get("create_scenario_agent", data)
                    with self.assertRaises(SystemExit) as caught:
                        module.main(argv)
                    self.assertEqual(caught.exception.code, 2)
                    for text in ("tool_choice", "FOUNDRY_SOURCE_AGENT_NAME", "kb-policy", "auto"):
                        self.assertIn(text, self.stderr.getvalue())
                    self.assertEqual(self.http.get.call_count, 2)
                    self.http.post.assert_not_called()
                    self.assertEqual(data, before)

    def test_scenario_rejects_source_equal_to_target_before_side_effects(self):
        for target in (SOURCE, f" \t{SOURCE} "):
            for argv in ([], ["--apply"]):
                with self.subTest(target=target, argv=argv), mock.patch.dict(
                    os.environ, {"FOUNDRY_AGENT_NAME": target}
                ), mock.patch.object(
                    Path, "read_text", side_effect=AssertionError("read before identity validation")
                ):
                    self.assert_config_error(
                        self.tool("create_scenario_agent"), "must differ", argv)

    def test_scenario_reads_existing_target_version(self):
        module = self.tool("create_scenario_agent")
        data = definition()
        self.http.get.side_effect = [
            response({"versions": {"latest": {"version": "3"}}}),
            response({"version": "3", "definition": data}),
            response({"versions": {"latest": {"version": "7"}}}),
            response({"version": "7", "definition": definition([])}),
        ]
        with self.instructions():
            self.assertEqual(module.main([]), 0)
        self.assertIn("v7", self.stdout.getvalue())
        self.assertEqual(self.http.get.call_args.args[0],
                         f"{TARGET_URL}/versions/7?api-version={API}")
        self.http.post.assert_not_called()

    def test_scenario_rejects_duplicate_tool_types_not_just_wrong_total(self):
        fabric, kb = definition()["tools"][:2]
        for tools in ([], [fabric], [kb], [fabric, fabric], [kb, kb],
                      [fabric, kb, kb], [fabric, fabric, kb],
                      [fabric, {"type": "mcp", "server_label": "not-a-kb"}]):
            with self.subTest(tools=tools), self.instructions():
                self.http.get.reset_mock()
                module = self.tool("create_scenario_agent")
                self.configure_get("create_scenario_agent", definition(tools))
                with self.assertRaises(SystemExit) as caught:
                    module.main(["--apply"])
                self.assertEqual(caught.exception.code, 2)
                self.assertIn("FOUNDRY_SOURCE_AGENT_NAME", self.stderr.getvalue())
                self.assertEqual(self.http.get.call_count, 2)
                self.http.post.assert_not_called()

    def test_scenario_missing_source_fails_without_posting(self):
        module = self.tool("create_scenario_agent")
        self.http.get.return_value = response(status=404)
        with self.instructions(), self.assertRaises(SystemExit) as caught:
            module.main(["--apply"])
        self.assertEqual(caught.exception.code, 2)
        self.assertIn("FOUNDRY_SOURCE_AGENT_NAME", self.stderr.getvalue())
        self.http.get.assert_called_once()
        self.http.post.assert_not_called()

    def test_push_uses_numeric_latest_and_preserves_definition_and_reasoning(self):
        module = self.tool("push_agent_instructions")
        data = definition()
        before = copy.deepcopy(data)
        self.configure_get("push_agent_instructions", data)
        with self.instructions():
            self.assertEqual(module.main(["--apply", "--effort", "low"]), 0)
        expected = copy.deepcopy(before)
        expected["instructions"] = "Use governed sources."
        expected["reasoning"]["effort"] = "low"
        self.assert_post(expected)
        self.assertEqual(data, before)
        self.assertEqual(self.http.get.call_args.args[0],
                         f"{TARGET_URL}/versions?api-version={API}")
        self.assert_reads()

    def test_push_default_effort_is_medium_with_missing_or_null_reasoning(self):
        for reasoning in ("missing", None):
            with self.subTest(reasoning=reasoning), self.instructions():
                self.http.post.reset_mock()
                module = self.tool("push_agent_instructions")
                data = definition()
                if reasoning == "missing":
                    del data["reasoning"]
                else:
                    data["reasoning"] = None
                self.configure_get("push_agent_instructions", data)
                self.assertEqual(module.main(["--apply"]), 0)
                posted = self.http.post.call_args.kwargs["json"]["definition"]
                self.assertEqual(posted["reasoning"], {"effort": "medium"})

    def test_allowlist_changes_preserve_every_other_property(self):
        module = self.tool("set_tool_allowlist")
        data = definition([
            {"type": "mcp", "server_label": label, "allowed_tools": ["old"],
             "require_approval": "always", "extra": {"keep": True}}
            for label in module.ALLOWLIST
        ] + [{"type": "mcp", "server_label": "other", "allowed_tools": ["keep"],
              "extra": {"nested": [1, 2]}}])
        del data["tools"][0]["server_label"]
        data["tools"][0]["project_connection_id"] = "connections/WorkIQMail"
        before = copy.deepcopy(data)
        self.configure_get("set_tool_allowlist", data)
        self.assertEqual(module.main(["--apply"]), 0)
        expected = copy.deepcopy(before)
        for tool in expected["tools"]:
            wanted = module.ALLOWLIST.get(module.label(tool))
            if wanted is not None:
                tool["allowed_tools"] = wanted
        self.assert_post(expected)
        self.assertEqual(data, before)
        self.assert_reads()

    def test_allowlist_is_idempotent_for_list_and_service_dictionary_shapes(self):
        for service_shape in (False, True):
            with self.subTest(service_shape=service_shape):
                module = self.tool("set_tool_allowlist")
                tools = []
                for label, names in module.ALLOWLIST.items():
                    allowed = {"tool_names": list(names), "read_only": True} if service_shape else list(names)
                    tools.append({"type": "mcp", "server_label": label, "allowed_tools": allowed})
                data = definition(tools)
                before = copy.deepcopy(data)
                self.configure_get("set_tool_allowlist", data)
                self.assertEqual(module.main(["--apply"]), 0)
                self.http.post.assert_not_called()
                self.assertEqual(data, before)

    def test_allowlist_clear_removes_all_filters_without_changing_other_properties(self):
        module = self.tool("set_tool_allowlist")
        data = definition([
            {"type": "mcp", "server_label": "WorkIQMail",
             "allowed_tools": {"tool_names": ["search"]}, "require_approval": "always"},
            {"type": "mcp", "server_label": "other", "allowed_tools": ["keep"]},
            {"type": "fabric_iq_preview", "allowed_tools": None, "extra": {"keep": True}},
            {"type": "web_search", "extra": "untouched"},
        ])
        before = copy.deepcopy(data)
        self.configure_get("set_tool_allowlist", data)
        self.assertEqual(module.main(["--clear", "--apply"]), 0)
        expected = copy.deepcopy(before)
        for tool in expected["tools"]:
            tool.pop("allowed_tools", None)
        self.assert_post(expected)
        self.assertEqual(data, before)
        self.http.post.reset_mock()
        self.configure_get("set_tool_allowlist", expected)
        self.assertEqual(module.main(["--clear", "--apply"]), 0)
        self.http.post.assert_not_called()

    def test_allowlist_clear_dry_run_does_not_post(self):
        module = self.tool("set_tool_allowlist")
        data = definition()
        before = copy.deepcopy(data)
        self.configure_get("set_tool_allowlist", data)
        self.assertEqual(module.main(["--clear"]), 0)
        self.assert_reads()
        self.http.post.assert_not_called()
        self.assertEqual(data, before)

    def test_approvals_change_only_approvable_types(self):
        module = self.tool("set_tool_autoapprove")
        data = definition([
            {"type": "mcp", "server_label": "kb-test", "require_approval": {"always": {}}},
            {"type": "fabric_iq_preview", "project_connection_id": "connections/fabric",
             "require_approval": "always", "extra": {"keep": True}},
            {"type": "work_iq_preview", "server_label": "WorkIQMail"},
            {"type": "mcp", "server_label": "already-never", "require_approval": "never"},
            {"type": "web_search", "extra": "keep"},
            {"type": "bing_grounding", "require_approval": "always"},
            {"type": "function", "require_approval": {"always": {}}, "extra": [1, 2]},
        ])
        before = copy.deepcopy(data)
        self.configure_get("set_tool_autoapprove", data)
        self.assertEqual(module.main(["--apply"]), 0)
        expected = copy.deepcopy(before)
        for tool in expected["tools"][:4]:
            tool["require_approval"] = "never"
        self.assert_post(expected)
        self.assertEqual(data, before)
        self.assert_reads()

    def test_approvals_already_never_and_non_approvable_only_are_no_ops(self):
        module = self.tool("set_tool_autoapprove")
        cases = [
            [{"type": kind, "require_approval": "never"} for kind in module.APPROVABLE],
            [{"type": "web_search"}, {"type": "bing_grounding", "require_approval": "always"}],
            [],
        ]
        for tools in cases:
            with self.subTest(tools=tools):
                self.configure_get("set_tool_autoapprove", definition(tools))
                self.assertEqual(module.main(["--apply"]), 0)
                self.http.post.assert_not_called()

    def test_get_failures_propagate_without_posting(self):
        for name in TOOL_NAMES:
            with self.subTest(tool=name), self.instructions():
                module = self.tool(name)
                failure = response(status=403)
                failure.raise_for_status.side_effect = RuntimeError("mock GET denied")
                self.http.get.return_value = failure
                with self.assertRaisesRegex(RuntimeError, "mock GET denied"):
                    module.main(["--apply"])
                self.http.post.assert_not_called()

    def test_credential_failures_propagate_without_http(self):
        for name in TOOL_NAMES:
            with self.subTest(tool=name), self.instructions():
                module = self.tool(name)
                module._test_token.side_effect = RuntimeError("mock credential failure")
                with self.assertRaisesRegex(RuntimeError, "mock credential failure"):
                    module.main(["--apply"])
                self.http.get.assert_not_called()
                self.http.post.assert_not_called()

    def test_post_failures_are_reported_not_successfully_swallowed(self):
        for name in TOOL_NAMES:
            with self.subTest(tool=name), self.instructions():
                self.http.post.reset_mock()
                self.http.post.return_value = response(status=409)
                module = self.tool(name)
                self.configure_get(name, definition())
                if name == "create_scenario_agent":
                    with self.assertRaisesRegex(SystemExit, "create failed 409"):
                        module.main(["--apply"])
                else:
                    self.assertEqual(module.main(["--apply"]), 1)
                    self.assertIn("FAILED 409", self.stdout.getvalue())
                self.http.post.assert_called_once()


if __name__ == "__main__":
    unittest.main()
