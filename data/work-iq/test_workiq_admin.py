"""Offline regression tests. Run only this file with ``python -B``."""

from __future__ import annotations

import builtins
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import time
from contextlib import ExitStack, contextmanager, redirect_stderr, redirect_stdout
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit
import urllib.request


sys.dont_write_bytecode = True

OWNED_MODULES = (
    "workiq_admin_config",
    "configure_workiq_connector",
    "configure_workiq_redirect",
    "grant_workiq_scope",
    "provision_seeder_app",
)
ROOT = Path(__file__).resolve().parent
TENANT = "10000000-0000-4000-8000-000000000001"
OTHER_TENANT = "10000000-0000-4000-8000-000000000002"
CONNECTOR_ID = "20000000-0000-4000-8000-000000000001"
GRAPH_ID = "20000000-0000-4000-8000-000000000002"
WORKIQ_ID = "20000000-0000-4000-8000-000000000003"
OTHER_RESOURCE_ID = "20000000-0000-4000-8000-000000000004"
SEEDER_ID = "20000000-0000-4000-8000-000000000005"
DECOY_ID = "20000000-0000-4000-8000-000000000006"
CONNECTOR_OBJECT = "30000000-0000-4000-8000-000000000001"
SEEDER_OBJECT = "30000000-0000-4000-8000-000000000002"
DECOY_OBJECT = "30000000-0000-4000-8000-000000000003"
GRAPH_SP = "40000000-0000-4000-8000-000000000001"
WORKIQ_SP = "40000000-0000-4000-8000-000000000002"
CONNECTOR_SP = "40000000-0000-4000-8000-000000000003"
SEEDER_SP = "40000000-0000-4000-8000-000000000004"
OTHER_SP = "40000000-0000-4000-8000-000000000005"
GRANT_ID = "50000000-0000-4000-8000-000000000001"
OTHER_GRANT_ID = "50000000-0000-4000-8000-000000000002"
USER_GRANT_ID = "50000000-0000-4000-8000-000000000003"
NEW_GRANT_ID = "50000000-0000-4000-8000-000000000004"
USER_ID = "60000000-0000-4000-8000-000000000001"
LEGACY_ROLE = "70000000-0000-4000-8000-000000000001"
LEGACY_SCOPE = "70000000-0000-4000-8000-000000000002"
OTHER_PERMISSION = "70000000-0000-4000-8000-000000000003"
WORKIQ_PERMISSION = "70000000-0000-4000-8000-000000000004"
APP_NAME = "Synthetic O'Brien Seeder"
OLD_REDIRECT = "https://old.example.invalid/callback"
NEW_REDIRECT = "https://new.example.invalid/callback"
PROTOCOL_URI = "api://workiq.svc.cloud.microsoft"
GRAPH_ORIGIN = "https://graph.microsoft.com"
GRAPH_BASE = GRAPH_ORIGIN + "/v1.0"
AZ_EXECUTABLE = r"C:\synthetic-tools\az.cmd"
FAKE_TOKEN = "offline-test-token-not-a-credential"
FAKE_SECRET = "offline-test-secret-not-a-credential"
CONNECTOR_SCOPES = (
    "User.Read", "offline_access", "Mail.Read", "Files.Read.All", "Sites.Read.All",
    "ChannelMessage.Read.All", "Chat.Read", "Calendars.Read", "People.Read",
    "Group.Read.All",
)
SEEDER_ROLES = (
    "User.Read.All", "User.ReadWrite.All", "Mail.ReadWrite", "Group.ReadWrite.All",
    "Team.Create", "TeamMember.ReadWrite.All", "Channel.Create", "Teamwork.Migrate.All",
    "ChannelMessage.Read.All", "Files.ReadWrite.All", "Sites.ReadWrite.All",
)
DEVICE_SCOPES = ("ChannelMessage.Send", "Group.ReadWrite.All", "Files.ReadWrite.All", "User.Read.All")
SCOPE_IDS = {
    name: f"80000000-0000-4000-8000-{index:012d}"
    for index, name in enumerate(dict.fromkeys(CONNECTOR_SCOPES + DEVICE_SCOPES), 1)
}
ROLE_IDS = {
    name: f"90000000-0000-4000-8000-{index:012d}"
    for index, name in enumerate(SEEDER_ROLES, 1)
}
FULL_ENV = {
    "WORKIQ_TENANT_ID": TENANT,
    "WORKIQ_CONNECTOR_CLIENT_ID": CONNECTOR_ID,
    "WORKIQ_RESOURCE_APP_ID": WORKIQ_ID,
    "WORKIQ_SEEDER_APP_NAME": APP_NAME,
}
OPTIONAL_IMPORTS = ("azure", "msal", "adal", "requests", "httpx", "keyring", "dotenv")


def forbidden_io(*args, **kwargs):
    raise AssertionError("Real subprocess, credential discovery, network, or file writes are forbidden")


@contextmanager
def import_trap(prefixes=OPTIONAL_IMPORTS):
    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        if any(name == prefix or name.startswith(prefix + ".") for prefix in prefixes):
            raise AssertionError(f"Forbidden import: {name}")
        return original(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=guarded) as trap:
        yield trap


@contextmanager
def load_owned_modules():
    """Read only the five explicitly allowed source files, never cached bytecode."""
    with patch.dict(sys.modules):
        loaded = {}
        for name in OWNED_MODULES:
            path = ROOT / (name + ".py")
            spec = importlib.util.spec_from_file_location(name, str(path))
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            source = spec.loader.get_source(name)
            exec(compile(source, str(path), "exec"), module.__dict__)
            loaded[name] = module
        yield loaded


def install_io_guards(stack):
    for target in (
        "subprocess.run", "subprocess.Popen", "shutil.which", "os.system",
        "urllib.request.urlopen", "urllib.request.build_opener",
        "urllib.request.OpenerDirector.open", "socket.create_connection",
        "socket.socket.connect", "socket.socket.connect_ex", "time.sleep",
    ):
        stack.enter_context(patch(target, side_effect=forbidden_io))

    for target in ("builtins.open", "io.open"):
        original = builtins.open if target == "builtins.open" else io.open

        def guarded_open(file, mode="r", *args, _original=original, **kwargs):
            if any(flag in mode for flag in "wax+"):
                forbidden_io()
            return _original(file, mode, *args, **kwargs)

        stack.enter_context(patch(target, side_effect=guarded_open))
    original_os_open = os.open

    def guarded_os_open(path, flags, *args, **kwargs):
        if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
            forbidden_io()
        return original_os_open(path, flags, *args, **kwargs)

    stack.enter_context(patch("os.open", side_effect=guarded_os_open))
    stack.enter_context(import_trap())


def setUpModule():
    global MODULE_STACK, admin, connector, redirect, grant, seeder, REAL_TOKEN
    MODULE_STACK = ExitStack()
    unittest.addModuleCleanup(MODULE_STACK.close)
    install_io_guards(MODULE_STACK)
    modules = MODULE_STACK.enter_context(load_owned_modules())
    admin, connector, redirect, grant, seeder = [modules[name] for name in OWNED_MODULES]
    REAL_TOKEN = admin.GraphClient._token
    MODULE_STACK.enter_context(patch.object(admin.GraphClient, "_token", side_effect=forbidden_io))


def permission_block(resource, entries):
    return {"resourceAppId": resource, "resourceAccess": copy.deepcopy(entries)}


def preserved_permissions(target):
    return [
        permission_block(OTHER_RESOURCE_ID, [{"id": OTHER_PERMISSION, "type": "Role"}]),
        permission_block(target, [
            {"id": LEGACY_ROLE, "type": "Role"},
            {"id": LEGACY_SCOPE, "type": "Scope"},
        ]),
    ]


def consent(client, resource, *, id=GRANT_ID, scope="Existing.Access", per_user=False):
    return {
        "id": id, "clientId": client, "resourceId": resource,
        "consentType": "Principal" if per_user else "AllPrincipals",
        "principalId": USER_ID if per_user else None, "scope": scope,
    }


def resource_catalog():
    return [
        {
            "id": GRAPH_SP, "appId": GRAPH_ID, "displayName": "Synthetic Graph",
            "oauth2PermissionScopes": [
                {"id": id, "value": name, "isEnabled": True}
                for name, id in SCOPE_IDS.items()
            ],
            "appRoles": [
                {"id": id, "value": name, "isEnabled": True, "allowedMemberTypes": ["Application"]}
                for name, id in ROLE_IDS.items()
            ],
        },
        {
            "id": WORKIQ_SP, "appId": WORKIQ_ID, "displayName": "Synthetic Work IQ",
            "servicePrincipalNames": [PROTOCOL_URI],
            "oauth2PermissionScopes": [
                {"id": WORKIQ_PERMISSION, "value": "WorkIQAgent.Ask", "isEnabled": True},
            ],
        },
    ]


