"""Offline native unittest coverage. No credentials, network, CLI or disk writes.

Run from the repository root with Python's -B option:
python -B -m unittest discover -s capital-markets-client-intelligence\\app\\infra -p test_infra_portability.py
"""

from __future__ import annotations

import ast
import builtins
import copy
import importlib
import io
import json
import os
from pathlib import Path
import runpy
import socket
import subprocess
import sys
import types
import unittest
from contextlib import ExitStack, contextmanager, redirect_stderr, redirect_stdout
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, unquote, urlsplit

INFRA = Path(__file__).resolve().parent
ENTRYPOINTS = (
    "audit_permissions", "configure_rbac", "grant_foundry_permission",
    "grant_mail_draft_permission", "provision_app_registrations",
)
TENANT = "11111111-1111-4111-8111-111111111111"
CLIENT = "22222222-2222-4222-8222-222222222222"
UPN = "coverage@example.invalid"
BASE_ENV = {
    "AZURE_TENANT_ID": TENANT,
    "INFRA_SPA_NAME": "bank_spa",
    "INFRA_BFF_NAME": "bank_bff",
    "INFRA_BFF_CLIENT_ID": CLIENT,
    "INFRA_ROLE_ASSIGNMENTS": json.dumps({UPN: "Coverage"}),
}


@contextmanager
def no_external_effects():
    """Block process execution, network, optional SDK imports and file writes."""
    real_import, real_open, real_io_open, real_os_open = builtins.__import__, builtins.open, io.open, os.open

    def guarded_import(name, *args, **kwargs):
        if name == "requests" or name == "azure" or name.startswith("azure."):
            raise AssertionError(f"Unexpected runtime dependency import: {name}")
        return real_import(name, *args, **kwargs)

    def guarded_open(original):
        def open_read_only(file, mode="r", *args, **kwargs):
            if any(flag in mode for flag in "wax+"):
                raise AssertionError("Unexpected filesystem write")
            return original(file, mode, *args, **kwargs)
        return open_read_only

    def os_open_read_only(path, flags, *args, **kwargs):
        if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
            raise AssertionError("Unexpected filesystem write")
        return real_os_open(path, flags, *args, **kwargs)

    with ExitStack() as stack:
        stack.enter_context(patch("builtins.__import__", side_effect=guarded_import))
        stack.enter_context(patch("builtins.open", side_effect=guarded_open(real_open)))
        stack.enter_context(patch("io.open", side_effect=guarded_open(real_io_open)))
        stack.enter_context(patch("os.open", side_effect=os_open_read_only))
        for target in (
            "subprocess.Popen", "subprocess.run", "os.system", "socket.create_connection",
            "socket.socket.connect", "socket.getaddrinfo", "os.mkdir", "os.remove",
            "os.unlink", "os.rename", "os.replace",
        ):
            stack.enter_context(patch(target, side_effect=AssertionError(f"Blocked {target}")))
        yield


def load_modules():
    # A private package prevents collision with any Fabric portability helper.
    package = types.ModuleType("_bank_infra_portability_tests")
    package.__path__ = [str(INFRA)]
    sys.modules[package.__name__] = package
    with no_external_effects():
        helper = importlib.import_module(f"{package.__name__}.portability_config")
        modules = {
            name: importlib.import_module(f"{package.__name__}.{name}")
            for name in ENTRYPOINTS
        }
    return helper, modules


config, MODULES = load_modules()


