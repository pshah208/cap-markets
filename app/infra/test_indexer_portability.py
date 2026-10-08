"""Offline indexer tests; Azure imports, credentials and requests are mocked."""

import builtins
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import types
import unittest
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from unittest.mock import MagicMock, Mock, patch

from test_infra_portability import no_external_effects


INDEXER = Path(__file__).resolve().parents[2] / "data" / "foundry-iq" / "index_cm_policies.py"
ENV = {
    "SEARCH_ENDPOINT": "https://search.example.com",
    "SEARCH_INDEX": "bank-policies",
    "SEARCH_SEMANTIC_CONFIGURATION": "bank-semantic",
    "AZURE_AUTH_MODE": "azure_cli",
    "AZURE_TENANT_ID": "11111111-1111-4111-8111-111111111111",
    "AZURE_SUBSCRIPTION_ID": "22222222-2222-4222-8222-222222222222",
    "AZURE_CLIENT_ID": "33333333-3333-4333-8333-333333333333",
    "AZURE_CLIENT_SECRET": "not-a-real-secret",
    "SEARCH_ADMIN_KEY": "not-a-real-key",
}
DOCUMENT = {
    "id": "CP-001", "title": "Synthetic policy", "category": "Credit",
    "effective_date": "2026-01-01", "owner": "The Bank",
    "regulatory_anchor": "Demo", "content": "Synthetic demonstration only.",
    "applies_to": ["Coverage"],
}