class FakeGraph:
    """Strict stateful Graph substitute; unsupported queries and writes fail closed."""

    def __init__(self):
        self.apps = []
        self.principals = resource_catalog()
        self.grants = []
        self.assignments = {}
        self.calls = []
        self.collections = []
        self.events = []
        self.fail_on = None

    def app(self, id):
        return next(app for app in self.apps if app["id"] == id)

    def principal(self, id):
        return next(sp for sp in self.principals if sp["id"] == id)

    @staticmethod
    def _literal(value):
        return value.replace("''", "'")

    def collection(self, path, filter_expr=None, select=None):
        self.collections.append((path, filter_expr, select))
        self.events.append(("collection", path, filter_expr))
        if self.fail_on == ("collection", path):
            raise RuntimeError("Synthetic collection failure")
        if path in ("/applications", "/servicePrincipals"):
            rows = self.apps if path == "/applications" else self.principals
            match = re.fullmatch(r"(appId|displayName) eq '((?:[^']|'')*)'", filter_expr or "")
            uri_match = re.fullmatch(
                r"servicePrincipalNames/any\(n:n eq '((?:[^']|'')*)'\)", filter_expr or "",
            )
            if match:
                field, value = match.groups()
                rows = [row for row in rows if row.get(field) == self._literal(value)]
            elif path == "/servicePrincipals" and uri_match:
                value = self._literal(uri_match.group(1))
                rows = [row for row in rows if value in row.get("servicePrincipalNames", [])]
            else:
                raise AssertionError(f"Expected exact identity lookup, got {path}: {filter_expr!r}")
        elif path == "/oauth2PermissionGrants":
            match = re.fullmatch(r"clientId eq '([^']+)'", filter_expr or "")
            if not match:
                raise AssertionError(f"Unbounded or unsupported grant query: {filter_expr!r}")
            client = match.group(1)
            rows = [
                row for row in self.grants
                if row["clientId"] == client
            ]
        else:
            match = re.fullmatch(r"/servicePrincipals/([^/]+)/appRoleAssignments", path)
            if not match or filter_expr is not None:
                raise AssertionError(f"Unexpected collection: {path}, {filter_expr!r}")
            rows = self.assignments.get(match.group(1), [])
        if select:
            rows = [{key: row[key] for key in select.split(",") if key in row} for row in rows]
        return copy.deepcopy(rows)

    def call(self, method, path, body=None, **kwargs):
        if kwargs:
            raise AssertionError(f"Unexpected call options: {kwargs}")
        self.calls.append((method, path, copy.deepcopy(body)))
        self.events.append((method, path, copy.deepcopy(body)))
        if self.fail_on == (method, path):
            raise RuntimeError("Synthetic write failure")
        if method == "POST" and path == "/applications":
            app = {"id": SEEDER_OBJECT, "appId": SEEDER_ID, **copy.deepcopy(body)}
            self.apps.append(app)
            return copy.deepcopy(app)
        if method == "POST" and path == "/servicePrincipals":
            app_id = body["appId"]
            if app_id not in (CONNECTOR_ID, SEEDER_ID):
                raise AssertionError(f"Unexpected new client principal: {app_id}")
            sp = {"id": CONNECTOR_SP if app_id == CONNECTOR_ID else SEEDER_SP, "appId": app_id}
            self.principals.append(sp)
            return copy.deepcopy(sp)
        if method == "POST" and path == "/oauth2PermissionGrants":
            row = {"id": NEW_GRANT_ID, **copy.deepcopy(body)}
            self.grants.append(row)
            return copy.deepcopy(row)
        match = re.fullmatch(r"/servicePrincipals/([^/]+)/appRoleAssignments", path)
        if method == "POST" and match:
            if body["principalId"] != match.group(1):
                raise AssertionError("Assignment principal does not match the URL")
            self.assignments.setdefault(match.group(1), []).append(copy.deepcopy(body))
            return copy.deepcopy(body)
        match = re.fullmatch(r"/applications/([^/]+)/addPassword", path)
        if method == "POST" and match:
            self.app(match.group(1))
            return {"secretText": FAKE_SECRET}
        match = re.fullmatch(r"/(applications|oauth2PermissionGrants)/([^/]+)", path)
        if match:
            collection, id = match.groups()
            rows = self.apps if collection == "applications" else self.grants
            row = next((row for row in rows if row["id"] == id), None)
            if row is None:
                raise AssertionError(f"Unknown object: {path}")
            if method == "PATCH":
                row.update(copy.deepcopy(body))
                return None
            if method == "DELETE" and collection == "applications":
                rows.remove(row)
                return None
        raise AssertionError(f"Unexpected Graph call: {method} {path} {body!r}")

    def snapshot(self):
        return copy.deepcopy((self.apps, self.principals, self.grants, self.assignments))

    def clear_records(self):
        self.calls.clear()
        self.collections.clear()
        self.events.clear()


def connector_graph(*, target=GRAPH_ID, with_sp=True):
    graph = FakeGraph()
    graph.apps.append({
        "id": CONNECTOR_OBJECT, "appId": CONNECTOR_ID, "displayName": "Synthetic Connector",
        "requiredResourceAccess": preserved_permissions(target),
        "web": {
            "redirectUris": [OLD_REDIRECT], "homePageUrl": "https://old.example.invalid/",
            "implicitGrantSettings": {"enableIdTokenIssuance": False},
        },
    })
    if with_sp:
        graph.principals.append({"id": CONNECTOR_SP, "appId": CONNECTOR_ID})
    return graph


def seeder_graph(*, existing=True, with_sp=True):
    graph = FakeGraph()
    if existing:
        graph.apps.append({
            "id": SEEDER_OBJECT, "appId": SEEDER_ID, "displayName": APP_NAME,
            "requiredResourceAccess": preserved_permissions(GRAPH_ID),
            "isFallbackPublicClient": False,
            "publicClient": {"redirectUris": [OLD_REDIRECT], "syntheticSetting": "preserve"},
        })
        if with_sp:
            graph.principals.append({"id": SEEDER_SP, "appId": SEEDER_ID})
    return graph


class OfflineTest(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.dict(os.environ, FULL_ENV, clear=True))
        self.stdout = self.stack.enter_context(redirect_stdout(io.StringIO()))
        self.stderr = self.stack.enter_context(redirect_stderr(io.StringIO()))
        self.sleep = self.stack.enter_context(patch("time.sleep"))
        self.stack.enter_context(patch("time.time", return_value=1234567890))
        for module in (admin, connector, seeder):
            self.stack.enter_context(patch.object(module, "GRAPH_APP_ID", GRAPH_ID))

    def invoke(self, module, graph, args=()):
        with patch.object(module, "GraphClient", return_value=graph) as factory:
            result = module.main(list(args))
        factory.assert_called_once_with(TENANT)
        self.assertEqual(result, 0)
        return self.stdout.getvalue()

    def assert_read_only(self, module, graph, args):
        before = graph.snapshot()
        self.invoke(module, graph, args)
        self.assertEqual(graph.calls, [])
        self.assertEqual(graph.snapshot(), before)
        self.sleep.assert_not_called()

    def assert_no_secret(self, graph):
        self.assertFalse(any(path.endswith("/addPassword") for _, path, _ in graph.calls))
        self.assertNotIn(FAKE_SECRET, self.stdout.getvalue())

    def assert_preserved(self, before, after):
        for block in before:
            matches = [b for b in after if b["resourceAppId"] == block["resourceAppId"]]
            self.assertTrue(matches, block)
            entries = [entry for candidate in matches for entry in candidate["resourceAccess"]]
            for entry in block["resourceAccess"]:
                self.assertIn(entry, entries)
            if block["resourceAppId"] == OTHER_RESOURCE_ID:
                self.assertEqual(matches, [block])


