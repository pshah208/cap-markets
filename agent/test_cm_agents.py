"""Offline regression tests for mission-agent validation and copying."""

from __future__ import annotations

import builtins
import copy
import importlib.util
import io
import os
from pathlib import Path
import runpy
import socket
import subprocess
import sys
import types
import unittest
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from unittest import mock


DIRECTORY = Path(__file__).resolve().parent
ENDPOINT = "https://foundry.invalid/api/projects/unit-test"
SOURCE = "source / agent"
SOURCE_URL = ENDPOINT + "/agents/source%20%2F%20agent"
API = "2025-05-15-preview"
AUTH_FIELDS = {
    "azure_cli": ("AZURE_TENANT_ID", "AZURE_SUBSCRIPTION_ID"),
    "service_principal": ("AZURE_TENANT_ID", "AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET"),
    "managed_identity": ("AZURE_CLIENT_ID",),
}


def environment(mode="managed_identity"):
    return {
        "FOUNDRY_PROJECT_ENDPOINT": ENDPOINT + "/",
        "FOUNDRY_SOURCE_AGENT_NAME": SOURCE,
        "AZURE_AUTH_MODE": mode,
        **{field: "offline-test-value" for field in AUTH_FIELDS[mode]},
    }


def block(name="mission-one", kinds="fabric,kb,work,web", instructions="Mission instructions."):
    return f"<!-- AGENT {name} tools={kinds} -->\n{instructions}\n<!-- END -->\n"


def response(body=None, status=200):
    result = mock.Mock()
    result.status_code = status
    result.json.return_value = body
    result.text = "offline response error"
    if status >= 400:
        result.raise_for_status.side_effect = RuntimeError(f"HTTP {status}")
    return result