def load():
    spec = importlib.util.spec_from_file_location("_indexer_portability", INDEXER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


with no_external_effects():
    indexer = load()


@contextmanager
def fake_azure():
    real_import = builtins.__import__
    names = (
        "azure", "azure.core", "azure.core.exceptions", "azure.core.credentials",
        "azure.identity", "azure.search", "azure.search.documents",
        "azure.search.documents.indexes", "azure.search.documents.indexes.models",
    )
    modules = {name: types.ModuleType(name) for name in names}
    models = modules["azure.search.documents.indexes.models"]
    for name in (
        "SearchableField", "SearchIndex", "SemanticConfiguration", "SemanticField",
        "SemanticPrioritizedFields", "SemanticSearch", "SimpleField",
    ):
        setattr(models, name, lambda **kwargs: types.SimpleNamespace(**kwargs))
    models.SearchFieldDataType = types.SimpleNamespace(String="Edm.String")

    class ResourceNotFoundError(Exception):
        pass

    modules["azure.core.exceptions"].ResourceNotFoundError = ResourceNotFoundError
    for name in ("AzureCliCredential", "ClientSecretCredential", "ManagedIdentityCredential"):
        setattr(modules["azure.identity"], name, Mock(name=name))
    modules["azure.core.credentials"].AzureKeyCredential = Mock()
    search = MagicMock()
    indexes = MagicMock()
    modules["azure.search.documents"].SearchClient = search
    modules["azure.search.documents.indexes"].SearchIndexClient = indexes
    with no_external_effects(), patch.dict(sys.modules, modules):
        # Only fake Azure modules are permitted; other filesystem/network guards remain active.
        def fake_import(name, *args, **kwargs):
            if name == "requests" or (name.startswith("azure") and name not in modules):
                raise AssertionError(f"Unexpected SDK import: {name}")
            return real_import(name, *args, **kwargs)
        with patch("builtins.__import__", side_effect=fake_import):
            yield modules, search, indexes


class IndexerConfigurationTests(unittest.TestCase):
    def test_import_has_no_environment_or_runtime_effects(self):
        with no_external_effects(), patch.dict(os.environ, {}, clear=True):
            module = load()
        self.assertFalse(hasattr(module, "CRED"))

    def test_every_required_field_precedes_credentials_and_corpus_reads(self):
        for mode, fields in indexer.AUTH_FIELDS.items():
            for name in (*indexer.REQUIRED_ENV, *fields):
                for value in (None, "", " \t "):
                    env = {**ENV, "AZURE_AUTH_MODE": mode}
                    if value is None:
                        del env[name]
                    else:
                        env[name] = value
                    with self.subTest(mode=mode, name=name, value=value):
                        err = io.StringIO()
                        with no_external_effects(), redirect_stderr(err):
                            with patch.object(Path, "read_text", side_effect=AssertionError("Corpus read too early")):
                                with self.assertRaises(SystemExit) as raised:
                                    indexer.main([], environ=env)
                        self.assertEqual(raised.exception.code, 2)
                        self.assertIn(name, err.getvalue())

    def test_missing_environment_reports_all_base_settings(self):
        with no_external_effects(), self.assertRaises(indexer.ConfigurationError) as raised:
            indexer.load_config({})
        for field in indexer.REQUIRED_ENV:
            self.assertIn(field, str(raised.exception))

    def test_no_credential_fallback_or_unselected_secrets_required(self):
        with no_external_effects():
            for mode, fields in indexer.AUTH_FIELDS.items():
                env = {name: ENV[name] for name in (*indexer.REQUIRED_ENV, *fields)}
                env["AZURE_AUTH_MODE"] = mode
                self.assertEqual(indexer.load_config(env), env)
            for mode in ("default", "key", "AzureCli"):
                with self.assertRaisesRegex(indexer.ConfigurationError, "AZURE_AUTH_MODE"):
                    indexer.load_config({**ENV, "AZURE_AUTH_MODE": mode})

    def test_invalid_endpoint_index_and_semantic_configuration(self):
        cases = {
            "SEARCH_ENDPOINT": (
                "http://search.example.com", "https://user:pass@search.example.com",
                "https://search.example.com/path", "https://search.example.com?",
                "https://search.example.com/#", "https://<service>.search.windows.net",
                "https://search.example.com:bad", "https://search.example.com\\path",
            ),
            "SEARCH_INDEX": ("x", "-invalid", "BadName", "bad--name", "x" * 129),
            "SEARCH_SEMANTIC_CONFIGURATION": ("bad name", "x" * 129, "<semantic>"),
        }
        with no_external_effects():
            for name, values in cases.items():
                for value in values:
                    with self.subTest(name=name, value=value):
                        with self.assertRaisesRegex(indexer.ConfigurationError, name):
                            indexer.load_config({**ENV, name: value})
            config = indexer.load_config({**ENV, "SEARCH_ENDPOINT": ENV["SEARCH_ENDPOINT"] + "/"})
            self.assertEqual(config["SEARCH_ENDPOINT"], ENV["SEARCH_ENDPOINT"])

    def test_conflicting_actions_and_help_need_no_config(self):
        with no_external_effects(), patch.dict(os.environ, {}, clear=True):
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
                indexer.main(["--verify", "--recreate"])
            self.assertEqual(raised.exception.code, 2)
            with redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as raised:
                indexer.main(["--help"])
            self.assertEqual(raised.exception.code, 0)

    def test_invalid_corpus_precedes_credentials_even_with_recreate(self):
        payloads = (
            "not-json", "[]", "{}", '{"documents":[]}',
            json.dumps({"documents": [DOCUMENT, DOCUMENT]}),
            json.dumps({"documents": [{**DOCUMENT, "applies_to": "Coverage"}]}),
            json.dumps({"documents": [{**DOCUMENT, "id": "bad/key"}]}),
            json.dumps({"documents": [{**DOCUMENT, "content": " "}]}),
            json.dumps({"documents": [{**DOCUMENT, "extra": "unknown"}]}),
        )
        for payload in payloads:
            with self.subTest(payload=payload), no_external_effects():
                with patch.object(Path, "read_text", return_value=payload):
                    with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
                        indexer.main(["--recreate"], environ=ENV)
                self.assertEqual(raised.exception.code, 2)

    def test_unreadable_corpus_is_a_configuration_error(self):
        with no_external_effects(), patch.object(Path, "read_text", side_effect=OSError("unreadable")):
            with self.assertRaisesRegex(indexer.ConfigurationError, "Cannot read policy corpus"):
                indexer.load_documents(indexer.CORPUS)

    def test_tracked_corpus_remains_schema_compatible(self):
        with no_external_effects():
            self.assertGreater(len(indexer.load_documents(indexer.CORPUS)), 0)


class IndexerOperationTests(unittest.TestCase):
    def setUp(self):
        self.config = indexer.load_config(ENV)
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def test_each_explicit_auth_constructs_only_the_selected_credential(self):
        for mode in indexer.AUTH_FIELDS:
            config = indexer.load_config({**ENV, "AZURE_AUTH_MODE": mode})
            with self.subTest(mode=mode), fake_azure() as (modules, _, _):
                credential = indexer.build_credential(config)
                identity = modules["azure.identity"]
                factories = {
                    "azure_cli": identity.AzureCliCredential,
                    "service_principal": identity.ClientSecretCredential,
                    "managed_identity": identity.ManagedIdentityCredential,
                    "admin_key": modules["azure.core.credentials"].AzureKeyCredential,
                }
                self.assertIs(credential, factories[mode].return_value)
                for key, factory in factories.items():
                    self.assertEqual(factory.call_count, int(key == mode))
                if mode == "azure_cli":
                    factories[mode].assert_called_once_with(
                        tenant_id=ENV["AZURE_TENANT_ID"], subscription=ENV["AZURE_SUBSCRIPTION_ID"])

    def test_index_schema_and_semantic_name_are_preserved(self):
        credential = object()
        with fake_azure() as (_, _, factory):
            indexer.build_index(self.config, credential)
            factory.assert_called_once_with(ENV["SEARCH_ENDPOINT"], credential)
            client = factory.return_value.__enter__.return_value
            client.delete_index.assert_not_called()
            model = client.create_or_update_index.call_args.args[0]
            self.assertEqual(model.name, ENV["SEARCH_INDEX"])
            applies_to = next(field for field in model.fields if field.name == "applies_to")
            self.assertTrue(applies_to.collection)
            semantic = model.semantic_search.configurations[0]
            self.assertEqual(semantic.name, ENV["SEARCH_SEMANTIC_CONFIGURATION"])
            self.assertEqual(semantic.prioritized_fields.content_fields[0].field_name, "content")

    def test_recreate_ignores_only_missing_index_not_permission_failure(self):
        with fake_azure() as (modules, _, factory), patch.object(indexer.time, "sleep"):
            client = factory.return_value.__enter__.return_value
            client.delete_index.side_effect = modules["azure.core.exceptions"].ResourceNotFoundError()
            indexer.build_index(self.config, object(), recreate=True)
            client.create_or_update_index.assert_called_once()
            client.reset_mock()
            client.delete_index.side_effect = PermissionError("denied")
            with self.assertRaises(PermissionError):
                indexer.build_index(self.config, object(), recreate=True)
            client.create_or_update_index.assert_not_called()

    def test_upload_uses_validated_documents_and_fails_on_partial_success(self):
        docs = [DOCUMENT, {**DOCUMENT, "id": "CP-002"}]
        with fake_azure() as (_, factory, _):
            client = factory.return_value.__enter__.return_value
            client.upload_documents.return_value = [
                types.SimpleNamespace(key=doc["id"], succeeded=True) for doc in docs
            ]
            self.assertEqual(indexer.upload_docs(self.config, object(), docs), 2)
            client.upload_documents.assert_called_once_with(documents=docs)
            client.upload_documents.return_value[1].succeeded = False
            with self.assertRaisesRegex(RuntimeError, "CP-002"):
                indexer.upload_docs(self.config, object(), docs)

    def test_verification_uses_configured_semantics_and_detects_missing_hits(self):
        with fake_azure() as (_, factory, _):
            client = factory.return_value.__enter__.return_value
            client.search.side_effect = [[{"id": expected}] for _, expected in indexer.VERIFY_QUERIES]
            self.assertEqual(indexer.verify(self.config, object()), 0)
            for call in client.search.call_args_list:
                self.assertEqual(call.kwargs["semantic_configuration_name"], ENV["SEARCH_SEMANTIC_CONFIGURATION"])
                self.assertEqual(call.kwargs["top"], 3)
            client.search.side_effect = None
            client.search.return_value = []
            self.assertEqual(indexer.verify(self.config, object()), len(indexer.VERIFY_QUERIES))

    def test_verify_only_skips_corpus_and_mutations_and_closes_credential(self):
        with no_external_effects(), patch.object(indexer, "build_credential", return_value=Mock()) as credential:
            with patch.object(indexer, "load_documents") as corpus, patch.object(indexer, "build_index") as build:
                with patch.object(indexer, "upload_docs") as upload, patch.object(indexer, "verify", return_value=0):
                    self.assertEqual(indexer.main(["--verify"], environ=ENV), 0)
            corpus.assert_not_called()
            build.assert_not_called()
            upload.assert_not_called()
            credential.return_value.close.assert_called_once()

    def test_operation_order_and_failed_upload_stop_verification(self):
        calls = []
        def record(name, result=None):
            def invoke(*args, **kwargs):
                calls.append(name)
                return result
            return invoke
        credential = Mock()
        with no_external_effects(), patch.object(indexer, "load_documents", side_effect=record("corpus", [DOCUMENT])):
            with patch.object(indexer, "build_credential", side_effect=record("credential", credential)):
                with patch.object(indexer, "build_index", side_effect=record("index")):
                    with patch.object(indexer, "upload_docs", side_effect=record("upload", 1)) as upload:
                        with patch.object(indexer.time, "sleep", side_effect=record("settle")):
                            with patch.object(indexer, "verify", side_effect=record("verify", 0)):
                                self.assertEqual(indexer.main([], environ=ENV), 0)
                                self.assertEqual(calls, ["corpus", "credential", "index", "upload", "settle", "verify"])
                                calls.clear()
                                upload.side_effect = RuntimeError("incomplete upload")
                                with redirect_stderr(io.StringIO()):
                                    self.assertEqual(indexer.main([], environ=ENV), 1)
                                self.assertEqual(calls, ["corpus", "credential", "index"])
        self.assertEqual(credential.close.call_count, 2)


if __name__ == "__main__":
    unittest.main()