class FakeGraph:
    """Stateful, strict Graph double; unknown request shapes fail the test."""

    def __init__(self):
        self.calls = []
        self.apps = {}
        self.sps = {}
        self.grants = {}
        self.assignments = []
        self.users = {UPN: {"id": "user-coverage", "displayName": "Coverage User"}}
        self.counter = 10
        provision = MODULES["provision_app_registrations"]
        self.graph_app_id = provision.GRAPH_APP_ID
        self.aml_app_id = provision.AML_APP_ID
        self.add_sp(self.graph_app_id, [
            {"id": f"graph-{name}", "value": name, "isEnabled": True}
            for name in provision.BFF_GRAPH_SCOPES + ["Mail.ReadWrite"]
        ])
        self.add_sp(self.aml_app_id, [{
            "id": provision.AML_USER_IMPERSONATION_SCOPE,
            "value": "user_impersonation", "isEnabled": True,
        }])

    def new_id(self):
        self.counter += 1
        return f"00000000-0000-4000-8000-{self.counter:012d}"

    def add_app(self, name, client=None):
        app = {
            "id": self.new_id(), "appId": client or self.new_id(), "displayName": name,
            "requiredResourceAccess": [], "appRoles": [], "api": {},
        }
        self.apps[app["id"]] = app
        return app

    def add_sp(self, client, scopes=None):
        sp = {
            "id": self.new_id(), "appId": client, "displayName": f"Resource {client}",
            "oauth2PermissionScopes": scopes or [], "appRoles": [],
        }
        self.sps[sp["id"]] = sp
        return sp

    def sp(self, client):
        return next(sp for sp in self.sps.values() if sp["appId"] == client)

    def add_grant(self, client_id, resource_id, scope, consent="AllPrincipals"):
        grant = {
            "id": self.new_id(), "clientId": client_id, "resourceId": resource_id,
            "scope": scope, "consentType": consent,
        }
        if consent == "Principal":
            grant["principalId"] = "user-coverage"
        self.grants[grant["id"]] = grant
        return grant

    def seed_bff(self):
        app = self.add_app(BASE_ENV["INFRA_BFF_NAME"], CLIENT)
        self.add_sp(CLIENT)
        return app

    def seed_spa(self):
        app = self.add_app(BASE_ENV["INFRA_SPA_NAME"])
        self.add_sp(app["appId"])
        return app

    def writes(self):
        return [call for call in self.calls if call[0] != "GET"]

    def collection(self, path):
        return self.call("GET", path)["value"]

    def call(self, method, path, body=None, ok=(200, 201, 204)):
        self.calls.append((method, path, copy.deepcopy(body)))
        parsed = urlsplit(path)
        parts = parsed.path.strip("/").split("/")
        query = parse_qs(parsed.query)
        tables = {"applications": self.apps, "servicePrincipals": self.sps,
                  "oauth2PermissionGrants": self.grants}
        if len(parts) == 1 and parts[0] in tables:
            table = tables[parts[0]]
            if method == "GET":
                rows = list(table.values())
                if "$filter" in query:
                    field, value = query["$filter"][0].split(" eq ", 1)
                    self_literal = value[1:-1].replace("''", "'")
                    rows = [row for row in rows if row.get(field) == self_literal]
                return {"value": copy.deepcopy(rows)}
            if method == "POST":
                if parts[0] == "applications":
                    row = self.add_app(body["displayName"])
                    row.update(copy.deepcopy(body))
                elif parts[0] == "servicePrincipals":
                    if body["appId"] == self.aml_app_id:
                        row = self.add_sp(self.aml_app_id, [{
                            "id": MODULES["provision_app_registrations"].AML_USER_IMPERSONATION_SCOPE,
                            "value": "user_impersonation", "isEnabled": True,
                        }])
                    else:
                        row = self.add_sp(body["appId"])
                else:
                    row = self.add_grant(body["clientId"], body["resourceId"],
                                         body["scope"], body["consentType"])
                return copy.deepcopy(row)
        if len(parts) == 2 and parts[0] in tables:
            table = tables[parts[0]]
            row = table[parts[1]]
            if method == "GET":
                return copy.deepcopy(row)
            if method == "PATCH":
                for key, value in copy.deepcopy(body).items():
                    if isinstance(value, dict) and isinstance(row.get(key), dict):
                        row[key].update(value)
                    else:
                        row[key] = value
                return None
            if method == "DELETE":
                del table[parts[1]]
                return None
        if len(parts) == 2 and parts[0] == "users" and method == "GET":
            upn = unquote(parts[1])
            if upn not in self.users:
                raise RuntimeError("Configured user does not exist")
            return copy.deepcopy(self.users[upn])
        if len(parts) == 3 and parts[0] == "applications" and parts[2] == "addPassword":
            if method == "POST":
                return {"secretText": "unit-test-placeholder-not-a-real-secret"}
        if len(parts) == 3 and parts[0] == "users" and parts[2] == "appRoleAssignments":
            if method == "POST":
                assignment = copy.deepcopy(body)
                assignment["principalDisplayName"] = "Coverage User"
                self.assignments.append(assignment)
                return assignment
        if len(parts) == 3 and parts[0] == "servicePrincipals" and method == "GET":
            if parts[2] == "appRoleAssignedTo":
                return {"value": copy.deepcopy([
                    a for a in self.assignments if a["resourceId"] == parts[1]
                ])}
            if parts[2] == "appRoleAssignments":
                return {"value": copy.deepcopy([
                    a for a in self.assignments if a["principalId"] == parts[1]
                ])}
        raise AssertionError(f"Unhandled Graph request: {method} {path} {body}")


class OfflineTest(unittest.TestCase):
    def setUp(self):
        self.effects = no_external_effects()
        self.effects.__enter__()
        self.addCleanup(self.effects.__exit__, None, None, None)

    def invoke(self, name, graph, args=(), env=None):
        module = MODULES[name]
        output = io.StringIO()
        with ExitStack() as stack:
            stack.enter_context(redirect_stdout(output))
            factory = stack.enter_context(patch.object(module, "GraphClient", return_value=graph))
            if hasattr(module, "time"):
                stack.enter_context(patch.object(module.time, "sleep"))
            module.main(list(args), BASE_ENV if env is None else env)
            factory.assert_called_once_with(TENANT)
        return output.getvalue()

    def invalid(self, name, args, env, message):
        error = io.StringIO()
        with patch.object(MODULES[name], "GraphClient",
                          side_effect=AssertionError("Validation must precede credential construction")) as factory, redirect_stderr(error):
            with self.assertRaises(SystemExit) as raised:
                MODULES[name].main(list(args), env)
            self.assertEqual(raised.exception.code, 2)
            factory.assert_not_called()
        self.assertIn(message, error.getvalue())


