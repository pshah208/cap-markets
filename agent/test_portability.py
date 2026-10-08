"""Offline unittest coverage for explicit configuration and single-credential auth."""

from __future__ import annotations

import argparse
import builtins
import csv
import importlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import types
import typing
import unittest
from contextlib import ExitStack, contextmanager
from unittest import mock
from urllib.parse import urlsplit


DIRECTORY = Path(__file__).resolve().parent
ENDPOINT = "https://foundry.invalid/api/projects/offline-test"
COMMON_FIELDS = (
    "FOUNDRY_PROJECT_ENDPOINT", "FOUNDRY_AGENT_NAME", "FOUNDRY_MODEL",
    "CM_CLIENT_ID", "IQ_MODE", "AZURE_AUTH_MODE",
)
AUTH_FIELDS = {
    "azure_cli": ("AZURE_TENANT_ID", "AZURE_SUBSCRIPTION_ID"),
    "service_principal": ("AZURE_TENANT_ID", "AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET"),
    "managed_identity": ("AZURE_CLIENT_ID",),
}
AUTH_VALUES = {
    "AZURE_TENANT_ID": "11111111-1111-4111-8111-111111111111",
    "AZURE_SUBSCRIPTION_ID": "22222222-2222-4222-8222-222222222222",
    "AZURE_CLIENT_ID": "33333333-3333-4333-8333-333333333333",
    "AZURE_CLIENT_SECRET": "fake-unit-test-secret-not-a-credential",
}
HYBRID_VALUES = {
    "SEARCH_ENDPOINT": "https://search.invalid/",
    "SEARCH_INDEX": "offline-index",
    "SEARCH_SEMANTIC_CONFIGURATION": "offline-semantic",
    "BING_GROUNDING_CONNECTION_ID": (
        "/subscriptions/22222222-2222-4222-8222-222222222222/resourceGroups/"
        "offline-test/providers/Microsoft.CognitiveServices/accounts/offline-test/"
        "projects/offline-test/connections/offline-bing"
    ),
}
INVALID_URLS = (
    "", " \t ", "http://foundry.invalid", "ftp://foundry.invalid",
    "foundry.invalid", "//foundry.invalid", "https://", "https:///missing-host",
    "https://user@foundry.invalid", "https://user:password@foundry.invalid",
    "https://foundry.invalid?api-key=offline", "https://foundry.invalid#fragment",
    "https://foundry.invalid?", "https://foundry.invalid#",
    "https://foundry.invalid/bad path", "https://foundry.invalid/\tpath",
    "https://foundry.invalid/\npath", "https://foundry.invalid/<project>",
    "https://foundry.invalid\\project", "https://[broken",
    "https://foundry.invalid:not-a-port", "https://foundry.invalid:65536",
    "https://foundry.invalid:-1",
)
INVALID_AUTH_MODES = ("default", "auto", "DefaultAzureCredential", "Azure_Cli", "cli", "unknown")
INVALID_IQ_MODES = ("auto", "cloud", "live", "offline", "LOCAL", "Hybrid", "unknown")
CREDENTIAL_NAMES = ("AzureCliCredential", "ClientSecretCredential", "ManagedIdentityCredential")


def environment(auth_mode="azure_cli", iq_mode="local"):
    values = {
        "FOUNDRY_PROJECT_ENDPOINT": ENDPOINT + "/",
        "FOUNDRY_AGENT_NAME": "offline-agent",
        "FOUNDRY_MODEL": "offline-model",
        "CM_CLIENT_ID": "OFFLINE-CLIENT",
        "IQ_MODE": iq_mode,
        "AZURE_AUTH_MODE": auth_mode,
        **{name: AUTH_VALUES[name] for name in AUTH_FIELDS[auth_mode]},
    }
    if iq_mode == "hybrid":
        values.update(HYBRID_VALUES)
    return values


def missing_variants(values, fields):
    for field in fields:
        for replacement in (None, "", " \t\r\n "):
            changed = dict(values)
            if replacement is None:
                changed.pop(field, None)
            else:
                changed[field] = replacement
            yield field, replacement, changed


