"""Offline native unittest coverage for the three standalone Fabric entrypoints."""

import ast
import base64
import builtins
from contextlib import contextmanager, redirect_stderr, redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
import runpy
import sys
import types
import unittest
from unittest.mock import MagicMock, Mock, patch

from test_infra_portability import no_external_effects


FABRIC = Path(__file__).resolve().parents[2] / "data" / "fabric-iq"
TENANT = "11111111-1111-4111-8111-111111111111"
WORKSPACE = "22222222-2222-4222-8222-222222222222"
LAKEHOUSE = "33333333-3333-4333-8333-333333333333"
DEPLOY_ENV = {
    "AZURE_TENANT_ID": TENANT,
    "FABRIC_WORKSPACE_NAME": "bank_workspace",
    "FABRIC_LAKEHOUSE_NAME": "bank_lakehouse",
    "FABRIC_CAPACITY_NAME": "bank_capacity",
    "FABRIC_LOAD_NOTEBOOK_NAME": "bank_load",
    "FABRIC_SEMANTIC_NOTEBOOK_NAME": "bank_semantic",
    "FABRIC_SEMANTIC_MODEL_NAME": "bank_model",
}
NOTEBOOK_ENV = {
    "FABRIC_WORKSPACE_ID": WORKSPACE,
    "FABRIC_LAKEHOUSE_ID": LAKEHOUSE,
    "FABRIC_LAKEHOUSE_NAME": "bank_lakehouse",
    "FABRIC_SEMANTIC_MODEL_NAME": "bank_model",
}
NAMES = ("deploy_fabric", "load_client_intel_fabric", "create_semantic_model_fabric")


@contextmanager
def no_runtime():
    real_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name.split(".")[0] in ("azure", "requests", "pyspark", "sempy_labs", "notebookutils"):
            raise AssertionError(f"Runtime imported before configuration: {name}")
        return real_import(name, *args, **kwargs)

    with no_external_effects(), patch("builtins.__import__", side_effect=guarded_import):
        yield