class ConfigurationTests(OfflineTest):
    def test_required_settings_missing_blank_invalid_in_every_mode(self):
        cases = [
            ("audit_permissions", [], ["INFRA_SPA_NAME", "INFRA_BFF_NAME"]),
            ("configure_rbac", [], ["INFRA_SPA_NAME", "INFRA_ROLE_ASSIGNMENTS"]),
            ("configure_rbac", ["--show"], ["INFRA_SPA_NAME"]),
            ("configure_rbac", ["--open"], ["INFRA_SPA_NAME"]),
            ("grant_foundry_permission", [], ["INFRA_BFF_NAME"]),
            ("grant_foundry_permission", ["--show"], ["INFRA_BFF_NAME"]),
            ("grant_mail_draft_permission", [], ["INFRA_BFF_CLIENT_ID"]),
            ("grant_mail_draft_permission", ["--show"], ["INFRA_BFF_CLIENT_ID"]),
        ]
        for args in (["--show"], ["--delete"], ["--spa-redirect", "https://bank.example.invalid"],
                     ["--add-redirect", "https://bank.example.invalid"]):
            cases.append(("provision_app_registrations", args, ["INFRA_SPA_NAME", "INFRA_BFF_NAME"]))
        for name, args, keys in cases:
            for key in ["AZURE_TENANT_ID"] + keys:
                invalid_value = ("invalid-guid" if key.endswith("_ID") else
                                 "not-json" if key == "INFRA_ROLE_ASSIGNMENTS" else "bad\nname")
                for value in (None, "", " \t ", invalid_value):
                    with self.subTest(script=name, args=args, key=key, value=value):
                        env = dict(BASE_ENV)
                        if value is None:
                            del env[key]
                        else:
                            env[key] = value
                        self.invalid(name, args, env, key)

    def test_empty_explicit_environment_never_uses_process_environment(self):
        with patch.dict(os.environ, BASE_ENV, clear=True):
            for name in ENTRYPOINTS:
                self.invalid(name, [], {}, "AZURE_TENANT_ID")

    def test_guid_and_name_validation(self):
        for value in ("00000000-0000-0000-0000-000000000000", "{"+TENANT+"}",
                      TENANT.replace("-", ""), "example.invalid"):
            with self.subTest(value=value):
                self.invalid("audit_permissions", [], dict(BASE_ENV, AZURE_TENANT_ID=value), "AZURE_TENANT_ID")
                self.invalid("grant_mail_draft_permission", [], dict(BASE_ENV, INFRA_BFF_CLIENT_ID=value),
                             "INFRA_BFF_CLIENT_ID")
        for name in ("audit_permissions", "provision_app_registrations"):
            args = [] if name == "audit_permissions" else ["--show"]
            self.invalid(name, args, dict(BASE_ENV, INFRA_BFF_NAME="BANK_SPA"), "must be distinct")
            self.invalid(name, args, dict(BASE_ENV, INFRA_SPA_NAME="x" * 257), "INFRA_SPA_NAME")
        self.assertEqual(config.guid(TENANT.upper(), "id"), TENANT)
        self.assertEqual(config.tenant_id({"AZURE_TENANT_ID": " " + TENANT + " "}), TENANT)

    def test_assignment_schema_and_duplicate_users(self):
        values = ("[]", "{}", "null", "1", '"value"', "{bad",
                  '{"prefix":"Coverage"}', '{"a@invalid":"Coverage"}',
                  '{"a@example.invalid":"Owner"}', '{"a@example.invalid":[]}',
                  '{"a@example.invalid":null}', '{"a@example.invalid":""}',
                  '{" a@example.invalid":"Coverage"}',
                  '{"a@-example.invalid":"Coverage"}',
                  '{"a@example.invalid":"Coverage","A@example.invalid":"Research"}',
                  '{"a@example.invalid":"Coverage","a@example.invalid":"Research"}')
        for value in values:
            with self.subTest(value=value):
                self.invalid("configure_rbac", [], dict(BASE_ENV, INFRA_ROLE_ASSIGNMENTS=value),
                             "INFRA_ROLE_ASSIGNMENTS")

    def test_redirect_validation_and_mode_conflicts_before_credentials(self):
        values = ("", " ", "relative/path", "https://", "//bank.example.invalid",
                  "http://bank.example.invalid", "ftp://bank.example.invalid",
                  "https://user:password@bank.example.invalid",
                  "https://bank.example.invalid?x=1", "https://bank.example.invalid#fragment",
                  "https://bank.example.invalid:", "https://bank.example.invalid:0",
                  "https://bank.example.invalid:65536", "https://bank.example.invalid:abc",
                  "https://[broken", "https://bank.example.invalid\\evil", "https://bad_host.invalid",
                  "https://bank.example.invalid/%zz", "https://bank.example.invalid/\ncallback",
                  "https://bank.example.invalid/<callback>")
        for flag in ("--spa-redirect", "--add-redirect"):
            for value in values:
                with self.subTest(flag=flag, value=value):
                    self.invalid("provision_app_registrations", [flag, value], BASE_ENV, flag)
        for args in ([], ["--no-secret"], ["--show", "--delete"],
                     ["--show", "--spa-redirect", "https://bank.example.invalid"],
                     ["--delete", "--no-secret"],
                     ["--add-redirect", "https://bank.example.invalid", "--no-secret"],
                     ["--spa-redirect", "https://bank.example.invalid", "--add-redirect", "https://other.example.invalid"]):
            with self.subTest(args=args):
                self.invalid("provision_app_registrations", args, BASE_ENV, "error:")
        self.invalid("configure_rbac", ["--show", "--open"], BASE_ENV, "not allowed")

    def test_explicit_development_redirects_and_https_are_allowed(self):
        for value in ("https://bank.example.invalid/callback", "http://localhost:5173",
                      "http://127.0.0.1:3000/callback", "https://localhost:5173",
                      "https://127.0.0.1:3000/callback",
                      "https://bank.example.invalid/path%20segment"):
            self.assertEqual(config.redirect_uri(value, "uri"), value)

    def test_ipv6_redirects_rejected_before_credentials(self):
        for scheme in ("http", "https"):
            for host in ("[::1]", "[0:0:0:0:0:0:0:1]", "[2001:db8::1]"):
                for suffix in ("/callback", ":5000/callback"):
                    value = f"{scheme}://{host}{suffix}"
                    with self.subTest(value=value):
                        with self.assertRaisesRegex(config.ConfigurationError, "uri.*IPv6"):
                            config.redirect_uri(value, "uri")
                    for flag in ("--spa-redirect", "--add-redirect"):
                        with self.subTest(value=value, flag=flag):
                            self.invalid(
                                "provision_app_registrations",
                                [flag, "https://bank.example.invalid", flag, value],
                                BASE_ENV, f"{flag} must not use IPv6",
                            )

    def test_redirect_length_boundary_before_credentials(self):
        for prefix in ("http://localhost/", "http://127.0.0.1/", "https://bank.example.invalid/"):
            value = prefix + "a" * (256 - len(prefix))
            with self.subTest(prefix=prefix):
                self.assertEqual(len(value), 256)
                self.assertEqual(config.redirect_uri(value, "uri"), value)
                self.assertEqual(len(value + "a"), 257)
                with self.assertRaisesRegex(config.ConfigurationError, "uri.*at most 256"):
                    config.redirect_uri(value + "a", "uri")
            for flag in ("--spa-redirect", "--add-redirect"):
                with self.subTest(prefix=prefix, flag=flag):
                    self.invalid(
                        "provision_app_registrations",
                        [flag, "https://bank.example.invalid", flag, value + "a"],
                        BASE_ENV, f"{flag} must be at most 256",
                    )

    def test_odata_filters_escape_literals_and_query_delimiters(self):
        name = "The Bank's & Partners #1"
        query = config.eq_filter("displayName", name)
        self.assertEqual(parse_qs(query), {"$filter": ["displayName eq 'The Bank''s & Partners #1'"]})
        graph = FakeGraph()
        app = graph.add_app(name)
        self.assertEqual(config.find_app(graph, name)["id"], app["id"])

    def test_ambiguous_display_name_and_sp_are_errors(self):
        graph = FakeGraph()
        graph.add_app("bank_spa")
        graph.add_app("bank_spa")
        with self.assertRaisesRegex(RuntimeError, "Ambiguous"):
            config.find_app(graph, "bank_spa")
        graph.add_sp(CLIENT)
        graph.add_sp(CLIENT)
        with self.assertRaisesRegex(RuntimeError, "Ambiguous"):
            config.find_sp(graph, CLIENT)