def definition():
    return {
        "kind": "source-kind",
        "model": "source-model",
        "instructions": "Source instructions",
        "temperature": 0.25,
        "reasoning": {"effort": "high", "summary": "auto"},
        "text": {"format": {"type": "json_object"}},
        "settings": {"nested": {"preserve": [1, 2]}},
        "tools": [
            {"type": "web_search", "filters": {"allowed_domains": ["example.invalid"]}},
            {"type": "mcp", "server_label": "WorkIQMail",
             "require_approval": "always", "allowed_tools": ["read_mail"]},
            {"type": "mcp", "server_label": "kb-policy",
             "server_url": "https://knowledge.invalid/mcp",
             "require_approval": {"always": {"tool_names": ["search"]}},
             "allowed_tools": {"tool_names": ["search"], "read_only": True}},
            {"type": "fabric_iq_preview", "project_connection_id": "connections/fabric-test",
             "extra": {"preserve": [1, 2]}},
            {"type": "mcp", "server_label": "unrelated"},
            {"type": "web_search_preview", "search_context_size": "low"},
            {"type": "work_iq_preview", "server_label": "workiqTeams", "extra": True},
            {"type": "bing_grounding", "bing_grounding": {"search_configurations": []}},
            {"type": "mcp", "server_label": "kb-second", "require_approval": "always"},
            {"type": "fabric_iq_preview", "project_connection_id": "connections/fabric-second"},
        ],
    }


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MissionAgentTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(mock.patch.object(sys, "dont_write_bytecode", True))
        self.stack.enter_context(mock.patch.dict(os.environ, environment(), clear=True))
        self.stdout = self.stack.enter_context(redirect_stdout(io.StringIO()))
        self.stderr = self.stack.enter_context(redirect_stderr(io.StringIO()))
        self.block_requests = False
        original_import = builtins.__import__

        def guarded_import(name, *args, **kwargs):
            if name == "azure" or name.startswith("azure."):
                raise AssertionError("Azure imports are forbidden in offline tests")
            if name == "requests" and self.block_requests:
                raise AssertionError("requests imported before local validation")
            return original_import(name, *args, **kwargs)

        self.stack.enter_context(mock.patch("builtins.__import__", side_effect=guarded_import))
        self.stack.enter_context(mock.patch.object(
            socket, "socket", side_effect=AssertionError("No sockets in offline tests")))
        self.stack.enter_context(mock.patch.object(
            subprocess, "Popen", side_effect=AssertionError("No subprocesses in offline tests")))
        self.stack.enter_context(mock.patch.object(
            Path, "write_text", side_effect=AssertionError("No file writes in offline tests")))
        self.stack.enter_context(mock.patch.object(
            Path, "write_bytes", side_effect=AssertionError("No file writes in offline tests")))
        self.helper = load_module("_cm_test_portability", DIRECTORY / "portability.py")
        self.credential = self.stack.enter_context(mock.patch.object(
            self.helper, "build_credential", side_effect=AssertionError("No real credentials")))
        package = types.ModuleType("_cm_test_agent")
        package.__path__ = [str(DIRECTORY)]
        package.__spec__ = importlib.util.spec_from_loader(
            package.__name__, loader=None, is_package=True)
        self.http = types.ModuleType("requests")
        self.http.get = mock.Mock()
        self.http.post = mock.Mock(return_value=response({"version": "12"}))
        self.stack.enter_context(mock.patch.dict(sys.modules, {
            "portability": self.helper,
            "_cm_test_agent": package,
            "_cm_test_agent.portability": self.helper,
            "requests": self.http,
        }))

    def builder(self, package=False):
        name = "_cm_test_agent.create_cm_agents" if package else "_cm_test_builder"
        module = load_module(name, DIRECTORY / "create_cm_agents.py")
        module.test_token = self.stack.enter_context(
            mock.patch.object(module, "foundry_token", return_value="offline-token"))
        return module

    def source(self, data=None, targets=1):
        self.http.get.side_effect = [
            response({"versions": {"latest": {"version": "3"}}}),
            response({"version": "3", "definition": definition() if data is None else data}),
            *[response(status=404) for _ in range(targets)],
        ]

    def assert_local_error(self, module, message):
        self.block_requests = True
        with self.assertRaises(SystemExit) as caught:
            module.main(["--apply"])
        self.assertEqual(caught.exception.code, 2)
        self.assertIn(message, self.stderr.getvalue())
        module.test_token.assert_not_called()
        self.credential.assert_not_called()
        self.http.get.assert_not_called()
        self.http.post.assert_not_called()

    def test_import_is_inert_for_direct_and_package(self):
        self.block_requests = True
        with mock.patch.object(os, "getenv", side_effect=AssertionError("No environment reads")), \
                mock.patch.object(os._Environ, "__getitem__", side_effect=AssertionError("No env reads")), \
                mock.patch.object(Path, "read_text", side_effect=AssertionError("No data reads")), \
                mock.patch.object(Path, "is_file", side_effect=AssertionError("No file checks")):
            for package in (False, True):
                with self.subTest(package=package):
                    module = self.builder(package)
                    self.assertEqual(module.SPEC, DIRECTORY / "cm_agents.md")
                    self.assertIs(module.ConfigurationError, self.helper.ConfigurationError)
                    self.assertIs(module.compatible_tool_choice, self.helper.compatible_tool_choice)
                    self.assertEqual(module.API, API)
        self.credential.assert_not_called()
        self.http.get.assert_not_called()
        self.http.post.assert_not_called()

    def test_help_works_as_direct_script_and_package_without_config(self):
        self.block_requests = True
        with mock.patch.dict(os.environ, {}, clear=True), \
                mock.patch.object(sys, "argv", ["create_cm_agents.py", "--help"]), \
                mock.patch.object(Path, "read_text", side_effect=AssertionError("No spec reads")):
            for package in (False, True):
                with self.subTest(package=package), self.assertRaises(SystemExit) as caught:
                    if package:
                        runpy.run_module("_cm_test_agent.create_cm_agents", run_name="__main__")
                    else:
                        runpy.run_path(str(DIRECTORY / "create_cm_agents.py"), run_name="__main__")
                self.assertEqual(caught.exception.code, 0)
        self.assertIn("--apply", self.stdout.getvalue())
        self.credential.assert_not_called()

    def test_missing_configuration_precedes_spec_auth_and_requests(self):
        module = self.builder()
        cases = [({}, "FOUNDRY_PROJECT_ENDPOINT")]
        for mode in AUTH_FIELDS:
            for field in ("FOUNDRY_PROJECT_ENDPOINT", "FOUNDRY_SOURCE_AGENT_NAME",
                          "AZURE_AUTH_MODE", *AUTH_FIELDS[mode]):
                for value in (None, " \t"):
                    config = environment(mode)
                    if value is None:
                        config.pop(field)
                    else:
                        config[field] = value
                    cases.append((config, field))
        with mock.patch.object(Path, "read_text", side_effect=AssertionError("No spec read")), \
                mock.patch.object(Path, "is_file", side_effect=AssertionError("No spec check")):
            for config, field in cases:
                with self.subTest(config=config, field=field), \
                        mock.patch.dict(os.environ, config, clear=True):
                    self.stderr.seek(0)
                    self.stderr.truncate()
                    self.assert_local_error(module, field)

    def test_invalid_endpoint_or_auth_mode_precedes_auth(self):
        module = self.builder()
        for field, value in (
            ("FOUNDRY_PROJECT_ENDPOINT", "http://foundry.invalid"),
            ("FOUNDRY_PROJECT_ENDPOINT", "https://foundry.invalid?secret=value"),
            ("AZURE_AUTH_MODE", "default"),
        ):
            with self.subTest(field=field, value=value), \
                    mock.patch.dict(os.environ, {field: value}):
                self.assert_local_error(module, field)

    def test_missing_spec_precedes_auth(self):
        module = self.builder()
        with mock.patch.object(Path, "is_file", return_value=False):
            self.assert_local_error(module, "Missing mission agent specification file")

    def test_unreadable_spec_precedes_auth(self):
        module = self.builder()
        for error in (OSError("cannot read"), UnicodeError("bad encoding")):
            with self.subTest(error=error), mock.patch.object(Path, "read_text", side_effect=error):
                self.assert_local_error(module, "Cannot read mission agent specification")

    def test_entire_malformed_spec_precedes_auth(self):
        module = self.builder()
        cases = [
            ("", "no AGENT blocks"),
            (" \n\t", "no AGENT blocks"),
            ("# Markdown without agents", "no AGENT blocks"),
            ("<!-- AGENT mission tools=kb -->\nInstructions", "missing END"),
            ("<!-- END -->", "END without an AGENT"),
            (block(instructions=" \n\t"), "empty instructions"),
            (block(kinds="fabric,unknown"), "unrecognized tool categories"),
            (block(kinds="fabric,"), "unrecognized tool categories"),
            (block(kinds="kb,kb"), "duplicate tool categories"),
            (block(kinds=""), "malformed"),
            (block() + block(), "duplicate agent name"),
            ("<!-- AGENT mission tools=kb -->\n" + block(), "nested AGENT"),
            ("<!-- AGENT mission tools=kb --\nText\n<!-- END -->", "malformed"),
            (block() + "<!-- AGENT later tools=kb -->\n", "missing END"),
            (block() + block("later", "unknown"), "unrecognized tool categories"),
            (block() + "<!-- AGENT later tool=kb -->\n", "malformed"),
            (block() + "<!-- agent later tools=kb -->\n", "malformed"),
            (block() + "<!-- END extra -->", "malformed"),
        ]
        for text, message in cases:
            with self.subTest(text=text), mock.patch.object(Path, "read_text", return_value=text):
                self.stderr.seek(0)
                self.stderr.truncate()
                self.assert_local_error(module, message)

    def test_spec_handles_crlf_and_surrounding_markdown(self):
        module = self.builder()
        text = "Preamble\n" + block(instructions=" First line.\n\nSecond line. ") + "\nAppendix"
        with mock.patch.object(Path, "read_text", return_value=text.replace("\n", "\r\n")):
            agents = module.load_spec(module.SPEC)
        self.assertEqual(agents, [(
            "mission-one", ["fabric", "kb", "work", "web"], "First line.\r\n\r\nSecond line.",
        )])

    def test_repository_spec_is_valid_without_auth(self):
        module = self.builder()
        agents = module.load_spec(module.SPEC)
        self.assertGreater(len(agents), 0)
        self.assertEqual(len(agents), len({name for name, _, _ in agents}))
        module.test_token.assert_not_called()

    def test_source_collision_anywhere_in_spec_precedes_credentials_and_http(self):
        for package in (False, True):
            module = self.builder(package)
            for source in ("mission-source", " \tmission-source \n"):
                for text in (
                    block("mission-source") + block("other"),
                    block("other") + block("mission-source"),
                ):
                    for argv in ([], ["--apply"]):
                        with self.subTest(package=package, source=source, text=text, argv=argv), \
                                mock.patch.dict(os.environ, {"FOUNDRY_SOURCE_AGENT_NAME": source}), \
                                mock.patch.object(Path, "read_text", return_value=text):
                            self.block_requests = True
                            self.stderr.seek(0)
                            self.stderr.truncate()
                            with self.assertRaises(SystemExit) as caught:
                                module.main(argv)
                            self.assertEqual(caught.exception.code, 2)
                            for message in ("FOUNDRY_SOURCE_AGENT_NAME", "mission-source", "overwriting"):
                                self.assertIn(message, self.stderr.getvalue())
                            module.test_token.assert_not_called()
                            self.credential.assert_not_called()
                            self.http.get.assert_not_called()
                            self.http.post.assert_not_called()

    def test_dry_run_is_default_and_preserves_read_protocol(self):
        module = self.builder(package=True)
        self.source()
        with mock.patch.object(Path, "read_text", return_value=block()):
            self.assertEqual(module.main([]), 0)
        self.http.post.assert_not_called()
        self.assertIn("Dry run. Re-run with --apply.", self.stdout.getvalue())
        self.assertIn("source-model", self.stdout.getvalue())
        self.assertEqual(self.http.get.call_count, 3)
        self.assertEqual(self.http.get.call_args_list[0].args[0], SOURCE_URL + f"?api-version={API}")
        self.assertEqual(self.http.get.call_args_list[1].args[0],
                         SOURCE_URL + f"/versions/3?api-version={API}")
        self.assertEqual(self.http.get.call_args_list[2].args[0],
                         ENDPOINT + f"/agents/mission-one?api-version={API}")
        for call in self.http.get.call_args_list:
            self.assertEqual(call.kwargs["timeout"], 120)
            self.assertEqual(call.kwargs["headers"], {
                "Authorization": "Bearer offline-token", "Content-Type": "application/json",
            })
        module.test_token.assert_called_once_with({
            **environment(), "FOUNDRY_PROJECT_ENDPOINT": ENDPOINT,
        })
        self.credential.assert_not_called()

    def test_apply_preserves_definition_and_groups_all_matching_tools(self):
        module = self.builder()
        source = definition()
        original = copy.deepcopy(source)
        self.source(source, targets=2)
        text = block(kinds="work,fabric,web,kb") + block("mission-two", "kb", "Second mission.")
        with mock.patch.object(Path, "read_text", return_value=text):
            self.assertEqual(module.main(["--apply"]), 0)
        self.assertEqual(self.http.post.call_count, 2)
        for index, (name, indices, instructions) in enumerate((
            ("mission-one", [1, 6, 3, 9, 0, 5, 7, 2, 8], "Mission instructions."),
            ("mission-two", [2, 8], "Second mission."),
        )):
            call = self.http.post.call_args_list[index]
            self.assertEqual(call.args[0], ENDPOINT + f"/agents/{name}/versions?api-version={API}")
            self.assertEqual(call.kwargs["timeout"], 180)
            self.assertEqual(call.kwargs["headers"]["Authorization"], "Bearer offline-token")
            expected = copy.deepcopy(original)
            expected["instructions"] = instructions
            expected["tools"] = [original["tools"][i] for i in indices]
            self.assertEqual(call.kwargs["json"], {
                "definition": expected, "description": f"Capital Markets - {name}",
            })
        self.assertEqual(source, original)
        first = self.http.post.call_args_list[0].kwargs["json"]["definition"]
        second = self.http.post.call_args_list[1].kwargs["json"]["definition"]
        first["settings"]["nested"]["preserve"].append(3)
        first["tools"][-2]["allowed_tools"]["tool_names"].append("changed")
        self.assertEqual(source, original)
        self.assertEqual(second["settings"], original["settings"])
        self.assertEqual(second["tools"][0], original["tools"][2])

    def test_apply_preserves_compatible_choices_and_other_definition_properties(self):
        module = self.builder()
        cases = [
            (choice, "kb") for choice in (
                None, "auto", "none", "required",
                {"type": "mcp", "server_label": "kb-policy"},
                {"type": "mcp", "server_label": "kb-policy", "name": None},
                {"type": "mcp", "server_label": "kb-policy", "name": "search"},
                {"type": "mcp", "server_label": "kb-second", "name": "unfiltered"},
            )
        ] + [
            ({"type": "mcp", "server_label": "WorkIQMail", "name": "read_mail"}, "work"),
            ({"type": "web_search_preview"}, "web"),
            ({"type": "web_search_preview_2025_03_11"}, "web"),
        ] + [
            ({"type": "allowed_tools", "mode": mode, "tools": [
                {"type": "mcp", "server_label": "kb-policy", "name": "search"},
                {"type": "mcp", "server_label": "WorkIQMail", "name": "read_mail"},
                {"type": "web_search_preview"},
                {"type": "web_search_preview_2025_03_11"},
            ]}, "kb,work,web") for mode in ("auto", "required")
        ]
        for choice, kinds in cases:
            with self.subTest(choice=choice, kinds=kinds):
                data = definition()
                data["tools"].append({"type": "web_search_preview_2025_03_11"})
                data["tool_choice"] = choice
                before = copy.deepcopy(data)
                self.http.get.reset_mock()
                self.http.post.reset_mock()
                self.source(data, targets=2)
                text = block("earlier") + block("later", kinds, "Later instructions.")
                with mock.patch.object(Path, "read_text", return_value=text):
                    self.assertEqual(module.main(["--apply"]), 0)
                self.assertEqual(self.http.post.call_count, 2)
                for index, call in enumerate(self.http.post.call_args_list):
                    payload = call.kwargs["json"]["definition"]
                    self.assertEqual(payload["tool_choice"], choice)
                    self.assertEqual(
                        {key: value for key, value in payload.items()
                         if key not in ("instructions", "tools")},
                        {key: value for key, value in before.items()
                         if key not in ("instructions", "tools")},
                    )
                    self.assertEqual(payload["instructions"],
                                     "Later instructions." if index else "Mission instructions.")
                self.assertEqual(data, before)
                if isinstance(choice, dict):
                    first, second = [
                        call.kwargs["json"]["definition"] for call in self.http.post.call_args_list
                    ]
                    self.assertIsNot(first["tool_choice"], second["tool_choice"])
                    first["tool_choice"]["type"] = "changed"
                    self.assertEqual(second["tool_choice"], choice)
                    self.assertEqual(data, before)

    def test_later_incompatible_choice_prevents_all_posts_and_target_reads(self):
        module = self.builder()
        choices = (
            {"type": "mcp", "server_label": "WorkIQMail", "name": "read_mail"},
            {"type": "web_search_preview"},
            {"type": "web_search_preview_2025_03_11"},
            *({"type": "allowed_tools", "mode": mode, "tools": [
                {"type": "mcp", "server_label": "kb-policy", "name": "search"},
                {"type": "mcp", "server_label": "WorkIQMail", "name": "read_mail"},
            ]} for mode in ("auto", "required")),
            {"type": "allowed_tools", "mode": "required", "tools": [
                {"type": "mcp", "server_label": "kb-policy"},
                {"type": "web_search_preview"},
            ]},
        )
        for choice in choices:
            for argv in ([], ["--apply"]):
                with self.subTest(choice=choice, argv=argv):
                    data = definition()
                    data["tools"].append({"type": "web_search_preview_2025_03_11"})
                    data["tool_choice"] = choice
                    before = copy.deepcopy(data)
                    earlier = [("earlier", ["kb", "work", "web"], "Earlier instructions.")]
                    self.assertEqual(
                        module.mission_definitions({"definition": data}, SOURCE, earlier)[0][1]
                        ["tool_choice"], choice)
                    self.http.get.reset_mock()
                    self.source(data, targets=2)
                    self.stderr.seek(0)
                    self.stderr.truncate()
                    text = block("earlier", "kb,work,web") + block("later", "kb")
                    with mock.patch.object(Path, "read_text", return_value=text), \
                            self.assertRaises(SystemExit) as caught:
                        module.main(argv)
                    self.assertEqual(caught.exception.code, 2)
                    for message in ("later", "tool_choice", SOURCE, "kb-policy", "auto"):
                        self.assertIn(message, self.stderr.getvalue())
                    self.assertEqual(self.http.get.call_count, 2)
                    self.http.post.assert_not_called()
                    self.assertEqual(data, before)

    def test_rejects_excluded_and_unsupported_choices_even_when_source_has_tool(self):
        module = self.builder()
        choices = (
            {"type": "mcp", "server_label": "unrelated"},
            {"type": "mcp", "server_label": "kb-policy", "name": "excluded"},
            {"type": "mcp", "server_label": "WorkIQMail", "name": "excluded"},
            {"type": "function", "name": "lookup_account"},
            {"type": "function", "function": {"name": "lookup_account"}},
            {"type": "code_interpreter"},
            {"type": "fabric_iq_preview"},
            {"type": "work_iq_preview"},
            {"type": "bing_grounding"},
            {"type": "web_search"},
            {"type": "web_search_2025_08_26"},
            {"type": "allowed_tools", "mode": "required", "tools": [
                {"type": "mcp", "server_label": "kb-policy"},
                {"type": "function", "name": "lookup_account"},
            ]},
            {"type": "allowed_tools", "mode": "auto", "tools": [
                {"type": "mcp", "server_label": "kb-policy"},
                {"type": "mcp", "server_label": "unrelated"},
            ]},
            {}, False, "unknown",
        )
        for choice in choices:
            for argv in ([], ["--apply"]):
                with self.subTest(choice=choice, argv=argv):
                    data = definition()
                    data["tools"].extend([
                        {"type": "function", "name": "lookup_account", "parameters": {}},
                        {"type": "code_interpreter", "container": {"type": "auto"}},
                        {"type": "web_search_2025_08_26"},
                    ])
                    data["tool_choice"] = choice
                    before = copy.deepcopy(data)
                    self.http.get.reset_mock()
                    self.source(data)
                    with mock.patch.object(Path, "read_text", return_value=block()), \
                            self.assertRaises(SystemExit) as caught:
                        module.main(argv)
                    self.assertEqual(caught.exception.code, 2)
                    self.assertIn("tool_choice", self.stderr.getvalue())
                    self.assertEqual(self.http.get.call_count, 2)
                    self.http.post.assert_not_called()
                    self.assertEqual(data, before)

    def test_web_variants_are_retained_verbatim_with_generic_choices(self):
        module = self.builder()
        for kind in ("web_search", "web_search_2025_08_26", "web_search_preview",
                     "web_search_preview_2025_03_11", "bing_grounding"):
            for choice in (None, "auto", "none", "required"):
                with self.subTest(kind=kind, choice=choice):
                    data = definition()
                    data["tools"] = [{"type": kind, "settings": {"preserve": [1, 2]}}]
                    data["tool_choice"] = choice
                    before = copy.deepcopy(data)
                    result = module.mission_definitions(
                        {"definition": data}, SOURCE, [("mission", ["web"], "Instructions.")])
                    expected = copy.deepcopy(before)
                    expected["instructions"] = "Instructions."
                    self.assertEqual(result, [("mission", expected)])
                    self.assertEqual(data, before)

    def test_each_selected_auth_mode_uses_shared_config(self):
        module = self.builder()
        for mode in AUTH_FIELDS:
            with self.subTest(mode=mode), mock.patch.dict(os.environ, environment(mode), clear=True), \
                    mock.patch.object(Path, "read_text", return_value=block()):
                self.source()
                module.test_token.reset_mock()
                self.assertEqual(module.main([]), 0)
                module.test_token.assert_called_once_with({
                    **environment(mode), "FOUNDRY_PROJECT_ENDPOINT": ENDPOINT,
                })
        self.credential.assert_not_called()
        self.http.post.assert_not_called()

    def test_missing_later_source_category_prevents_all_writes(self):
        module = self.builder()
        data = definition()
        data["tools"] = [tool for tool in data["tools"] if tool["type"] == "fabric_iq_preview"]
        self.source(data, targets=2)
        text = block("earlier", "fabric") + block("later", "work,kb,web")
        with mock.patch.object(Path, "read_text", return_value=text), \
                self.assertRaises(SystemExit) as caught:
            module.main(["--apply"])
        self.assertEqual(caught.exception.code, 2)
        for kind in ("work", "kb", "web"):
            self.assertIn(f"later: no {kind} tool on {SOURCE}", self.stderr.getvalue())
        self.assertEqual(self.http.get.call_count, 2)
        self.http.post.assert_not_called()

    def test_missing_source_is_an_error_not_an_empty_success(self):
        module = self.builder()
        self.http.get.return_value = response(status=404)
        with mock.patch.object(Path, "read_text", return_value=block()), \
                self.assertRaises(SystemExit) as caught:
            module.main(["--apply"])
        self.assertEqual(caught.exception.code, 2)
        self.assertIn(f"Source agent {SOURCE} not found", self.stderr.getvalue())
        self.assertEqual(self.http.get.call_count, 1)
        self.http.post.assert_not_called()

    def test_invalid_source_definition_never_gets_defaults_or_posts(self):
        module = self.builder()
        cases = []
        for field in ("kind", "model", "tools"):
            missing = definition()
            del missing[field]
            cases.append((missing, field))
            for value in (None, "", " ", 7, {}):
                data = definition()
                data[field] = value
                cases.append((data, field))
        for tools in ([None], [{}], [{"type": ""}], [{"type": 1}]):
            cases.append(({**definition(), "tools": tools}, "tools"))
        for data, field in cases:
            with self.subTest(field=field, data=data), \
                    mock.patch.object(Path, "read_text", return_value=block()):
                self.source(data)
                self.stderr.seek(0)
                self.stderr.truncate()
                with self.assertRaises(SystemExit) as caught:
                    module.main(["--apply"])
                self.assertEqual(caught.exception.code, 2)
                self.assertIn(f"source definition {field}", self.stderr.getvalue())
                self.http.post.assert_not_called()

    def test_missing_source_definition_is_actionable(self):
        module = self.builder()
        self.http.get.side_effect = [
            response({"versions": {"latest": {"version": "3"}}}), response({"version": "3"}),
        ]
        with mock.patch.object(Path, "read_text", return_value=block()), \
                self.assertRaises(SystemExit):
            module.main(["--apply"])
        self.assertIn("missing or invalid source definition", self.stderr.getvalue())
        self.http.post.assert_not_called()

    def test_existing_target_latest_version_is_reported(self):
        module = self.builder()
        self.http.get.side_effect = [
            response({"versions": {"latest": {"version": "3"}}}),
            response({"definition": definition()}),
            response({"versions": {"latest": {"version": "11"}}}),
            response({"version": "11"}),
        ]
        with mock.patch.object(Path, "read_text", return_value=block()):
            self.assertEqual(module.main([]), 0)
        self.assertIn("v11", self.stdout.getvalue())
        self.assertEqual(self.http.get.call_args.args[0],
                         ENDPOINT + f"/agents/mission-one/versions/11?api-version={API}")
        self.http.post.assert_not_called()

    def test_read_failures_cannot_trigger_posts(self):
        module = self.builder()
        self.http.get.side_effect = [
            response({"versions": {"latest": {"version": "3"}}}), response(status=403),
        ]
        with mock.patch.object(Path, "read_text", return_value=block()), \
                self.assertRaisesRegex(RuntimeError, "HTTP 403"):
            module.main(["--apply"])
        self.http.post.assert_not_called()

    def test_all_target_reads_precede_posts(self):
        module = self.builder()
        self.http.get.side_effect = [
            response({"versions": {"latest": {"version": "3"}}}),
            response({"definition": definition()}),
            response(status=404),
            response(status=403),
        ]
        text = block("earlier", "kb") + block("later", "kb")
        with mock.patch.object(Path, "read_text", return_value=text), \
                self.assertRaisesRegex(RuntimeError, "HTTP 403"):
            module.main(["--apply"])
        self.http.post.assert_not_called()

    def test_post_failure_is_not_reported_as_success(self):
        module = self.builder()
        self.source()
        self.http.post.return_value = response(status=400)
        with mock.patch.object(Path, "read_text", return_value=block()), \
                self.assertRaisesRegex(SystemExit, "mission-one: 400"):
            module.main(["--apply"])
        self.assertNotIn("created version", self.stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