class OfflineTestCase(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(mock.patch.object(sys, "dont_write_bytecode", True))
        self.stack.enter_context(mock.patch.dict(os.environ, {}, clear=True))
        self.forbidden_calls = []
        self.fake_azure = {}
        original_import = builtins.__import__
        original_import_module = importlib.import_module

        def check_import(name):
            if name == "azure" or name.startswith("azure."):
                if name not in self.fake_azure or sys.modules.get(name) is not self.fake_azure[name]:
                    self.azure_import(name)
            if name.split(".", 1)[0] in ("requests", "httpx", "aiohttp", "dotenv", "msal"):
                self.external_import(name)

        def guarded_import(name, *args, **kwargs):
            check_import(name)
            return original_import(name, *args, **kwargs)

        def guarded_import_module(name, package=None):
            absolute = importlib.util.resolve_name(name, package) if name.startswith(".") else name
            check_import(absolute)
            return original_import_module(name, package)

        self.azure_import = self.forbidden("real Azure SDK import")
        self.external_import = self.forbidden("external dependency import")
        self.stack.enter_context(mock.patch.object(builtins, "__import__", guarded_import))
        self.stack.enter_context(mock.patch.object(importlib, "import_module", guarded_import_module))
        for owner, names in (
            (socket, ("socket", "socketpair", "create_connection", "getaddrinfo",
                      "gethostbyname", "gethostbyname_ex", "gethostbyaddr")),
            (subprocess, ("Popen", "run", "call", "check_call", "check_output",
                          "getoutput", "getstatusoutput")),
            (os, ("system", "popen", "startfile", "fork", "posix_spawn", "posix_spawnp",
                  "spawnl", "spawnle", "spawnlp", "spawnlpe", "spawnv", "spawnve",
                  "spawnvp", "spawnvpe", "execl", "execle", "execlp", "execlpe",
                  "execv", "execve", "execvp", "execvpe")),
            (Path, ("write_text", "write_bytes", "touch", "mkdir", "unlink", "rename",
                    "replace", "rmdir")),
            (os, ("mkdir", "makedirs", "remove", "unlink", "rename", "replace", "rmdir",
                  "removedirs", "chmod", "chown", "link", "symlink", "truncate")),
        ):
            for name in names:
                if hasattr(owner, name):
                    self.stack.enter_context(mock.patch.object(
                        owner, name, self.forbidden(f"{owner.__name__}.{name}")))

        denied_write = self.forbidden("file write")

        def read_only_open(original):
            def guarded(file, mode="r", *args, **kwargs):
                if any(flag in mode for flag in "wax+"):
                    denied_write(file, mode)
                return original(file, mode, *args, **kwargs)
            return guarded

        self.stack.enter_context(mock.patch.object(builtins, "open", read_only_open(builtins.open)))
        self.stack.enter_context(mock.patch.object(io, "open", read_only_open(io.open)))
        original_os_open = os.open

        def guarded_os_open(path, flags, *args, **kwargs):
            if flags & (os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_TRUNC):
                denied_write(path, flags)
            return original_os_open(path, flags, *args, **kwargs)

        self.stack.enter_context(mock.patch.object(os, "open", guarded_os_open))
        self.helper = self.load_source("_portability_unit_helper", "portability.py")
        self.assertEqual(dict(os.environ), {})

    def tearDown(self):
        for call in self.forbidden_calls:
            call.assert_not_called()

    def forbidden(self, description):
        result = mock.Mock(name=description, side_effect=AssertionError(
            f"Forbidden in offline portability tests: {description}"))
        self.forbidden_calls.append(result)
        return result

    @contextmanager
    def no_data_access(self):
        with ExitStack() as stack:
            for owner, names in (
                (builtins, ("open",)),
                (io, ("open",)),
                (os, ("open", "listdir", "scandir")),
                (Path, ("open", "read_text", "read_bytes", "is_file", "is_dir", "exists",
                        "glob", "rglob", "iterdir")),
            ):
                for name in names:
                    stack.enter_context(mock.patch.object(
                        owner, name, self.forbidden(f"data access: {owner.__name__}.{name}")))
            yield

    @contextmanager
    def no_environment_access(self):
        with ExitStack() as stack:
            for name in ("getenv", "getenvb", "putenv", "unsetenv"):
                if hasattr(os, name):
                    stack.enter_context(mock.patch.object(
                        os, name, self.forbidden(f"environment access: {name}")))
            for name in ("__getitem__", "__setitem__", "__delitem__", "__iter__", "__len__",
                         "__contains__", "get", "copy", "keys", "values", "items"):
                stack.enter_context(mock.patch.object(
                    type(os.environ), name, self.forbidden(f"environment access: {name}")))
            yield

    def prepared_source(self, name, filename):
        path = DIRECTORY / filename
        code = compile(path.read_text(encoding="utf-8"), str(path), "exec")
        spec = importlib.util.spec_from_loader(name, loader=None, origin=str(path))
        module = importlib.util.module_from_spec(spec)
        module.__file__ = str(path)
        return module, code

    def load_source(self, name, filename):
        module, code = self.prepared_source(name, filename)
        with self.no_data_access():
            exec(code, module.__dict__)
        return module

    def cloud_module(self):
        # IQ requirements are composed by create_agent, not by load_foundry_config.
        with mock.patch.dict(sys.modules, {"portability": self.helper}):
            return self.load_source("_portability_unit_cloud", "create_agent.py")

    def assert_configuration_error(self, action, field):
        with self.no_data_access(), self.assertRaises(self.helper.ConfigurationError) as caught:
            action()
        self.assertIn(field, str(caught.exception))
        self.assertNotIn(AUTH_VALUES["AZURE_CLIENT_SECRET"], str(caught.exception))

    @contextmanager
    def fake_sdk(self):
        azure = types.ModuleType("azure")
        azure.__path__ = []
        identity = types.ModuleType("azure.identity")
        azure.identity = identity
        credential = mock.Mock(spec_set=("get_token", "close"))
        credential.get_token.return_value = types.SimpleNamespace(token="offline-foundry-token")
        for name in CREDENTIAL_NAMES:
            setattr(identity, name, mock.Mock(name=name, return_value=credential))
        identity.DefaultAzureCredential = self.forbidden("DefaultAzureCredential chain")
        identity.ChainedTokenCredential = self.forbidden("ChainedTokenCredential chain")
        modules = {"azure": azure, "azure.identity": identity}
        with mock.patch.dict(sys.modules, modules), mock.patch.object(self, "fake_azure", modules):
            yield identity, credential

    def assert_selected_credential(self, sdk, mode, config):
        expected = {
            "azure_cli": ("AzureCliCredential", {
                "tenant_id": config.get("AZURE_TENANT_ID"),
                "subscription": config.get("AZURE_SUBSCRIPTION_ID"),
            }),
            "service_principal": ("ClientSecretCredential", {
                "tenant_id": config.get("AZURE_TENANT_ID"),
                "client_id": config.get("AZURE_CLIENT_ID"),
                "client_secret": config.get("AZURE_CLIENT_SECRET"),
            }),
            "managed_identity": ("ManagedIdentityCredential", {
                "client_id": config.get("AZURE_CLIENT_ID"),
            }),
        }
        selected, kwargs = expected[mode]
        for name in CREDENTIAL_NAMES:
            constructor = getattr(sdk, name)
            if name == selected:
                constructor.assert_called_once_with(**kwargs)
            else:
                constructor.assert_not_called()
        sdk.DefaultAzureCredential.assert_not_called()
        sdk.ChainedTokenCredential.assert_not_called()


class ImportSafetyTests(OfflineTestCase):
    def assert_inert_import(self, filename, package):
        name = f"_portability_inert_package.{filename[:-3]}" if package else "_portability_inert_direct"
        module, code = self.prepared_source(name, filename)
        injected = {"portability": self.helper}
        if package:
            parent = types.ModuleType("_portability_inert_package")
            parent.__path__ = [str(DIRECTORY)]
            injected.update({
                parent.__name__: parent,
                parent.__name__ + ".portability": self.helper,
            })
        original_path = list(sys.path)
        deny_path_change = self.forbidden("sys.path mutation")

        class FrozenPath(list):
            def reject(self, *args, **kwargs):
                deny_path_change(*args, **kwargs)

            append = extend = insert = pop = remove = clear = sort = reverse = reject
            __setitem__ = __delitem__ = __iadd__ = __imul__ = reject

        frozen_path = FrozenPath(original_path)
        output, errors = io.StringIO(), io.StringIO()
        with mock.patch.dict(sys.modules, injected), \
                mock.patch.object(sys, "path", frozen_path), \
                mock.patch.object(sys, "stdout", output), \
                mock.patch.object(sys, "stderr", errors), \
                self.no_environment_access(), self.no_data_access():
            exec(code, module.__dict__)
            self.assertIs(sys.path, frozen_path)
            self.assertEqual(sys.path, original_path)
        self.assertEqual(output.getvalue(), "")
        self.assertEqual(errors.getvalue(), "")
        return module

    def test_portability_direct_import_has_no_side_effects(self):
        module = self.assert_inert_import("portability.py", package=False)
        self.assertTrue(issubclass(module.ConfigurationError, ValueError))
        self.assertTrue(callable(module.build_credential))

    def test_portability_package_import_has_no_side_effects(self):
        module = self.assert_inert_import("portability.py", package=True)
        self.assertTrue(callable(module.load_foundry_config))
        self.assertTrue(callable(module.foundry_token))

    def test_common_config_adapter_import_is_inert_direct_and_package(self):
        for package in (False, True):
            with self.subTest(package=package):
                module = self.assert_inert_import("create_agent.py", package)
                self.assertIs(module.ConfigurationError, self.helper.ConfigurationError)
                self.assertTrue(callable(module._cloud_config))


class ConfigurationTests(OfflineTestCase):
    def setUp(self):
        super().setUp()
        self.stack.enter_context(mock.patch.object(
            self.helper, "build_credential", self.forbidden("credential creation during configuration")))

    def test_require_environment_reports_all_missing_and_blank_names(self):
        with mock.patch.dict(os.environ, {"ONE": " ", "TWO": ""}, clear=True):
            with self.assertRaises(self.helper.ConfigurationError) as caught:
                self.helper.require_environment("ONE", "TWO", "THREE")
        for field in ("ONE", "TWO", "THREE"):
            self.assertIn(field, str(caught.exception))

    def test_require_environment_strips_values_and_returns_only_requested_names(self):
        values = {"ONE": " value-one \n", "TWO": "\tvalue-two ", "UNRELATED": "ignored"}
        with mock.patch.dict(os.environ, values, clear=True):
            self.assertEqual(self.helper.require_environment("ONE", "TWO"),
                             {"ONE": "value-one", "TWO": "value-two"})
            self.assertEqual(dict(os.environ), values)

    def test_require_values_rejects_each_missing_or_blank_field(self):
        for field, replacement, config in missing_variants(
                {"ONE": "one", "TWO": "two"}, ("ONE", "TWO")):
            with self.subTest(field=field, replacement=replacement):
                self.assert_configuration_error(
                    lambda: self.helper.require_values(config, "ONE", "TWO"), field)

    def test_require_values_accepts_explicit_values_without_mutation_or_env_reads(self):
        config = {"ONE": " one ", "TWO": "two"}
        original = dict(config)
        with self.no_environment_access():
            self.helper.require_values(config, "ONE", "TWO")
        self.assertEqual(config, original)

    def test_auth_config_requires_every_selected_field_and_mode(self):
        for mode in AUTH_FIELDS:
            for field, replacement, config in missing_variants(
                    environment(mode), ("AZURE_AUTH_MODE", *AUTH_FIELDS[mode])):
                with self.subTest(mode=mode, field=field, replacement=replacement), \
                        mock.patch.dict(os.environ, config, clear=True):
                    self.assert_configuration_error(self.helper.load_auth_config, field)

    def test_auth_config_returns_only_selected_fields_and_strips_values(self):
        for mode, fields in AUTH_FIELDS.items():
            config = {"AZURE_AUTH_MODE": f" {mode} ", **AUTH_VALUES, "UNRELATED": "ignored"}
            config.update({field: f" \t{AUTH_VALUES[field]}\n" for field in fields})
            with self.subTest(mode=mode), mock.patch.dict(os.environ, config, clear=True):
                self.assertEqual(self.helper.load_auth_config(), {
                    "AZURE_AUTH_MODE": mode, **{field: AUTH_VALUES[field] for field in fields},
                })

    def test_auth_config_rejects_invalid_modes_without_sdk_imports(self):
        for mode in INVALID_AUTH_MODES:
            with self.subTest(mode=mode), \
                    mock.patch.dict(os.environ, {"AZURE_AUTH_MODE": mode, **AUTH_VALUES}, clear=True):
                self.assert_configuration_error(self.helper.load_auth_config, "AZURE_AUTH_MODE")

    def test_auth_config_never_substitutes_other_modes_or_ambient_chain_fields(self):
        for mode, fields in AUTH_FIELDS.items():
            for field in fields:
                config = {
                    **AUTH_VALUES, "AZURE_AUTH_MODE": mode,
                    "MSI_ENDPOINT": "https://identity.invalid",
                    "IDENTITY_ENDPOINT": "https://identity.invalid",
                    "AZURE_FEDERATED_TOKEN_FILE": "must-not-read-token-file",
                }
                del config[field]
                with self.subTest(mode=mode, field=field), \
                        mock.patch.dict(os.environ, config, clear=True):
                    self.assert_configuration_error(self.helper.load_auth_config, field)

    def test_validate_auth_rejects_every_missing_field_without_environment_reads(self):
        for mode in AUTH_FIELDS:
            for field, replacement, config in missing_variants(
                    environment(mode), ("AZURE_AUTH_MODE", *AUTH_FIELDS[mode])):
                with self.subTest(mode=mode, field=field, replacement=replacement), \
                        self.no_environment_access():
                    self.assert_configuration_error(lambda: self.helper.validate_auth(config), field)

    def test_validate_auth_rejects_invalid_modes(self):
        for mode in INVALID_AUTH_MODES:
            with self.subTest(mode=mode):
                self.assert_configuration_error(
                    lambda: self.helper.validate_auth({"AZURE_AUTH_MODE": mode, **AUTH_VALUES}),
                    "AZURE_AUTH_MODE")

    def test_foundry_loader_requires_endpoint_agent_and_requested_extra_fields(self):
        required = ("FOUNDRY_PROJECT_ENDPOINT", "FOUNDRY_AGENT_NAME", "FOUNDRY_MODEL", "CM_CLIENT_ID")
        for field, replacement, config in missing_variants(environment(), required):
            with self.subTest(field=field, replacement=replacement), \
                    mock.patch.dict(os.environ, config, clear=True):
                self.assert_configuration_error(
                    lambda: self.helper.load_foundry_config("FOUNDRY_MODEL", "CM_CLIENT_ID"), field)

    def test_foundry_loader_normalizes_endpoint_and_does_not_mutate_environment(self):
        config = {name: f" \t{value}\n" for name, value in environment().items()}
        with mock.patch.dict(os.environ, config, clear=True):
            result = self.helper.load_foundry_config("FOUNDRY_MODEL", "CM_CLIENT_ID")
            self.assertEqual(dict(os.environ), config)
        expected = environment()
        expected.pop("IQ_MODE")
        expected["FOUNDRY_PROJECT_ENDPOINT"] = ENDPOINT
        self.assertEqual(result, expected)

    def test_foundry_loader_can_require_source_without_target_agent(self):
        config = environment()
        config.pop("FOUNDRY_AGENT_NAME")
        config["FOUNDRY_SOURCE_AGENT_NAME"] = "source-agent"
        with mock.patch.dict(os.environ, config, clear=True):
            result = self.helper.load_foundry_config("FOUNDRY_SOURCE_AGENT_NAME", require_agent=False)
        self.assertEqual(result["FOUNDRY_SOURCE_AGENT_NAME"], "source-agent")
        self.assertNotIn("FOUNDRY_AGENT_NAME", result)
        self.assertEqual(result["FOUNDRY_PROJECT_ENDPOINT"], ENDPOINT)

    def test_disabling_agent_requirement_does_not_disable_endpoint_or_extra_requirements(self):
        config = environment()
        config.pop("FOUNDRY_AGENT_NAME")
        config["FOUNDRY_SOURCE_AGENT_NAME"] = "source-agent"
        for field, replacement, values in missing_variants(
                config, ("FOUNDRY_PROJECT_ENDPOINT", "FOUNDRY_SOURCE_AGENT_NAME")):
            with self.subTest(field=field, replacement=replacement), \
                    mock.patch.dict(os.environ, values, clear=True):
                self.assert_configuration_error(
                    lambda: self.helper.load_foundry_config(
                        "FOUNDRY_SOURCE_AGENT_NAME", require_agent=False), field)

    def test_foundry_loader_rejects_invalid_endpoint_before_auth_configuration(self):
        for endpoint in INVALID_URLS:
            config = environment()
            config["FOUNDRY_PROJECT_ENDPOINT"] = endpoint
            with self.subTest(endpoint=endpoint), mock.patch.dict(os.environ, config, clear=True), \
                    mock.patch.object(self.helper, "load_auth_config",
                                      self.forbidden("auth lookup before endpoint validation")):
                self.assert_configuration_error(self.helper.load_foundry_config, "FOUNDRY_PROJECT_ENDPOINT")

    def test_local_common_configuration_is_complete_for_each_auth_mode(self):
        cloud = self.cloud_module()
        for mode in AUTH_FIELDS:
            config = environment(mode)
            with self.subTest(mode=mode), mock.patch.dict(os.environ, config, clear=True), \
                    self.no_data_access():
                result = cloud._cloud_config()
            expected = dict(config)
            expected["FOUNDRY_PROJECT_ENDPOINT"] = ENDPOINT
            self.assertEqual(result, expected)
            self.assertFalse(set(HYBRID_VALUES).intersection(result))

    def test_hybrid_common_configuration_is_complete_for_each_auth_mode(self):
        cloud = self.cloud_module()
        for mode in AUTH_FIELDS:
            config = environment(mode, "hybrid")
            with self.subTest(mode=mode), mock.patch.dict(os.environ, config, clear=True), \
                    self.no_data_access():
                result = cloud._cloud_config()
            expected = dict(config)
            expected["FOUNDRY_PROJECT_ENDPOINT"] = ENDPOINT
            expected["SEARCH_ENDPOINT"] = HYBRID_VALUES["SEARCH_ENDPOINT"].rstrip("/")
            self.assertEqual(result, expected)

    def test_common_configuration_requires_every_common_and_selected_auth_field(self):
        cloud = self.cloud_module()
        for iq_mode in ("local", "hybrid"):
            for mode, fields in AUTH_FIELDS.items():
                for field, replacement, config in missing_variants(
                        environment(mode, iq_mode), (*COMMON_FIELDS, *fields)):
                    with self.subTest(iq_mode=iq_mode, auth_mode=mode, field=field,
                                      replacement=replacement), \
                            mock.patch.dict(os.environ, config, clear=True):
                        self.assert_configuration_error(cloud._cloud_config, field)

    def test_hybrid_requires_each_search_and_bing_field(self):
        cloud = self.cloud_module()
        for mode in AUTH_FIELDS:
            for field, replacement, config in missing_variants(
                    environment(mode, "hybrid"), HYBRID_VALUES):
                with self.subTest(mode=mode, field=field, replacement=replacement), \
                        mock.patch.dict(os.environ, config, clear=True):
                    self.assert_configuration_error(cloud._cloud_config, field)

    def test_invalid_iq_modes_fail_without_imports_credentials_or_data_reads(self):
        cloud = self.cloud_module()
        for iq_mode in INVALID_IQ_MODES:
            config = environment()
            config.update(HYBRID_VALUES)
            config["IQ_MODE"] = iq_mode
            with self.subTest(iq_mode=iq_mode), mock.patch.dict(os.environ, config, clear=True):
                self.assert_configuration_error(cloud._cloud_config, "IQ_MODE")

    def test_invalid_auth_modes_fail_in_local_and_hybrid_configuration(self):
        cloud = self.cloud_module()
        for iq_mode in ("local", "hybrid"):
            for mode in INVALID_AUTH_MODES:
                config = {**environment(iq_mode=iq_mode), **AUTH_VALUES, "AZURE_AUTH_MODE": mode}
                with self.subTest(iq_mode=iq_mode, mode=mode), \
                        mock.patch.dict(os.environ, config, clear=True):
                    self.assert_configuration_error(cloud._cloud_config, "AZURE_AUTH_MODE")

    def test_invalid_foundry_urls_fail_in_local_and_hybrid_configuration(self):
        cloud = self.cloud_module()
        for iq_mode in ("local", "hybrid"):
            for endpoint in INVALID_URLS:
                config = {**environment(iq_mode=iq_mode), "FOUNDRY_PROJECT_ENDPOINT": endpoint}
                with self.subTest(iq_mode=iq_mode, endpoint=endpoint), \
                        mock.patch.dict(os.environ, config, clear=True):
                    self.assert_configuration_error(cloud._cloud_config, "FOUNDRY_PROJECT_ENDPOINT")

    def test_hybrid_rejects_invalid_search_urls_without_local_fallback(self):
        cloud = self.cloud_module()
        for endpoint in INVALID_URLS:
            config = {**environment(iq_mode="hybrid"), "SEARCH_ENDPOINT": endpoint}
            with self.subTest(endpoint=endpoint), mock.patch.dict(os.environ, config, clear=True):
                self.assert_configuration_error(cloud._cloud_config, "SEARCH_ENDPOINT")

    def test_local_mode_does_not_require_or_use_stale_hybrid_configuration(self):
        cloud = self.cloud_module()
        config = {**environment(), **{name: "invalid-unused-value" for name in HYBRID_VALUES}}
        with mock.patch.dict(os.environ, config, clear=True), self.no_data_access():
            result = cloud._cloud_config()
        self.assertEqual(result["IQ_MODE"], "local")
        self.assertFalse(set(HYBRID_VALUES).intersection(result))

    def test_configuration_is_reloaded_instead_of_cached_or_defaulted(self):
        cloud = self.cloud_module()
        with mock.patch.dict(os.environ, environment(), clear=True):
            self.assertEqual(cloud._cloud_config()["FOUNDRY_MODEL"], "offline-model")
        changed = environment("managed_identity", "hybrid")
        changed["FOUNDRY_MODEL"] = "second-offline-model"
        with mock.patch.dict(os.environ, changed, clear=True):
            result = cloud._cloud_config()
        self.assertEqual(result["FOUNDRY_MODEL"], "second-offline-model")
        self.assertEqual(result["IQ_MODE"], "hybrid")
        self.assertEqual(result["AZURE_AUTH_MODE"], "managed_identity")
        self.assert_configuration_error(cloud._cloud_config, "FOUNDRY_PROJECT_ENDPOINT")


class CredentialTests(OfflineTestCase):
    def check_credential(self, mode):
        config = environment(mode)
        original = dict(config)
        with self.fake_sdk() as (sdk, credential), self.no_environment_access(), self.no_data_access():
            result = self.helper.build_credential(config)
            self.assertIs(result, credential)
            self.assert_selected_credential(sdk, mode, config)
            credential.get_token.assert_not_called()
            credential.close.assert_not_called()
        self.assertEqual(config, original)

    def test_azure_cli_uses_exact_tenant_and_subscription_kwargs(self):
        self.check_credential("azure_cli")

    def test_service_principal_uses_exact_tenant_client_and_secret_kwargs(self):
        self.check_credential("service_principal")

    def test_managed_identity_uses_exact_user_assigned_client_id(self):
        self.check_credential("managed_identity")

    def test_selected_credential_ignores_other_identity_fields_and_ambient_auth(self):
        for mode in AUTH_FIELDS:
            config = {**environment(mode), **AUTH_VALUES}
            with self.subTest(mode=mode), \
                    mock.patch.dict(os.environ, {"AZURE_AUTH_MODE": "default", **AUTH_VALUES}, clear=True), \
                    self.fake_sdk() as (sdk, credential):
                self.assertIs(self.helper.build_credential(config), credential)
                self.assert_selected_credential(sdk, mode, config)

    def test_missing_mode_and_selected_fields_fail_before_any_sdk_import(self):
        for mode in AUTH_FIELDS:
            for field, replacement, config in missing_variants(
                    environment(mode), ("AZURE_AUTH_MODE", *AUTH_FIELDS[mode])):
                with self.subTest(mode=mode, field=field, replacement=replacement):
                    self.assert_configuration_error(lambda: self.helper.build_credential(config), field)

    def test_invalid_modes_fail_before_any_sdk_import(self):
        for mode in INVALID_AUTH_MODES:
            with self.subTest(mode=mode):
                self.assert_configuration_error(
                    lambda: self.helper.build_credential({"AZURE_AUTH_MODE": mode, **AUTH_VALUES}),
                    "AZURE_AUTH_MODE")

    def test_constructor_errors_propagate_without_credential_chain_fallback(self):
        for mode, name in zip(AUTH_FIELDS, CREDENTIAL_NAMES):
            error = RuntimeError("offline constructor failure")
            config = environment(mode)
            with self.subTest(mode=mode), self.fake_sdk() as (sdk, credential):
                getattr(sdk, name).side_effect = error
                with self.assertRaises(RuntimeError) as caught:
                    self.helper.build_credential(config)
                self.assertIs(caught.exception, error)
                self.assert_selected_credential(sdk, mode, config)
                credential.get_token.assert_not_called()
                credential.close.assert_not_called()


class FoundryTokenTests(OfflineTestCase):
    def test_token_uses_foundry_scope_and_closes_each_selected_credential_once(self):
        for mode in AUTH_FIELDS:
            config = environment(mode)
            with self.subTest(mode=mode), self.fake_sdk() as (sdk, credential), \
                    self.no_environment_access(), self.no_data_access():
                self.assertEqual(self.helper.foundry_token(config), "offline-foundry-token")
                self.assert_selected_credential(sdk, mode, config)
                self.assertEqual(credential.mock_calls, [
                    mock.call.get_token("https://ai.azure.com/.default"),
                    mock.call.close(),
                ])

    def test_token_acquisition_error_propagates_and_closes_without_fallback(self):
        for mode in AUTH_FIELDS:
            error = RuntimeError("offline token acquisition failure")
            config = environment(mode)
            with self.subTest(mode=mode), self.fake_sdk() as (sdk, credential):
                credential.get_token.side_effect = error
                with self.assertRaises(RuntimeError) as caught:
                    self.helper.foundry_token(config)
                self.assertIs(caught.exception, error)
                self.assert_selected_credential(sdk, mode, config)
                self.assertEqual(credential.mock_calls, [
                    mock.call.get_token("https://ai.azure.com/.default"),
                    mock.call.close(),
                ])

    def test_empty_tokens_fail_and_close_the_credential(self):
        for mode in AUTH_FIELDS:
            for empty_token in ("", None):
                with self.subTest(mode=mode, token=empty_token), self.fake_sdk() as (sdk, credential):
                    credential.get_token.return_value = types.SimpleNamespace(token=empty_token)
                    with self.assertRaisesRegex(RuntimeError, "empty.*token"):
                        self.helper.foundry_token(environment(mode))
                    credential.get_token.assert_called_once_with("https://ai.azure.com/.default")
                    credential.close.assert_called_once_with()
                    self.assert_selected_credential(sdk, mode, environment(mode))

    def test_token_property_failure_still_closes_the_credential(self):
        error = RuntimeError("offline token property failure")

        class BrokenToken:
            @property
            def token(self):
                raise error

        with self.fake_sdk() as (sdk, credential):
            credential.get_token.return_value = BrokenToken()
            with self.assertRaises(RuntimeError) as caught:
                self.helper.foundry_token(environment())
            self.assertIs(caught.exception, error)
            credential.get_token.assert_called_once_with("https://ai.azure.com/.default")
            credential.close.assert_called_once_with()
            self.assert_selected_credential(sdk, "azure_cli", environment())

    def test_close_failure_after_successful_token_is_not_swallowed_or_retried(self):
        error = RuntimeError("offline credential close failure")
        with self.fake_sdk() as (sdk, credential):
            credential.close.side_effect = error
            with self.assertRaises(RuntimeError) as caught:
                self.helper.foundry_token(environment())
            self.assertIs(caught.exception, error)
            self.assertEqual(credential.mock_calls, [
                mock.call.get_token("https://ai.azure.com/.default"),
                mock.call.close(),
            ])
            self.assert_selected_credential(sdk, "azure_cli", environment())

    def test_close_failure_retains_token_error_as_exception_context_without_retry(self):
        token_error = RuntimeError("offline token acquisition failure")
        close_error = RuntimeError("offline credential close failure")
        with self.fake_sdk() as (sdk, credential):
            credential.get_token.side_effect = token_error
            credential.close.side_effect = close_error
            with self.assertRaises(RuntimeError) as caught:
                self.helper.foundry_token(environment())
            self.assertIs(caught.exception, close_error)
            self.assertIs(caught.exception.__context__, token_error)
            self.assertEqual(credential.mock_calls, [
                mock.call.get_token("https://ai.azure.com/.default"),
                mock.call.close(),
            ])
            self.assert_selected_credential(sdk, "azure_cli", environment())

    def test_missing_endpoint_fails_before_building_a_credential(self):
        for field, replacement, config in missing_variants(environment(), ("FOUNDRY_PROJECT_ENDPOINT",)):
            with self.subTest(replacement=replacement), mock.patch.object(
                    self.helper, "build_credential", self.forbidden("credential before endpoint validation")):
                self.assert_configuration_error(lambda: self.helper.foundry_token(config), field)

    def test_invalid_endpoint_fails_before_building_a_credential(self):
        for endpoint in INVALID_URLS:
            config = {**environment(), "FOUNDRY_PROJECT_ENDPOINT": endpoint}
            with self.subTest(endpoint=endpoint), mock.patch.object(
                    self.helper, "build_credential", self.forbidden("credential before URL validation")):
                self.assert_configuration_error(
                    lambda: self.helper.foundry_token(config), "FOUNDRY_PROJECT_ENDPOINT")

    def test_missing_auth_fields_fail_before_sdk_imports_or_token_requests(self):
        for mode in AUTH_FIELDS:
            for field, replacement, config in missing_variants(
                    environment(mode), ("AZURE_AUTH_MODE", *AUTH_FIELDS[mode])):
                with self.subTest(mode=mode, field=field, replacement=replacement):
                    self.assert_configuration_error(lambda: self.helper.foundry_token(config), field)

    def test_invalid_auth_modes_fail_before_sdk_imports_or_token_requests(self):
        for mode in INVALID_AUTH_MODES:
            config = {**environment(), "AZURE_AUTH_MODE": mode}
            with self.subTest(mode=mode):
                self.assert_configuration_error(lambda: self.helper.foundry_token(config), "AZURE_AUTH_MODE")

    def test_credential_constructor_failure_is_not_masked_by_cleanup(self):
        for mode, name in zip(AUTH_FIELDS, CREDENTIAL_NAMES):
            error = RuntimeError("offline credential initialization failure")
            config = environment(mode)
            with self.subTest(mode=mode), self.fake_sdk() as (sdk, credential):
                getattr(sdk, name).side_effect = error
                with self.assertRaises(RuntimeError) as caught:
                    self.helper.foundry_token(config)
                self.assertIs(caught.exception, error)
                self.assert_selected_credential(sdk, mode, config)
                credential.get_token.assert_not_called()
                credential.close.assert_not_called()


class UrlTests(OfflineTestCase):
    def test_https_validation_rejects_malformed_or_unsafe_urls(self):
        for endpoint in INVALID_URLS:
            with self.subTest(endpoint=endpoint):
                self.assert_configuration_error(
                    lambda: self.helper.require_https_url("TEST_ENDPOINT", endpoint), "TEST_ENDPOINT")

    def test_https_validation_accepts_explicit_hosts_ports_and_project_paths(self):
        for endpoint in (ENDPOINT, ENDPOINT + "///", "https://foundry.invalid:443/project/",
                         "https://[::1]:8443/project/"):
            with self.subTest(endpoint=endpoint), self.no_environment_access():
                self.assertEqual(self.helper.require_https_url("TEST_ENDPOINT", endpoint),
                                 endpoint.rstrip("/"))

    def test_agent_url_normalizes_endpoint_and_encodes_agent_name(self):
        config = environment()
        config["FOUNDRY_AGENT_NAME"] = "agent / name?#%"
        original = dict(config)
        with self.no_environment_access():
            self.assertEqual(self.helper.agent_url(config),
                             ENDPOINT + "/agents/agent%20%2F%20name%3F%23%25")
        self.assertEqual(config, original)

    def test_agent_url_allows_explicit_override_without_configured_agent(self):
        config = {"FOUNDRY_PROJECT_ENDPOINT": ENDPOINT + "/"}
        self.assertEqual(self.helper.agent_url(config, "source / agent"),
                         ENDPOINT + "/agents/source%20%2F%20agent")

    def test_agent_url_rejects_missing_endpoint_or_agent(self):
        for field, replacement, config in missing_variants(
                environment(), ("FOUNDRY_PROJECT_ENDPOINT", "FOUNDRY_AGENT_NAME")):
            with self.subTest(field=field, replacement=replacement):
                self.assert_configuration_error(lambda: self.helper.agent_url(config), field)

    def test_agent_url_rejects_blank_override_and_unsafe_endpoint(self):
        for name in ("", " \t "):
            with self.subTest(name=name):
                with self.assertRaises(self.helper.ConfigurationError):
                    self.helper.agent_url(environment(), name)
        for endpoint in INVALID_URLS:
            with self.subTest(endpoint=endpoint):
                self.assert_configuration_error(
                    lambda: self.helper.agent_url({**environment(), "FOUNDRY_PROJECT_ENDPOINT": endpoint}),
                    "FOUNDRY_PROJECT_ENDPOINT")


class ToolChoiceTests(OfflineTestCase):
    def assert_choice(self, choice, tools, expected):
        before = json.dumps({"choice": choice, "tools": tools}, sort_keys=True)
        with self.no_environment_access(), self.no_data_access():
            self.assertIs(self.helper.compatible_tool_choice(choice, tools), expected)
        self.assertEqual(json.dumps({"choice": choice, "tools": tools}, sort_keys=True), before)

    def test_generic_choices_are_compatible_without_tools(self):
        for choice in (None, "auto", "none", "required"):
            with self.subTest(choice=choice):
                self.assert_choice(choice, [], True)

    def test_mcp_matches_retained_label_and_allowed_name(self):
        for allowed in (None, ["search"], {"tool_names": ["search"], "read_only": True}):
            tools = [{"type": "mcp", "server_label": "kb-policy", "allowed_tools": allowed}]
            for choice in (
                {"type": "mcp", "server_label": "kb-policy"},
                {"type": "mcp", "server_label": "kb-policy", "name": None},
                {"type": "mcp", "server_label": "kb-policy", "name": "search"},
            ):
                with self.subTest(allowed=allowed, choice=choice):
                    self.assert_choice(choice, tools, True)
            with self.subTest(allowed=allowed):
                self.assert_choice(
                    {"type": "mcp", "server_label": "kb-policy", "name": "excluded"},
                    tools, allowed is None)
                self.assert_choice(
                    {"type": "mcp", "server_label": "excluded", "name": "search"}, tools, False)

    def test_mcp_empty_allowlists_reject_named_selections(self):
        for allowed in ([], {"tool_names": []}):
            with self.subTest(allowed=allowed):
                self.assert_choice(
                    {"type": "mcp", "server_label": "WorkIQMail", "name": "read_mail"},
                    [{"type": "mcp", "server_label": "WorkIQMail", "allowed_tools": allowed}],
                    False)

    def test_sdk_supported_web_choices_require_exact_retained_type(self):
        for kind in ("web_search_preview", "web_search_preview_2025_03_11"):
            choice = {"type": kind}
            with self.subTest(kind=kind):
                self.assert_choice(choice, [{"type": kind}], True)
                self.assert_choice(choice, [], False)
                self.assert_choice(choice, [{"type": "web_search"}], False)
                other = ("web_search_preview" if kind.endswith("2025_03_11")
                         else "web_search_preview_2025_03_11")
                self.assert_choice(choice, [{"type": other}], False)
                for extra in ("name", "server_label", "unknown"):
                    self.assert_choice({**choice, extra: "unexpected"}, [{"type": kind}], False)

    def test_tool_definitions_without_supported_choice_shapes_cannot_be_forced(self):
        for kind in ("web_search", "web_search_2025_08_26", "bing_grounding",
                     "fabric_iq_preview", "work_iq_preview", "unknown"):
            with self.subTest(kind=kind):
                self.assert_choice({"type": kind}, [{"type": kind}], False)

    def test_allowed_tools_requires_every_selection_to_be_retained(self):
        tools = [
            {"type": "mcp", "server_label": "kb-policy", "allowed_tools": ["search"]},
            {"type": "web_search_preview"},
            {"type": "web_search_preview_2025_03_11"},
        ]
        selections = [
            {"type": "mcp", "server_label": "kb-policy", "name": "search"},
            {"type": "web_search_preview"},
            {"type": "web_search_preview_2025_03_11"},
        ]
        for mode in ("auto", "required"):
            with self.subTest(mode=mode):
                choice = {"type": "allowed_tools", "mode": mode, "tools": selections}
                self.assert_choice(choice, tools, True)
                for index in range(len(tools)):
                    self.assert_choice(choice, tools[:index] + tools[index + 1:], False)
                self.assert_choice(
                    {**choice, "tools": selections + [
                        {"type": "mcp", "server_label": "kb-policy", "name": "excluded"},
                    ]}, tools, False)

    def test_malformed_and_excluded_choices_fail_closed(self):
        tools = [
            {"type": "mcp", "server_label": "kb-policy", "allowed_tools": ["search"]},
            {"type": "web_search_preview"},
        ]
        for choice in (
            "unknown", "", False, 1, [], {},
            {"type": []}, {"type": None},
            {"type": "function", "name": "excluded"},
            {"type": "function", "function": {"name": "excluded"}},
            {"type": "code_interpreter"},
            {"type": "mcp"},
            {"type": "mcp", "server_label": ""},
            {"type": "mcp", "server_label": " \t"},
            {"type": "mcp", "server_label": ["kb-policy"]},
            {"type": "mcp", "server_label": "KB-policy"},
            {"type": "mcp", "server_label": "kb-policy", "name": ""},
            {"type": "mcp", "server_label": "kb-policy", "name": " \t"},
            {"type": "mcp", "server_label": "kb-policy", "name": ["search"]},
            {"type": "mcp", "server_label": "kb-policy", "unknown": True},
            {"type": "allowed_tools", "mode": "auto"},
            {"type": "allowed_tools", "tools": [{"type": "web_search_preview"}]},
            {"type": "allowed_tools", "mode": "none", "tools": [{"type": "web_search_preview"}]},
            {"type": "allowed_tools", "mode": "auto", "tools": [], "unknown": True},
            *({"type": "allowed_tools", "mode": "auto", "tools": selections} for selections in (
                [], None, {}, "auto", ["auto"], [None], [{"type": "allowed_tools"}],
            )),
        ):
            with self.subTest(choice=choice):
                self.assert_choice(choice, tools, False)


if __name__ == "__main__":
    with mock.patch.dict(os.environ, {}, clear=True):
        unittest.main()