class ImportSafetyTests(OfflineTest):
    def test_reimport_requires_neither_configuration_nor_runtime_dependencies(self):
        with patch.dict(os.environ, {}, clear=True), redirect_stdout(io.StringIO()) as output:
            importlib.reload(config)
            for module in MODULES.values():
                importlib.reload(module)
        self.assertEqual(output.getvalue(), "")

    def test_help_executes_main_guard_without_auth(self):
        with patch.dict(sys.modules, {"portability_config": config}):
            for name in ENTRYPOINTS:
                with self.subTest(name=name), patch.object(sys, "argv", [name, "--help"]):
                    output = io.StringIO()
                    with redirect_stdout(output), self.assertRaises(SystemExit) as raised:
                        runpy.run_path(str(INFRA / f"{name}.py"), run_name="__main__")
                    self.assertEqual(raised.exception.code, 0)
                    self.assertIn("AZURE_TENANT_ID", output.getvalue())

    def test_direct_main_with_empty_environment_fails_before_dependencies(self):
        with patch.dict(sys.modules, {"portability_config": config}), patch.dict(os.environ, {}, clear=True):
            for name in ENTRYPOINTS:
                with self.subTest(name=name), patch.object(sys, "argv", [name]), redirect_stderr(io.StringIO()) as output:
                    with self.assertRaises(SystemExit) as raised:
                        runpy.run_path(str(INFRA / f"{name}.py"), run_name="__main__")
                    self.assertEqual(raised.exception.code, 2)
                    self.assertIn("AZURE_TENANT_ID", output.getvalue())

    def test_source_contains_no_legacy_identity_defaults_or_import_calls(self):
        forbidden = ("b" + "mo", "r" + "bc", "sc" + "otia", "m365" + "cpi", "cm-" + "client-intelligence",
                     "95a1" + "ca5c", "sydney" + "m", "sasha" + "o", "quinn" + "c", "vance" + "d", "robin" + "k")
        for name in (*ENTRYPOINTS, "portability_config"):
            source = (INFRA / f"{name}.py").read_text(encoding="utf-8")
            self.assertFalse(any(value in source.lower() for value in forbidden), name)
            tree = ast.parse(source)
            for statement in tree.body:
                if isinstance(statement, (ast.Assign, ast.AnnAssign)):
                    self.assertFalse(any(isinstance(node, ast.Call) for node in ast.walk(statement)), name)


