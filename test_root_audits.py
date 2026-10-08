"""Offline tests: python -B -m unittest discover -s . -p test_root_audits.py -v.

All identity, mapping, corpus, authentication and HTTP responses are synthetic
and mocked. No files are created, and no configured tenant is contacted.
"""
from __future__ import annotations

import importlib
import importlib.util
import io
import json
import os
import socket
import subprocess
import sys
import types
import unittest
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

TENANT = "11111111-1111-4111-8111-111111111111"
CLIENT = "22222222-2222-4222-8222-222222222222"
TEAM = "33333333-3333-4333-8333-333333333333"
UPN = "reader@tenant.test"
MAPPING = {"mapping": {"reader": {"upn": UPN}}}
CORPUS = {"emails": [{"subject": "Selected coverage note"}]}
ENV = {
    "WORKIQ_TENANT_ID": TENANT,
    "WORKIQ_CLIENT_ID": CLIENT,
    "WORKIQ_CLIENT_SECRET": "offline-test-placeholder",
    "WORKIQ_USER_MAPPING_FILE": "user_mapping.json",
    "WORKIQ_TEAM_ID": TEAM,
    "WORKIQ_FORBIDDEN_TERMS": '["other-demo", "foreign programme"]',
    "WORKIQ_MAIL_SOURCE_FILES": '["offline-corpus.json"]',
}
TOOL_NAMES = ("audit_files", "audit_teams", "audit_tenant_leakage", "triage_mailboxes")


class TransportError(Exception):
    pass


def response(body=None, status=200):
    result = mock.MagicMock()
    result.status_code = status
    result.json.return_value = body
    result.__enter__.return_value = result
    return result


def page(*items, next_link=None):
    body = {"value": list(items)}
    if next_link is not None:
        body["@odata.nextLink"] = next_link
    return response(body)


def message(mid="m1", subject="Selected coverage note", parent="inbox-id", content="neutral"):
    return {"id": mid, "subject": subject, "parentFolderId": parent, "body": {"content": content}}


def call_main(tool, *args):
    return tool.main(list(args)) if tool is triage_mailboxes else tool.main()


class OfflineAuditTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(mock.patch.dict(os.environ, ENV, clear=True))
        self.stack.enter_context(mock.patch.object(sys, "dont_write_bytecode", True))
        self.stdout = self.stack.enter_context(redirect_stdout(io.StringIO()))
        self.stderr = self.stack.enter_context(redirect_stderr(io.StringIO()))
        for owner, name in ((socket, "socket"), (socket, "create_connection"),
                            (socket, "getaddrinfo"), (subprocess, "run"), (subprocess, "Popen"),
                            (os, "system"), (os, "popen")):
            self.stack.enter_context(mock.patch.object(owner, name, side_effect=AssertionError("External action forbidden")))
        self.http = types.ModuleType("requests")
        self.http.RequestException = TransportError
        self.http.get = mock.Mock(side_effect=AssertionError("Unmocked GET forbidden"))
        self.http.post = mock.Mock(side_effect=AssertionError("Unmocked POST forbidden"))
        self.stack.enter_context(mock.patch.dict(sys.modules, {"requests": self.http}))
        self.mapping = json.loads(json.dumps(MAPPING))
        self.corpus = json.loads(json.dumps(CORPUS))

        def read(path, *args, **kwargs):
            if path.name in ("user_mapping.json", "user_mapping.example.json"):
                return json.dumps(self.mapping)
            if path.name == "offline-corpus.json":
                return json.dumps(self.corpus)
            raise AssertionError(f"Unmocked file read forbidden: {path}")

        self.read = self.stack.enter_context(mock.patch.object(Path, "read_text", autospec=True, side_effect=read))
        # Import only after all external operations and private-file reads are guarded.
        global support, audit_files, audit_teams, audit_tenant_leakage, triage_mailboxes, TOOLS
        support = importlib.import_module("diagnostic_support")
        TOOLS = tuple(importlib.import_module(name) for name in TOOL_NAMES)
        audit_files, audit_teams, audit_tenant_leakage, triage_mailboxes = TOOLS
        self.graph = support.GraphClient(self.http, "offline-bearer")

    def fake_auth(self):
        return self.stack.enter_context(mock.patch.object(support.GraphClient, "authenticate", return_value=self.graph))

    def reset_output(self):
        for stream in (self.stdout, self.stderr):
            stream.seek(0)
            stream.truncate()

    def assert_inconclusive(self, tool, *args):
        self.assertEqual(call_main(tool, *args), 2)
        self.assertIn("INCONCLUSIVE", self.stderr.getvalue())
        self.assertNotIn("CLEAN", self.stdout.getvalue())
        self.assertNotIn("No unmatched", self.stdout.getvalue())

    def test_imports_do_not_read_config_authenticate_or_connect(self):
        with mock.patch.dict(os.environ, {}, clear=True), \
                mock.patch.object(Path, "read_text", side_effect=AssertionError("Import read configuration")), \
                mock.patch.object(support.GraphClient, "authenticate", side_effect=AssertionError("Import authenticated")):
            for tool in TOOLS:
                importlib.reload(tool)
        self.http.get.assert_not_called()
        self.http.post.assert_not_called()

    def test_helper_import_does_not_read_environment_or_private_files(self):
        with mock.patch.dict(os.environ, {}, clear=True), \
                mock.patch.object(Path, "read_text", side_effect=AssertionError("Import read configuration")):
            # Execute a fresh helper copy without replacing the classes used by other tests.
            spec = importlib.util.spec_from_file_location("offline_support_import", Path(support.__file__))
            module = importlib.util.module_from_spec(spec)
            with mock.patch.dict(sys.modules, {spec.name: module}):
                spec.loader.exec_module(module)
        self.http.get.assert_not_called()
        self.http.post.assert_not_called()

    def test_each_missing_setting_stops_before_authentication(self):
        auth = self.fake_auth()
        common = ("WORKIQ_TENANT_ID", "WORKIQ_CLIENT_ID", "WORKIQ_CLIENT_SECRET")
        for tool in TOOLS:
            required = list(common)
            if tool is not audit_teams:
                required.append("WORKIQ_USER_MAPPING_FILE")
            if tool in (audit_files, audit_teams):
                required.append("WORKIQ_TEAM_ID")
            required.append("WORKIQ_MAIL_SOURCE_FILES" if tool is triage_mailboxes else "WORKIQ_FORBIDDEN_TERMS")
            for name in required:
                for value in ("", " \t "):
                    with self.subTest(tool=tool.__name__, name=name, value=value), \
                            mock.patch.dict(os.environ, {name: value}):
                        self.reset_output()
                        self.assertEqual(call_main(tool), 2)
                        self.assertIn(name, self.stderr.getvalue())
                        auth.assert_not_called()
        self.http.get.assert_not_called()
        self.http.post.assert_not_called()

    def test_empty_environment_lists_missing_config_not_keyerror(self):
        auth = self.fake_auth()
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(audit_files.main(), 2)
        for name in ("WORKIQ_TENANT_ID", "WORKIQ_CLIENT_ID", "WORKIQ_CLIENT_SECRET",
                     "WORKIQ_USER_MAPPING_FILE", "WORKIQ_TEAM_ID", "WORKIQ_FORBIDDEN_TERMS"):
            self.assertIn(name, self.stderr.getvalue())
        auth.assert_not_called()

    def test_invalid_identifiers_fail_before_authentication(self):
        auth = self.fake_auth()
        for name in ("WORKIQ_TENANT_ID", "WORKIQ_CLIENT_ID", "WORKIQ_TEAM_ID"):
            with self.subTest(name=name), mock.patch.dict(os.environ, {name: "not/a/guid"}):
                self.reset_output()
                self.assertEqual(audit_files.main(), 2)
                self.assertIn(name, self.stderr.getvalue())
        auth.assert_not_called()

    def test_invalid_term_configuration_fails_before_authentication(self):
        auth = self.fake_auth()
        for terms in ('[]', '{}', 'null', '"term"', '[""]', '["a", 3]', '["\\n"]', 'not-json'):
            with self.subTest(terms=terms), mock.patch.dict(os.environ, {"WORKIQ_FORBIDDEN_TERMS": terms}):
                self.assertEqual(audit_files.main(), 2)
        auth.assert_not_called()

    def test_mapping_validation_precedes_authentication(self):
        auth = self.fake_auth()
        for mapping in ({}, {"mapping": {}}, {"mapping": {"one": {}}},
                        {"mapping": {"one": {"upn": "not-a-upn"}}},
                        {"mapping": {"one": {"upn": "person@example.com"}}},
                        {"mapping": MAPPING["mapping"], "tenant_id": TEAM}):
            with self.subTest(mapping=mapping):
                self.mapping = mapping
                self.assertEqual(audit_files.main(), 2)
        auth.assert_not_called()

    def test_missing_or_malformed_mapping_file_is_useful_error(self):
        auth = self.fake_auth()
        for failure in (FileNotFoundError("missing"), json.JSONDecodeError("invalid", "", 0)):
            self.read.side_effect = failure
            self.assertEqual(audit_files.main(), 2)
            self.assertIn("WORKIQ_USER_MAPPING_FILE", self.stderr.getvalue())
        auth.assert_not_called()

    def test_example_mapping_is_never_used_even_with_nonexample_upn(self):
        auth = self.fake_auth()
        with mock.patch.dict(os.environ, {"WORKIQ_USER_MAPPING_FILE": "user_mapping.example.json"}):
            self.assertEqual(audit_files.main(), 2)
        self.assertIn("private mapping", self.stderr.getvalue())
        auth.assert_not_called()

    def test_mapping_accounts_not_stock_people_are_used_and_deduplicated(self):
        self.mapping["mapping"]["second-persona"] = {"upn": UPN.upper()}
        config = support.load_audit_config(team=True)
        self.assertEqual(config.users, (("reader", UPN),))
        self.assertEqual(config.team_id, TEAM)

    def test_secret_is_preserved_and_team_only_needs_no_mapping(self):
        with mock.patch.dict(os.environ, {"WORKIQ_CLIENT_SECRET": " significant whitespace ",
                                         "WORKIQ_USER_MAPPING_FILE": ""}):
            config = support.load_audit_config(users=False, team=True)
        self.assertEqual(config.client_secret, " significant whitespace ")
        self.assertEqual(config.users, ())
        self.read.assert_not_called()

    def test_terms_are_literal_case_insensitive_prefixes_without_stock_allowlists(self):
        scanner = support.LeakageScanner(("other-demo", "term+"))
        scanner.scan("example", "OTHER-DEMO items; term+ records")
        scanner.scan("not-matched", "another-demo term")
        self.assertEqual(scanner.hits, [("example", "other-demo"), ("example", "term+")])

    def test_graph_auth_checks_http_status_before_extracting_token(self):
        self.http.post.side_effect = None
        self.http.post.return_value = response({"access_token": "do-not-print"}, 401)
        self.assert_inconclusive(audit_files)
        self.http.get.assert_not_called()
        self.assertNotIn("do-not-print", self.stderr.getvalue())

    def test_graph_auth_rejects_missing_token_or_wrong_token_type(self):
        self.http.post.side_effect = None
        for body in ({}, {"access_token": ""}, {"access_token": "test", "token_type": "Basic"},
                     {"access_token": "test", "token_type": "Bearer", "error": "failure"}):
            with self.subTest(body=body):
                self.http.post.return_value = response(body)
                self.assert_inconclusive(audit_files)
        self.http.get.assert_not_called()

    def test_graph_auth_uses_only_explicit_credentials(self):
        self.http.post.side_effect = None
        self.http.post.return_value = response({"access_token": "test", "token_type": "Bearer"})
        support.GraphClient.authenticate(support.load_audit_config())
        url = self.http.post.call_args.args[0]
        request = self.http.post.call_args.kwargs
        self.assertIn(TENANT, url)
        self.assertEqual(request["data"]["client_id"], CLIENT)
        self.assertEqual(request["data"]["client_secret"], ENV["WORKIQ_CLIENT_SECRET"])
        self.assertFalse(request["allow_redirects"])

    def test_graph_transport_errors_are_not_success_and_do_not_print_secrets(self):
        self.http.get.side_effect = TransportError("sensitive response details")
        with self.assertRaisesRegex(support.AuditError, "transport failed"):
            self.graph.get(support.GRAPH + "/me", "read")
        self.assertNotIn("sensitive", self.stderr.getvalue())

    def test_required_reads_fail_for_all_non_success_statuses(self):
        self.http.get.side_effect = None
        for status in (301, 302, 401, 403, 404, 429, 500, 503):
            with self.subTest(status=status):
                self.http.get.return_value = response({"value": []}, status)
                with self.assertRaisesRegex(support.AuditError, f"HTTP {status}"):
                    list(self.graph.collection(support.GRAPH + "/users", "users"))

    def test_malformed_or_error_json_cannot_look_like_empty_collection(self):
        self.http.get.side_effect = None
        for body in ({}, [], None, {"value": None}, {"value": [None]},
                     {"value": [], "error": {"code": "Failure"}}):
            with self.subTest(body=body):
                self.http.get.return_value = response(body)
                with self.assertRaises(support.AuditError):
                    list(self.graph.collection(support.GRAPH + "/users", "users"))
        broken = response()
        broken.json.side_effect = ValueError("bad JSON")
        self.http.get.return_value = broken
        with self.assertRaisesRegex(support.AuditError, "malformed JSON"):
            self.graph.get(support.GRAPH + "/users", "users")

    def test_all_collection_pages_are_returned(self):
        next_url = support.GRAPH + "/users?$skiptoken=next"
        self.http.get.side_effect = [page({"id": "one"}, next_link=next_url), page({"id": "two"})]
        self.assertEqual(list(self.graph.collection(support.GRAPH + "/users", "users")),
                         [{"id": "one"}, {"id": "two"}])
        self.assertEqual(self.http.get.call_args.args[0], next_url)

    def test_later_page_failure_is_not_empty_success(self):
        next_url = support.GRAPH + "/users?$skiptoken=next"
        self.http.get.side_effect = [page({"id": "one"}, next_link=next_url), response({}, 403)]
        with self.assertRaisesRegex(support.AuditError, "HTTP 403"):
            list(self.graph.collection(support.GRAPH + "/users", "users"))

    def test_bad_next_links_are_rejected_before_followup_request(self):
        for link in ("https://untrusted.invalid/collect", "http://graph.microsoft.com/v1.0/users",
                     "https://graph.microsoft.com@untrusted.invalid/v1.0/users", "/v1.0/users",
                     "https://graph.microsoft.com/v1.0/users#fragment", "", None, 7):
            with self.subTest(link=link):
                self.http.get.reset_mock()
                self.http.get.side_effect = [response({"value": [], "@odata.nextLink": link})]
                with self.assertRaises(support.AuditError):
                    list(self.graph.collection(support.GRAPH + "/users", "users"))
                self.assertEqual(self.http.get.call_count, 1)

    def test_pagination_cycle_fails(self):
        url = support.GRAPH + "/users"
        self.http.get.side_effect = [page(next_link=url)]
        with self.assertRaisesRegex(support.AuditError, "pagination cycle"):
            list(self.graph.collection(url, "users"))
        self.assertEqual(self.http.get.call_count, 1)

    def test_only_archive_metadata_404_is_optional(self):
        self.http.get.side_effect = None
        self.http.get.return_value = response({}, 404)
        base = support.user_url(UPN) + "/mailFolders/"
        self.assertIsNone(self.graph.get(base + "archive?$select=id", "archive", optional_folder=True))
        for suffix in ("inbox", "archive/messages", "deleteditems"):
            with self.subTest(suffix=suffix):
                with self.assertRaises(support.AuditError):
                    self.graph.get(base + suffix, "required", optional_folder=True)
                with self.assertRaises(support.AuditError):
                    self.graph.get(base + suffix, "required")
        self.http.get.return_value = response({}, 403)
        with self.assertRaises(support.AuditError):
            self.graph.get(base + "archive", "archive", optional_folder=True)

    def test_file_walk_pages_and_nested_folders_detect_all_names(self):
        self.fake_auth()
        next_url = support.GRAPH + "/drives/offline/items/root/children?$skiptoken=next"
        self.http.get.side_effect = [
            response({"id": "root"}),
            page({"id": "folder", "name": "other-demo", "folder": {}}, next_link=next_url),
            page({"id": "file", "name": "neutral.txt"}),
            page({"id": "child", "name": "document.txt"}),
            response({"id": "team-root"}), page(),
        ]
        self.assertEqual(audit_files.main(), 1)
        self.assertIn("other-demo", self.stdout.getvalue())
        urls = [call.args[0] for call in self.http.get.call_args_list]
        self.assertTrue(any("reader%40tenant.test" in url for url in urls))
        self.assertTrue(any(f"/groups/{TEAM}/drive/root" in url for url in urls))
        self.assertTrue(any("/items/folder/children" in url for url in urls))

    def test_drive_read_failure_after_a_hit_is_inconclusive(self):
        self.fake_auth()
        self.http.get.side_effect = [
            response({"id": "root"}), page({"id": "file", "name": "other-demo.txt"}),
            response({}, 403),
        ]
        self.assert_inconclusive(audit_files)

    def test_drive_shortcuts_or_missing_names_are_not_clean(self):
        for item in ({"id": "link", "name": "shortcut", "remoteItem": {}}, {"id": "nameless"}):
            with self.subTest(item=item):
                self.http.get.side_effect = [page(item)]
                with self.assertRaises(support.AuditError):
                    audit_files.walk(self.graph, support.GRAPH + "/drives/offline", "root")

    def test_drive_hierarchy_cycle_fails(self):
        self.http.get.side_effect = [page({"id": "root", "name": "loop", "folder": {}})]
        with self.assertRaisesRegex(support.AuditError, "repeated folder"):
            audit_files.walk(self.graph, support.GRAPH + "/drives/offline", "root")

    def test_file_results_do_not_persist_across_runs(self):
        self.fake_auth()
        self.http.get.side_effect = [response({"id": "root"}), page({"id": "file", "name": "other-demo"}),
                                     response({"id": "team-root"}), page()]
        self.assertEqual(audit_files.main(), 1)
        self.reset_output()
        self.http.get.side_effect = [response({"id": "root"}), page(), response({"id": "team-root"}), page()]
        self.assertEqual(audit_files.main(), 0)
        self.assertIn("CLEAN", self.stdout.getvalue())

    def test_teams_channel_message_and_reply_pagination(self):
        self.fake_auth()
        channels = f"{support.GRAPH}/teams/{TEAM}/channels"
        messages = channels + "/channel%3Aid/messages"
        self.http.get.side_effect = [
            page({"id": "channel:id", "displayName": "neutral"}, next_link=channels + "?$skiptoken=next"),
            page(message(), next_link=messages + "?$skiptoken=next"),
            page(next_link=messages + "/m1/replies?$skiptoken=next"),
            page(message("reply", content="other-demo")),
            page(),
            page({"id": "channel-two", "displayName": "second"}),
            page(),
        ]
        self.assertEqual(audit_teams.main(), 1)
        self.assertIn("reply/reply", self.stdout.getvalue())
        self.assertEqual(self.http.get.call_count, 7)

    def test_reply_404_or_missing_content_is_inconclusive(self):
        self.fake_auth()
        for reply in (response({}, 404), page({"id": "reply"})):
            with self.subTest(reply=reply):
                self.reset_output()
                self.http.get.side_effect = [page({"id": "channel", "displayName": "neutral"}),
                                             page(message()), reply]
                self.assert_inconclusive(audit_teams)

    def test_teams_read_failures_do_not_report_zero_clean(self):
        self.fake_auth()
        self.http.get.side_effect = [response({}, 404)]
        self.assert_inconclusive(audit_teams)

    def test_live_mail_follows_pages_and_subfolders_archive_only_optional(self):
        self.fake_auth()
        next_url = support.user_url(UPN) + "/mailFolders/inbox-id/messages?$skiptoken=next"
        self.http.get.side_effect = [
            response({"id": "inbox-id"}), page(message(), next_link=next_url),
            page(message("m2", content="other-demo")), page({"id": "child-id"}), page(message("m3")), page(),
            response({"id": "sent-id"}), page(), page(),
            response({"id": "draft-id"}), page(), page(),
            response({}, 404),
        ]
        self.assertEqual(audit_tenant_leakage.main(), 1)
        self.assertIn("3 message(s)", self.stdout.getvalue())
        self.assertEqual(self.http.get.call_count, 13)

    def test_mail_folder_read_or_message_404_is_inconclusive(self):
        self.fake_auth()
        for responses in ([response({}, 404)], [response({"id": "inbox-id"}), response({}, 404)]):
            with self.subTest(responses=responses):
                self.reset_output()
                self.http.get.side_effect = responses
                self.assert_inconclusive(audit_tenant_leakage)

    def test_missing_mail_body_is_inconclusive(self):
        self.fake_auth()
        self.http.get.side_effect = [response({"id": "inbox-id"}), page({"id": "message", "subject": "normal"})]
        self.assert_inconclusive(audit_tenant_leakage)

    def test_subject_normalization_handles_repeated_reply_prefixes(self):
        self.assertEqual(triage_mailboxes.norm(" Re: FW: Fwd: Selected   coverage note "),
                         triage_mailboxes.norm("selected coverage note"))

    def test_invalid_corpus_stops_purge_before_auth(self):
        auth = self.fake_auth()
        for corpus in ({}, {"emails": []}, {"emails": [{}]}, {"emails": [{"subject": "Re: "}]}):
            with self.subTest(corpus=corpus):
                self.corpus = corpus
                self.assertEqual(triage_mailboxes.main(["--purge"]), 2)
        auth.assert_not_called()
        self.http.post.assert_not_called()

    def test_all_corpora_are_validated_before_auth(self):
        auth = self.fake_auth()
        original = self.read.side_effect

        def read(path, *args, **kwargs):
            if path.name == "missing-corpus.json":
                raise FileNotFoundError("missing")
            return original(path, *args, **kwargs)

        self.read.side_effect = read
        with mock.patch.dict(os.environ, {"WORKIQ_MAIL_SOURCE_FILES": '["offline-corpus.json", "missing-corpus.json"]'}):
            self.assertEqual(triage_mailboxes.main(["--purge"]), 2)
        auth.assert_not_called()
        self.http.post.assert_not_called()

    def test_multiple_explicit_corpora_are_combined(self):
        original = self.read.side_effect

        def read(path, *args, **kwargs):
            if path.name == "mission-corpus.json":
                return json.dumps({"emails": [{"subject": "Selected mission note"}]})
            return original(path, *args, **kwargs)

        self.read.side_effect = read
        with mock.patch.dict(os.environ, {"WORKIQ_MAIL_SOURCE_FILES": '["offline-corpus.json", "mission-corpus.json"]'}):
            self.assertEqual(triage_mailboxes.load_subjects(),
                             {"selected coverage note", "selected mission note"})

    def test_purge_waits_until_every_mailbox_is_inventoried(self):
        self.fake_auth()
        self.mapping["mapping"]["second"] = {"upn": "second@tenant.test"}
        self.http.get.side_effect = [response({"id": "deleted"}), page(),
                                     page(message(subject="unmatched")), response({}, 403)]
        self.assert_inconclusive(triage_mailboxes, "--purge")
        self.http.post.assert_not_called()

    def test_triage_read_failure_never_returns_clean_even_with_zero_messages(self):
        self.fake_auth()
        self.http.get.side_effect = [response({"id": "deleted"}), page(), response({}, 403)]
        self.assert_inconclusive(triage_mailboxes)
        self.http.post.assert_not_called()

    def test_late_inventory_page_failure_prevents_purge(self):
        self.fake_auth()
        next_url = support.user_url(UPN) + "/messages?$skiptoken=next"
        self.http.get.side_effect = [response({"id": "deleted"}), page(),
                                     page(message(subject="unmatched"), next_link=next_url), response({}, 500)]
        self.assert_inconclusive(triage_mailboxes, "--purge")
        self.http.post.assert_not_called()

    def test_report_follows_pages_and_excludes_deleted_descendants(self):
        self.fake_auth()
        next_url = support.user_url(UPN) + "/messages?$skiptoken=next"
        self.http.get.side_effect = [
            response({"id": "deleted"}), page({"id": "deleted-child"}), page(),
            page(message(), message("deleted-msg", subject="unmatched", parent="deleted-child"), next_link=next_url),
            page(message("unmatched-msg", subject="Needs review")),
        ]
        self.assertEqual(triage_mailboxes.main([]), 1)
        self.assertIn("2 outside Deleted Items, 1 unmatched", self.stdout.getvalue())
        self.http.post.assert_not_called()

    def test_successful_purge_checks_destination_and_does_not_retry(self):
        self.fake_auth()
        self.http.get.side_effect = [response({"id": "deleted"}), page(),
                                     page(message("id/encoded", subject="unmatched"))]
        self.http.post.side_effect = [response({"id": "new-id", "parentFolderId": "deleted"}, 201)]
        self.assertEqual(triage_mailboxes.main(["--purge"]), 0)
        self.assertTrue(self.http.post.call_args.args[0].endswith("/id%2Fencoded/move"))
        self.assertEqual(self.http.post.call_args.kwargs["json"], {"destinationId": "deleted"})
        self.assertEqual(self.http.post.call_count, 1)

    def test_purge_failure_stops_and_reports_inconclusive(self):
        self.fake_auth()
        self.http.get.side_effect = [response({"id": "deleted"}), page(),
                                     page(message(subject="unmatched"), message("m2", subject="unmatched too"))]
        self.http.post.side_effect = [response({}, 403)]
        self.assert_inconclusive(triage_mailboxes, "--purge")
        self.assertEqual(self.http.post.call_count, 1)

    def test_purge_ambiguous_transport_failure_is_not_retried(self):
        self.fake_auth()
        self.http.get.side_effect = [response({"id": "deleted"}), page(), page(message(subject="unmatched"))]
        self.http.post.side_effect = TransportError("unknown outcome")
        self.assert_inconclusive(triage_mailboxes, "--purge")
        self.assertIn("outcome unknown", self.stderr.getvalue())
        self.assertEqual(self.http.post.call_count, 1)

    def test_purge_response_must_confirm_actual_destination(self):
        self.fake_auth()
        self.http.get.side_effect = [response({"id": "deleted"}), page(), page(message(subject="unmatched"))]
        self.http.post.side_effect = [response({"id": "new-id", "parentFolderId": "wrong"}, 201)]
        self.assert_inconclusive(triage_mailboxes, "--purge")

    def test_missing_message_fields_prevent_purge(self):
        self.fake_auth()
        for field in ("subject", "parentFolderId", "id"):
            with self.subTest(field=field):
                self.reset_output()
                item = message(subject="unmatched")
                del item[field]
                self.http.get.side_effect = [response({"id": "deleted"}), page(), page(item)]
                self.assert_inconclusive(triage_mailboxes, "--purge")
                self.http.post.assert_not_called()

    def test_duplicate_message_in_paged_inventory_prevents_purge(self):
        self.fake_auth()
        self.http.get.side_effect = [response({"id": "deleted"}), page(),
                                     page(message(subject="unmatched"), message(subject="unmatched"))]
        self.assert_inconclusive(triage_mailboxes, "--purge")
        self.http.post.assert_not_called()

    def test_known_subjects_or_deleted_only_return_zero_without_moves(self):
        self.fake_auth()
        self.http.get.side_effect = [response({"id": "deleted"}), page(),
                                     page(message(), message("m2", subject="unmatched", parent="deleted"))]
        self.assertEqual(triage_mailboxes.main(["--purge"]), 0)
        self.http.post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