def load(name):
    spec = importlib.util.spec_from_file_location(f"_fabric_test_{name}", FABRIC / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@contextmanager
def offline_runtime(modules):
    real_import = builtins.__import__
    with no_external_effects(), patch("builtins.__import__", side_effect=real_import):
        with patch.dict(sys.modules, modules):
            yield


with no_runtime():
    DEPLOY, LOADER, SEMANTIC = [load(name) for name in NAMES]


def config(only=None, status=False, capacity=None, env=None):
    return DEPLOY.DeploymentConfig(
        types.SimpleNamespace(only=only, status=status, capacity=capacity),
        DEPLOY_ENV if env is None else env,
    )


def response(status=200, body=None, headers=None):
    return types.SimpleNamespace(
        status_code=status, content=b"body" if body is not None else b"",
        headers={"Content-Type": "application/json", **(headers or {})},
        json=lambda: body, text="test response",
    )


class ConfigurationTests(unittest.TestCase):
    def test_imports_do_not_read_environment_or_create_runtime(self):
        class Unreadable(dict):
            def get(self, *args, **kwargs):
                raise AssertionError("Import read deployment environment")
        with no_runtime(), patch.object(os, "environ", Unreadable()):
            for name in NAMES:
                with self.subTest(name=name):
                    load(name)

    def test_main_guards_fail_closed_without_settings(self):
        for name in NAMES:
            with self.subTest(name=name), no_runtime(), patch.dict(os.environ, {}, clear=True):
                with patch.object(sys, "argv", [name]), redirect_stderr(io.StringIO()):
                    with self.assertRaises((SystemExit, ValueError)):
                        runpy.run_path(str(FABRIC / f"{name}.py"), run_name="__main__")

    def test_every_deploy_setting_missing_or_blank_precedes_runtime(self):
        for key in DEPLOY_ENV:
            for value in (None, "", " \t "):
                env = dict(DEPLOY_ENV)
                if value is None:
                    del env[key]
                else:
                    env[key] = value
                with self.subTest(key=key, value=value), no_runtime():
                    stderr = io.StringIO()
                    with redirect_stderr(stderr), self.assertRaises(SystemExit) as raised:
                        DEPLOY.main([], environ=env)
                    self.assertEqual(raised.exception.code, 2)
                    self.assertIn(key, stderr.getvalue())

    def test_every_notebook_setting_missing_or_blank_precedes_runtime(self):
        for module in (LOADER, SEMANTIC):
            for key in module.REQUIRED_ENV:
                for value in (None, "", " "):
                    env = dict(NOTEBOOK_ENV)
                    if value is None:
                        del env[key]
                    else:
                        env[key] = value
                    with self.subTest(module=module.__name__, key=key, value=value), no_runtime():
                        with self.assertRaisesRegex(ValueError, key):
                            module.main(environ=env)

    def test_invalid_ids_and_names_precede_runtime(self):
        for key in ("FABRIC_WORKSPACE_ID", "FABRIC_LAKEHOUSE_ID"):
            for value in ("bad", "00000000-0000-0000-0000-000000000000", "{" + WORKSPACE + "}"):
                for module in (LOADER, SEMANTIC):
                    with self.subTest(key=key, value=value), no_runtime():
                        with self.assertRaisesRegex(ValueError, key):
                            module.main(environ={**NOTEBOOK_ENV, key: value})
        for key, value in (
            ("AZURE_TENANT_ID", "bad"),
            ("AZURE_TENANT_ID", "00000000-0000-0000-0000-000000000000"),
            ("FABRIC_WORKSPACE_NAME", "bad\nname"),
            ("FABRIC_LAKEHOUSE_NAME", "bank;drop"),
            ("FABRIC_SEMANTIC_MODEL_NAME", "bad\nname"),
            ("FABRIC_SEMANTIC_NOTEBOOK_NAME", DEPLOY_ENV["FABRIC_LOAD_NOTEBOOK_NAME"]),
        ):
            with self.subTest(key=key), no_runtime(), redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    DEPLOY.main([], environ={**DEPLOY_ENV, key: value})
        with no_runtime(), self.assertRaisesRegex(ValueError, "FABRIC_LAKEHOUSE_NAME"):
            LOADER.main(environ={**NOTEBOOK_ENV, "FABRIC_LAKEHOUSE_NAME": "bank.lake"})
        with no_runtime(), self.assertRaisesRegex(ValueError, "FABRIC_SEMANTIC_MODEL_NAME"):
            SEMANTIC.main(environ={**NOTEBOOK_ENV, "FABRIC_SEMANTIC_MODEL_NAME": "bad\nname"})

    def test_mode_specific_requirements_and_explicit_capacity(self):
        base = {key: DEPLOY_ENV[key] for key in (
            "AZURE_TENANT_ID", "FABRIC_WORKSPACE_NAME", "FABRIC_LAKEHOUSE_NAME",
        )}
        with no_runtime():
            self.assertEqual(config(status=True, env=base).steps, [])
            self.assertEqual(config(only="upload", env=base).steps, ["upload"])
            self.assertEqual(config(only="workspace", capacity="explicit_capacity", env=base).capacity, "explicit_capacity")
            with self.assertRaisesRegex(ValueError, "FABRIC_CAPACITY_NAME"):
                config(only="workspace", capacity="", env=DEPLOY_ENV)

    def test_partial_notebook_deploy_rejects_configured_name_collision(self):
        env = {**DEPLOY_ENV, "FABRIC_SEMANTIC_NOTEBOOK_NAME": DEPLOY_ENV["FABRIC_LOAD_NOTEBOOK_NAME"]}
        for mode in ("notebook", "semantic-model"):
            with self.subTest(mode=mode), no_runtime(), redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    DEPLOY.main(["--only", mode], environ=env)

    def test_missing_inputs_precede_credentials(self):
        with no_runtime(), patch.object(Path, "is_file", return_value=False):
            err = io.StringIO()
            with redirect_stderr(err), self.assertRaises(SystemExit):
                DEPLOY.main([], environ=DEPLOY_ENV)
            self.assertIn("Missing deployment inputs", err.getvalue())
            self.assertIn("clients.csv", err.getvalue())

    def test_loader_requires_explicit_spark_session(self):
        with no_runtime(), self.assertRaisesRegex(RuntimeError, "Fabric notebook"):
            LOADER.main(environ=NOTEBOOK_ENV)

    def test_missing_semantic_dependency_does_not_install_or_write(self):
        with no_external_effects(), patch.dict(sys.modules, {"sempy_labs": None}):
            with self.assertRaisesRegex(RuntimeError, "Install semantic-link-labs"):
                SEMANTIC.main(environ=NOTEBOOK_ENV)

    def test_status_uses_tenant_bound_credentials_and_no_write_methods(self):
        azure, identity = types.ModuleType("azure"), types.ModuleType("azure.identity")
        identity.AzureCliCredential = Mock()
        http, deployment = Mock(), Mock()
        with offline_runtime({"azure": azure, "azure.identity": identity, "requests": http}):
            with patch.object(DEPLOY, "FabricDeployment", return_value=deployment) as factory:
                DEPLOY.main(["--status"], environ=DEPLOY_ENV)
        identity.AzureCliCredential.assert_called_once_with(tenant_id=TENANT)
        deployment.status.assert_called_once_with()
        self.assertEqual(len(deployment.mock_calls), 1)
        self.assertEqual(factory.call_args.args[0].workspace, "bank_workspace")


class FabricRequestTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(no_external_effects())
        self.http = Mock()
        self.credential = Mock()
        self.credential.get_token.return_value.token = "offline-token"
        self.api = DEPLOY.Api("https://api.fabric.microsoft.com", DEPLOY.FABRIC_API, self.credential, self.http)
        self.deployment = DEPLOY.FabricDeployment(config(), self.credential, self.http)

    def test_request_payload_and_audience(self):
        self.http.request.return_value = response(201, {"id": WORKSPACE})
        body = {"displayName": "bank_workspace"}
        self.assertEqual(self.api.call("POST", "/workspaces", json_body=body), {"id": WORKSPACE})
        self.credential.get_token.assert_called_once_with("https://api.fabric.microsoft.com/.default")
        call = self.http.request.call_args
        self.assertEqual(call.args, ("POST", DEPLOY.FABRIC_API + "/workspaces"))
        self.assertEqual(call.kwargs["json"], body)
        self.assertEqual(call.kwargs["headers"]["Authorization"], "Bearer offline-token")
        self.assertFalse(call.kwargs["allow_redirects"])

    def test_unsafe_url_rejected_before_token(self):
        for path in ("https://outside.example.invalid/path", "//outside.example.invalid",
                     "http://api.fabric.microsoft.com/v1/workspaces",
                     "https://api.fabric.microsoft.com.evil/v1/workspaces",
                     "https://api.fabric.microsoft.com/v1/workspaces#fragment"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.api.call("GET", path)
        self.credential.get_token.assert_not_called()
        self.http.request.assert_not_called()

    def test_empty_token_fails_before_request(self):
        self.credential.get_token.return_value.token = ""
        with self.assertRaisesRegex(RuntimeError, "Empty token"):
            self.api.call("GET", "/workspaces")
        self.http.request.assert_not_called()

    def test_lro_polls_and_reads_result(self):
        location = DEPLOY.FABRIC_API + "/operations/offline"
        self.http.request.return_value = response(202, headers={"Location": location, "Retry-After": "0"})
        self.http.get.side_effect = [
            response(200, {"status": "Succeeded"}),
            response(200, {"id": WORKSPACE}),
        ]
        with patch.object(DEPLOY.time, "sleep"):
            self.assertEqual(self.api.call("POST", "/workspaces"), {"id": WORKSPACE})
        self.assertEqual(self.http.get.call_args.args[0], location + "/result")

    def test_lro_rejects_external_location(self):
        self.http.request.return_value = response(202, headers={"Location": "https://outside.example.invalid"})
        with self.assertRaises(ValueError):
            self.api.call("POST", "/workspaces")
        self.http.get.assert_not_called()

    def test_lro_failure_is_not_success(self):
        self.http.request.return_value = response(202, headers={"Location": DEPLOY.FABRIC_API + "/operations/offline"})
        self.http.get.return_value = response(200, {"status": "Failed"})
        with patch.object(DEPLOY.time, "sleep"), self.assertRaisesRegex(RuntimeError, "LRO failed"):
            self.api.call("POST", "/workspaces")

    def test_collection_pagination_and_duplicate_identity(self):
        second = DEPLOY.FABRIC_API + "/workspaces?continuationToken=next"
        self.http.request.side_effect = [
            response(body={"value": [{"displayName": "other"}], "continuationUri": second}),
            response(body={"value": [{"displayName": "bank_workspace", "id": WORKSPACE}]}),
        ]
        self.assertEqual(DEPLOY.find(self.api.collection("/workspaces"), "bank_workspace")["id"], WORKSPACE)
        with self.assertRaisesRegex(RuntimeError, "Ambiguous"):
            DEPLOY.find([{"displayName": "bank_workspace"}] * 2, "bank_workspace")

    def test_capacity_validation_precedes_workspace_write(self):
        self.deployment.fab = Mock()
        for capacities in ([], [{"displayName": "bank_capacity", "state": "Paused"}]):
            self.deployment.fab.collection.return_value = capacities
            with self.assertRaises(RuntimeError):
                self.deployment.ensure_workspace("bank_capacity")
            self.deployment.fab.call.assert_not_called()

    def test_workspace_payload_and_assignment(self):
        fab = self.deployment.fab = Mock()
        fab.collection.side_effect = [[{
            "displayName": "bank_capacity", "state": "Active",
            "id": "capacity-id", "sku": "F2", "region": "configured-region",
        }], []]
        fab.call.side_effect = [{"id": WORKSPACE}, {"capacityId": None}, None]
        with redirect_stdout(io.StringIO()):
            self.assertEqual(self.deployment.ensure_workspace("bank_capacity"), WORKSPACE)
        self.assertEqual(fab.call.call_args_list[0].kwargs["json_body"]["displayName"], "bank_workspace")
        self.assertEqual(fab.call.call_args_list[-1].kwargs["json_body"], {"capacityId": "capacity-id"})

    def test_upload_preserves_onelake_create_append_flush(self):
        self.deployment.lake = Mock()
        with patch.object(DEPLOY, "CSVS", ["clients.csv"]), patch.object(Path, "read_bytes", return_value=b"one,two\n"):
            with redirect_stdout(io.StringIO()):
                self.deployment.upload_csvs(WORKSPACE, LAKEHOUSE)
        calls = self.deployment.lake.call.call_args_list
        self.assertEqual([c.args[0] for c in calls], ["PUT", "PATCH", "PATCH"])
        self.assertIn(f"/{WORKSPACE}/{LAKEHOUSE}/Files/client-intel/clients.csv", calls[0].args[1])
        self.assertEqual(calls[1].kwargs["data"], b"one,two\n")
        self.assertEqual(calls[2].kwargs["params"], {"action": "flush", "position": "8"})

    def test_notebook_definition_contains_settings_not_credentials(self):
        for source in ("load_client_intel_fabric.py", "create_semantic_model_fabric.py"):
            with self.subTest(source=source):
                payload = self.deployment.notebook_payload(WORKSPACE, LAKEHOUSE, source)
                notebook = json.loads(base64.b64decode(payload))
                metadata = notebook["metadata"]["dependencies"]["lakehouse"]
                self.assertEqual(metadata["default_lakehouse"], LAKEHOUSE)
                self.assertEqual(metadata["default_lakehouse_workspace_id"], WORKSPACE)
                with patch.dict(os.environ, {}, clear=True):
                    exec("".join(notebook["cells"][0]["source"]), {})
                    target = SEMANTIC if source.startswith("create_") else LOADER
                    settings = target.load_config()
                    self.assertEqual(settings["FABRIC_WORKSPACE_ID"], WORKSPACE)
                    self.assertNotIn("AZURE_TENANT_ID", os.environ)
                ast.parse("".join(notebook["cells"][1]["source"]))

    def test_notebook_settings_are_quoted_as_data(self):
        value = "bank_model'); raise RuntimeError('injected"
        self.deployment.config.semantic_model = value
        payload = self.deployment.notebook_payload(WORKSPACE, LAKEHOUSE, "create_semantic_model_fabric.py")
        notebook = json.loads(base64.b64decode(payload))
        with patch.dict(os.environ, {}, clear=True):
            exec("".join(notebook["cells"][0]["source"]), {})
            self.assertEqual(os.environ["FABRIC_SEMANTIC_MODEL_NAME"], value)

    def test_skip_run_also_skips_semantic_execution(self):
        with patch.object(self.deployment, "ensure_notebook", return_value="notebook") as ensure:
            with patch.object(self.deployment, "run_notebook") as run:
                self.deployment.ensure_semantic_model(WORKSPACE, LAKEHOUSE, skip_run=True)
        ensure.assert_called_once()
        run.assert_not_called()

    def test_run_notebook_requires_location_and_polls_completion(self):
        self.http.post.return_value = response(202)
        with redirect_stdout(io.StringIO()), self.assertRaisesRegex(RuntimeError, "no Location"):
            self.deployment.run_notebook(WORKSPACE, "notebook")
        location = DEPLOY.FABRIC_API + "/jobs/offline"
        self.http.post.return_value = response(202, headers={"Location": location})
        self.http.get.return_value = response(body={"status": "Completed"})
        with patch.object(DEPLOY.time, "sleep"), redirect_stdout(io.StringIO()):
            self.deployment.run_notebook(WORKSPACE, "notebook")
        self.assertEqual(self.http.post.call_args.kwargs["params"], {"jobType": "RunNotebook"})


class NotebookTests(unittest.TestCase):
    def runtime(self, **overrides):
        return types.SimpleNamespace(context={
            "currentWorkspaceId": WORKSPACE,
            "defaultLakehouseId": LAKEHOUSE,
            "defaultLakehouseName": "bank_lakehouse", **overrides,
        })

    def test_wrong_notebook_context_does_not_write(self):
        spark = Mock()
        for key in ("currentWorkspaceId", "defaultLakehouseId", "defaultLakehouseName"):
            runtime = self.runtime(**{key: "wrong"})
            with offline_runtime({"notebookutils": types.SimpleNamespace(runtime=runtime)}):
                with self.assertRaisesRegex(ValueError, key):
                    LOADER.main(environ=NOTEBOOK_ENV, spark_session=spark)
        self.assertEqual(spark.mock_calls, [])

    def test_loader_uses_configured_database_and_session(self):
        spark = Mock()
        with offline_runtime({"notebookutils": types.SimpleNamespace(runtime=self.runtime())}):
            with patch.object(LOADER, "load_tables") as load_tables:
                LOADER.main(environ=NOTEBOOK_ENV, spark_session=spark)
        spark.catalog.setCurrentDatabase.assert_called_once_with("bank_lakehouse")
        self.assertIs(load_tables.call_args.args[0], spark)
        self.assertEqual(load_tables.call_args.args[1]["FABRIC_LAKEHOUSE_ID"], LAKEHOUSE)

    @contextmanager
    def semantic_runtime(self, generator):
        tom = MagicMock()
        tom.all_measures.return_value = []
        connect = Mock(return_value=MagicMock())
        connect.return_value.__enter__.return_value = tom
        fs = Mock()
        modules = {
            "sempy_labs": types.SimpleNamespace(directlake=types.SimpleNamespace(generate_direct_lake_semantic_model=generator)),
            "sempy_labs.tom": types.SimpleNamespace(connect_semantic_model=connect),
            "notebookutils": types.SimpleNamespace(mssparkutils=types.SimpleNamespace(fs=fs)),
        }
        with offline_runtime(modules), redirect_stdout(io.StringIO()):
            yield tom, connect, fs

    def test_semantic_request_keeps_explicit_scope_relationships_and_measures(self):
        calls = []

        def generate(dataset, source, tables, workspace, source_workspace, source_type, overwrite, refresh):
            calls.append(dict(locals()))

        with self.semantic_runtime(generate) as (tom, connect, fs):
            SEMANTIC.main(environ=NOTEBOOK_ENV)
        self.assertEqual(calls[0]["source"], LAKEHOUSE)
        self.assertEqual(calls[0]["workspace"], WORKSPACE)
        self.assertEqual(calls[0]["source_workspace"], WORKSPACE)
        self.assertEqual(calls[0]["dataset"], "bank_model")
        self.assertEqual(len(calls[0]["tables"]), 13)
        connect.assert_called_once_with(dataset="bank_model", workspace=WORKSPACE, readonly=False)
        self.assertEqual(tom.add_relationship.call_count, 11)
        self.assertGreater(tom.add_measure.call_count, 25)
        self.assertTrue(any(c.kwargs["measure_name"] == "Wallet Share Pct" for c in tom.add_measure.call_args_list))
        self.assertIn(f"{WORKSPACE}@onelake.dfs.fabric.microsoft.com/{LAKEHOUSE}/", fs.put.call_args.args[0])
        self.assertIn("STATUS: SUCCESS", fs.put.call_args.args[1])

    def test_semantic_version_without_explicit_workspaces_fails_closed(self):
        calls = []

        def generate(dataset, source, tables):
            calls.append(dataset)

        with self.semantic_runtime(generate) as (_, connect, fs):
            with self.assertRaisesRegex(RuntimeError, "explicit workspace"):
                SEMANTIC.main(environ=NOTEBOOK_ENV)
        self.assertEqual(calls, [])
        connect.assert_not_called()
        self.assertIn("STATUS: FAILED", fs.put.call_args.args[1])

    def test_loader_schemas_and_curated_logic_remain_executable_offline(self):
        expression = MagicMock()
        for name in ("alias", "otherwise", "over", "desc"):
            getattr(expression, name).return_value = expression
        for name in ("__sub__", "__truediv__", "__mul__", "__eq__"):
            getattr(expression, name).return_value = expression
        functions = Mock()
        for name in ("round", "sum", "count", "when", "col", "row_number", "coalesce", "lit"):
            getattr(functions, name).return_value = expression
        window = Mock()
        window.partitionBy.return_value.orderBy.return_value = expression
        sql_types = types.ModuleType("pyspark.sql.types")
        for name in ("BooleanType", "DoubleType", "IntegerType", "StringType"):
            setattr(sql_types, name, lambda: "type")
        sql_types.StructField = lambda name, kind: name
        sql_types.StructType = list
        modules = {
            "pyspark": types.ModuleType("pyspark"),
            "pyspark.sql": types.SimpleNamespace(functions=functions),
            "pyspark.sql.window": types.SimpleNamespace(Window=window),
            "pyspark.sql.types": sql_types,
        }
        frame = Mock()
        for name in ("format", "option", "schema", "load", "mode", "groupBy", "agg",
                     "filter", "select", "withColumn", "join", "alias", "drop"):
            getattr(frame, name).return_value = frame
        frame.write = frame
        frame.count.return_value = 1
        frame.collect.return_value = [{
            "total_committed_cad_m": 465.0, "total_drawn_cad_m": 288.4,
            "total_exposure_cad_m": 341.7, "fy26_ytd_revenue_cad_k": 8420.0,
            "fy25_same_period_revenue_cad_k": 7140.0, "revenue_yoy_pct": 17.9,
            "wallet_share_pct": 21.4, "single_name_limit_cad_m": 500.0,
            "single_name_utilisation_pct": 68.3, "tightest_actual": 4.18,
            "tightest_threshold": 4.5, "tightest_headroom": 0.32,
            "tightest_covenant": "Total Net Debt to Adjusted EBITDA", "internal_risk_rating": "IG-6",
        }]
        spark = Mock(read=frame)
        spark.table.return_value = frame
        with offline_runtime(modules), redirect_stdout(io.StringIO()):
            LOADER.load_tables(spark, LOADER.load_config(NOTEBOOK_ENV))
        self.assertEqual(frame.saveAsTable.call_count, 16)
        self.assertEqual(frame.load.call_count, 13)
        self.assertTrue(all(c.args[0].startswith(
            f"abfss://{WORKSPACE}@onelake.dfs.fabric.microsoft.com/{LAKEHOUSE}/Files/client-intel/"
        ) for c in frame.load.call_args_list))
        fields = [field for call in frame.schema.call_args_list for field in call.args[0]]
        self.assertIn("bank_role", fields)
        self.assertIn("bank_revenue_cad_k", fields)
        self.assertIn("bank_wallet_share_pct", fields)
        self.assertIn("bank_rank", fields)
        self.assertIn("bank_wallet_cad_k", [c.args[0] for c in expression.alias.call_args_list])


if __name__ == "__main__":
    unittest.main()