class ProvisionTests(OfflineTest):
    def provision(self, graph, extra=()):
        return self.invoke("provision_app_registrations", graph,
                           ["--spa-redirect", "https://bank.example.invalid", *extra])

    def test_supported_redirects_reach_graph_in_both_modes(self):
        redirects = [
            "http://localhost:5173", "http://127.0.0.1:3000/callback",
            "https://bank.example.invalid/callback",
        ]
        redirects += [
            prefix + "a" * (256 - len(prefix))
            for prefix in ("http://localhost/", "http://127.0.0.1/", "https://bank.example.invalid/")
        ]
        for flag in ("--spa-redirect", "--add-redirect"):
            with self.subTest(flag=flag):
                graph = FakeGraph()
                if flag == "--add-redirect":
                    graph.seed_spa()
                args = [arg for uri in redirects for arg in (flag, uri)]
                if flag == "--spa-redirect":
                    args.append("--no-secret")
                self.invoke("provision_app_registrations", graph, args)
                spa = next(a for a in graph.apps.values() if a["displayName"] == BASE_ENV["INFRA_SPA_NAME"])
                self.assertEqual(spa["spa"]["redirectUris"], sorted(redirects))

    def test_provision_creates_configured_apps_scopes_spa_and_consent(self):
        graph = FakeGraph()
        output = self.provision(graph)
        self.assertEqual({a["displayName"] for a in graph.apps.values()}, {"bank_spa", "bank_bff"})
        bff = next(a for a in graph.apps.values() if a["displayName"] == "bank_bff")
        spa = next(a for a in graph.apps.values() if a["displayName"] == "bank_spa")
        self.assertTrue(bff["description"].startswith("The Bank"))
        self.assertEqual(bff["signInAudience"], "AzureADMyOrg")
        self.assertEqual(bff["identifierUris"], [f"api://{bff['appId']}"])
        self.assertEqual(bff["api"]["requestedAccessTokenVersion"], 2)
        scope = bff["api"]["oauth2PermissionScopes"][0]
        self.assertEqual(scope["value"], "access_as_user")
        self.assertEqual(scope["type"], "User")
        self.assertTrue(scope["isEnabled"])
        self.assertEqual(spa["spa"]["redirectUris"], ["https://bank.example.invalid"])
        self.assertEqual(spa["requiredResourceAccess"], [{
            "resourceAppId": bff["appId"], "resourceAccess": [{"id": scope["id"], "type": "Scope"}],
        }])
        self.assertEqual(bff["api"]["preAuthorizedApplications"], [{
            "appId": spa["appId"], "delegatedPermissionIds": [scope["id"]],
        }])
        self.assertEqual(len(graph.grants), 3)
        self.assertTrue(all(g["consentType"] == "AllPrincipals" for g in graph.grants.values()))
        self.assertEqual(len([c for c in graph.writes() if c[1].endswith("/addPassword")]), 1)
        self.assertIn(f'AAD_TENANT_ID   = "{TENANT}"', output)
        self.assertIn('AAD_CLIENT_SECRET = "unit-test-placeholder-not-a-real-secret"', output)
        self.assertFalse(any("/organization" in path for _, path, _ in graph.calls))

    def test_no_secret_and_rerun_preserve_mail_permissions_and_consents(self):
        graph = FakeGraph()
        self.provision(graph, ["--no-secret"])
        bff = next(a for a in graph.apps.values() if a["displayName"] == "bank_bff")
        graph_access = next(b for b in bff["requiredResourceAccess"] if b["resourceAppId"] == graph.graph_app_id)
        mail = {"id": "graph-Mail.ReadWrite", "type": "Scope"}
        graph_access["resourceAccess"].append(mail)
        grant = next(g for g in graph.grants.values() if g["resourceId"] == graph.sp(graph.graph_app_id)["id"])
        grant["scope"] += " Mail.ReadWrite"
        counts = len(graph.apps), len(graph.sps), len(graph.grants)
        output = self.provision(graph, ["--no-secret"])
        self.assertEqual(counts, (len(graph.apps), len(graph.sps), len(graph.grants)))
        self.assertIn(mail, next(b for b in bff["requiredResourceAccess"]
                                if b["resourceAppId"] == graph.graph_app_id)["resourceAccess"])
        self.assertIn("Mail.ReadWrite", grant["scope"].split())
        self.assertNotIn("AAD_CLIENT_SECRET =", output)
        self.assertFalse(any(path.endswith("/addPassword") for _, path, _ in graph.calls))

    def test_provision_show_is_read_only(self):
        graph = FakeGraph()
        graph.seed_spa()
        self.invoke("provision_app_registrations", graph, ["--show"])
        self.assertEqual(graph.writes(), [])

    def test_existing_spa_permissions_and_bff_api_settings_are_preserved(self):
        graph = FakeGraph()
        bff, spa = graph.seed_bff(), graph.seed_spa()
        bff["identifierUris"] = ["api://existing-identifier"]
        bff["api"]["preAuthorizedApplications"] = [{
            "appId": "another-client", "delegatedPermissionIds": ["other-scope"],
        }]
        original_permission = {"resourceAppId": graph.graph_app_id, "resourceAccess": [
            {"id": "graph-User.Read", "type": "Scope"},
        ]}
        spa["requiredResourceAccess"] = [copy.deepcopy(original_permission)]
        spa["spa"] = {"redirectUris": ["https://existing.example.invalid"]}
        self.provision(graph, ["--no-secret"])
        self.assertIn("api://existing-identifier", bff["identifierUris"])
        self.assertIn({"appId": "another-client", "delegatedPermissionIds": ["other-scope"]},
                      bff["api"]["preAuthorizedApplications"])
        self.assertIn(original_permission, spa["requiredResourceAccess"])
        self.assertEqual(spa["spa"]["redirectUris"],
                         ["https://bank.example.invalid", "https://existing.example.invalid"])

    def test_existing_spa_consent_and_preauthorization_gain_missing_scope(self):
        graph = FakeGraph()
        self.provision(graph, ["--no-secret"])
        bff = next(a for a in graph.apps.values() if a["displayName"] == "bank_bff")
        spa = next(a for a in graph.apps.values() if a["displayName"] == "bank_spa")
        bff["api"]["preAuthorizedApplications"][0]["delegatedPermissionIds"] = ["other-scope"]
        grant = next(g for g in graph.grants.values() if g["clientId"] == graph.sp(spa["appId"])["id"])
        grant["scope"] = "other_scope"
        self.provision(graph, ["--no-secret"])
        self.assertEqual(set(grant["scope"].split()), {"access_as_user", "other_scope"})
        self.assertEqual(set(bff["api"]["preAuthorizedApplications"][0]["delegatedPermissionIds"]),
                         {"other-scope", bff["api"]["oauth2PermissionScopes"][0]["id"]})

    def test_missing_required_graph_scope_does_not_get_silently_dropped(self):
        graph = FakeGraph()
        graph.sp(graph.graph_app_id)["oauth2PermissionScopes"][0]["isEnabled"] = False
        with self.assertRaisesRegex(RuntimeError, "missing enabled delegated scopes: User.Read"):
            self.provision(graph, ["--no-secret"])
        self.assertEqual(graph.grants, {})
        self.assertFalse(any(path.endswith("/addPassword") for _, path, _ in graph.calls))

    def test_add_redirect_only_changes_existing_spa_and_merges(self):
        graph = FakeGraph()
        spa = graph.seed_spa()
        spa["spa"] = {"redirectUris": ["https://existing.example.invalid"]}
        self.invoke("provision_app_registrations", graph,
                    ["--add-redirect", "https://new.example.invalid",
                     "--add-redirect", "https://existing.example.invalid"])
        self.assertEqual(graph.writes(), [("PATCH", f"/applications/{spa['id']}", {
            "spa": {"redirectUris": ["https://existing.example.invalid", "https://new.example.invalid"]},
        })])

    def test_add_redirect_missing_app_does_not_provision(self):
        graph = FakeGraph()
        with self.assertRaisesRegex(RuntimeError, "not found"):
            self.invoke("provision_app_registrations", graph,
                        ["--add-redirect", "https://new.example.invalid"])
        self.assertEqual(graph.writes(), [])

    def test_delete_targets_only_configured_apps(self):
        graph = FakeGraph()
        spa, bff = graph.seed_spa(), graph.seed_bff()
        other = graph.add_app("another_application")
        self.invoke("provision_app_registrations", graph, ["--delete"])
        self.assertEqual(set(graph.apps), {other["id"]})
        self.assertEqual(graph.writes(), [
            ("DELETE", f"/applications/{spa['id']}", None),
            ("DELETE", f"/applications/{bff['id']}", None),
        ])

    def test_delete_resolves_ambiguity_before_any_delete(self):
        graph = FakeGraph()
        graph.seed_spa()
        graph.seed_bff()
        graph.add_app("bank_bff")
        with self.assertRaisesRegex(RuntimeError, "Ambiguous"):
            self.invoke("provision_app_registrations", graph, ["--delete"])
        self.assertEqual(graph.writes(), [])