class ImportAndConfigurationTests(OfflineTest):
    def test_all_five_imports_are_side_effect_free_without_configuration(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch("argparse.ArgumentParser.parse_args", side_effect=forbidden_io):
                with patch("builtins.print", side_effect=forbidden_io):
                    with load_owned_modules() as modules:
                        self.assertEqual(tuple(modules), OWNED_MODULES)
                        for name in OWNED_MODULES[1:]:
                            self.assertTrue(callable(modules[name].main))

    def test_all_five_imports_ignore_invalid_configuration(self):
        with patch.dict(os.environ, {name: "not-valid" for name in FULL_ENV}, clear=True):
            with patch("argparse.ArgumentParser.parse_args", side_effect=forbidden_io):
                with patch("builtins.print", side_effect=forbidden_io):
                    with load_owned_modules() as modules:
                        client = modules["workiq_admin_config"].GraphClient(TENANT)
                        self.assertEqual(client.tenant_id, TENANT)

    def test_import_trap_rejects_cached_optional_libraries(self):
        for name in OPTIONAL_IMPORTS:
            with self.subTest(name=name), self.assertRaisesRegex(AssertionError, "Forbidden import"):
                __import__(name)

    def test_global_guards_block_real_io_and_token_discovery(self):
        attempts = (
            lambda: subprocess.run(["must-not-run"]),
            lambda: subprocess.Popen(["must-not-run"]),
            lambda: shutil.which("az"),
            lambda: urllib.request.urlopen(GRAPH_BASE),
            lambda: urllib.request.build_opener(),
            lambda: admin.GraphClient(TENANT)._token(),
            lambda: builtins.open(ROOT / "forbidden-scratch", "w"),
            lambda: io.open(ROOT / "forbidden-scratch", "w"),
            lambda: os.open(str(ROOT / "forbidden-scratch"), os.O_CREAT | os.O_WRONLY),
        )
        for index, attempt in enumerate(attempts):
            with self.subTest(index=index), self.assertRaises(AssertionError):
                attempt()

    def test_every_entrypoint_reports_all_missing_variables_before_client_or_imports(self):
        cases = (
            (connector, ("WORKIQ_TENANT_ID", "WORKIQ_CONNECTOR_CLIENT_ID")),
            (redirect, ("WORKIQ_TENANT_ID", "WORKIQ_CONNECTOR_CLIENT_ID")),
            (grant, ("WORKIQ_TENANT_ID", "WORKIQ_CONNECTOR_CLIENT_ID", "WORKIQ_RESOURCE_APP_ID")),
            (seeder, ("WORKIQ_TENANT_ID", "WORKIQ_SEEDER_APP_NAME")),
        )
        for module, required in cases:
            for empty in ({}, {name: " \t " for name in FULL_ENV}):
                with self.subTest(module=module.__name__, empty=empty):
                    with patch.dict(os.environ, empty, clear=True):
                        with patch.object(module, "GraphClient", side_effect=forbidden_io) as factory:
                            with import_trap(OPTIONAL_IMPORTS + ("subprocess", "urllib.request")):
                                with self.assertRaises(ValueError) as caught:
                                    module.main([])
                        factory.assert_not_called()
                    self.assertIn("Required environment variables", str(caught.exception))
                    for name in required:
                        self.assertIn(name, str(caught.exception))
        self.assertEqual(self.stdout.getvalue(), "")

    def test_tenant_is_required_on_each_entrypoint_even_if_cli_environment_exists(self):
        for module in (connector, redirect, grant, seeder):
            with self.subTest(module=module.__name__):
                env = {key: value for key, value in FULL_ENV.items() if key != "WORKIQ_TENANT_ID"}
                env.update(AZURE_TENANT_ID=OTHER_TENANT, ARM_TENANT_ID=OTHER_TENANT)
                with patch.dict(os.environ, env, clear=True):
                    with patch.object(module, "GraphClient", side_effect=forbidden_io) as factory:
                        with self.assertRaisesRegex(ValueError, "WORKIQ_TENANT_ID"):
                            module.main(["--show"])
                        factory.assert_not_called()

    def test_three_connector_entrypoints_require_connector_uuid(self):
        for module in (connector, redirect, grant):
            for value in ("", "Connector Display Name", "common", "organizations", "123"):
                with self.subTest(module=module.__name__, value=value):
                    with patch.dict(os.environ, {"WORKIQ_CONNECTOR_CLIENT_ID": value}):
                        with patch.object(module, "GraphClient", side_effect=forbidden_io) as factory:
                            with self.assertRaisesRegex(ValueError, "WORKIQ_CONNECTOR_CLIENT_ID"):
                                module.main(["--show"])
                            factory.assert_not_called()

    def test_all_entrypoints_reject_non_uuid_tenants_before_client(self):
        for module in (connector, redirect, grant, seeder):
            for value in ("common", "organizations", "tenant.example.invalid", "not-a-uuid"):
                with self.subTest(module=module.__name__, value=value):
                    with patch.dict(os.environ, {"WORKIQ_TENANT_ID": value}):
                        with patch.object(module, "GraphClient", side_effect=forbidden_io) as factory:
                            with self.assertRaisesRegex(ValueError, "WORKIQ_TENANT_ID"):
                                module.main([])
                            factory.assert_not_called()

    def test_scope_entrypoint_requires_explicit_resource_uuid(self):
        for value in ("", "Work IQ", PROTOCOL_URI, "0000"):
            with self.subTest(value=value), patch.dict(os.environ, {"WORKIQ_RESOURCE_APP_ID": value}):
                with patch.object(grant, "GraphClient", side_effect=forbidden_io) as factory:
                    with self.assertRaisesRegex(ValueError, "WORKIQ_RESOURCE_APP_ID"):
                        grant.main([])
                    factory.assert_not_called()

    def test_redirect_rejects_supplied_invalid_optional_resource_before_client(self):
        for value in ("", " ", PROTOCOL_URI, "Work IQ"):
            with self.subTest(value=value), patch.dict(os.environ, {"WORKIQ_RESOURCE_APP_ID": value}):
                with patch.object(redirect, "GraphClient", side_effect=forbidden_io) as factory:
                    with self.assertRaisesRegex(ValueError, "WORKIQ_RESOURCE_APP_ID"):
                        redirect.main(["--show"])
                    factory.assert_not_called()

    def test_seeder_name_is_required_and_validated_before_client(self):
        for value in ("", " ", "x" * 257, "bad\nname", "bad\x7fname"):
            with self.subTest(value=value), patch.dict(os.environ, {"WORKIQ_SEEDER_APP_NAME": value}):
                with patch.object(seeder, "GraphClient", side_effect=forbidden_io) as factory:
                    with self.assertRaisesRegex(ValueError, "WORKIQ_SEEDER_APP_NAME"):
                        seeder.main([])
                    factory.assert_not_called()

    def test_config_reports_missing_values_before_validating_present_invalid_values(self):
        with patch.dict(os.environ, {"WORKIQ_TENANT_ID": "bad"}, clear=True):
            with self.assertRaises(ValueError) as caught:
                admin.load_config("WORKIQ_CONNECTOR_CLIENT_ID", "WORKIQ_RESOURCE_APP_ID")
        self.assertIn("WORKIQ_CONNECTOR_CLIENT_ID", str(caught.exception))
        self.assertIn("WORKIQ_RESOURCE_APP_ID", str(caught.exception))
        self.assertIn("Required environment variables", str(caught.exception))

    def test_config_normalizes_uuid_and_trims_exact_name(self):
        upper_id = "AAAAAAAA-BBBB-4CCC-8DDD-EEEEEEEEEEEE"
        with patch.dict(os.environ, {
            "WORKIQ_TENANT_ID": f" {upper_id} ",
            "WORKIQ_SEEDER_APP_NAME": f" {APP_NAME} ",
        }):
            config = admin.load_config("WORKIQ_SEEDER_APP_NAME")
        self.assertEqual(config, {
            "WORKIQ_TENANT_ID": upper_id.lower(), "WORKIQ_SEEDER_APP_NAME": APP_NAME,
        })

    def test_absent_optional_configuration_is_not_inferred(self):
        with patch.dict(os.environ, {"WORKIQ_TENANT_ID": TENANT}, clear=True):
            self.assertEqual(
                admin.load_config(optional=("WORKIQ_RESOURCE_APP_ID",)),
                {"WORKIQ_TENANT_ID": TENANT},
            )

    def test_redirect_apply_requires_explicit_uri_before_graph_client(self):
        with patch.object(redirect, "GraphClient", side_effect=forbidden_io) as factory:
            with self.assertRaises(SystemExit) as caught:
                redirect.main(["--apply"])
            self.assertEqual(caught.exception.code, 2)
            factory.assert_not_called()
        self.assertIn("--apply requires an explicit --redirect-uri", self.stderr.getvalue())

    def test_seeder_show_and_delete_are_mutually_exclusive_before_configuration(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch.object(seeder, "GraphClient", side_effect=forbidden_io) as factory:
                with self.assertRaises(SystemExit) as caught:
                    seeder.main(["--delete", "--show"])
                self.assertEqual(caught.exception.code, 2)
                factory.assert_not_called()

    def test_seeder_redirect_requires_device_code_before_graph_client(self):
        for args in (["--redirect-uri", NEW_REDIRECT], ["--show", "--redirect-uri", NEW_REDIRECT]):
            with self.subTest(args=args):
                with patch.object(seeder, "GraphClient", side_effect=forbidden_io) as factory:
                    with self.assertRaises(SystemExit) as caught:
                        seeder.main(args)
                    self.assertEqual(caught.exception.code, 2)
                    factory.assert_not_called()

    def test_redirect_validation_accepts_explicit_https_and_loopback_and_deduplicates(self):
        uris = [
            NEW_REDIRECT, "http://localhost:8400/callback", "http://127.0.0.1/cb",
            "https://localhost:8400/callback", "https://127.0.0.1/cb",
        ]
        self.assertEqual(admin.validate_redirect_uris(uris + [NEW_REDIRECT]), uris)
        self.assertEqual(admin.validate_redirect_uris([]), [])

    def test_redirect_validation_enforces_256_character_boundary(self):
        for prefix in ("http://localhost/", "http://127.0.0.1/", "https://example.invalid/"):
            with self.subTest(prefix=prefix):
                uri = prefix + "a" * (256 - len(prefix))
                self.assertEqual(len(uri), 256)
                self.assertEqual(admin.validate_redirect_uris([uri, uri]), [uri])
                self.assertEqual(len(uri + "a"), 257)
                with self.assertRaisesRegex(ValueError, "Invalid redirect URI.*at most 256"):
                    admin.validate_redirect_uris([uri + "a"])

    def test_redirect_validation_rejects_ipv6_hosts_for_http_and_https(self):
        for scheme in ("http", "https"):
            for host in ("[::1]", "[0:0:0:0:0:0:0:1]", "[2001:db8::1]"):
                for suffix in ("/cb", ":8400/cb"):
                    uri = f"{scheme}://{host}{suffix}"
                    with self.subTest(uri=uri):
                        with self.assertRaisesRegex(ValueError, "Invalid redirect URI.*IPv6"):
                            admin.validate_redirect_uris([uri])

    def test_invalid_redirects_fail_before_graph_client_on_both_entrypoints(self):
        invalid = (
            "http://example.invalid/cb", "https://user:password@example.invalid/cb",
            "https://example.invalid/cb#fragment", "https://example.invalid:bad/cb",
            "https://example.invalid:65536/cb", "https:///cb", "javascript:alert(1)",
            " https://example.invalid/cb", "https://example.invalid/c b",
            "https://example.invalid/\\cb", "https://example.invalid/\ncb",
            "http://[::1]/cb", "https://[::1]/cb",
            "http://[::1]:8400/cb", "https://[::1]:8400/cb",
        ) + tuple(
            prefix + "a" * (257 - len(prefix))
            for prefix in ("http://localhost/", "http://127.0.0.1/", "https://example.invalid/")
        )
        entrypoints = (
            (redirect, []), (redirect, ["--apply"]), (redirect, ["--show", "--apply"]),
            (seeder, ["--enable-device-code"]),
            (seeder, ["--show", "--enable-device-code"]),
            (seeder, ["--delete", "--enable-device-code"]),
        )
        for module, prefix in entrypoints:
            for uri in invalid:
                with self.subTest(module=module.__name__, args=prefix, uri=uri):
                    with patch.object(module, "GraphClient", side_effect=forbidden_io) as factory:
                        with import_trap(OPTIONAL_IMPORTS + ("subprocess", "urllib.request")):
                            with self.assertRaisesRegex(ValueError, "Invalid redirect URI"):
                                module.main(prefix + [
                                    "--redirect-uri", NEW_REDIRECT, "--redirect-uri", uri,
                                ])
                        factory.assert_not_called()


class GraphTransportTests(OfflineTest):
    @contextmanager
    def transport(self, *, payload=None, stdout=None, returncode=0, executable=AZ_EXECUTABLE):
        if stdout is None:
            stdout = json.dumps(payload if payload is not None else {
                "tenant": TENANT, "accessToken": FAKE_TOKEN,
            })
        result = SimpleNamespace(returncode=returncode, stdout=stdout, stderr="synthetic stderr")
        opener = Mock(name="offline-opener")
        with ExitStack() as stack:
            which = stack.enter_context(patch("shutil.which", return_value=executable))
            run = stack.enter_context(patch("subprocess.run", return_value=result))
            build = stack.enter_context(patch("urllib.request.build_opener", return_value=opener))
            stack.enter_context(patch.object(admin.GraphClient, "_token", REAL_TOKEN))
            yield SimpleNamespace(which=which, run=run, build=build, opener=opener)

    @staticmethod
    def response(payload=None, status=200, raw=None):
        response = Mock()
        response.status = status
        response.read.return_value = raw if raw is not None else (
            json.dumps(payload).encode() if payload is not None else b""
        )
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        return response

    def test_constructor_validates_tenant_without_cli_or_network(self):
        client = admin.GraphClient(TENANT)
        self.assertEqual(client.tenant_id, TENANT)
        self.assertIsNone(client._access_token)
        for value in ("common", "", "tenant.example.invalid"):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "WORKIQ_TENANT_ID"):
                admin.GraphClient(value)

    def test_cli_resolution_is_lazy_and_explicit_tenant_token_is_cached(self):
        with self.transport() as transport:
            client = admin.GraphClient(TENANT)
            transport.which.assert_not_called()
            transport.run.assert_not_called()
            transport.build.assert_not_called()
            transport.opener.open.side_effect = [
                self.response({"value": []}), self.response(status=204),
            ]
            self.assertEqual(client.call("GET", "/applications"), {"value": []})
            self.assertIsNone(client.call("DELETE", f"/applications/{CONNECTOR_OBJECT}"))
            transport.which.assert_called_once_with("az")
            transport.run.assert_called_once_with(
                [AZ_EXECUTABLE, "account", "get-access-token", "--tenant", TENANT,
                 "--resource", GRAPH_ORIGIN, "--output", "json"],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                shell=False, timeout=90,
            )
            self.assertEqual(transport.opener.open.call_count, 2)
            for request_call in transport.opener.open.call_args_list:
                request = request_call.args[0]
                self.assertEqual(request.get_header("Authorization"), "Bearer " + FAKE_TOKEN)
                self.assertEqual(request_call.kwargs, {"timeout": 90})

    def test_requests_have_expected_method_url_bearer_and_json_body(self):
        with self.transport() as transport:
            body = {"web": {"redirectUris": [NEW_REDIRECT]}, "displayName": APP_NAME}
            transport.opener.open.return_value = self.response(status=204)
            admin.GraphClient(TENANT).call("patch", f"/applications/{CONNECTOR_OBJECT}", body)
            request = transport.opener.open.call_args.args[0]
            self.assertIsInstance(request, urllib.request.Request)
            self.assertEqual(request.get_method(), "PATCH")
            self.assertEqual(request.full_url, f"{GRAPH_BASE}/applications/{CONNECTOR_OBJECT}")
            self.assertEqual(request.get_header("Authorization"), "Bearer " + FAKE_TOKEN)
            self.assertEqual(request.get_header("Content-type"), "application/json")
            self.assertEqual(request.get_header("Accept"), "application/json")
            self.assertEqual(json.loads(request.data.decode("utf-8")), body)

    def test_get_has_no_body_and_post_empty_object_is_not_discarded(self):
        with self.transport() as transport:
            transport.opener.open.return_value = self.response({"id": CONNECTOR_OBJECT}, status=201)
            client = admin.GraphClient(TENANT)
            client.call("GET", "/applications")
            self.assertIsNone(transport.opener.open.call_args.args[0].data)
            client.call("POST", "/applications", {})
            self.assertEqual(transport.opener.open.call_args.args[0].data, b"{}")

    def test_missing_cli_fails_without_subprocess_or_http(self):
        with self.transport(executable=None) as transport:
            with self.assertRaisesRegex(RuntimeError, "Azure CLI is required"):
                admin.GraphClient(TENANT).call("GET", "/applications")
            transport.which.assert_called_once_with("az")
            transport.run.assert_not_called()
            transport.build.assert_not_called()
            transport.opener.open.assert_not_called()

    def test_cli_failure_fails_without_http_and_does_not_echo_token(self):
        with self.transport(returncode=1) as transport:
            with self.assertRaisesRegex(RuntimeError, TENANT) as caught:
                admin.GraphClient(TENANT).call("GET", "/applications")
            self.assertNotIn(FAKE_TOKEN, str(caught.exception))
            transport.build.assert_not_called()

    def test_wrong_token_tenant_never_reaches_http(self):
        with self.transport(payload={"tenant": OTHER_TENANT, "accessToken": FAKE_TOKEN}) as transport:
            with self.assertRaisesRegex(RuntimeError, "different tenant") as caught:
                admin.GraphClient(TENANT).call("GET", "/applications")
            self.assertNotIn(FAKE_TOKEN, str(caught.exception))
            transport.build.assert_not_called()
            transport.opener.open.assert_not_called()

    def test_invalid_token_payloads_never_reach_http(self):
        payloads = (
            {}, {"accessToken": FAKE_TOKEN}, {"tenant": TENANT},
            {"tenant": "common", "accessToken": FAKE_TOKEN},
            {"tenant": TENANT, "accessToken": ""},
            {"tenant": TENANT, "accessToken": " \t"},
            {"tenant": TENANT, "accessToken": None},
            {"tenant": TENANT, "accessToken": 123},
            {"tenant": TENANT, "accessToken": ["not-a-token"]},
            [], None, "not-an-object",
        )
        for payload in payloads:
            with self.subTest(payload=payload), self.transport(stdout=json.dumps(payload)) as transport:
                with self.assertRaises(RuntimeError):
                    admin.GraphClient(TENANT).call("GET", "/applications")
                transport.build.assert_not_called()
                transport.opener.open.assert_not_called()

    def test_non_json_cli_output_never_reaches_http(self):
        with self.transport(stdout="not-json") as transport:
            with self.assertRaisesRegex(RuntimeError, "invalid tenant-bound token"):
                admin.GraphClient(TENANT).call("GET", "/applications")
            transport.build.assert_not_called()

    def test_subprocess_timeout_does_not_fall_back_to_another_tenant_or_http(self):
        with self.transport() as transport:
            transport.run.side_effect = subprocess.TimeoutExpired("synthetic-az", 90)
            with self.assertRaises(subprocess.TimeoutExpired):
                admin.GraphClient(TENANT).call("GET", "/applications")
            transport.run.assert_called_once()
            transport.build.assert_not_called()

    def test_url_only_accepts_public_graph_v1_origin(self):
        client = admin.GraphClient(TENANT)
        for path in ("/applications", GRAPH_BASE + "/applications?$top=1"):
            with self.subTest(path=path):
                self.assertEqual(client._url(path), GRAPH_BASE + path if path.startswith("/") else path)
        invalid = (
            "http://graph.microsoft.com/v1.0/applications",
            "https://graph.microsoft.com.evil.invalid/v1.0/applications",
            "https://evil.invalid/v1.0/applications",
            "https://graph.microsoft.com@evil.invalid/v1.0/applications",
            "https://user@graph.microsoft.com/v1.0/applications",
            "https://graph.microsoft.com:443/v1.0/applications",
            "https://graph.microsoft.us/v1.0/applications",
            "https://graph.microsoft.com/beta/applications",
            "https://graph.microsoft.com/v1.00/applications",
            GRAPH_BASE + "/applications#fragment", "applications", "file:///applications",
        )
        for path in invalid:
            with self.subTest(path=path), self.assertRaises(ValueError):
                client.call("GET", path)

    def test_http_redirect_handler_refuses_to_forward_bearer(self):
        with self.transport() as transport:
            transport.opener.open.return_value = self.response({"value": []})
            admin.GraphClient(TENANT).call("GET", "/applications")
            handler = transport.build.call_args.args[0]
            self.assertIsInstance(handler, urllib.request.HTTPRedirectHandler)
            request = transport.opener.open.call_args.args[0]
            for status in (301, 302, 303, 307, 308):
                for destination in ("https://evil.invalid/steal", GRAPH_BASE + "/other"):
                    with self.subTest(status=status, destination=destination):
                        with self.assertRaisesRegex(RuntimeError, "redirects are refused"):
                            handler.redirect_request(request, None, status, "moved", {}, destination)
            self.assertEqual(transport.opener.open.call_count, 1)

    def test_http_errors_are_sanitized(self):
        for status in (301, 401, 403, 429, 500):
            with self.subTest(status=status), self.transport() as transport:
                transport.opener.open.side_effect = HTTPError(
                    GRAPH_BASE + "/applications", status, FAKE_TOKEN, {}, None,
                )
                with self.assertRaisesRegex(RuntimeError, f"HTTP {status}") as caught:
                    admin.GraphClient(TENANT).call("GET", "/applications")
                self.assertNotIn(FAKE_TOKEN, str(caught.exception))

    def test_network_failure_is_sanitized(self):
        with self.transport() as transport:
            transport.opener.open.side_effect = URLError(FAKE_TOKEN)
            with self.assertRaisesRegex(RuntimeError, "could not reach") as caught:
                admin.GraphClient(TENANT).call("GET", "/applications")
            self.assertNotIn(FAKE_TOKEN, str(caught.exception))

    def test_unexpected_status_fails_and_explicit_ok_status_is_honored(self):
        with self.transport() as transport:
            transport.opener.open.return_value = self.response(status=202)
            client = admin.GraphClient(TENANT)
            with self.assertRaisesRegex(RuntimeError, "HTTP 202"):
                client.call("POST", "/applications", {})
            self.assertIsNone(client.call("POST", "/applications", {}, ok=(202,)))

    def test_collection_encodes_exact_filter_select_and_follows_pagination_once_per_page(self):
        filter_expr = "displayName eq 'Synthetic O''Brien Seeder'"
        next_link = GRAPH_BASE + "/applications?$skiptoken=synthetic%2Btoken"
        with self.transport() as transport:
            transport.opener.open.side_effect = [
                self.response({"value": [{"id": CONNECTOR_OBJECT}], "@odata.nextLink": next_link}),
                self.response({"value": [{"id": SEEDER_OBJECT}]}),
            ]
            rows = admin.GraphClient(TENANT).collection(
                "/applications?$top=1", filter_expr, "id,displayName",
            )
            self.assertEqual(rows, [{"id": CONNECTOR_OBJECT}, {"id": SEEDER_OBJECT}])
            first, second = [call.args[0] for call in transport.opener.open.call_args_list]
            self.assertEqual(first.get_method(), "GET")
            self.assertIsNone(first.data)
            self.assertEqual(urlsplit(first.full_url).path, "/v1.0/applications")
            self.assertEqual(parse_qs(urlsplit(first.full_url).query), {
                "$top": ["1"], "$filter": [filter_expr], "$select": ["id,displayName"],
            })
            self.assertEqual(second.full_url, next_link)
            transport.run.assert_called_once()

    def test_collection_rejects_external_next_link_before_second_http_request(self):
        with self.transport() as transport:
            transport.opener.open.return_value = self.response({
                "value": [], "@odata.nextLink": "https://evil.invalid/v1.0/applications",
            })
            with self.assertRaises(ValueError):
                admin.GraphClient(TENANT).collection("/applications")
            transport.opener.open.assert_called_once()

    def test_collection_rejects_repeated_pagination_link(self):
        with self.transport() as transport:
            transport.opener.open.return_value = self.response({
                "value": [], "@odata.nextLink": GRAPH_BASE + "/applications",
            })
            with self.assertRaisesRegex(RuntimeError, "repeated pagination"):
                admin.GraphClient(TENANT).collection("/applications")
            transport.opener.open.assert_called_once()

    def test_collection_rejects_malformed_pages(self):
        for page in (None, [], {}, {"value": None}, {"value": {}}, {"value": "bad"}):
            with self.subTest(page=page), self.transport() as transport:
                transport.opener.open.return_value = self.response(raw=json.dumps(page).encode())
                with self.assertRaisesRegex(RuntimeError, "invalid collection"):
                    admin.GraphClient(TENANT).collection("/applications")

    def test_collection_continues_after_empty_page_with_next_link(self):
        with self.transport() as transport:
            transport.opener.open.side_effect = [
                self.response({"value": [], "@odata.nextLink": GRAPH_BASE + "/applications?$skip=1"}),
                self.response({"value": [{"id": SEEDER_OBJECT}]}),
            ]
            self.assertEqual(
                admin.GraphClient(TENANT).collection("/applications"), [{"id": SEEDER_OBJECT}],
            )


class PermissionHelperTests(OfflineTest):
    def test_find_unique_fails_missing_and_duplicates_and_supports_optional_missing(self):
        graph = connector_graph()
        self.assertEqual(admin.find_application(graph, CONNECTOR_ID)["id"], CONNECTOR_OBJECT)
        with self.assertRaisesRegex(RuntimeError, "not found"):
            admin.find_application(graph, DECOY_ID)
        self.assertIsNone(admin.find_service_principal(graph, OTHER_RESOURCE_ID, required=False))
        graph.apps.append({**graph.apps[0], "id": DECOY_OBJECT})
        for required in (True, False):
            with self.subTest(required=required), self.assertRaisesRegex(RuntimeError, "Ambiguous"):
                admin.find_unique(
                    graph, "/applications", f"appId eq '{CONNECTOR_ID}'", "synthetic app",
                    required=required,
                )
        self.assertEqual(graph.calls, [])

    def test_find_unique_passes_select_and_odata_escapes_apostrophes(self):
        graph = seeder_graph()
        self.assertEqual(admin.odata_literal(APP_NAME), "'Synthetic O''Brien Seeder'")
        row = admin.find_unique(
            graph, "/applications", "displayName eq 'Synthetic O''Brien Seeder'",
            "synthetic app", select="id,displayName",
        )
        self.assertEqual(row, {"id": SEEDER_OBJECT, "displayName": APP_NAME})
        self.assertEqual(graph.collections[-1][2], "id,displayName")

    def test_permission_entries_return_enabled_scope_and_application_role_ids(self):
        graph = FakeGraph()
        resource = graph.principal(GRAPH_SP)
        self.assertEqual(admin.permission_entries(resource, ["User.Read"]), [
            {"id": SCOPE_IDS["User.Read"], "type": "Scope"},
        ])
        self.assertEqual(admin.permission_entries(resource, ["User.Read.All"], application=True), [
            {"id": ROLE_IDS["User.Read.All"], "type": "Role"},
        ])

    def test_permissions_require_boolean_true_not_truthy_values(self):
        for application in (False, True):
            for enabled in (False, None, 1, "true"):
                with self.subTest(application=application, enabled=enabled):
                    entry = {
                        "id": LEGACY_ROLE, "value": "Synthetic.Permission",
                        "isEnabled": enabled, "allowedMemberTypes": ["Application"],
                    }
                    key = "appRoles" if application else "oauth2PermissionScopes"
                    with self.assertRaisesRegex(RuntimeError, "missing/disabled"):
                        admin.permission_entries({key: [entry]}, ["Synthetic.Permission"], application=application)
            key = "appRoles" if application else "oauth2PermissionScopes"
            with self.subTest(application=application, enabled="absent"):
                with self.assertRaisesRegex(RuntimeError, "missing/disabled"):
                    admin.permission_entries(
                        {key: [{"id": LEGACY_ROLE, "value": "Synthetic.Permission", "allowedMemberTypes": ["Application"]}]},
                        ["Synthetic.Permission"], application=application,
                    )

    def test_application_roles_must_allow_application_members(self):
        for members in ([], ["User"], ["application"]):
            with self.subTest(members=members), self.assertRaisesRegex(RuntimeError, "missing/disabled"):
                admin.permission_entries({"appRoles": [{
                    "id": LEGACY_ROLE, "value": "Synthetic.Role", "isEnabled": True,
                    "allowedMemberTypes": members,
                }]}, ["Synthetic.Role"], application=True)
        self.assertEqual(admin.permission_entries({"appRoles": [{
            "id": LEGACY_ROLE, "value": "Synthetic.Role", "isEnabled": True,
            "allowedMemberTypes": ["User", "Application"],
        }]}, ["Synthetic.Role"], application=True), [{"id": LEGACY_ROLE, "type": "Role"}])

    def test_permissions_fail_missing_ambiguous_and_idless_catalog_entries(self):
        for application in (False, True):
            key = "appRoles" if application else "oauth2PermissionScopes"
            entry = {
                "id": LEGACY_ROLE, "value": "Synthetic.Permission",
                "isEnabled": True, "allowedMemberTypes": ["Application"],
            }
            cases = (
                ([], "missing/disabled"),
                ([entry, {**entry, "id": OTHER_PERMISSION}], "ambiguous"),
                ([{**entry, "id": None}], "no ID"),
                ([{key: value for key, value in entry.items() if key != "id"}], "no ID"),
            )
            for entries, message in cases:
                with self.subTest(application=application, entries=entries):
                    with self.assertRaisesRegex(RuntimeError, message):
                        admin.permission_entries({key: entries}, ["Synthetic.Permission"], application=application)

    def test_disabled_duplicate_does_not_make_enabled_permission_ambiguous(self):
        entry = {"id": LEGACY_SCOPE, "value": "Synthetic.Scope", "isEnabled": True}
        self.assertEqual(admin.permission_entries({
            "oauth2PermissionScopes": [entry, {**entry, "id": OTHER_PERMISSION, "isEnabled": False}],
        }, ["Synthetic.Scope"]), [{"id": LEGACY_SCOPE, "type": "Scope"}])

    def test_merge_preserves_blocks_roles_scopes_input_and_is_idempotent(self):
        app = {"requiredResourceAccess": preserved_permissions(GRAPH_ID)}
        before = copy.deepcopy(app)
        additions = [
            {"id": SCOPE_IDS["User.Read"], "type": "Scope"},
            {"id": ROLE_IDS["User.Read.All"], "type": "Role"},
            {"id": SCOPE_IDS["User.Read"], "type": "Scope"},
        ]
        merged = admin.merge_resource_access(app, GRAPH_ID, additions)
        self.assertEqual(app, before)
        self.assert_preserved(before["requiredResourceAccess"], merged)
        self.assertEqual(len(merged[1]["resourceAccess"]), 4)
        self.assertEqual(admin.merge_resource_access({"requiredResourceAccess": merged}, GRAPH_ID, additions), merged)
        merged[0]["resourceAccess"].clear()
        self.assertEqual(app, before)

    def test_merge_resource_matching_is_case_insensitive_and_preserves_duplicate_blocks(self):
        resource = "AAAAAAAA-BBBB-4CCC-8DDD-EEEEEEEEEEEE"
        scope = {"id": LEGACY_SCOPE, "type": "Scope"}
        role = {"id": LEGACY_SCOPE, "type": "Role"}
        app = {"requiredResourceAccess": [
            permission_block(resource, [scope]), permission_block(resource.lower(), [role]),
        ]}
        before = copy.deepcopy(app)
        merged = admin.merge_resource_access(app, resource.lower(), [scope, role, {"id": OTHER_PERMISSION, "type": "Role"}])
        self.assertEqual(len(merged), 2)
        self.assertEqual(merged[1], before["requiredResourceAccess"][1])
        self.assertEqual(len(merged[0]["resourceAccess"]), 2)
        self.assertEqual(app, before)

    def test_merge_adds_missing_resource_without_discarding_existing_resources(self):
        before = preserved_permissions(GRAPH_ID)
        addition = {"id": WORKIQ_PERMISSION, "type": "Scope"}
        merged = admin.merge_resource_access({"requiredResourceAccess": before}, WORKIQ_ID, [addition])
        self.assertEqual(merged[:2], before)
        self.assertEqual(merged[2], permission_block(WORKIQ_ID, [addition]))

    def test_grant_lookup_is_bound_to_client_resource_and_all_principals(self):
        graph = FakeGraph()
        wanted = consent(CONNECTOR_SP, GRAPH_SP)
        graph.grants = [
            wanted,
            consent(CONNECTOR_SP, WORKIQ_SP, id=OTHER_GRANT_ID),
            consent(CONNECTOR_SP, GRAPH_SP, id=USER_GRANT_ID, per_user=True),
        ]
        self.assertEqual(admin.find_tenant_grant(graph, CONNECTOR_SP, GRAPH_SP), wanted)
        self.assertEqual(graph.collections[-1], (
            "/oauth2PermissionGrants",
            f"clientId eq '{CONNECTOR_SP}'",
            None,
        ))

    def test_grant_lookup_validates_client_resource_and_consent_locally(self):
        wanted = consent(CONNECTOR_SP, GRAPH_SP)
        graph = Mock()
        graph.collection.return_value = [
            consent(SEEDER_SP, GRAPH_SP),
            consent(CONNECTOR_SP, WORKIQ_SP, id=OTHER_GRANT_ID),
            consent(CONNECTOR_SP, GRAPH_SP, id=USER_GRANT_ID, per_user=True),
            wanted,
        ]
        self.assertEqual(admin.find_tenant_grant(graph, CONNECTOR_SP, GRAPH_SP), wanted)
        graph.collection.assert_called_once_with(
            "/oauth2PermissionGrants", f"clientId eq '{CONNECTOR_SP}'",
        )

    def test_grant_merge_preserves_scopes_and_is_idempotent(self):
        graph = FakeGraph()
        graph.grants = [consent(CONNECTOR_SP, GRAPH_SP, scope="Existing.Access User.Read")]
        before = copy.deepcopy(graph.grants[0])
        admin.write_tenant_grant(graph, CONNECTOR_SP, GRAPH_SP, ["Mail.Read", "User.Read"], before)
        self.assertEqual(graph.calls, [
            ("PATCH", f"/oauth2PermissionGrants/{GRANT_ID}", {"scope": "Existing.Access Mail.Read User.Read"}),
        ])
        self.assertEqual(before["scope"], "Existing.Access User.Read")
        graph.clear_records()
        admin.write_tenant_grant(graph, CONNECTOR_SP, GRAPH_SP, ["User.Read", "Mail.Read"], graph.grants[0])
        self.assertEqual(graph.calls, [])

    def test_grant_writer_refuses_per_user_consent_without_writes(self):
        graph = FakeGraph()
        with self.assertRaisesRegex(RuntimeError, "per-user"):
            admin.write_tenant_grant(
                graph, CONNECTOR_SP, GRAPH_SP, ["Mail.Read"],
                consent(CONNECTOR_SP, GRAPH_SP, per_user=True),
            )
        self.assertEqual(graph.calls, [])

    def test_grant_creation_uses_only_requested_resource_and_all_principals(self):
        graph = FakeGraph()
        admin.write_tenant_grant(graph, CONNECTOR_SP, WORKIQ_SP, ["WorkIQAgent.Ask"], None)
        self.assertEqual(graph.calls, [("POST", "/oauth2PermissionGrants", {
            "clientId": CONNECTOR_SP, "resourceId": WORKIQ_SP,
            "consentType": "AllPrincipals", "scope": "WorkIQAgent.Ask",
        })])


class ConnectorAndScopeTests(OfflineTest):
    def variants(self):
        return (
            (connector, GRAPH_ID, GRAPH_SP, CONNECTOR_SCOPES),
            (grant, WORKIQ_ID, WORKIQ_SP, ("WorkIQAgent.Ask",)),
        )

    def test_expected_permission_catalogs_are_exercised(self):
        self.assertEqual(tuple(name for name, _ in connector.REQUIRED), CONNECTOR_SCOPES)
        self.assertEqual(tuple(grant.WANTED), ("WorkIQAgent.Ask",))
        self.assertEqual(tuple(name for name, _ in seeder.REQUIRED), SEEDER_ROLES)
        self.assertEqual(tuple(seeder.DEVICE_SCOPES), DEVICE_SCOPES)

    def test_defaults_and_show_override_apply_are_read_only_even_without_client_sp(self):
        for module, target, _, _ in self.variants():
            for args in ([], ["--show"], ["--show", "--apply"]):
                for with_sp in (True, False):
                    with self.subTest(module=module.__name__, args=args, with_sp=with_sp):
                        self.assert_read_only(module, connector_graph(target=target, with_sp=with_sp), args)

    def test_apply_preserves_permissions_and_merges_only_target_tenant_grant(self):
        for module, target, resource_sp, scopes in self.variants():
            with self.subTest(module=module.__name__):
                graph = connector_graph(target=target)
                before = copy.deepcopy(graph.app(CONNECTOR_OBJECT)["requiredResourceAccess"])
                other_sp = WORKIQ_SP if resource_sp == GRAPH_SP else GRAPH_SP
                graph.grants = [
                    consent(CONNECTOR_SP, resource_sp),
                    consent(CONNECTOR_SP, resource_sp, id=USER_GRANT_ID, per_user=True),
                    consent(CONNECTOR_SP, other_sp, id=OTHER_GRANT_ID),
                ]
                untouched = copy.deepcopy(graph.grants[1:])
                self.invoke(module, graph, ["--apply"])
                merged = graph.app(CONNECTOR_OBJECT)["requiredResourceAccess"]
                self.assert_preserved(before, merged)
                target_block = next(b for b in merged if b["resourceAppId"] == target)
                for name in scopes:
                    expected = SCOPE_IDS[name] if target == GRAPH_ID else WORKIQ_PERMISSION
                    self.assertIn({"id": expected, "type": "Scope"}, target_block["resourceAccess"])
                self.assertEqual(set(graph.grants[0]["scope"].split()), {"Existing.Access", *scopes})
                self.assertEqual(graph.grants[1:], untouched)
                self.assertEqual([(m, p) for m, p, _ in graph.calls], [
                    ("PATCH", f"/applications/{CONNECTOR_OBJECT}"),
                    ("PATCH", f"/oauth2PermissionGrants/{GRANT_ID}"),
                ])
                graph.clear_records()
                self.invoke(module, graph, ["--apply"])
                self.assertEqual(graph.calls, [])

    def test_apply_creates_missing_sp_and_all_principals_grant(self):
        for module, target, resource_sp, scopes in self.variants():
            with self.subTest(module=module.__name__):
                graph = connector_graph(target=target, with_sp=False)
                self.invoke(module, graph, ["--apply"])
                self.assertIn(("POST", "/servicePrincipals", {"appId": CONNECTOR_ID}), graph.calls)
                self.assertIn(("POST", "/oauth2PermissionGrants", {
                    "clientId": CONNECTOR_SP, "resourceId": resource_sp,
                    "consentType": "AllPrincipals", "scope": " ".join(scopes),
                }), graph.calls)
                self.assertEqual(graph.principal(CONNECTOR_SP)["appId"], CONNECTOR_ID)
                graph.clear_records()
                self.invoke(module, graph, ["--apply"])
                self.assertEqual(graph.calls, [])

    def test_per_user_grant_is_not_reused_when_tenant_grant_is_missing(self):
        for module, target, resource_sp, scopes in self.variants():
            with self.subTest(module=module.__name__):
                graph = connector_graph(target=target)
                original = consent(CONNECTOR_SP, resource_sp, id=USER_GRANT_ID, per_user=True)
                graph.grants = [copy.deepcopy(original)]
                self.invoke(module, graph, ["--apply"])
                self.assertEqual(graph.grants[0], original)
                self.assertEqual(graph.grants[1]["consentType"], "AllPrincipals")
                self.assertEqual(graph.grants[1]["resourceId"], resource_sp)
                self.assertEqual(set(graph.grants[1]["scope"].split()), set(scopes))

    def test_ambiguous_grants_fail_before_any_writes(self):
        for module, target, resource_sp, _ in self.variants():
            with self.subTest(module=module.__name__):
                graph = connector_graph(target=target)
                graph.grants = [
                    consent(CONNECTOR_SP, resource_sp),
                    consent(CONNECTOR_SP, resource_sp, id=OTHER_GRANT_ID),
                ]
                before = graph.snapshot()
                with self.assertRaisesRegex(RuntimeError, "Ambiguous"):
                    self.invoke(module, graph, ["--apply"])
                self.assertEqual(graph.calls, [])
                self.assertEqual(graph.snapshot(), before)

    def test_each_missing_or_disabled_scope_fails_before_any_write(self):
        for module, target, resource_sp, scopes in self.variants():
            for name in scopes:
                for disabled in (False, True):
                    with self.subTest(module=module.__name__, name=name, disabled=disabled):
                        graph = connector_graph(target=target, with_sp=False)
                        entries = graph.principal(resource_sp)["oauth2PermissionScopes"]
                        if disabled:
                            next(entry for entry in entries if entry["value"] == name)["isEnabled"] = False
                        else:
                            entries[:] = [entry for entry in entries if entry["value"] != name]
                        before = graph.snapshot()
                        with self.assertRaisesRegex(RuntimeError, re.escape(name)):
                            self.invoke(module, graph, ["--apply"])
                        self.assertEqual(graph.calls, [])
                        self.assertEqual(graph.snapshot(), before)

    def test_missing_or_ambiguous_app_or_resource_fails_before_writes(self):
        for module, target, resource_sp, _ in self.variants():
            for kind in ("missing-app", "duplicate-app", "missing-resource", "duplicate-resource", "duplicate-client"):
                with self.subTest(module=module.__name__, kind=kind):
                    graph = connector_graph(target=target)
                    if kind == "missing-app":
                        graph.apps.clear()
                    elif kind == "duplicate-app":
                        graph.apps.append({**graph.apps[0], "id": DECOY_OBJECT})
                    elif kind == "missing-resource":
                        graph.principals[:] = [sp for sp in graph.principals if sp["id"] != resource_sp]
                    else:
                        id = resource_sp if kind == "duplicate-resource" else CONNECTOR_SP
                        graph.principals.append({**graph.principal(id), "id": OTHER_SP})
                    with self.assertRaises(RuntimeError):
                        self.invoke(module, graph, ["--apply"])
                    self.assertEqual(graph.calls, [])

    def test_unexpected_per_user_grant_response_fails_before_application_patch(self):
        for module, target, resource_sp, _ in self.variants():
            with self.subTest(module=module.__name__):
                graph = connector_graph(target=target)
                with patch.object(admin, "find_tenant_grant", return_value=consent(CONNECTOR_SP, resource_sp, per_user=True)):
                    with self.assertRaisesRegex(RuntimeError, "AllPrincipals"):
                        self.invoke(module, graph, ["--apply"])
                self.assertEqual(graph.calls, [])


class RedirectTests(OfflineTest):
    def test_show_and_default_are_read_only_even_with_apply_and_new_redirect(self):
        for args in (
            [], ["--show"], ["--show", "--apply"],
            ["--redirect-uri", NEW_REDIRECT],
            ["--show", "--apply", "--redirect-uri", NEW_REDIRECT],
        ):
            with self.subTest(args=args):
                self.assert_read_only(redirect, connector_graph(), args)

    def test_explicit_resource_uuid_uses_only_exact_app_id_lookup(self):
        graph = connector_graph()
        graph.principals.append({
            "id": OTHER_SP, "appId": DECOY_ID, "displayName": "Work IQ",
            "servicePrincipalNames": [PROTOCOL_URI],
        })
        self.invoke(redirect, graph, ["--show"])
        lookups = [entry for entry in graph.collections if entry[0] == "/servicePrincipals"]
        self.assertEqual(lookups, [("/servicePrincipals", f"appId eq '{WORKIQ_ID}'", None)])

    def test_absent_resource_uuid_uses_only_exact_protocol_uri_never_name_heuristic(self):
        graph = connector_graph()
        graph.principals.append({
            "id": OTHER_SP, "appId": DECOY_ID, "displayName": "Work IQ",
            "servicePrincipalNames": [PROTOCOL_URI + "/not-exact"],
        })
        env = {key: value for key, value in FULL_ENV.items() if key != "WORKIQ_RESOURCE_APP_ID"}
        with patch.dict(os.environ, env, clear=True):
            self.invoke(redirect, graph, ["--show"])
        lookups = [entry for entry in graph.collections if entry[0] == "/servicePrincipals"]
        self.assertEqual(lookups, [(
            "/servicePrincipals", f"servicePrincipalNames/any(n:n eq '{PROTOCOL_URI}')", None,
        )])

    def test_missing_explicit_resource_does_not_fall_back_to_uri_or_display_name(self):
        graph = connector_graph()
        with patch.dict(os.environ, {"WORKIQ_RESOURCE_APP_ID": DECOY_ID}):
            self.invoke(redirect, graph, ["--show"])
        self.assertIn("not provisioned", self.stdout.getvalue())
        self.assertEqual([f for p, f, _ in graph.collections if p == "/servicePrincipals"], [
            f"appId eq '{DECOY_ID}'",
        ])
        self.assertEqual(graph.calls, [])

    def test_protocol_lookup_missing_resource_allows_first_consent_callback(self):
        env = {key: value for key, value in FULL_ENV.items() if key != "WORKIQ_RESOURCE_APP_ID"}
        with patch.dict(os.environ, env, clear=True):
            graph = connector_graph()
            graph.principals[:] = [sp for sp in graph.principals if sp["id"] != WORKIQ_SP]
            self.invoke(redirect, graph, ["--apply", "--redirect-uri", NEW_REDIRECT])
            self.assertEqual(len(graph.calls), 1)
            method, path, body = graph.calls[0]
            self.assertEqual((method, path), ("PATCH", f"/applications/{CONNECTOR_OBJECT}"))
            self.assertIn(NEW_REDIRECT, body["web"]["redirectUris"])

    def test_protocol_lookup_ambiguous_resource_fails_apply_without_writes(self):
        env = {key: value for key, value in FULL_ENV.items() if key != "WORKIQ_RESOURCE_APP_ID"}
        with patch.dict(os.environ, env, clear=True):
            graph = connector_graph()
            graph.principals.append({**graph.principal(WORKIQ_SP), "id": OTHER_SP, "appId": DECOY_ID})
            with self.assertRaises(RuntimeError):
                self.invoke(redirect, graph, ["--apply", "--redirect-uri", NEW_REDIRECT])
            self.assertEqual(graph.calls, [])

    def test_explicit_resource_lookup_allows_first_consent_callback(self):
        graph = connector_graph()
        graph.principals[:] = [sp for sp in graph.principals if sp["id"] != WORKIQ_SP]
        original = copy.deepcopy(graph.app(CONNECTOR_OBJECT)["requiredResourceAccess"])
        self.invoke(redirect, graph, ["--apply", "--redirect-uri", NEW_REDIRECT])
        self.assertEqual(len(graph.calls), 1)
        method, path, body = graph.calls[0]
        self.assertEqual((method, path), ("PATCH", f"/applications/{CONNECTOR_OBJECT}"))
        self.assertIn(NEW_REDIRECT, body["web"]["redirectUris"])
        self.assertEqual(graph.app(CONNECTOR_OBJECT)["requiredResourceAccess"], original)
        self.assertEqual([f for p, f, _ in graph.collections if p == "/servicePrincipals"],
                         [f"appId eq '{WORKIQ_ID}'"])

    def test_missing_resource_show_remains_read_only(self):
        graph = connector_graph()
        graph.principals[:] = [sp for sp in graph.principals if sp["id"] != WORKIQ_SP]
        self.assert_read_only(redirect, graph, ["--show", "--apply"])
        self.assertIn("not provisioned", self.stdout.getvalue())

    def test_apply_merges_explicit_web_redirects_preserving_settings_and_is_idempotent(self):
        graph = connector_graph()
        original = copy.deepcopy(graph.app(CONNECTOR_OBJECT))
        args = ["--apply", "--redirect-uri", NEW_REDIRECT, "--redirect-uri", NEW_REDIRECT, "--redirect-uri", OLD_REDIRECT]
        self.invoke(redirect, graph, args)
        expected = {**original["web"], "redirectUris": [OLD_REDIRECT, NEW_REDIRECT]}
        self.assertEqual(graph.calls, [("PATCH", f"/applications/{CONNECTOR_OBJECT}", {"web": expected})])
        self.assertEqual(graph.app(CONNECTOR_OBJECT)["requiredResourceAccess"], original["requiredResourceAccess"])
        graph.clear_records()
        self.invoke(redirect, graph, args)
        self.assertEqual(graph.calls, [])

    def test_apply_supports_missing_web_settings_without_implicit_redirects(self):
        graph = connector_graph()
        graph.app(CONNECTOR_OBJECT)["web"] = None
        self.invoke(redirect, graph, ["--apply", "--redirect-uri", NEW_REDIRECT])
        self.assertEqual(graph.calls, [("PATCH", f"/applications/{CONNECTOR_OBJECT}", {
            "web": {"redirectUris": [NEW_REDIRECT]},
        })])

    def test_redirect_patch_excludes_read_only_graph_web_properties(self):
        graph = connector_graph()
        web = graph.app(CONNECTOR_OBJECT)["web"]
        web["redirectUriSettings"] = [{"uri": OLD_REDIRECT, "index": 0}]
        web["@odata.type"] = "#microsoft.graph.webApplication"
        web["logoutUrl"] = "https://old.example.invalid/logout"
        expected = {
            "redirectUris": [OLD_REDIRECT, NEW_REDIRECT],
            "homePageUrl": web["homePageUrl"],
            "logoutUrl": web["logoutUrl"],
            "implicitGrantSettings": copy.deepcopy(web["implicitGrantSettings"]),
        }
        self.invoke(redirect, graph, ["--apply", "--redirect-uri", NEW_REDIRECT])
        self.assertEqual(graph.calls, [("PATCH", f"/applications/{CONNECTOR_OBJECT}", {"web": expected})])

    def test_missing_disabled_or_ambiguous_workiq_scope_fails_before_redirect_patch(self):
        for state in ("missing", "disabled", "ambiguous"):
            with self.subTest(state=state):
                graph = connector_graph()
                entries = graph.principal(WORKIQ_SP)["oauth2PermissionScopes"]
                if state == "missing":
                    entries.clear()
                elif state == "disabled":
                    entries[0]["isEnabled"] = False
                else:
                    entries.append({**entries[0], "id": OTHER_PERMISSION})
                with self.assertRaisesRegex(RuntimeError, "WorkIQAgent.Ask"):
                    self.invoke(redirect, graph, ["--apply", "--redirect-uri", NEW_REDIRECT])
                self.assertEqual(graph.calls, [])


class SeederTests(OfflineTest):
    def test_show_existing_non_public_app_is_read_only_with_or_without_principal(self):
        for with_sp in (False, True):
            for args in (
                ["--show"], ["--show", "--enable-device-code"],
                ["--show", "--enable-device-code", "--redirect-uri", NEW_REDIRECT],
            ):
                with self.subTest(with_sp=with_sp, args=args):
                    graph = seeder_graph(with_sp=with_sp)
                    self.assert_read_only(seeder, graph, args)
                    self.assertFalse(graph.app(SEEDER_OBJECT)["isFallbackPublicClient"])
                    self.assert_no_secret(graph)

    def test_show_missing_app_does_not_create_or_lookup_permissions(self):
        graph = seeder_graph(existing=False)
        self.assert_read_only(seeder, graph, ["--show", "--enable-device-code", "--redirect-uri", NEW_REDIRECT])
        self.assertEqual(graph.collections, [("/applications", "displayName eq 'Synthetic O''Brien Seeder'", None)])
        self.assertIn("NOT CREATED", self.stdout.getvalue())

    def test_exact_name_with_apostrophe_does_not_match_similar_apps(self):
        graph = seeder_graph()
        graph.apps.append({"id": DECOY_OBJECT, "appId": DECOY_ID, "displayName": APP_NAME + " copy"})
        self.invoke(seeder, graph, ["--show"])
        self.assertEqual(graph.collections[0], ("/applications", "displayName eq 'Synthetic O''Brien Seeder'", None))
        self.assertEqual(graph.calls, [])

    def test_duplicate_exact_names_fail_all_modes_before_writes(self):
        for args in ([], ["--no-secret"], ["--show"], ["--delete"], ["--enable-device-code"]):
            with self.subTest(args=args):
                graph = seeder_graph()
                graph.apps.append({**graph.apps[0], "id": DECOY_OBJECT, "appId": DECOY_ID})
                before = graph.snapshot()
                with self.assertRaisesRegex(RuntimeError, "Ambiguous"):
                    self.invoke(seeder, graph, args)
                self.assertEqual(graph.calls, [])
                self.assertEqual(graph.snapshot(), before)
                self.assertEqual(len(graph.collections), 1)

    def test_delete_removes_only_unique_exact_named_app_without_other_graph_queries(self):
        graph = seeder_graph()
        decoy = {"id": DECOY_OBJECT, "appId": DECOY_ID, "displayName": APP_NAME + " copy"}
        graph.apps.append(copy.deepcopy(decoy))
        principals = copy.deepcopy(graph.principals)
        self.invoke(seeder, graph, ["--delete"])
        self.assertEqual(graph.calls, [("DELETE", f"/applications/{SEEDER_OBJECT}", None)])
        self.assertEqual(graph.apps, [decoy])
        self.assertEqual(graph.principals, principals)
        self.assertEqual(len(graph.collections), 1)
        self.assert_no_secret(graph)
        self.sleep.assert_not_called()

    def test_delete_missing_exact_name_is_noop_even_if_similar_name_exists(self):
        graph = seeder_graph(existing=False)
        graph.apps.append({"id": DECOY_OBJECT, "appId": DECOY_ID, "displayName": APP_NAME + " copy"})
        self.assert_read_only(seeder, graph, ["--delete"])
        self.assertIn("Nothing to delete", self.stdout.getvalue())
        self.assertEqual(len(graph.collections), 1)

    def test_new_provisioning_no_secret_creates_only_requested_app_and_application_roles(self):
        graph = seeder_graph(existing=False)
        self.invoke(seeder, graph, ["--no-secret"])
        app = graph.app(SEEDER_OBJECT)
        self.assertEqual(app["displayName"], APP_NAME)
        self.assertEqual(app["signInAudience"], "AzureADMyOrg")
        self.assertNotIn("isFallbackPublicClient", app)
        self.assertNotIn("publicClient", app)
        self.assertNotIn("web", app)
        self.assertEqual(app["requiredResourceAccess"], [
            permission_block(GRAPH_ID, [{"id": ROLE_IDS[name], "type": "Role"} for name in SEEDER_ROLES]),
        ])
        self.assertEqual(graph.calls[0][0:2], ("POST", "/applications"))
        self.assertEqual(graph.calls[1], ("POST", "/servicePrincipals", {"appId": SEEDER_ID}))
        self.assertEqual(graph.assignments[SEEDER_SP], [
            {"principalId": SEEDER_SP, "resourceId": GRAPH_SP, "appRoleId": ROLE_IDS[name]}
            for name in SEEDER_ROLES
        ])
        self.assertEqual(graph.grants, [])
        self.assert_no_secret(graph)
        self.assertEqual([call.args for call in self.sleep.call_args_list], [(10,), (10,)])
        graph.clear_records()
        self.invoke(seeder, graph, ["--no-secret"])
        self.assertEqual(graph.calls, [])

    def test_new_default_provisioning_issues_password_after_roles_and_outputs_configured_tenant(self):
        graph = seeder_graph(existing=False)
        with patch.dict(os.environ, {"AZURE_TENANT_ID": OTHER_TENANT, "ARM_TENANT_ID": OTHER_TENANT}):
            output = self.invoke(seeder, graph)
        self.assertEqual(graph.calls[-1], (
            "POST", f"/applications/{SEEDER_OBJECT}/addPassword",
            {"passwordCredential": {"displayName": "seeder-1234567890"}},
        ))
        role_calls = [call for call in graph.calls if call[1].endswith("/appRoleAssignments")]
        self.assertEqual(len(role_calls), len(SEEDER_ROLES))
        self.assertIn(f'$env:WORKIQ_TENANT_ID     = "{TENANT}"', output)
        self.assertIn(f'$env:WORKIQ_CLIENT_ID     = "{SEEDER_ID}"', output)
        self.assertIn(f'$env:WORKIQ_CLIENT_SECRET = "{FAKE_SECRET}"', output)
        self.assertEqual(output.count(FAKE_SECRET), 1)
        self.assertNotIn(OTHER_TENANT, output)

    def test_existing_permissions_and_public_flags_are_preserved_without_device_opt_in(self):
        graph = seeder_graph()
        before = copy.deepcopy(graph.app(SEEDER_OBJECT))
        self.invoke(seeder, graph, ["--no-secret"])
        app = graph.app(SEEDER_OBJECT)
        self.assert_preserved(before["requiredResourceAccess"], app["requiredResourceAccess"])
        self.assertEqual(app["publicClient"], before["publicClient"])
        self.assertFalse(app["isFallbackPublicClient"])
        patches = [body for method, path, body in graph.calls if method == "PATCH" and path.startswith("/applications/")]
        self.assertEqual(len(patches), 1)
        self.assertEqual(set(patches[0]), {"requiredResourceAccess"})
        self.assertEqual(graph.grants, [])
        self.assert_no_secret(graph)
        self.sleep.assert_not_called()

    def test_existing_app_missing_principal_creates_principal_not_duplicate_application(self):
        graph = seeder_graph(with_sp=False)
        self.invoke(seeder, graph, ["--no-secret"])
        self.assertFalse(any(method == "POST" and path == "/applications" for method, path, _ in graph.calls))
        self.assertIn(("POST", "/servicePrincipals", {"appId": SEEDER_ID}), graph.calls)
        self.assertEqual(len(graph.apps), 1)
        self.sleep.assert_called_once_with(10)

    def test_device_code_opt_in_without_redirect_has_no_implicit_redirect(self):
        graph = seeder_graph(existing=False)
        self.invoke(seeder, graph, ["--enable-device-code", "--no-secret"])
        app = graph.app(SEEDER_OBJECT)
        self.assertTrue(app["isFallbackPublicClient"])
        self.assertNotIn("publicClient", app)
        self.assertNotIn("web", app)
        accesses = app["requiredResourceAccess"][0]["resourceAccess"]
        self.assertEqual(
            accesses,
            [{"id": ROLE_IDS[name], "type": "Role"} for name in SEEDER_ROLES]
            + [{"id": SCOPE_IDS[name], "type": "Scope"} for name in DEVICE_SCOPES],
        )
        self.assertEqual(graph.grants, [{
            "id": NEW_GRANT_ID, "clientId": SEEDER_SP, "resourceId": GRAPH_SP,
            "consentType": "AllPrincipals", "scope": " ".join(DEVICE_SCOPES),
        }])
        self.assert_no_secret(graph)
        graph.clear_records()
        self.invoke(seeder, graph, ["--enable-device-code", "--no-secret"])
        self.assertEqual(graph.calls, [])

    def test_explicit_public_redirect_merges_existing_settings_and_is_idempotent(self):
        graph = seeder_graph()
        original = copy.deepcopy(graph.app(SEEDER_OBJECT))
        args = ["--enable-device-code", "--no-secret", "--redirect-uri", NEW_REDIRECT, "--redirect-uri", NEW_REDIRECT]
        self.invoke(seeder, graph, args)
        app = graph.app(SEEDER_OBJECT)
        self.assertEqual(app["publicClient"], {
            **original["publicClient"], "redirectUris": [OLD_REDIRECT, NEW_REDIRECT],
        })
        self.assertTrue(app["isFallbackPublicClient"])
        self.assert_preserved(original["requiredResourceAccess"], app["requiredResourceAccess"])
        self.assert_no_secret(graph)
        graph.clear_records()
        self.invoke(seeder, graph, args)
        self.assertEqual(graph.calls, [])

    def test_new_explicit_redirect_is_only_redirect_and_no_web_settings_are_added(self):
        graph = seeder_graph(existing=False)
        self.invoke(seeder, graph, [
            "--no-secret", "--enable-device-code", "--redirect-uri", NEW_REDIRECT,
        ])
        app = graph.app(SEEDER_OBJECT)
        self.assertEqual(app["publicClient"], {"redirectUris": [NEW_REDIRECT]})
        self.assertNotIn("web", app)

    def test_device_code_without_new_redirect_preserves_existing_public_redirects(self):
        graph = seeder_graph()
        before = copy.deepcopy(graph.app(SEEDER_OBJECT)["publicClient"])
        self.invoke(seeder, graph, ["--no-secret", "--enable-device-code"])
        self.assertEqual(graph.app(SEEDER_OBJECT)["publicClient"], before)
        for method, path, body in graph.calls:
            if method == "PATCH" and path.startswith("/applications/"):
                self.assertNotIn("publicClient", body)

    def test_every_role_is_prevalidated_before_new_create_or_existing_patch(self):
        for existing in (False, True):
            for name in SEEDER_ROLES:
                for state in ("missing", "disabled", "user-only"):
                    with self.subTest(existing=existing, name=name, state=state):
                        graph = seeder_graph(existing=existing)
                        entries = graph.principal(GRAPH_SP)["appRoles"]
                        if state == "missing":
                            entries[:] = [entry for entry in entries if entry["value"] != name]
                        else:
                            entry = next(entry for entry in entries if entry["value"] == name)
                            if state == "disabled":
                                entry["isEnabled"] = False
                            else:
                                entry["allowedMemberTypes"] = ["User"]
                        before = graph.snapshot()
                        with self.assertRaisesRegex(RuntimeError, re.escape(name)):
                            self.invoke(seeder, graph, ["--enable-device-code"])
                        self.assertEqual(graph.calls, [])
                        self.assertEqual(graph.snapshot(), before)
                        self.assert_no_secret(graph)
        self.sleep.assert_not_called()

    def test_every_requested_delegated_scope_is_prevalidated_before_any_writes(self):
        for existing in (False, True):
            for name in DEVICE_SCOPES:
                for disabled in (False, True):
                    with self.subTest(existing=existing, name=name, disabled=disabled):
                        graph = seeder_graph(existing=existing)
                        entries = graph.principal(GRAPH_SP)["oauth2PermissionScopes"]
                        if disabled:
                            next(entry for entry in entries if entry["value"] == name)["isEnabled"] = False
                        else:
                            entries[:] = [entry for entry in entries if entry["value"] != name]
                        before = graph.snapshot()
                        with self.assertRaisesRegex(RuntimeError, re.escape(name)):
                            self.invoke(seeder, graph, ["--enable-device-code", "--redirect-uri", NEW_REDIRECT])
                        self.assertEqual(graph.calls, [])
                        self.assertEqual(graph.snapshot(), before)
                        self.assert_no_secret(graph)
        self.sleep.assert_not_called()

    def test_unrequested_delegated_scopes_are_not_required_for_app_only_provisioning(self):
        graph = seeder_graph(existing=False)
        graph.principal(GRAPH_SP)["oauth2PermissionScopes"] = []
        self.invoke(seeder, graph, ["--no-secret"])
        self.assertEqual(len(graph.assignments[SEEDER_SP]), len(SEEDER_ROLES))
        self.assertEqual(graph.grants, [])

    def test_seeder_merges_only_target_all_principals_grant_and_preserves_other_scopes(self):
        graph = seeder_graph()
        graph.grants = [
            consent(SEEDER_SP, GRAPH_SP, scope="Existing.Access User.Read"),
            consent(SEEDER_SP, WORKIQ_SP, id=OTHER_GRANT_ID),
            consent(SEEDER_SP, GRAPH_SP, id=USER_GRANT_ID, per_user=True),
        ]
        untouched = copy.deepcopy(graph.grants[1:])
        self.invoke(seeder, graph, ["--no-secret", "--enable-device-code"])
        self.assertEqual(set(graph.grants[0]["scope"].split()), {"Existing.Access", "User.Read", *DEVICE_SCOPES})
        self.assertEqual(graph.grants[1:], untouched)
        grant_calls = [(method, path) for method, path, _ in graph.calls if path.startswith("/oauth2PermissionGrants")]
        self.assertEqual(grant_calls, [("PATCH", f"/oauth2PermissionGrants/{GRANT_ID}")])
        self.assertIn((
            "/oauth2PermissionGrants",
            f"clientId eq '{SEEDER_SP}'",
            None,
        ), graph.collections)

    def test_seeder_does_not_patch_per_user_grant_when_creating_tenant_grant(self):
        graph = seeder_graph()
        before = consent(SEEDER_SP, GRAPH_SP, id=USER_GRANT_ID, per_user=True)
        graph.grants = [copy.deepcopy(before)]
        self.invoke(seeder, graph, ["--no-secret", "--enable-device-code"])
        self.assertEqual(graph.grants[0], before)
        self.assertEqual(graph.grants[1]["consentType"], "AllPrincipals")
        self.assertEqual(graph.grants[1]["resourceId"], GRAPH_SP)

    def test_ambiguous_grants_abort_before_public_flags_permissions_assignments_or_password(self):
        graph = seeder_graph()
        graph.grants = [consent(SEEDER_SP, GRAPH_SP), consent(SEEDER_SP, GRAPH_SP, id=OTHER_GRANT_ID)]
        before = graph.snapshot()
        with self.assertRaisesRegex(RuntimeError, "Ambiguous"):
            self.invoke(seeder, graph, ["--enable-device-code", "--redirect-uri", NEW_REDIRECT])
        self.assertEqual(graph.calls, [])
        self.assertEqual(graph.snapshot(), before)
        self.assert_no_secret(graph)

    def test_unexpected_per_user_grant_response_aborts_before_any_write(self):
        graph = seeder_graph()
        with patch.object(seeder, "find_tenant_grant", return_value=consent(SEEDER_SP, GRAPH_SP, per_user=True)):
            with self.assertRaisesRegex(RuntimeError, "AllPrincipals"):
                self.invoke(seeder, graph, ["--enable-device-code"])
        self.assertEqual(graph.calls, [])

    def test_existing_role_assignments_are_deduplicated_only_within_target_resource(self):
        graph = seeder_graph()
        first, second = [ROLE_IDS[name] for name in SEEDER_ROLES[:2]]
        originals = [
            {"principalId": SEEDER_SP, "resourceId": GRAPH_SP, "appRoleId": first},
            {"principalId": SEEDER_SP, "resourceId": OTHER_SP, "appRoleId": second},
        ]
        graph.assignments[SEEDER_SP] = copy.deepcopy(originals)
        self.invoke(seeder, graph, ["--no-secret"])
        assignments = [body for _, path, body in graph.calls if path.endswith("/appRoleAssignments")]
        self.assertEqual(len(assignments), len(SEEDER_ROLES) - 1)
        self.assertNotIn(first, [body["appRoleId"] for body in assignments])
        self.assertIn(second, [body["appRoleId"] for body in assignments])
        self.assertTrue(all(body["resourceId"] == GRAPH_SP for body in assignments))
        self.assertEqual(graph.assignments[SEEDER_SP][:2], originals)
        graph.clear_records()
        self.invoke(seeder, graph, ["--no-secret"])
        self.assertEqual(graph.calls, [])

    def test_assignment_enumeration_error_aborts_before_any_write_or_password(self):
        graph = seeder_graph()
        graph.fail_on = ("collection", f"/servicePrincipals/{SEEDER_SP}/appRoleAssignments")
        with self.assertRaisesRegex(RuntimeError, "Synthetic collection failure"):
            self.invoke(seeder, graph)
        self.assertEqual(graph.calls, [])
        self.assert_no_secret(graph)

    def test_assignment_write_error_stops_before_password_issuance(self):
        for existing in (False, True):
            with self.subTest(existing=existing):
                graph = seeder_graph(existing=existing)
                graph.fail_on = ("POST", f"/servicePrincipals/{SEEDER_SP}/appRoleAssignments")
                with self.assertRaisesRegex(RuntimeError, "Synthetic write failure"):
                    self.invoke(seeder, graph)
                self.assertEqual(graph.calls[-1][1], f"/servicePrincipals/{SEEDER_SP}/appRoleAssignments")
                self.assertEqual(len([call for call in graph.calls if call[1].endswith("/appRoleAssignments")]), 1)
                self.assert_no_secret(graph)

    def test_consent_write_error_stops_before_password_issuance(self):
        graph = seeder_graph()
        graph.fail_on = ("POST", "/oauth2PermissionGrants")
        with self.assertRaisesRegex(RuntimeError, "Synthetic write failure"):
            self.invoke(seeder, graph, ["--enable-device-code"])
        self.assert_no_secret(graph)
        self.assertEqual(graph.calls[-1][1], "/oauth2PermissionGrants")

    def test_application_or_principal_write_error_stops_before_assignments_and_password(self):
        for path in ("/applications", "/servicePrincipals"):
            with self.subTest(path=path):
                graph = seeder_graph(existing=False)
                graph.fail_on = ("POST", path)
                with self.assertRaisesRegex(RuntimeError, "Synthetic write failure"):
                    self.invoke(seeder, graph)
                self.assertEqual(graph.calls[-1][1], path)
                self.assertFalse(any(p.endswith("/appRoleAssignments") for _, p, _ in graph.calls))
                self.assert_no_secret(graph)

    def test_missing_or_duplicate_graph_resource_fails_before_any_write(self):
        for duplicate in (False, True):
            with self.subTest(duplicate=duplicate):
                graph = seeder_graph(existing=False)
                if duplicate:
                    graph.principals.append({**graph.principal(GRAPH_SP), "id": OTHER_SP})
                else:
                    graph.principals[:] = [sp for sp in graph.principals if sp["id"] != GRAPH_SP]
                with self.assertRaises(RuntimeError):
                    self.invoke(seeder, graph)
                self.assertEqual(graph.calls, [])

    def test_duplicate_client_principals_fail_before_any_write(self):
        graph = seeder_graph()
        graph.principals.append({"id": OTHER_SP, "appId": SEEDER_ID})
        with self.assertRaisesRegex(RuntimeError, "Ambiguous"):
            self.invoke(seeder, graph)
        self.assertEqual(graph.calls, [])


if __name__ == "__main__":
    unittest.main()
