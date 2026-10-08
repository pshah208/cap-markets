"""Offline seeder tests. All credentials, HTTP requests and writes are mocked."""

import builtins
import copy
import importlib
import io
import json
import os
import sys
import types
import unittest
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock, patch

import seed_work_iq as seed
import seed_mission_mail as mission
import workiq_config as config

HERE = Path(__file__).parent
TENANT = "11111111-1111-4111-8111-111111111111"
CLIENT = "22222222-2222-4222-8222-222222222222"
EXAMPLE = json.loads((HERE / "user_mapping.example.json").read_text(encoding="utf-8"))
ENV = {
    "WORKIQ_TENANT_ID": TENANT,
    "WORKIQ_CLIENT_ID": CLIENT,
    "WORKIQ_CLIENT_SECRET": "fake-test-secret",
    "WORKIQ_USER_MAPPING_FILE": str(HERE / "user_mapping.example.json"),
}


class SeederTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.dict(os.environ, ENV, clear=True))
        self.stack.enter_context(redirect_stdout(io.StringIO()))
        self.stack.enter_context(redirect_stderr(io.StringIO()))
        self.stack.enter_context(patch("socket.socket", side_effect=AssertionError("network forbidden")))
        self.stack.enter_context(patch("subprocess.run", side_effect=AssertionError("process forbidden")))
        self.writes = self.stack.enter_context(patch.object(
            Path, "write_text", side_effect=AssertionError("disk writes forbidden"),
        ))
        self.identity = types.ModuleType("azure.identity")
        for name in ("ClientSecretCredential", "AzureCliCredential", "DeviceCodeCredential",
                     "TokenCachePersistenceOptions"):
            setattr(self.identity, name, Mock(name=name))
        self.http = types.ModuleType("requests")
        self.http.request = Mock(name="request")
        self.stack.enter_context(patch.dict(sys.modules, {
            "azure": types.ModuleType("azure"), "azure.identity": self.identity, "requests": self.http,
        }))

    def load(self, actions=("mail",), **kwargs):
        return config.load_config("app", actions=actions, source_dir=HERE, **kwargs)

    def graph(self, actions=("mail",)):
        return seed.Graph("app", config=self.load(actions))

    def fixture(self, document):
        original = config.read_object

        def read(path, setting):
            if setting == "WORKIQ_USER_MAPPING_FILE":
                return copy.deepcopy(document)
            return original(path, setting)
        return patch.object(config, "read_object", side_effect=read)

    def no_credentials(self):
        for name in ("ClientSecretCredential", "AzureCliCredential", "DeviceCodeCredential"):
            getattr(self.identity, name).assert_not_called()
        self.http.request.assert_not_called()
        self.writes.assert_not_called()

    def test_import_has_no_configuration_reads_optional_imports_or_side_effects(self):
        original_import = builtins.__import__

        def checked(name, *args, **kwargs):
            if name == "requests" or name.startswith("azure"):
                raise AssertionError(f"Optional import on module load: {name}")
            return original_import(name, *args, **kwargs)
        with patch.dict(os.environ, {}, clear=True), patch.object(
            Path, "read_text", side_effect=AssertionError("mapping read on import"),
        ), patch("builtins.__import__", side_effect=checked):
            for module in (config, seed, mission):
                importlib.reload(module)
        self.no_credentials()

    def test_mission_import_does_not_monkeypatch_hero_loader(self):
        original = seed.load
        importlib.reload(mission)
        self.assertIs(seed.load, original)

    def test_missing_env_fails_before_reading_config_or_optional_imports(self):
        original_import = builtins.__import__

        def checked(name, *args, **kwargs):
            if name.startswith("azure") or name == "requests":
                raise AssertionError("optional import before validation")
            return original_import(name, *args, **kwargs)
        for name in ENV:
            with self.subTest(name=name), patch.dict(os.environ, {**ENV, name: ""}, clear=True):
                with patch.object(Path, "read_text") as read, patch("builtins.__import__", side_effect=checked):
                    with self.assertRaisesRegex(config.ConfigurationError, name):
                        seed.Graph("app")
                    read.assert_not_called()
        self.no_credentials()

    def test_missing_configuration_for_every_seeder_action(self):
        cases = [
            (seed, []), (seed, ["--all", "--dry-run"]),
            (seed, ["--auth", "cli", "--check-users"]),
            (seed, ["--auth", "device", "--only", "teams"]),
            (seed, ["--map-users"]), (seed, ["--restore-users"]),
            (seed, ["--only", "mail", "--purge"]), (seed, ["--only", "files"]),
            (seed, ["--only", "teams", "--migrate", "--recreate"]),
            (mission, []), (mission, ["--purge", "--dry-run"]),
        ]
        for module, args in cases:
            with self.subTest(module=module.__name__, args=args), patch.dict(os.environ, {}, clear=True):
                with patch.object(sys, "argv", [module.__name__, *args]), patch.object(seed, "Graph") as graph:
                    with self.assertRaises(SystemExit) as exc:
                        module.main()
                    self.assertEqual(exc.exception.code, 2)
                    graph.assert_not_called()
        self.no_credentials()

    def test_whitespace_and_invalid_tenant_or_client_fail(self):
        for name in ("WORKIQ_TENANT_ID", "WORKIQ_CLIENT_ID"):
            for value in ("  ", "not-a-guid"):
                with self.subTest(name=name, value=value), patch.dict(os.environ, {name: value}):
                    with self.assertRaisesRegex(config.ConfigurationError, name):
                        seed.Graph("app")
        self.no_credentials()

    def test_missing_mapping_path_has_useful_error(self):
        with patch.dict(os.environ, {"WORKIQ_USER_MAPPING_FILE": str(HERE / "absent-test.local.json")}):
            with self.assertRaisesRegex(config.ConfigurationError, "WORKIQ_USER_MAPPING_FILE"):
                seed.Graph("app")
        self.no_credentials()

    def test_invalid_mapping_json_fails_before_authentication(self):
        with patch.object(Path, "read_text", return_value="invalid JSON"):
            with self.assertRaisesRegex(config.ConfigurationError, "readable JSON object"):
                seed.Graph("app")
        self.no_credentials()

    def test_partial_mapping_never_falls_back_to_domain(self):
        data = copy.deepcopy(EXAMPLE)
        del data["mapping"]["vance.deleon"]
        with self.fixture(data), patch.dict(os.environ, {"WORKIQ_TENANT_DOMAIN": "example.com"}):
            with self.assertRaisesRegex(config.ConfigurationError, "vance.deleon"):
                seed.Graph("app")
        self.no_credentials()

    def test_driver_must_be_explicit_and_mapped(self):
        for value in (None, "", "missing-alias", []):
            data = {**EXAMPLE, "driver_alias": value}
            with self.subTest(value=value), self.fixture(data):
                with self.assertRaisesRegex(config.ConfigurationError, "driver_alias"):
                    seed.Graph("app")
        self.no_credentials()

    def test_tenant_conflict_fails_without_credentials(self):
        with self.fixture({**EXAMPLE, "tenant_id": CLIENT}):
            with self.assertRaisesRegex(config.ConfigurationError, "conflicts"):
                seed.Graph("app")
        self.no_credentials()

    def test_invalid_upn_fails_before_credentials(self):
        for value in ("", "user", "user@example.com/drive", "user @example.com"):
            data = copy.deepcopy(EXAMPLE)
            data["mapping"]["admin"]["upn"] = value
            with self.subTest(value=value), self.fixture(data):
                with self.assertRaisesRegex(config.ConfigurationError, "valid upn"):
                    seed.Graph("app")
        self.no_credentials()

    def test_all_fixture_aliases_have_fake_example_mappings(self):
        self.load(("mail", "teams", "files"))
        self.load(mail_source="mission_emails.json")
        self.assertTrue(all(entry["upn"].endswith("@example.com") for entry in EXAMPLE["mapping"].values()))

    def test_unknown_onedrive_alias_fails_before_credentials(self):
        with self.assertRaisesRegex(config.ConfigurationError, "unknown"):
            self.load(("files",), onedrive_alias="unknown")
        self.no_credentials()

    def test_map_restore_require_explicit_snapshot_path(self):
        for action in ("map", "restore"):
            with self.subTest(action=action), self.assertRaisesRegex(config.ConfigurationError, "WORKIQ_RESTORE_FILE"):
                self.load((action,))
        self.no_credentials()

    def test_missing_restore_file_fails_before_credentials(self):
        with patch.dict(os.environ, {"WORKIQ_RESTORE_FILE": str(HERE / "absent-test.restore.json")}):
            with self.assertRaisesRegex(config.ConfigurationError, "WORKIQ_RESTORE_FILE"):
                self.load(("restore",))
        self.no_credentials()

    def test_invalid_restore_payload_fails_before_credentials(self):
        original = config.read_object
        invalid = (
            {},
            {"outside@example.com": {"displayName": "Original", "jobTitle": None, "department": None}},
            {"demo-operator@example.com": {"displayName": "Original", "passwordProfile": {}}},
            {"demo-operator@example.com": {"displayName": [], "jobTitle": None, "department": None}},
        )
        for snapshot in invalid:
            with self.subTest(snapshot=snapshot), patch.dict(
                os.environ, {"WORKIQ_RESTORE_FILE": str(HERE / "absent-test.restore.json")},
            ):
                with patch.object(config, "read_object", side_effect=lambda path, setting:
                                  snapshot if setting == "WORKIQ_RESTORE_FILE" else original(path, setting)):
                    with self.assertRaisesRegex(config.ConfigurationError, "WORKIQ_RESTORE_FILE"):
                        self.load(("restore",))
        self.no_credentials()

    def test_map_validates_all_rename_fields(self):
        data = copy.deepcopy(EXAMPLE)
        del data["mapping"]["vance.deleon"]["jobTitle"]
        with self.fixture(data), patch.dict(os.environ, {"WORKIQ_RESTORE_FILE": str(HERE / "absent-test.restore.json")}):
            with self.assertRaisesRegex(config.ConfigurationError, "jobTitle"):
                self.load(("map",))
        self.no_credentials()

    def test_map_rejects_duplicate_accounts(self):
        data = copy.deepcopy(EXAMPLE)
        data["mapping"]["admin"]["upn"] = data["mapping"]["vance.deleon"]["upn"]
        with self.fixture(data), patch.dict(os.environ, {"WORKIQ_RESTORE_FILE": str(HERE / "absent-test.restore.json")}):
            with self.assertRaisesRegex(config.ConfigurationError, "different account"):
                self.load(("map",))
        self.no_credentials()

    def test_cli_and_device_credentials_are_explicitly_tenant_bound(self):
        for mode in ("cli", "device"):
            with self.subTest(mode=mode):
                loaded = config.load_config(mode, actions=("check",), source_dir=HERE)
                seed.Graph(mode, config=loaded)
                factory = getattr(self.identity, "AzureCliCredential" if mode == "cli" else "DeviceCodeCredential")
                self.assertEqual(factory.call_args.kwargs["tenant_id"], TENANT)
                if mode == "device":
                    self.assertEqual(factory.call_args.kwargs["client_id"], CLIENT)
        self.http.request.assert_not_called()

    def test_provisioner_grants_exactly_the_seeders_delegated_scopes(self):
        import provision_seeder_app

        loaded = config.load_config("device", actions=("teams",), source_dir=HERE)
        graph = seed.Graph("device", config=loaded)
        scopes = {scope.removeprefix("https://graph.microsoft.com/") for scope in graph._scopes}
        self.assertEqual(scopes, set(provision_seeder_app.DEVICE_SCOPES))

    def test_injected_configuration_cannot_change_auth_modes_silently(self):
        loaded = config.load_config("cli", actions=("check",), source_dir=HERE)
        with self.assertRaisesRegex(config.ConfigurationError, "WORKIQ_CLIENT_ID"):
            seed.Graph("app", config=loaded)
        self.no_credentials()

    def test_app_credentials_receive_only_explicit_settings(self):
        self.graph()
        self.identity.ClientSecretCredential.assert_called_once_with(TENANT, CLIENT, "fake-test-secret")
        self.http.request.assert_not_called()

    def test_graph_operational_request_body_token_and_timeout(self):
        g = self.graph()
        g._cred.get_token.return_value = types.SimpleNamespace(token="fake-token", expires_on=9999999999)
        self.http.request.return_value = types.SimpleNamespace(status_code=201, content=b"x", json=lambda: {"id": "new"})
        self.assertEqual(g.call("POST", "/users/demo@example.com/messages", json_body={"subject": "test"}), {"id": "new"})
        self.http.request.assert_called_once_with(
            "POST", seed.GRAPH + "/users/demo@example.com/messages",
            headers={"Authorization": "Bearer fake-token", "Content-Type": "application/json"},
            json={"subject": "test"}, data=None, timeout=60, allow_redirects=False,
        )
        g._cred.get_token.assert_called_once_with("https://graph.microsoft.com/.default")

    def test_graph_upload_preserves_bytes_and_content_type(self):
        g = self.graph()
        g._cred.get_token.return_value = types.SimpleNamespace(token="fake", expires_on=9999999999)
        self.http.request.return_value = types.SimpleNamespace(status_code=201, content=b"", headers={})
        seed.upload(g, "/drives/id", "folder/file.txt", b"document")
        args = self.http.request.call_args
        self.assertEqual(args.args, ("PUT", seed.GRAPH + "/drives/id/root:/folder/file.txt:/content"))
        self.assertEqual(args.kwargs["data"], b"document")
        self.assertIsNone(args.kwargs["json"])
        self.assertEqual(args.kwargs["headers"]["Content-Type"], "text/plain")

    def test_graph_rejects_external_pagination_before_token(self):
        g = self.graph()
        with self.assertRaises(ValueError):
            g.call("GET", "https://example.com/v1.0/users")
        g._cred.get_token.assert_not_called()
        self.http.request.assert_not_called()

    def test_graph_refuses_redirect_and_handles_optional_404(self):
        g = self.graph()
        g._cred.get_token.return_value = types.SimpleNamespace(token="fake", expires_on=9999999999)
        self.http.request.return_value = types.SimpleNamespace(status_code=302)
        with self.assertRaisesRegex(RuntimeError, "redirects"):
            g.call("GET", "/users")
        self.http.request.return_value = types.SimpleNamespace(status_code=404)
        self.assertIsNone(g.call("GET", "/users", ok_404=True))

    def test_graph_retry_and_dry_run(self):
        g = self.graph()
        g._cred.get_token.return_value = types.SimpleNamespace(token="fake", expires_on=9999999999)
        self.http.request.side_effect = [
            types.SimpleNamespace(status_code=429, headers={"Retry-After": "3"}),
            types.SimpleNamespace(status_code=200, content=b"x", json=lambda: {"value": []}),
        ]
        with patch.object(seed.time, "sleep") as sleep:
            self.assertEqual(g.call("GET", "/users"), {"value": []})
            sleep.assert_called_once_with(3)
        self.http.request.reset_mock()
        g._cred.get_token.reset_mock()
        g.dry_run = True
        g.call("POST", "/users", json_body={})
        self.http.request.assert_not_called()
        g._cred.get_token.assert_not_called()

    def test_hero_mail_filters_other_clients_and_keeps_original_timestamps(self):
        g = Mock(config=self.load(), dry_run=False)
        seed.seed_mail(g)
        corpus = seed.load("emails.json")
        hero = [e for e in corpus["emails"] if e.get("client_id", seed.HERO_CLIENT_ID) == seed.HERO_CLIENT_ID]
        sent = [call for call in g.call.call_args_list if "/sentitems/" in call.args[1]]
        self.assertEqual(len(sent), len(hero))
        for call, email in zip(sent, hero):
            payload = call.kwargs["json_body"]
            self.assertEqual(payload["subject"], email["subject"])
            self.assertEqual(payload["sentDateTime"], email["sentDateTime"])
            self.assertEqual(payload["singleValueExtendedProperties"][1]["value"], email["sentDateTime"])
            self.assertTrue(payload["from"]["emailAddress"]["address"].endswith("@example.com"))

    def test_mission_mail_imports_every_client_without_rewriting_source(self):
        before = seed.load("mission_emails.json")
        loaded = self.load(mail_source="mission_emails.json")
        g = Mock(config=loaded, dry_run=False)
        seed.seed_mail(g, source="mission_emails.json", all_clients=True)
        sent = [call for call in g.call.call_args_list if "/sentitems/" in call.args[1]]
        self.assertEqual(len(sent), len(before["emails"]))
        self.assertEqual(seed.load("mission_emails.json"), before)
        addresses = {
            recipient["emailAddress"]["address"] for call in sent
            for recipient in call.kwargs["json_body"]["ccRecipients"]
        }
        self.assertIn("demo-operator@example.com", addresses)

    def test_external_explicit_driver_is_added_to_mail_and_purge(self):
        data = copy.deepcopy(EXAMPLE)
        data["driver_alias"] = "operator"
        data["mapping"]["operator"] = {"upn": "operator@example.com", "displayName": "Demo operator"}
        with self.fixture(data):
            loaded = self.load()
        g = Mock(config=loaded, dry_run=False)
        seed.seed_mail(g)
        posts = g.call.call_args_list
        self.assertTrue(any("/users/operator@example.com/mailFolders/inbox" in call.args[1] for call in posts))
        g.call.reset_mock()
        g.call.return_value = {"value": []}
        seed.purge_mail(g, seed.load("emails.json"))
        self.assertTrue(any("/users/operator@example.com/" in call.args[1] for call in g.call.call_args_list))

    def test_mission_main_preserves_wrapper_contract(self):
        with patch.object(sys, "argv", ["seed_mission_mail.py", "--purge", "--dry-run"]):
            with patch.object(seed, "Graph") as graph, patch.object(seed, "seed_mail") as send:
                mission.main()
                self.assertTrue(graph.call_args.kwargs["dry_run"])
                self.assertIn("admin", graph.call_args.kwargs["config"].accounts)
                send.assert_called_once_with(
                    graph.return_value, purge=True, source="mission_emails.json", all_clients=True,
                )

    def test_files_main_has_no_default_onedrive_author(self):
        with patch.object(sys, "argv", ["seed_work_iq.py", "--only", "files"]):
            with patch.object(seed, "Graph") as graph, patch.object(seed, "seed_files") as files:
                seed.main()
                files.assert_called_once_with(graph.return_value, None)

    def test_map_snapshots_before_mutation_and_preserves_originals(self):
        loaded = self.load()
        accounts = {"admin": loaded.accounts["admin"]}
        original = {"displayName": "Original", "jobTitle": None, "department": "Original department"}
        loaded = replace(loaded, accounts=accounts, restore_file=HERE / "unused-test.restore.json", snapshot={})
        events = []

        def call(method, path, **kwargs):
            events.append(method)
            return original if method == "GET" else None
        g = Mock(config=loaded, dry_run=False)
        g.call.side_effect = call
        with patch.object(Path, "write_text", side_effect=lambda *a, **k: events.append("snapshot")) as write:
            seed.map_users(g)
            self.assertEqual(events, ["GET", "snapshot", "PATCH"])
            self.assertEqual(json.loads(write.call_args.args[0]), {"demo-operator@example.com": original})
        loaded = replace(loaded, snapshot={"demo-operator@example.com": original})
        g.config = loaded
        g.call.side_effect = lambda *a, **k: {"displayName": "Already renamed"}
        with patch.object(Path, "write_text") as write:
            seed.map_users(g)
            self.assertEqual(json.loads(write.call_args.args[0]), loaded.snapshot)

    def test_snapshot_write_failure_prevents_directory_patch(self):
        loaded = self.load()
        loaded = replace(loaded, restore_file=HERE / "unused-test.restore.json")
        g = Mock(config=loaded, dry_run=False)
        g.call.return_value = {"displayName": "Original", "jobTitle": None, "department": None}
        with patch.object(Path, "write_text", side_effect=OSError("read-only")):
            with self.assertRaises(OSError):
                seed.map_users(g)
        self.assertTrue(all(call.args[0] == "GET" for call in g.call.call_args_list))

    def test_restore_requests_only_saved_properties(self):
        loaded = self.load()
        original = {"displayName": "Original", "jobTitle": None, "department": "Original department"}
        loaded = replace(loaded, restore_file=HERE / "unused-test.restore.json",
                         snapshot={"demo-operator@example.com": original})
        g = Mock(config=loaded, dry_run=False)
        seed.restore_users(g)
        g.call.assert_called_once_with("PATCH", "/users/demo-operator@example.com", json_body=original)

    def test_post_and_reply_preserve_authorship_and_thread_routing(self):
        g = Mock(mode="device")
        g.call.return_value = {"id": "message"}
        people = {"author": {"displayName": "Example Author", "title": "Coverage"}}
        with patch.object(seed.time, "sleep"):
            seed.post_message(g, "team", "channel", "author", people, text="content",
                              subject="subject", reply_to="root")
        call = g.call.call_args
        self.assertEqual(call.args, ("POST", "/teams/team/channels/channel/messages/root/replies"))
        self.assertNotIn("subject", call.kwargs["json_body"])
        self.assertIn("Example Author", call.kwargs["json_body"]["body"]["content"])

    def mock_teams(self, *, migration=False):
        owner, member = "sydney.mattos", "sasha.ouellet"
        people = [
            {"alias": alias, "displayName": alias, "title": "Coverage"}
            for alias in (owner, member)
        ]
        data = {
            "team": {
                "displayName": "Offline team", "description": "Offline test",
                "visibility": "private", "ownerAliases": [owner], "memberAliases": [member],
            },
            "channels": [{
                "displayName": "General", "description": "Offline channel",
                "conversations": [{
                    "id": "thread", "from": owner, "subject": "Test", "message": "Root",
                    "createdDateTime": "2020-01-01T12:00:00Z",
                    "replies": [{
                        "from": member, "message": "Reply",
                        "createdDateTime": "2020-01-01T12:01:00Z",
                    }],
                }],
            }],
        }
        g = Mock(config=self.load(("teams",)), mode="app", dry_run=False)
        self.stack.enter_context(patch.object(seed, "load", side_effect=lambda name: {
            "teams_messages.json": data, "emails.json": {"people": people},
        }[name]))
        self.stack.enter_context(patch.object(seed.time, "sleep"))
        created = not migration

        def call(method, path, **kwargs):
            nonlocal created
            if method == "GET":
                if path.startswith("/groups?"):
                    return {"value": [{"id": "team"}] if created else []}
                if path == "/teams/team/members":
                    return {"value": [{"userId": "owner"}]}
                if path == "/teams/team/channels":
                    return {"value": [{"displayName": "General", "id": "channel"}]}
                for alias, uid in ((owner, "owner"), (member, "member"), ("admin", "driver")):
                    if path.startswith(f"/users/{g.config.upn(alias)}?"):
                        return {"id": uid}
            elif method == "POST":
                if path == "/teams":
                    created = True
                    return None
                if path.endswith("/completeMigration") or path == "/teams/team/members":
                    return None
                if path == "/teams/team/channels/channel/messages":
                    return {"id": "root"}
                if path == "/teams/team/channels/channel/messages/root/replies":
                    return {"id": "reply"}
            raise AssertionError(f"Unexpected Graph request: {method} {path}")

        g.call.side_effect = call
        return g, data

    def test_teams_required_failures_propagate_without_main_success(self):
        for migration in (False, True):
            for operation in ("group read", "membership read", "user read", "channels read",
                              "membership write", "root", "reply"):
                for through_main in (False, True):
                    if migration and operation == "membership read":
                        continue
                    with self.subTest(migration=migration, operation=operation, main=through_main):
                        g, _ = self.mock_teams(migration=migration)
                        original = g.call.side_effect
                        method, path = {
                            "group read": ("GET", "/groups?$filter=displayName eq 'Offline team'"
                                          "&$select=id,displayName"),
                            "membership read": ("GET", "/teams/team/members"),
                            "user read": ("GET", f"/users/{g.config.upn('sasha.ouellet')}?$select=id"
                                          + (",displayName" if migration else "")),
                            "channels read": ("GET", "/teams/team/channels"),
                            "membership write": ("POST", "/teams/team/members"),
                            "root": ("POST", "/teams/team/channels/channel/messages"),
                            "reply": ("POST", "/teams/team/channels/channel/messages/root/replies"),
                        }[operation]
                        error = RuntimeError(f"{method} {seed.GRAPH}{path} -> 400: invalid request")

                        def fail(method_arg, path_arg, **kwargs):
                            if (method_arg, path_arg) == (method, path):
                                raise error
                            return original(method_arg, path_arg, **kwargs)

                        g.call.side_effect = fail
                        args = ["seed_work_iq.py", "--only", "teams"]
                        if migration:
                            args.append("--migrate")
                        output = io.StringIO()
                        with redirect_stdout(output), patch.object(seed, "Graph", return_value=g), \
                                patch.object(sys, "argv", args):
                            with self.assertRaises(RuntimeError) as raised:
                                if through_main:
                                    seed.main()
                                elif migration:
                                    seed.seed_teams_migration(g)
                                else:
                                    seed.seed_teams(g)
                        self.assertIs(raised.exception, error)
                        self.assertEqual(g.call.call_args.args, (method, path))
                        self.assertNotIn("Done.", output.getvalue())
                        self.assertNotIn("--auth device", output.getvalue())
                        if operation in ("root", "reply"):
                            self.assertNotIn("messages posted:", output.getvalue())
                        if operation == "membership write":
                            self.assertNotIn("members added:", output.getvalue())
                            self.assertNotIn("members: +", output.getvalue())
        self.http.request.assert_not_called()

    def test_teams_invalid_required_reads_cannot_become_empty_successes(self):
        for path in ("/groups?$filter=displayName eq 'Offline team'&$select=id,displayName",
                     "/teams/team/members", "/teams/team/channels"):
            for response in (None, {}):
                with self.subTest(path=path, response=response):
                    g, _ = self.mock_teams()
                    original = g.call.side_effect

                    def call(method, url, **kwargs):
                        if method == "GET" and url == path:
                            return response
                        return original(method, url, **kwargs)

                    g.call.side_effect = call
                    output = io.StringIO()
                    with redirect_stdout(output), patch.object(seed, "Graph", return_value=g), \
                            patch.object(sys, "argv", ["seed_work_iq.py", "--only", "teams"]):
                        with self.assertRaises((TypeError, KeyError)):
                            seed.main()
                    self.assertEqual(g.call.call_args.args, ("GET", path))
                    self.assertNotIn("Done.", output.getvalue())

    def test_teams_missing_member_is_not_reported_as_already_present(self):
        g, _ = self.mock_teams()
        original = g.call.side_effect
        missing = f"/users/{g.config.upn('sasha.ouellet')}?$select=id"
        error = RuntimeError(f"GET {seed.GRAPH}{missing} -> 404: user not found")

        def call(method, path, **kwargs):
            if path == missing:
                if kwargs.get("ok_404"):
                    return None
                raise error
            return original(method, path, **kwargs)

        g.call.side_effect = call
        with self.assertRaises(RuntimeError) as raised:
            seed.seed_teams(g)
        self.assertIs(raised.exception, error)
        self.assertEqual(g.call.call_args.args, ("GET", missing))

    def test_teams_success_preserves_membership_and_threading(self):
        for migration in (False, True):
            with self.subTest(migration=migration):
                g, data = self.mock_teams(migration=migration)
                # Repeated aliases must not cause a second membership write.
                data["team"]["memberAliases"].append("sasha.ouellet")
                args = ["seed_work_iq.py", "--only", "teams"] + (["--migrate"] if migration else [])
                output = io.StringIO()
                with redirect_stdout(output), patch.object(seed, "Graph", return_value=g), \
                        patch.object(sys, "argv", args):
                    seed.main()
                writes = [c for c in g.call.call_args_list if c.args == ("POST", "/teams/team/members")]
                self.assertEqual(len(writes), 2 if migration else 1)
                self.assertEqual(writes[-1].kwargs["json_body"]["roles"], [])
                self.assertIn("users('member')", writes[-1].kwargs["json_body"]["user@odata.bind"])
                posts = [c.args[1] for c in g.call.call_args_list
                         if c.args[0] == "POST" and "/messages" in c.args[1]]
                self.assertEqual(posts, [
                    "/teams/team/channels/channel/messages",
                    "/teams/team/channels/channel/messages/root/replies",
                ])
                self.assertIn("Done.", output.getvalue())
        self.http.request.assert_not_called()

    def test_migration_shared_persona_account_has_one_membership_with_owner_precedence(self):
        g, data = self.mock_teams(migration=True)
        data["team"]["memberAliases"].extend(["sydney.mattos", "sasha.ouellet"])
        with patch.object(seed, "resolve_users", return_value={
            "sydney.mattos": "shared-account", "sasha.ouellet": "shared-account",
        }):
            seed.seed_teams_migration(g)
        writes = [call for call in g.call.call_args_list
                  if call.args == ("POST", "/teams/team/members")]
        self.assertEqual(len(writes), 1)
        self.assertEqual(writes[0].kwargs["json_body"]["roles"], ["owner"])
        self.assertIn("users('shared-account')", writes[0].kwargs["json_body"]["user@odata.bind"])

    def test_post_auth_hint_only_for_app_http_auth_failures(self):
        path = "/teams/team/channels/channel/messages"
        people = {"author": {"displayName": "Author", "title": "Coverage"}}
        errors = [
            *(f"POST {seed.GRAPH}{path} -> {status}: test" for status in (400, 401, 403, 404, 429, 500)),
            f"POST {seed.GRAPH}{path} failed after retries",
            f"POST {seed.GRAPH}{path} -> 400: upstream -> 403: not an auth response",
        ]
        for mode in ("app", "device", "cli"):
            for message in errors:
                for reply_to in (None, "root"):
                    with self.subTest(mode=mode, error=message, reply_to=reply_to):
                        url = path + ("/root/replies" if reply_to else "")
                        error = RuntimeError(message.replace(path, url))
                        g = Mock(mode=mode)
                        g.call.side_effect = error
                        output = io.StringIO()
                        with redirect_stdout(output), self.assertRaises(RuntimeError) as raised:
                            seed.post_message(g, "team", "channel", "author", people,
                                              text="test", reply_to=reply_to)
                        self.assertIs(raised.exception, error)
                        expected_hint = mode == "app" and message.startswith(tuple(
                            f"POST {seed.GRAPH}{path} -> {status}:" for status in (401, 403)
                        ))
                        self.assertEqual("--auth device" in output.getvalue(), expected_hint)

    def test_teams_unexpected_errors_are_not_swallowed(self):
        for migration in (False, True):
            for path in ("/teams/team/members", "/teams/team/channels/channel/messages",
                         "/teams/team/channels/channel/messages/root/replies"):
                with self.subTest(migration=migration, path=path):
                    g, _ = self.mock_teams(migration=migration)
                    original = g.call.side_effect
                    error = ValueError("invalid local payload")

                    def fail(method, url, **kwargs):
                        if method == "POST" and url == path:
                            raise error
                        return original(method, url, **kwargs)

                    g.call.side_effect = fail
                    with self.assertRaises(ValueError) as raised:
                        (seed.seed_teams_migration if migration else seed.seed_teams)(g)
                    self.assertIs(raised.exception, error)
                    self.assertEqual(g.call.call_args.args, ("POST", path))

    def test_migration_resolves_members_not_in_message_authors(self):
        for missing in (False, True):
            with self.subTest(missing=missing):
                g, data = self.mock_teams(migration=True)
                data["team"]["memberAliases"].append("admin")
                original = g.call.side_effect

                def call(method, path, **kwargs):
                    if missing and path.startswith(f"/users/{g.config.upn('admin')}?"):
                        return None
                    return original(method, path, **kwargs)

                g.call.side_effect = call
                if missing:
                    with self.assertRaisesRegex(RuntimeError, "members must resolve"):
                        seed.seed_teams_migration(g, recreate=True)
                    self.assertTrue(all(c.args[0] == "GET" for c in g.call.call_args_list))
                else:
                    seed.seed_teams_migration(g)
                    self.assertIn("users('driver')", g.call.call_args.kwargs["json_body"]["user@odata.bind"])

    def test_migration_missing_author_stops_before_delete_or_create(self):
        g = Mock(config=self.load(("teams",)), dry_run=False)
        g.call.return_value = None
        with self.assertRaisesRegex(RuntimeError, "authors must resolve"):
            seed.seed_teams_migration(g, recreate=True)
        self.assertTrue(all(call.args[0] == "GET" for call in g.call.call_args_list))


if __name__ == "__main__":
    unittest.main()