class PermissionTests(OfflineTest):
    def test_mail_manifest_and_tenant_consent_preserve_existing_scopes(self):
        graph = FakeGraph()
        app = graph.seed_bff()
        app["requiredResourceAccess"] = [{
            "resourceAppId": graph.graph_app_id,
            "resourceAccess": [{"id": "graph-User.Read", "type": "Scope"}],
        }]
        grant = graph.add_grant(graph.sp(CLIENT)["id"], graph.sp(graph.graph_app_id)["id"], "User.Read")
        self.invoke("grant_mail_draft_permission", graph)
        self.assertEqual(set(grant["scope"].split()), {"User.Read", "Mail.ReadWrite"})
        self.assertEqual(app["requiredResourceAccess"][0]["resourceAccess"], [
            {"id": "graph-User.Read", "type": "Scope"}, {"id": "graph-Mail.ReadWrite", "type": "Scope"},
        ])
        self.assertNotIn("Mail.Send", json.dumps(graph.calls))
        graph.calls.clear()
        self.invoke("grant_mail_draft_permission", graph)
        self.assertEqual(graph.writes(), [])

    def test_mail_does_not_treat_single_user_consent_as_tenant_consent(self):
        graph = FakeGraph()
        graph.seed_bff()
        personal = graph.add_grant(graph.sp(CLIENT)["id"], graph.sp(graph.graph_app_id)["id"],
                                   "User.Read Mail.ReadWrite", "Principal")
        self.invoke("grant_mail_draft_permission", graph)
        self.assertEqual(personal["consentType"], "Principal")
        self.assertEqual(len(graph.grants), 2)
        self.assertEqual(config.tenant_grant(list(graph.grants.values()), personal["resourceId"])["scope"],
                         "Mail.ReadWrite")

    def test_mail_show_is_read_only(self):
        graph = FakeGraph()
        graph.seed_bff()
        output = self.invoke("grant_mail_draft_permission", graph, ["--show"])
        self.assertIn("admin consented : False", output)
        self.assertEqual(graph.writes(), [])

    def test_mail_missing_app_or_disabled_scope_fails_before_writes(self):
        for missing_app in (True, False):
            graph = FakeGraph()
            if not missing_app:
                graph.seed_bff()
                graph.sp(graph.graph_app_id)["oauth2PermissionScopes"][-1]["isEnabled"] = False
            with self.assertRaises(RuntimeError):
                self.invoke("grant_mail_draft_permission", graph)
            self.assertEqual(graph.writes(), [])

    def test_foundry_merges_manifest_and_consent(self):
        graph = FakeGraph()
        app = graph.seed_bff()
        app["requiredResourceAccess"] = [{
            "resourceAppId": graph.graph_app_id,
            "resourceAccess": [{"id": "graph-User.Read", "type": "Scope"}],
        }]
        grant = graph.add_grant(graph.sp(CLIENT)["id"], graph.sp(graph.aml_app_id)["id"], "existing_scope")
        self.invoke("grant_foundry_permission", graph)
        self.assertEqual(set(grant["scope"].split()), {"existing_scope", "user_impersonation"})
        aml = next(b for b in app["requiredResourceAccess"] if b["resourceAppId"] == graph.aml_app_id)
        self.assertEqual(aml["resourceAccess"], [{
            "id": MODULES["provision_app_registrations"].AML_USER_IMPERSONATION_SCOPE, "type": "Scope",
        }])
        self.assertEqual(len(app["requiredResourceAccess"]), 2)
        self.invoke("grant_foundry_permission", graph)
        self.assertEqual(len(graph.grants), 1)
        self.assertEqual(len(aml["resourceAccess"]), 1)

    def test_foundry_provisions_first_party_sp_when_missing(self):
        graph = FakeGraph()
        graph.seed_bff()
        del graph.sps[graph.sp(graph.aml_app_id)["id"]]
        self.invoke("grant_foundry_permission", graph)
        self.assertTrue(any(method == "POST" and path == "/servicePrincipals"
                            and body == {"appId": graph.aml_app_id}
                            for method, path, body in graph.calls))
        self.assertEqual(len(graph.grants), 1)

    def test_foundry_show_checks_actual_scope_and_tenant_consent(self):
        graph = FakeGraph()
        app = graph.seed_bff()
        app["requiredResourceAccess"] = [{"resourceAppId": graph.aml_app_id, "resourceAccess": []}]
        graph.add_grant(graph.sp(CLIENT)["id"], graph.sp(graph.aml_app_id)["id"], "other_scope")
        output = self.invoke("grant_foundry_permission", graph, ["--show"])
        self.assertIn("BFF requests it in manifest : False", output)
        self.assertIn("BFF consented               : False", output)
        self.assertEqual(graph.writes(), [])

    def test_foundry_does_not_overwrite_personal_consent(self):
        graph = FakeGraph()
        graph.seed_bff()
        personal = graph.add_grant(graph.sp(CLIENT)["id"], graph.sp(graph.aml_app_id)["id"],
                                   "user_impersonation", "Principal")
        self.invoke("grant_foundry_permission", graph)
        self.assertEqual(personal["consentType"], "Principal")
        self.assertEqual(len(graph.grants), 2)
        self.assertEqual(config.tenant_grant(list(graph.grants.values()), personal["resourceId"])["scope"],
                         "user_impersonation")

    def test_foundry_show_never_creates_missing_sp(self):
        graph = FakeGraph()
        graph.seed_bff()
        del graph.sps[graph.sp(graph.aml_app_id)["id"]]
        with self.assertRaises(SystemExit):
            self.invoke("grant_foundry_permission", graph, ["--show"])
        self.assertEqual(graph.writes(), [])

    def test_foundry_missing_bff_sp_or_disabled_scope_fails_before_writes(self):
        for missing_sp in (True, False):
            graph = FakeGraph()
            graph.seed_bff()
            if missing_sp:
                del graph.sps[graph.sp(CLIENT)["id"]]
            else:
                graph.sp(graph.aml_app_id)["oauth2PermissionScopes"][0]["isEnabled"] = False
            with self.assertRaises(SystemExit):
                self.invoke("grant_foundry_permission", graph)
            self.assertEqual(graph.writes(), [])


class RbacAndAuditTests(OfflineTest):
    def test_rbac_applies_only_explicit_users_and_reuses_role_ids(self):
        graph = FakeGraph()
        spa = graph.seed_spa()
        spa["appRoles"] = [{
            "id": "existing-coverage", "value": "Coverage", "allowedMemberTypes": ["User"], "isEnabled": True,
        }]
        self.invoke("configure_rbac", graph)
        self.assertEqual(len(spa["appRoles"]), 5)
        self.assertTrue(graph.sp(spa["appId"])["appRoleAssignmentRequired"])
        self.assertEqual(graph.assignments, [{
            "principalId": "user-coverage", "resourceId": graph.sp(spa["appId"])["id"],
            "appRoleId": "existing-coverage", "principalDisplayName": "Coverage User",
        }])
        self.invoke("configure_rbac", graph)
        self.assertEqual(len(graph.assignments), 1)
        self.assertEqual(len(spa["appRoles"]), 5)

    def test_rbac_full_upn_is_url_encoded(self):
        graph = FakeGraph()
        graph.seed_spa()
        upn = "external#EXT#@example.invalid"
        graph.users = {upn: {"id": "guest-user", "displayName": "Guest"}}
        env = dict(BASE_ENV, INFRA_ROLE_ASSIGNMENTS=json.dumps({upn: "Research"}))
        self.invoke("configure_rbac", graph, env=env)
        self.assertTrue(any("/users/external%23EXT%23%40example.invalid?" in path
                            for _, path, _ in graph.calls))

    def test_rbac_missing_configured_user_aborts_before_writes(self):
        graph = FakeGraph()
        graph.seed_spa()
        env = dict(BASE_ENV, INFRA_ROLE_ASSIGNMENTS=json.dumps({
            UPN: "Coverage", "missing@example.invalid": "Research",
        }))
        with self.assertRaisesRegex(RuntimeError, "user does not exist"):
            self.invoke("configure_rbac", graph, env=env)
        self.assertEqual(graph.writes(), [])

    def test_rbac_show_ignores_assignment_environment_and_is_read_only(self):
        graph = FakeGraph()
        graph.seed_spa()
        self.invoke("configure_rbac", graph, ["--show"],
                    dict(BASE_ENV, INFRA_ROLE_ASSIGNMENTS="invalid-but-unused"))
        self.assertEqual(graph.writes(), [])

    def test_rbac_open_only_changes_sign_in_policy(self):
        graph = FakeGraph()
        spa = graph.seed_spa()
        env = {k: v for k, v in BASE_ENV.items() if k != "INFRA_ROLE_ASSIGNMENTS"}
        self.invoke("configure_rbac", graph, ["--open"], env)
        self.assertEqual(graph.writes(), [
            ("PATCH", f"/servicePrincipals/{graph.sp(spa['appId'])['id']}",
             {"appRoleAssignmentRequired": False}),
        ])

    def test_audit_reports_permissions_and_roles_without_any_writes(self):
        graph = FakeGraph()
        graph.seed_spa()
        bff = graph.seed_bff()
        resource = graph.sp(graph.graph_app_id)
        bff["requiredResourceAccess"] = [{
            "resourceAppId": graph.graph_app_id,
            "resourceAccess": [{"id": "graph-User.Read", "type": "Scope"}],
        }]
        resource["appRoles"] = [{"id": "resource-role", "value": "Example.Read"}]
        graph.add_grant(graph.sp(CLIENT)["id"], resource["id"], "User.Read")
        graph.assignments = [{
            "principalId": graph.sp(CLIENT)["id"], "resourceId": resource["id"],
            "appRoleId": "resource-role",
        }]
        output = self.invoke("audit_permissions", graph)
        self.assertIn("bank_spa", output)
        self.assertIn("bank_bff", output)
        self.assertIn("User.Read", output)
        self.assertIn("Example.Read", output)
        self.assertEqual(graph.writes(), [])
        self.assertFalse(any("appId eq ''" in unquote(path) for _, path, _ in graph.calls))

    def test_audit_cache_does_not_leak_across_runs(self):
        for label in ("First resource", "Second resource"):
            graph = FakeGraph()
            bff = graph.seed_bff()
            graph.sp(graph.graph_app_id)["displayName"] = label
            bff["requiredResourceAccess"] = [{
                "resourceAppId": graph.graph_app_id,
                "resourceAccess": [{"id": "graph-User.Read", "type": "Scope"}],
            }]
            output = self.invoke("audit_permissions", graph)
            self.assertIn(label, output)


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch("subprocess.Popen", side_effect=AssertionError("No CLI execution")))
        self.stack.enter_context(patch("socket.socket.connect", side_effect=AssertionError("No network")))
        azure = types.ModuleType("azure")
        identity = types.ModuleType("azure.identity")
        self.factory = identity.AzureCliCredential = Mock()
        self.factory.return_value.get_token.return_value = types.SimpleNamespace(token="offline-test-token")
        azure.identity = identity
        self.requests = types.ModuleType("requests")
        self.requests.request = Mock()
        self.stack.enter_context(patch.dict(sys.modules, {
            "azure": azure, "azure.identity": identity, "requests": self.requests,
        }))

    def response(self, status=200, body=None):
        response = Mock(status_code=status, content=b"json" if body is not None else b"",
                        headers={"Content-Type": "application/json"}, text="offline error")
        response.json.return_value = body
        return response

    def test_tenant_bound_credential_graph_scope_and_json_request(self):
        client = config.GraphClient(TENANT)
        self.factory.assert_called_once_with(tenant_id=TENANT)
        self.factory.return_value.get_token.assert_not_called()
        self.requests.request.return_value = self.response(204)
        body = {"requiredResourceAccess": [{"resourceAppId": CLIENT, "resourceAccess": []}]}
        self.assertIsNone(client.call("PATCH", "/applications/object", body, ok=(204,)))
        self.factory.return_value.get_token.assert_called_once_with(config.GRAPH_SCOPE)
        self.requests.request.assert_called_once_with(
            "PATCH", config.GRAPH + "/applications/object",
            headers={"Authorization": "Bearer offline-test-token", "Content-Type": "application/json"},
            json=body, timeout=90, allow_redirects=False,
        )

    def test_invalid_tenant_precedes_credential_construction(self):
        for tenant in ("", "bad", "00000000-0000-0000-0000-000000000000"):
            with self.assertRaises(config.ConfigurationError):
                config.GraphClient(tenant)
        self.factory.assert_not_called()
        self.requests.request.assert_not_called()

    def test_auth_error_has_no_fallback_or_request(self):
        client = config.GraphClient(TENANT)
        self.factory.return_value.get_token.side_effect = RuntimeError("offline auth failure")
        with self.assertRaisesRegex(RuntimeError, "offline auth failure"):
            client.call("GET", "/applications")
        self.requests.request.assert_not_called()
        self.assertEqual(self.factory.call_count, 1)

    def test_empty_token_is_rejected_before_request(self):
        client = config.GraphClient(TENANT)
        self.factory.return_value.get_token.return_value.token = " "
        with self.assertRaisesRegex(RuntimeError, "empty"):
            client.call("GET", "/applications")
        self.requests.request.assert_not_called()

    def test_http_failure_is_not_silently_accepted(self):
        client = config.GraphClient(TENANT)
        self.requests.request.return_value = self.response(403)
        with self.assertRaisesRegex(RuntimeError, "403"):
            client.call("GET", "/applications")
        self.assertEqual(self.requests.request.call_count, 1)

    def test_nonrelative_request_rejected_before_token(self):
        client = config.GraphClient(TENANT)
        for path in ("https://outside.example.invalid", "//outside.example.invalid", "applications"):
            with self.assertRaises(ValueError):
                client.call("GET", path)
        self.factory.return_value.get_token.assert_not_called()

    def test_collection_pagination_and_json_response(self):
        client = config.GraphClient(TENANT)
        self.requests.request.side_effect = [
            self.response(body={"value": [{"id": "first"}],
                                "@odata.nextLink": config.GRAPH + "/applications?$skiptoken=next"}),
            self.response(body={"value": [{"id": "second"}]}),
        ]
        self.assertEqual(client.collection("/applications"), [{"id": "first"}, {"id": "second"}])
        self.assertEqual(self.requests.request.call_count, 2)
        self.assertEqual(self.factory.return_value.get_token.call_count, 2)

    def test_external_or_repeated_pagination_is_rejected(self):
        for link in ("https://outside.example.invalid", config.GRAPH + ".evil/applications",
                     config.GRAPH + "/applications"):
            with self.subTest(link=link):
                self.requests.request.reset_mock()
                self.requests.request.return_value = self.response(body={"value": [], "@odata.nextLink": link})
                client = config.GraphClient(TENANT)
                with self.assertRaisesRegex(RuntimeError, "pagination"):
                    client.collection("/applications")
                self.assertEqual(self.requests.request.call_count, 1)


if __name__ == "__main__":
    unittest.main()
