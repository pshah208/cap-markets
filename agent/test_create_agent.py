"""Offline behavioral tests for the SDK agent and its four source tools."""

from __future__ import annotations

import copy
import io
import json
import os
from pathlib import Path
import sys
import time
import types
import unittest
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from unittest import mock

from test_portability import (
    AUTH_FIELDS, COMMON_FIELDS, ENDPOINT, HYBRID_VALUES, INVALID_AUTH_MODES,
    INVALID_IQ_MODES, INVALID_URLS, OfflineTestCase, environment, missing_variants,
)


START = "<!-- INSTRUCTIONS-START -->"
END = "<!-- INSTRUCTIONS-END -->"
INSTRUCTIONS = "Use governed evidence. Never invent external intelligence."
DOCUMENT = f"Not instructions\n{START}\n  {INSTRUCTIONS}\n{END}\nAlso not instructions"
FACTS = {"as_of": "2031-04-20", "hero_client_id": "JUN-01"}
FUNCTIONS = {
    "search_client_relationship_history": "query",
    "query_client_exposure_analytics": "question",
    "lookup_capital_markets_policy": "query",
    "research_client_external_intelligence": "topic",
}
BAD_INSTRUCTIONS = (
    "", "unmarked instructions", START + "missing end", "missing start" + END,
    END + "reversed" + START, START + START + "duplicate" + END,
    START + "duplicate" + END + END, START + " \n\t " + END,
)


def config(iq_mode="local", auth_mode="azure_cli"):
    return {**environment(auth_mode, iq_mode), "CM_CLIENT_ID": FACTS["hero_client_id"]}


def client_row(cid, name, sector="Energy"):
    return {
        "client_id": cid, "client_name": name, "sector": sector,
        "ticker": cid[:3], "sub_sector": "Synthetic industry", "hq_city": "Test City",
        "internal_risk_rating": "4", "internal_risk_rating_prior": "3",
        "risk_trend": "Deteriorating", "watchlist_flag": "Y",
        "kyc_refresh_due": "2031-07-01", "public_ratings": "SYNTHETIC PLACEHOLDER",
    }


def limit_row(cid, name, kind, status="Green"):
    return {
        "client_id": cid, "client_name": name, "limit_id": "L-" + cid,
        "limit_type": kind, "limit_cad_m": "100", "utilised_cad_m": "60",
        "headroom_cad_m": "40", "utilisation_pct": "60", "status": status,
        "limit_owner": "Synthetic Risk Committee",
    }


def covenant_row(name, test, actual, prior, headroom, status="Amber"):
    return {
        "client_id": "JUN-01", "covenant": name, "test_type": test,
        "threshold": "4.5" if test == "maximum" else "2",
        "actual": str(actual), "prior_quarter_actual": str(prior),
        "headroom": str(headroom), "unit": "x", "utilisation_pct": "93",
        "status": status, "last_tested_date": "2031-03-31",
        "next_test_date": "2031-06-30", "source_facility": "Synthetic RCF",
    }


def tables():
    return {
        "clients.csv": [
            client_row("JUN-01", "Juniper Power"),
            client_row("JUN-02", "Juniper Metals", "Materials"),
            client_row("COB-03", "Cobalt Logistics", "Industrials"),
        ],
        "credit_facilities.csv": [
            {"client_id": "JUN-01", "commitment_cad_m": "80", "drawn_cad_m": "30"},
            {"client_id": "JUN-01", "commitment_cad_m": "20.5", "drawn_cad_m": "10"},
            {"client_id": "COB-03", "commitment_cad_m": "500", "drawn_cad_m": "400"},
        ],
        "exposures.csv": [
            {"client_id": "JUN-01", "current_exposure_cad_m": "40.2"},
            {"client_id": "JUN-01", "current_exposure_cad_m": "19.8"},
            {"client_id": "COB-03", "current_exposure_cad_m": "400"},
        ],
        "limits_utilization.csv": [
            limit_row("JUN-01", "Juniper Power", "Single-name credit limit"),
            {**limit_row("SECTOR-ENE", "Energy", "Sector concentration limit", "Amber"),
             "limit_cad_m": "1000", "utilised_cad_m": "860", "headroom_cad_m": "140",
             "utilisation_pct": "86"},
            limit_row("SECTOR-MAT", "Materials", "Sector concentration limit"),
        ],
        "covenants.csv": [
            covenant_row("Total Net Debt / EBITDA", "maximum", 4.2, 3.9, 0.3),
            covenant_row("Interest coverage", "minimum", 2.1, 2.4, 0.1),
            covenant_row("Liquidity cover", "minimum", 3, 2.9, 1, "Green"),
        ],
        "revenue_by_product.csv": [
            {"client_id": "JUN-01", "business_line": "Lending",
             "fy26_ytd_revenue_cad_k": "100.2", "fy25_same_period_revenue_cad_k": "80"},
            {"client_id": "JUN-01", "business_line": "Markets",
             "fy26_ytd_revenue_cad_k": "49.8", "fy25_same_period_revenue_cad_k": "40"},
            {"client_id": "COB-03", "business_line": "Markets",
             "fy26_ytd_revenue_cad_k": "900", "fy25_same_period_revenue_cad_k": "700"},
        ],
        "wallet_share.csv": [
            {"client_id": "JUN-01", "product_name": "FX", "estimated_street_wallet_cad_k": "400",
             "gap_to_25pct_target_cad_k": "50.2", "lead_competitor": "Synthetic Rival",
             "whitespace_flag": "Y"},
            {"client_id": "JUN-01", "product_name": "RCF", "estimated_street_wallet_cad_k": "200",
             "gap_to_25pct_target_cad_k": "0", "lead_competitor": "Synthetic Lender",
             "whitespace_flag": "N"},
            {"client_id": "COB-03", "product_name": "FX", "estimated_street_wallet_cad_k": "5000",
             "gap_to_25pct_target_cad_k": "300", "lead_competitor": "Synthetic Rival",
             "whitespace_flag": "Y"},
        ],
        "trades.csv": [
            {"client_id": cid, "trade_id": tid, "trade_date": date, "description": "Synthetic swap",
             "desk": "Rates", "notional_cad_m": "20.5", "revenue_cad_k": "2.5", "status": "Executed"}
            for cid, tid, date in (
                ("JUN-01", "OLD", "2031-01-01"), ("COB-03", "OTHER", "2031-04-19"),
                ("JUN-01", "NEW", "2031-04-01"))
        ],
        "coverage_team.csv": [
            {"client_id": cid, "display_name": name, "job_title": "Synthetic banker",
             "department": "Coverage", "coverage_role": "Lead", "interactions_90d": interactions,
             "last_interaction_date": "2031-04-18", "wall_status": "Private"}
            for cid, name, interactions in (
                ("JUN-01", "Test Banker One", "7"), ("JUN-01", "Test Banker Two", ""),
                ("COB-03", "Other Banker", "99"))
        ],
    }


class AgentTestCase(OfflineTestCase):
    def setUp(self):
        super().setUp()
        self.agent = self.cloud_module()
        self.stdout = self.stack.enter_context(redirect_stdout(io.StringIO()))
        self.stderr = self.stack.enter_context(redirect_stderr(io.StringIO()))
        self.credential = mock.Mock(spec_set=("close", "get_token"))
        self.credentials = self.stack.enter_context(mock.patch.object(
            self.agent, "build_credential", return_value=self.credential))

    def mock_client(self):
        client = mock.MagicMock(spec_set=(
            "list_agents", "create_agent", "update_agent", "threads", "messages", "runs",
            "__enter__", "__exit__",
        ))
        client.__enter__.return_value = client
        client.list_agents.return_value = []
        client.create_agent.return_value = types.SimpleNamespace(id="created-agent")
        client.update_agent.return_value = types.SimpleNamespace(id="updated-agent")
        return client

    @contextmanager
    def sdk(self, models=False, search=False):
        modules = {}
        names = ["azure", "azure.ai", "azure.ai.agents"]
        if models:
            names.append("azure.ai.agents.models")
        if search:
            names.extend(("azure.search", "azure.search.documents"))
        for name in names:
            module = types.ModuleType(name)
            module.__path__ = []
            modules[name] = module
            if "." in name:
                parent, child = name.rsplit(".", 1)
                setattr(modules[parent], child, module)
        agents = modules["azure.ai.agents"]
        agents.AgentsClient = mock.Mock(return_value=self.mock_client())
        if search:
            modules["azure.search.documents"].SearchClient = mock.MagicMock()
        if models:
            model = modules["azure.ai.agents.models"]

            class RequiredFunctionToolCall:
                def __init__(self, identifier, name, arguments):
                    self.id = identifier
                    self.function = types.SimpleNamespace(name=name, arguments=arguments)

            class SubmitToolOutputsAction:
                def __init__(self, calls):
                    self.submit_tool_outputs = types.SimpleNamespace(tool_calls=calls)

            class ToolOutput:
                def __init__(self, *, tool_call_id, output):
                    self.tool_call_id = tool_call_id
                    self.output = output

            model.RequiredFunctionToolCall = RequiredFunctionToolCall
            model.SubmitToolOutputsAction = SubmitToolOutputsAction
            model.ToolOutput = ToolOutput
            model.ListSortOrder = types.SimpleNamespace(ASCENDING="ascending-test-sentinel")
        with mock.patch.dict(sys.modules, modules), mock.patch.object(self, "fake_azure", modules):
            yield modules

    @contextmanager
    def valid_local_inputs(self, iq_mode="local"):
        with mock.patch.dict(os.environ, config(iq_mode), clear=True), \
                mock.patch.object(self.agent, "_validate_data") as validate, \
                mock.patch.object(self.agent, "_instructions", return_value=INSTRUCTIONS) as instructions:
            yield validate, instructions

    def entrypoints(self, client):
        return {
            "main --create": lambda: self.agent.main(["--create"]),
            "_client": self.agent._client,
            "create_or_update": lambda: self.agent.create_or_update(client),
            "ask": lambda: self.agent.ask(client, "existing-agent", "An offline question"),
        }

    def assert_invalid_entrypoints(self, values, field):
        for name, action in self.entrypoints(client := self.mock_client()).items():
            with self.subTest(entrypoint=name), mock.patch.dict(os.environ, values, clear=True), \
                    self.no_data_access():
                if name == "main --create":
                    self.stderr.seek(0)
                    self.stderr.truncate()
                    with self.assertRaises(SystemExit) as caught:
                        action()
                    self.assertEqual(caught.exception.code, 2)
                    self.assertIn(field, self.stderr.getvalue())
                else:
                    with self.assertRaises(self.agent.ConfigurationError) as caught:
                        action()
                    self.assertIn(field, str(caught.exception))
                self.assertEqual(client.mock_calls, [])
                self.credentials.assert_not_called()


class AgentValidationTests(AgentTestCase):
    def test_each_common_and_selected_auth_field_precedes_dependencies_at_every_entrypoint(self):
        for iq_mode in ("local", "hybrid"):
            for auth_mode, fields in AUTH_FIELDS.items():
                for field, replacement, values in missing_variants(
                        config(iq_mode, auth_mode), (*COMMON_FIELDS, *fields)):
                    with self.subTest(iq_mode=iq_mode, auth_mode=auth_mode, field=field,
                                      replacement=replacement):
                        self.assert_invalid_entrypoints(values, field)

    def test_each_hybrid_field_precedes_dependencies_at_every_entrypoint(self):
        for field, replacement, values in missing_variants(config("hybrid"), HYBRID_VALUES):
            with self.subTest(field=field, replacement=replacement):
                self.assert_invalid_entrypoints(values, field)

    def test_invalid_iq_and_auth_modes_precede_dependencies_at_every_entrypoint(self):
        for field, invalid in (("IQ_MODE", INVALID_IQ_MODES), ("AZURE_AUTH_MODE", INVALID_AUTH_MODES)):
            for value in invalid:
                with self.subTest(field=field, value=value):
                    self.assert_invalid_entrypoints({**config("hybrid"), field: value}, field)

    def test_invalid_urls_precede_dependencies_at_every_entrypoint(self):
        for field in ("FOUNDRY_PROJECT_ENDPOINT", "SEARCH_ENDPOINT"):
            for value in INVALID_URLS:
                with self.subTest(field=field, value=value):
                    self.assert_invalid_entrypoints({**config("hybrid"), field: value}, field)

    def test_data_validation_precedes_sdk_credentials_and_remote_operations(self):
        for name, action in self.entrypoints(client := self.mock_client()).items():
            with self.subTest(entrypoint=name), mock.patch.dict(os.environ, config(), clear=True), \
                    mock.patch.object(self.agent, "_validate_data",
                                      side_effect=self.agent.ConfigurationError("missing synthetic table")):
                expected = SystemExit if name == "main --create" else self.agent.ConfigurationError
                with self.assertRaises(expected):
                    action()
                self.assertEqual(client.mock_calls, [])
                self.credentials.assert_not_called()

    def test_validate_data_checks_all_mode_specific_files_and_selected_client(self):
        common = {self.agent.FABRIC / name for name in tables()}
        common.update(self.agent.WORK / name for name in ("emails.json", "teams_messages.json"))
        for mode in ("local", "hybrid"):
            with self.subTest(mode=mode), mock.patch.object(
                    self.agent, "require_file", side_effect=lambda path, label: path) as files, \
                    mock.patch.object(self.agent, "_facts", return_value=FACTS) as facts, \
                    mock.patch.object(self.agent, "_load_csv", return_value=tables()["clients.csv"]):
                self.agent._validate_data(config(mode))
                expected = common | {
                    self.agent.FOUNDRY / "cm_policies.json" if mode == "local"
                    else self.agent.DATA / "web-iq" / "web_iq_queries.json",
                }
                self.assertEqual({call.args[0] for call in files.call_args_list}, expected)
                self.assertEqual(files.call_count, len(expected))
                facts.assert_called_once_with()

    def test_each_missing_corpus_file_is_rejected(self):
        for mode in ("local", "hybrid"):
            required = [self.agent.FABRIC / name for name in tables()]
            required += [self.agent.WORK / name for name in ("emails.json", "teams_messages.json")]
            required += [self.agent.FOUNDRY / "cm_policies.json" if mode == "local"
                         else self.agent.DATA / "web-iq" / "web_iq_queries.json"]
            for missing in required:
                with self.subTest(mode=mode, missing=missing.name), mock.patch.object(
                        Path, "is_file", autospec=True, side_effect=lambda path: path != missing), \
                        mock.patch.object(self.agent, "_facts", return_value=FACTS), \
                        mock.patch.object(self.agent, "_load_csv", return_value=tables()["clients.csv"]):
                    with self.assertRaises(self.agent.ConfigurationError) as caught:
                        self.agent._validate_data(config(mode))
                    self.assertIn(missing.name, str(caught.exception))
        self.credentials.assert_not_called()

    def test_unknown_configured_client_fails_before_remote_access(self):
        with mock.patch.object(self.agent, "require_file", side_effect=lambda path, label: path), \
                mock.patch.object(self.agent, "_facts", return_value=FACTS), \
                mock.patch.object(self.agent, "_load_csv", return_value=tables()["clients.csv"]):
            values = {**config(), "CM_CLIENT_ID": "NO-SUCH-CLIENT"}
            for name, action in self.entrypoints(client := self.mock_client()).items():
                with self.subTest(entrypoint=name), mock.patch.dict(os.environ, values, clear=True):
                    expected = SystemExit if name == "main --create" else self.agent.ConfigurationError
                    with self.assertRaises(expected):
                        action()
                    self.assertEqual(client.mock_calls, [])
                    self.credentials.assert_not_called()

    def test_facts_are_loaded_only_on_invocation_without_sys_path_changes(self):
        path = self.agent.DATA / "scenario_facts.py"
        loader = mock.Mock()
        fake_spec = types.SimpleNamespace(loader=loader)
        module = types.SimpleNamespace(FACTS=FACTS)
        before = list(sys.path)
        with mock.patch.object(self.agent, "require_file", return_value=path) as required, \
                mock.patch.object(self.agent.importlib.util, "spec_from_file_location",
                                  return_value=fake_spec) as spec, \
                mock.patch.object(self.agent.importlib.util, "module_from_spec",
                                  return_value=module) as factory:
            self.assertIs(self.agent._facts(), FACTS)
            required.assert_called_once_with(path, "synthetic scenario facts")
            spec.assert_called_once_with("_cm_synthetic_facts", path)
            factory.assert_called_once_with(fake_spec)
            loader.exec_module.assert_called_once_with(module)
        self.assertEqual(sys.path, before)

    def test_missing_facts_fails_before_loading_module(self):
        with mock.patch.object(Path, "is_file", return_value=False), \
                mock.patch.object(self.agent.importlib.util, "spec_from_file_location") as spec:
            with self.assertRaises(self.agent.ConfigurationError):
                self.agent._facts()
            spec.assert_not_called()

    def test_instructions_extracts_only_ordered_marked_body(self):
        with mock.patch.object(Path, "is_file", return_value=True), \
                mock.patch.object(Path, "read_text", return_value=DOCUMENT) as read:
            self.assertEqual(self.agent._instructions(), INSTRUCTIONS)
            read.assert_called_once_with(encoding="utf-8")

    def test_missing_or_malformed_instructions_are_rejected(self):
        with mock.patch.object(Path, "is_file", return_value=False):
            with self.assertRaises(self.agent.ConfigurationError):
                self.agent._instructions()
        for text in BAD_INSTRUCTIONS:
            with self.subTest(text=text), mock.patch.object(Path, "is_file", return_value=True), \
                    mock.patch.object(Path, "read_text", return_value=text):
                with self.assertRaises(self.agent.ConfigurationError):
                    self.agent._instructions()

    def assert_instructions_before_remote(self, entrypoint):
        for text in BAD_INSTRUCTIONS:
            client = self.mock_client()
            with self.subTest(text=text), mock.patch.dict(os.environ, config(), clear=True), \
                    mock.patch.object(self.agent, "_validate_data"), \
                    mock.patch.object(Path, "is_file", return_value=True), \
                    mock.patch.object(Path, "read_text", return_value=text), self.sdk(models=True):
                action = self.entrypoints(client)[entrypoint]
                expected = SystemExit if entrypoint == "main --create" else self.agent.ConfigurationError
                with self.assertRaises(expected):
                    action()
                self.assertEqual(client.mock_calls, [])
                self.credentials.assert_not_called()

    def test_main_validates_instructions_before_remote(self):
        self.assert_instructions_before_remote("main --create")

    def test_client_validates_instructions_before_remote(self):
        self.assert_instructions_before_remote("_client")

    def test_create_or_update_validates_instructions_before_remote(self):
        self.assert_instructions_before_remote("create_or_update")

    def test_ask_validates_instructions_before_remote(self):
        self.assert_instructions_before_remote("ask")

    def test_help_and_no_action_are_config_free(self):
        for args, code in ((["--help"], 0), ([], 2)):
            with self.subTest(args=args), self.no_data_access(), \
                    mock.patch.object(self.agent, "_cloud_config", self.forbidden("cloud config for help")), \
                    mock.patch.object(self.agent, "_backend_config", self.forbidden("backend config for help")):
                with self.assertRaises(SystemExit) as caught:
                    self.agent.main(args)
                self.assertEqual(caught.exception.code, code)
        self.credentials.assert_not_called()

    def test_local_smoke_cannot_be_combined_with_any_cloud_action(self):
        for action in (["--create"], ["--ask", "question"], ["--demo"], ["--trap"], ["--chat"]):
            with self.subTest(action=action), self.no_data_access(), \
                    mock.patch.object(self.agent, "_cloud_config", self.forbidden("config before CLI validation")), \
                    mock.patch.object(self.agent, "local_smoke") as smoke:
                with self.assertRaises(SystemExit) as caught:
                    self.agent.main(["--local-smoke", *action])
                self.assertEqual(caught.exception.code, 2)
                self.assertIn("cannot be combined", self.stderr.getvalue())
                smoke.assert_not_called()


class LocalAnalyticsTests(AgentTestCase):
    def setUp(self):
        super().setUp()
        self.data = tables()
        self.csv = self.stack.enter_context(mock.patch.object(
            self.agent, "_load_csv", side_effect=lambda name: copy.deepcopy(self.data[name])))
        self.facts = self.stack.enter_context(mock.patch.object(self.agent, "_facts", return_value=FACTS))

    def analytics(self, question="", client="JUN-01", topic=None):
        return json.loads(self.agent._query_local_analytics(question, client, topic))

    def test_capacity_always_returns_covenants_and_sector_even_for_revenue_topic(self):
        for question in ("capacity", "headroom", "exposure", "hold", "upsize", "increase",
                         "can we lend", "commit", "covenant", "constraint", "amber", "limit"):
            with self.subTest(question=question):
                result = self.analytics(question, topic="revenue")
                self.assertEqual(result["layer"], "Fabric IQ")
                self.assertIn("synthetic", result["backend"])
                self.assertIn("not the Fabric", result["backend"])
                self.assertEqual(result["as_of"], FACTS["as_of"])
                self.assertEqual(result["sector_limit"]["sector"], "Energy")
                self.assertEqual(len(result["covenants"]), 3)
                self.assertEqual(result["limits"][0]["status"], "Green")
                self.assertIn("revenue", result)
                self.assertEqual(result["exposure"], {
                    "total_committed_cad_m": 100.5, "total_drawn_cad_m": 40.0,
                    "total_exposure_cad_m": 60.0, "facilities": 2,
                })

    def test_covenant_deterioration_respects_maximum_and_minimum_direction(self):
        result = self.analytics("capacity")
        covenants = {item["covenant"]: item for item in result["covenants"]}
        self.assertTrue(covenants["Total Net Debt / EBITDA"]["deteriorating"])
        self.assertTrue(covenants["Interest coverage"]["deteriorating"])
        self.assertFalse(covenants["Liquidity cover"]["deteriorating"])
        self.data["covenants.csv"][0]["actual"] = "3.8"
        self.data["covenants.csv"][1]["actual"] = "2.4"
        self.assertFalse(any(c["deteriorating"] for c in self.analytics("capacity")["covenants"]))

    def test_binding_constraint_uses_tightest_covenant_with_actionable_warnings(self):
        result = self.analytics("capacity")
        self.assertEqual(result["binding_constraint"], "Covenant - Interest coverage")
        for phrase in ("0.1x", "deteriorating from 2.4x", "CP-005", "Credit Risk",
                       "BEFORE", "NOT the constraint"):
            self.assertIn(phrase, result["_capacity_warning"])
        for phrase in ("Energy", "CP-002", "Synthetic Risk Committee", "originate-to-distribute"):
            self.assertIn(phrase, result["_sector_warning"])

    def test_binding_constraint_priority_sector_then_single_name_then_green(self):
        for covenant in self.data["covenants.csv"]:
            covenant["status"] = "Green"
        result = self.analytics("capacity")
        self.assertEqual(result["binding_constraint"], "Sector concentration")
        self.assertNotIn("_capacity_warning", result)
        self.assertIn("_sector_warning", result)
        self.data["limits_utilization.csv"][1]["status"] = "Green"
        self.data["limits_utilization.csv"][0]["status"] = "Breach"
        result = self.analytics("capacity")
        self.assertEqual(result["binding_constraint"], "Single name")
        self.assertNotIn("_sector_warning", result)
        self.data["limits_utilization.csv"][0]["status"] = "Green"
        self.assertEqual(self.analytics("capacity")["binding_constraint"],
                         "None - all limits and covenants green")

    def test_breached_and_improving_covenant_still_requires_credit_risk(self):
        self.data["covenants.csv"] = [covenant_row("Leverage test", "maximum", 4.6, 4.8, -0.1, "Breach")]
        result = self.analytics("capacity")
        self.assertEqual(result["binding_constraint"], "Covenant - Leverage test")
        self.assertIn("improving quarter on quarter", result["_capacity_warning"])
        self.assertIn("CP-005", result["_capacity_warning"])

    def test_capacity_with_no_covenants_or_limits_does_not_crash(self):
        self.data["covenants.csv"] = []
        self.data["limits_utilization.csv"] = []
        result = self.analytics("capacity")
        self.assertEqual(result["covenants"], [])
        self.assertEqual(result["limits"], [])
        self.assertNotIn("sector_limit", result)
        self.assertNotIn("_capacity_warning", result)
        self.assertNotIn("_sector_warning", result)

    def test_revenue_and_wallet_totals_are_client_scoped_and_confidential(self):
        result = self.analytics("revenue and wallet", topic="revenue")
        self.assertEqual(result["revenue"], {
            "fy26_ytd_cad_k": 150.0, "fy25_same_period_cad_k": 120.0, "yoy_pct": 25.0,
            "by_business_line": {"Lending": 100.2, "Markets": 49.8},
        })
        wallet = result["wallet"]
        self.assertEqual(wallet["our_revenue_cad_k"], 150.0)
        self.assertEqual(wallet["estimated_street_wallet_cad_k"], 600.0)
        self.assertEqual(wallet["our_wallet_share_pct"], 25.0)
        self.assertEqual(wallet["whitespace"], [{
            "product": "FX", "street_wallet_cad_k": 400.0,
            "gap_to_25pct_target_cad_k": 50.2, "lead_competitor": "Synthetic Rival",
        }])
        self.assertIn("CP-014", wallet["_confidential"])
        self.assertNotIn("limits", result)

    def test_zero_denominators_return_null_not_invented_percentage(self):
        self.data["revenue_by_product.csv"] = []
        self.data["wallet_share.csv"] = []
        result = self.analytics("revenue", topic="wallet")
        self.assertEqual(result["revenue"]["fy26_ytd_cad_k"], 0)
        self.assertIsNone(result["revenue"]["yoy_pct"])
        self.assertIsNone(result["wallet"]["our_wallet_share_pct"])
        self.assertEqual(result["wallet"]["whitespace"], [])

    def test_trades_sorted_newest_first_and_scoped_to_client(self):
        result = self.analytics(topic="trades")
        self.assertEqual([trade["trade_id"] for trade in result["trades"]], ["NEW", "OLD"])
        self.assertEqual(result["trades"][0]["notional_cad_m"], 20.5)
        self.assertEqual(result["trades"][0]["revenue_cad_k"], 2.5)

    def test_coverage_team_counts_and_information_barrier_warning(self):
        result = self.analytics(topic="coverage")
        self.assertEqual([row["name"] for row in result["coverage_team"]],
                         ["Test Banker One", "Test Banker Two"])
        self.assertEqual([row["interactions_90d"] for row in result["coverage_team"]], [7, 0])
        for row in result["coverage_team"]:
            self.assertEqual(row["wall_status"], "Private")
            self.assertIn("CP-008", row["_barrier_note"])
            self.assertIn("Never surface", row["_barrier_note"])

    def test_portfolio_totals_and_sector_envelopes_do_not_mix_client_rows(self):
        result = self.analytics(topic="portfolio")
        portfolio = {row["client_id"]: row for row in result["portfolio"]}
        self.assertEqual(set(portfolio), {"JUN-01", "JUN-02", "COB-03"})
        self.assertEqual(portfolio["JUN-01"]["total_exposure_cad_m"], 60)
        self.assertEqual(portfolio["JUN-01"]["fy26_ytd_revenue_cad_k"], 150)
        self.assertEqual(portfolio["JUN-02"]["total_exposure_cad_m"], 0)
        self.assertEqual(portfolio["COB-03"]["fy26_ytd_revenue_cad_k"], 900)
        self.assertEqual({row["sector"] for row in result["sector_envelopes"]}, {"Energy", "Materials"})

    def test_client_fields_preserve_internal_risk_and_public_rating_caveat(self):
        client = self.analytics(topic="trades")["client"]
        self.assertEqual(client["client_id"], "JUN-01")
        self.assertEqual(client["internal_risk_rating"], "4")
        self.assertEqual(client["internal_risk_rating_prior"], "3")
        self.assertTrue(client["watchlist"])
        self.assertEqual(client["public_ratings"], "SYNTHETIC PLACEHOLDER")
        self.assertIn("never quote", client["_rating_note"])

    def test_unknown_or_ambiguous_explicit_client_never_uses_hero_fallback(self):
        for client in ("no-such-client", "Juniper"):
            with self.subTest(client=client), mock.patch.dict(os.environ, config(), clear=True):
                with self.assertRaisesRegex(self.agent.ConfigurationError, "exactly one"):
                    self.analytics("capacity", client=client)

    def test_ambiguous_question_requires_explicit_client(self):
        with mock.patch.dict(os.environ, config(), clear=True):
            with self.assertRaisesRegex(self.agent.ConfigurationError, "multiple clients"):
                self.analytics("Juniper capacity", client=None)

    def test_explicit_client_id_or_unique_name_is_case_insensitive(self):
        for client in ("jun-01", "jUnIpEr PoWeR", "Power"):
            with self.subTest(client=client), self.no_environment_access():
                self.assertEqual(self.analytics(topic="trades", client=client)["client"]["client_id"], "JUN-01")

    def test_unique_question_client_overrides_configured_default(self):
        with mock.patch.dict(os.environ, config(), clear=True):
            self.assertEqual(self.analytics("Cobalt trades", client=None)["client"]["client_id"], "COB-03")

    def test_unqualified_question_requires_valid_explicit_default_not_hero(self):
        for values in ({}, {"CM_CLIENT_ID": "NO-SUCH-CLIENT"}):
            with self.subTest(values=values), mock.patch.dict(os.environ, values, clear=True):
                with self.assertRaisesRegex(self.agent.ConfigurationError, "CM_CLIENT_ID"):
                    self.analytics("capacity", client=None)
        with mock.patch.dict(os.environ, {"CM_CLIENT_ID": "COB-03"}, clear=True):
            self.assertEqual(self.analytics("trades", client=None)["client"]["client_id"], "COB-03")

    def test_dynamic_demo_and_trap_questions_use_selected_client_and_limits(self):
        for cid, expected in (("JUN-02", "Juniper Metals"), ("COB-03", "Cobalt Logistics")):
            questions = self.agent._demo_questions(cid)
            self.assertEqual(len(questions), 5)
            self.assertTrue(all(expected in question for question in questions))
            self.assertTrue(all("Juniper Power" not in question for question in questions))
        question = self.agent._trap_question("JUN-01")
        self.assertIn("Juniper Power", question)
        self.assertIn("100m", question)
        self.assertIn("60", question)
        self.data["clients.csv"][0]["client_name"] = "Renamed Synthetic Client"
        self.data["limits_utilization.csv"][0]["limit_cad_m"] = "177"
        self.assertIn("Renamed Synthetic Client", self.agent._trap_question("JUN-01"))
        self.assertIn("177m", self.agent._trap_question("JUN-01"))

    def test_local_smoke_is_config_free_and_calls_only_private_implementations(self):
        for values in ({}, {**config("hybrid"), "IQ_MODE": "invalid",
                            "CM_CLIENT_ID": "NO-SUCH-CLIENT", "AZURE_AUTH_MODE": "default"}):
            with self.subTest(values=values), mock.patch.dict(os.environ, values, clear=True), \
                    self.no_environment_access(), \
                    mock.patch.object(self.agent, "_backend_config",
                                      self.forbidden("backend configuration in local smoke")), \
                    mock.patch.object(self.agent, "_cloud_config",
                                      self.forbidden("cloud configuration in local smoke")), \
                    mock.patch.object(self.agent, "_lookup_local_policy",
                                      return_value=json.dumps({"results": [{"id": "CP-005"}]})) as policy, \
                    mock.patch.object(self.agent, "_search_local_relationships",
                                      return_value=json.dumps({"matches": 0, "results": []})) as work, \
                    mock.patch.object(self.agent, "_web_unavailable",
                                      wraps=self.agent._web_unavailable) as web:
                with mock.patch.multiple(self.agent, **{
                        name: self.forbidden("public wrapper used by local smoke: " + name)
                        for name in FUNCTIONS}):
                    self.assertEqual(self.agent.local_smoke(), 0)
                self.assertEqual(policy.call_count, 3)
                self.assertEqual(work.call_count, 3)
                web.assert_called_once_with()
        self.assertIn("All local tools responded", self.stdout.getvalue())
        self.credentials.assert_not_called()

    def test_main_local_smoke_routes_without_consulting_cloud_or_backend_configuration(self):
        for values in ({}, {**config("hybrid"), "IQ_MODE": "invalid", "AZURE_AUTH_MODE": "invalid"}):
            with self.subTest(values=values), mock.patch.dict(os.environ, values, clear=True), \
                    mock.patch.object(self.agent, "_cloud_config", self.forbidden("cloud config in smoke")), \
                    mock.patch.object(self.agent, "_backend_config", self.forbidden("backend config in smoke")), \
                    mock.patch.object(self.agent, "local_smoke", return_value=0) as smoke, \
                    self.no_data_access():
                self.assertEqual(self.agent.main(["--local-smoke"]), 0)
                smoke.assert_called_once_with()
        self.credentials.assert_not_called()


class LocalSourceTests(AgentTestCase):
    def setUp(self):
        super().setUp()
        self.stack.enter_context(mock.patch.object(self.agent, "_facts", return_value=FACTS))

    @contextmanager
    def relationship_corpus(self):
        emails = {"emails": [
            {"id": identifier, "subject": "Covenant review", "body": body,
             "sentDateTime": "2031-04-20T09:00:00Z", "from": "synthetic-sender",
             "category": category}
            for identifier, body, category in (
                ("E-HIGH", "covenant " * 6 + "x" * 800, "governance_and_escalation"),
                ("E-LOW", "covenant once", "coverage_and_planning"),
                ("E-NONE", "unrelated", "investment_banking"))
        ]}
        teams = {"channels": [{"displayName": "Synthetic Channel", "conversations": [
            {"id": "T-1", "subject": "Review", "message": "covenant " * 3 + "x" * 700,
             "createdDateTime": "2031-04-19T09:00:00Z", "from": "synthetic-team-member",
             "category": "coverage_and_planning"},
        ]}]}
        meeting = self.agent.WORK / "meetings" / "2031-04-18-test.md"
        document = self.agent.WORK / "files" / "2031-04-17-test.md"
        documents = {
            self.agent.WORK / "emails.json": json.dumps(emails),
            self.agent.WORK / "teams_messages.json": json.dumps(teams),
            meeting: "prefix " * 150 + "covenant " * 4 + "suffix " * 180,
            document: "covenant",
        }

        def glob(path, pattern):
            self.assertEqual(pattern, "*.md")
            return {self.agent.WORK / "meetings": [meeting],
                    self.agent.WORK / "files": [document]}[path]

        with mock.patch.object(Path, "read_text", autospec=True,
                               side_effect=lambda path, **kwargs: documents[path]), \
                mock.patch.object(Path, "glob", autospec=True, side_effect=glob):
            yield

    def test_work_search_ranks_all_sources_and_preserves_source_metadata(self):
        with self.relationship_corpus():
            result = json.loads(self.agent._search_local_relationships("COVENANT"))
        self.assertEqual(result["layer"], "Work IQ")
        self.assertIn("synthetic", result["backend"])
        self.assertIn("not Microsoft Graph", result["backend"])
        self.assertEqual(result["as_of"], FACTS["as_of"])
        hits = result["results"]
        self.assertEqual(result["matches"], 6)
        self.assertEqual(hits[0]["id"], "E-HIGH")
        self.assertEqual([row["score"] for row in hits], sorted(
            [row["score"] for row in hits], reverse=True))
        self.assertEqual({row["source"] for row in hits}, {"email", "teams", "document"})
        self.assertEqual(hits[0]["date"], "2031-04-20")
        self.assertEqual(len(hits[0]["excerpt"]), 700)
        team = next(row for row in hits if row["source"] == "teams")
        self.assertEqual(team["channel"], "Synthetic Channel")
        self.assertEqual(len(team["excerpt"]), 600)
        meeting = next(row for row in hits if row["id"] == "2031-04-18-test.md")
        self.assertIn("covenant", meeting["excerpt"])
        self.assertLessEqual(len(meeting["excerpt"]), 1100)

    def test_work_search_filters_email_categories(self):
        with self.relationship_corpus():
            result = json.loads(self.agent._search_local_relationships(
                "covenant", category="governance_and_escalation"))
        self.assertEqual([row["id"] for row in result["results"] if row["source"] == "email"],
                         ["E-HIGH"])

    def test_work_category_does_not_leak_nonmatching_teams_or_uncategorized_documents(self):
        with self.relationship_corpus():
            result = json.loads(self.agent._search_local_relationships(
                "covenant", category="governance_and_escalation"))
        self.assertEqual([row["id"] for row in result["results"]], ["E-HIGH"])

    def test_work_public_categories_match_shipped_email_categories(self):
        tool = next(t["function"] for t in self.agent._tool_defs()
                    if t["function"]["name"] == "search_client_relationship_history")
        categories = tool["parameters"]["properties"]["category"]["enum"]
        emails = json.loads((self.agent.WORK / "emails.json").read_text(encoding="utf-8"))
        self.assertEqual(set(categories), {e["category"] for e in emails["emails"]})
        self.assertEqual(len(categories), 5)

    def test_work_public_categories_retrieve_each_shipped_source_type(self):
        samples = {
            "client_interaction": (
                ("email", "EM-016", "comparison"),
                ("teams", "TH-C02", "comparison"),
                ("document", "2026-07-16-gibson-energy-coverage-call-report.md", "comparison")),
            "compliance_and_control": (
                ("email", "EM-022", "partial clearance"),
                ("teams", "TH-M03", "standing down"),
                ("document", "2026-10-01-control-room-briefing-cr-2026-0184.md", "briefing")),
            "credit_and_limits": (
                ("email", "EM-010", "fully drawn"),
                ("teams", "TH-R02", "fully drawn"),
                ("document", "2026-09-24-energy-sector-portfolio-review-minutes.md", "portfolio")),
            "executive_guidance": (
                ("email", "EM-001", "account plan"),
                ("teams", "TH-G01", "account plan"),
                ("document", "2026-09-29-capital-markets-quarterly-business-review.md", "quarterly")),
            "market_and_hedging": (
                ("email", "EM-004", "Chauvin overlay"),
                ("teams", "TH-M01", "Chauvin overlay"),
                ("document", "2026-10-06-deal-team-prep-transcript.md", "differential")),
        }
        with mock.patch.dict(os.environ, {"IQ_MODE": "local"}, clear=True):
            for category, sources in samples.items():
                for source, identifier, query in sources:
                    with self.subTest(category=category, source=source):
                        result = json.loads(self.agent.search_client_relationship_history(
                            query, category))
                        hit = next((row for row in result["results"]
                                    if row["id"] == identifier), None)
                        self.assertIsNotNone(hit, result)
                        self.assertEqual(hit["source"], source)
                        fields = {"source", "id", "date", "from", "subject", "score", "excerpt"}
                        if source == "email":
                            fields.add("category")
                            self.assertEqual(hit["category"], category)
                        elif source == "teams":
                            fields.add("channel")
                        self.assertEqual(set(hit), fields)
        self.credentials.assert_not_called()

    def test_work_legacy_aliases_match_shipped_canonical_categories(self):
        for alias, canonical, query in (
                ("coverage_and_planning", "client_interaction", "comparison"),
                ("investment_banking", "client_interaction", "comparison"),
                ("markets_and_hedging", "market_and_hedging", "differential"),
                ("lending_and_country_risk", "credit_and_limits", "covenant"),
                ("governance_and_escalation", "compliance_and_control", "solicitation")):
            with self.subTest(alias=alias):
                expected = json.loads(self.agent._search_local_relationships(query, canonical))
                actual = json.loads(self.agent._search_local_relationships(query, alias))
                self.assertGreater(expected["matches"], 0)
                self.assertEqual(actual, expected)
        result = json.loads(self.agent._search_local_relationships(
            "standing down", "governance_and_escalation"))
        self.assertIn("TH-M03", {row["id"] for row in result["results"]})

    def test_work_shipped_categories_exclude_unrelated_documents_and_threads(self):
        result = json.loads(self.agent._search_local_relationships(
            "covenant differential comparison briefing portfolio", "compliance_and_control"))
        ids = {row["id"] for row in result["results"]}
        self.assertIn("2026-10-01-control-room-briefing-cr-2026-0184.md", ids)
        self.assertTrue(ids.isdisjoint({
            "TH-M01", "TH-R02", "TH-C02",
            "2026-07-16-gibson-energy-coverage-call-report.md",
            "2026-09-24-energy-sector-portfolio-review-minutes.md",
        }))
        result = json.loads(self.agent._search_local_relationships("covenant", "unknown"))
        self.assertEqual(result["matches"], 0)

    def test_work_team_categories_respect_metadata_and_leave_unknown_ids_unclassified(self):
        for identifier, metadata in (
                ("TH-M03", {"category": "coverage_and_planning"}),
                ("T-UNKNOWN", {}),
                ("TH-M99", {})):
            with self.subTest(identifier=identifier):
                teams = {"channels": [{"displayName": "Markets and Hedging", "conversations": [
                    {"id": identifier, "subject": "Control Room", "message": "standing down",
                     "createdDateTime": "2031-04-19", "from": "synthetic", **metadata},
                ]}]}
                with mock.patch.object(Path, "read_text", autospec=True, side_effect=lambda p, **kw:
                                       json.dumps({"emails": []} if p.name == "emails.json" else teams)), \
                        mock.patch.object(Path, "glob", return_value=[]):
                    result = json.loads(self.agent._search_local_relationships(
                        "standing down", "compliance_and_control"))
                self.assertEqual(result["matches"], 0)

    def test_work_search_ignores_short_terms_and_reports_no_matches(self):
        with self.relationship_corpus():
            for query in ("", None, "a to the", "zzzzunmatched"):
                with self.subTest(query=query):
                    result = json.loads(self.agent._search_local_relationships(query))
                    self.assertEqual(result["matches"], 0)
                    self.assertEqual(result["results"], [])

    def test_work_search_caps_results_at_eight_without_losing_match_count(self):
        emails = {"emails": [
            {"id": str(i), "subject": "covenant", "body": "covenant " * i,
             "sentDateTime": "2031-04-20", "from": "synthetic", "category": "coverage_and_planning"}
            for i in range(12)
        ]}
        with mock.patch.object(Path, "read_text", autospec=True, side_effect=lambda path, **kw:
                               json.dumps(emails if path.name == "emails.json" else {"channels": []})), \
                mock.patch.object(Path, "glob", return_value=[]):
            result = json.loads(self.agent._search_local_relationships("covenant"))
        self.assertEqual(result["matches"], 12)
        self.assertEqual([row["id"] for row in result["results"]], [str(i) for i in range(11, 3, -1)])

    def policy_corpus(self):
        return {"documents": [
            {"id": f"CP-{i:03}", "title": f"Synthetic policy {i}", "category": category,
             "owner": "Synthetic Owner", "content": "covenant " * count + "x" * 2600,
             **({"regulatory_anchor": "Synthetic anchor"} if i == 5 else {})}
            for i, count, category in (
                (1, 10, "risk_appetite"), (2, 9, "concentration_limit"),
                (3, 8, "approval_authority"), (4, 7, "counterparty_risk"),
                (5, 1, "covenant_monitoring"), (6, 6, "kyc_aml"))
        ]}

    def test_local_policy_cp_id_boost_ranking_limit_and_content_projection(self):
        with mock.patch.object(Path, "read_text", return_value=json.dumps(self.policy_corpus())):
            result = json.loads(self.agent._lookup_local_policy("covenant cp-005"))
        self.assertEqual(result["layer"], "Foundry IQ")
        self.assertIn("synthetic", result["backend"])
        self.assertIn("not Azure AI Search", result["backend"])
        self.assertEqual(result["matches"], 6)
        self.assertEqual([row["id"] for row in result["results"]], ["CP-005", "CP-001", "CP-002", "CP-003"])
        self.assertEqual(len(result["results"][0]["content"]), 2500)
        self.assertEqual(result["results"][0]["regulatory_anchor"], "Synthetic anchor")
        self.assertIsNone(result["results"][1]["regulatory_anchor"])

    def test_local_policy_category_and_no_match_behavior(self):
        with mock.patch.object(Path, "read_text", return_value=json.dumps(self.policy_corpus())):
            result = json.loads(self.agent._lookup_local_policy("CP-005 covenant", "risk_appetite"))
            self.assertEqual([row["id"] for row in result["results"]], ["CP-001"])
            for query, category in (("zzzzunmatched", None), ("", None), (None, None),
                                    ("covenant", "missing-category")):
                with self.subTest(query=query, category=category):
                    result = json.loads(self.agent._lookup_local_policy(query, category))
                    self.assertEqual(result["matches"], 0)
                    self.assertEqual(result["results"], [])

    def test_csv_parser_handles_quoted_cells_without_disk_access(self):
        text = 'client_id,client_name,amount\nJUN-01,"Juniper, Synthetic",12.5\n'
        with mock.patch.object(Path, "open", return_value=io.StringIO(text)) as opened:
            self.assertEqual(self.agent._load_csv("clients.csv"), [
                {"client_id": "JUN-01", "client_name": "Juniper, Synthetic", "amount": "12.5"},
            ])
        opened.assert_called_once_with(encoding="utf-8")

    def test_numeric_conversion_handles_missing_empty_and_invalid_values(self):
        for value, expected in ((None, 0), ("", 0), ("invalid", 0), ({}, 0),
                                ("12.5", 12.5), ("-0.75", -0.75), (4, 4)):
            with self.subTest(value=value):
                self.assertEqual(self.agent._f({"number": value}, "number"), expected)
        self.assertEqual(self.agent._f({}, "absent"), 0)


class BackendRoutingTests(AgentTestCase):
    def tool_calls(self):
        return {
            "work": lambda: self.agent.search_client_relationship_history("covenant", "risk"),
            "fabric": lambda: self.agent.query_client_exposure_analytics("capacity", "JUN-01", "limits"),
            "foundry": lambda: self.agent.lookup_capital_markets_policy("CP-005", "risk"),
            "web": lambda: self.agent.research_client_external_intelligence("synthetic topic", 7),
        }

    def test_direct_tools_reject_missing_or_invalid_iq_mode_before_data_and_dependencies(self):
        for value in (None, "", " ", *INVALID_IQ_MODES):
            values = {} if value is None else {"IQ_MODE": value}
            for name, call in self.tool_calls().items():
                with self.subTest(tool=name, value=value), \
                        mock.patch.dict(os.environ, values, clear=True), self.no_data_access():
                    with self.assertRaisesRegex(self.agent.ConfigurationError, "IQ_MODE"):
                        call()
        self.credentials.assert_not_called()

    def test_direct_hybrid_tools_require_every_selected_backend_and_auth_field(self):
        for mode, fields in AUTH_FIELDS.items():
            for field, replacement, values in missing_variants(
                    config("hybrid", mode), (*HYBRID_VALUES, "AZURE_AUTH_MODE", *fields)):
                for name, call in self.tool_calls().items():
                    with self.subTest(tool=name, mode=mode, field=field, replacement=replacement), \
                            mock.patch.dict(os.environ, values, clear=True), self.no_data_access():
                        with self.assertRaises(self.agent.ConfigurationError) as caught:
                            call()
                        self.assertIn(field, str(caught.exception))
        self.credentials.assert_not_called()

    def test_direct_hybrid_tools_reject_bad_urls_and_auth_modes_before_dependencies(self):
        for field, values in (("SEARCH_ENDPOINT", INVALID_URLS), ("AZURE_AUTH_MODE", INVALID_AUTH_MODES)):
            for value in values:
                for name, call in self.tool_calls().items():
                    with self.subTest(tool=name, field=field, value=value), \
                            mock.patch.dict(os.environ, {**config("hybrid"), field: value}, clear=True), \
                            self.no_data_access():
                        with self.assertRaises(self.agent.ConfigurationError) as caught:
                            call()
                        self.assertIn(field, str(caught.exception))
        self.credentials.assert_not_called()

    def test_local_wrappers_use_explicit_synthetic_implementations_without_cloud_config(self):
        with mock.patch.dict(os.environ, {"IQ_MODE": "local"}, clear=True), \
                mock.patch.object(self.agent, "_search_local_relationships", return_value="work") as work, \
                mock.patch.object(self.agent, "_query_local_analytics", return_value="fabric") as fabric, \
                mock.patch.object(self.agent, "_lookup_local_policy", return_value="policy") as policy, \
                self.no_data_access():
            calls = self.tool_calls()
            self.assertEqual(calls["work"](), "work")
            self.assertEqual(calls["fabric"](), "fabric")
            self.assertEqual(calls["foundry"](), "policy")
            web = json.loads(calls["web"]())
        work.assert_called_once_with("covenant", "risk")
        fabric.assert_called_once_with("capacity", "JUN-01", "limits")
        policy.assert_called_once_with("CP-005", "risk")
        self.assertEqual(web["status"], "unavailable")
        self.assertIn("no offline web cache", web["reason"])
        self.assertIn("Do NOT substitute", web["instruction_to_agent"])
        self.credentials.assert_not_called()

    def test_hybrid_work_and_fabric_remain_synthetic_not_graph_or_fabric_sdk(self):
        with mock.patch.dict(os.environ, config("hybrid"), clear=True), \
                mock.patch.object(self.agent, "_search_local_relationships", return_value="work") as work, \
                mock.patch.object(self.agent, "_query_local_analytics", return_value="fabric") as fabric, \
                self.no_data_access():
            self.assertEqual(self.tool_calls()["work"](), "work")
            self.assertEqual(self.tool_calls()["fabric"](), "fabric")
        work.assert_called_once_with("covenant", "risk")
        fabric.assert_called_once_with("capacity", "JUN-01", "limits")
        self.credentials.assert_not_called()

    def test_hybrid_web_reports_native_connection_and_guardrails_without_fetching_web(self):
        rules = ["Cite live sources", "Include retrieval dates"]
        with mock.patch.dict(os.environ, config("hybrid"), clear=True), mock.patch.object(
                Path, "read_text", return_value=json.dumps({"answer_rules": rules})) as read:
            result = json.loads(self.agent.research_client_external_intelligence("Synthetic issuer", 14))
        self.assertEqual(result, {
            "layer": "Web IQ", "status": "live",
            "connection": HYBRID_VALUES["BING_GROUNDING_CONNECTION_ID"],
            "topic": "Synthetic issuer", "lookback_days": 14, "answer_rules": rules,
        })
        read.assert_called_once_with(encoding="utf-8")
        self.credentials.assert_not_called()

    def test_local_source_read_failures_propagate_instead_of_becoming_fabricated_answers(self):
        for method, args in ((self.agent.search_client_relationship_history, ("query",)),
                             (self.agent.lookup_capital_markets_policy, ("query",))):
            error = OSError("synthetic corpus unavailable")
            with self.subTest(method=method.__name__), \
                    mock.patch.dict(os.environ, {"IQ_MODE": "local"}, clear=True), \
                    mock.patch.object(Path, "read_text", side_effect=error):
                with self.assertRaises(OSError) as caught:
                    method(*args)
                self.assertIs(caught.exception, error)


class SearchBackendTests(AgentTestCase):
    def search_row(self):
        return {"id": "CP-005", "title": "Covenant monitoring", "category": "covenant_monitoring",
                "owner": "Synthetic Risk", "regulatory_anchor": "Synthetic regulation",
                "content": "z" * 2700, "@search.score": 1.5}

    def test_search_request_uses_exact_semantic_configuration_projection_and_escaped_filter(self):
        for category, expected_filter in ((None, None), ("", None), ("risk", "category eq 'risk'"),
                                          ("owner's risk", "category eq 'owner''s risk'"),
                                          ("x' or true or category eq 'x",
                                           "category eq 'x'' or true or category eq ''x'")):
            with self.subTest(category=category), self.sdk(search=True) as modules, \
                    mock.patch.dict(os.environ, config("hybrid"), clear=True), \
                    mock.patch.object(self.agent, "_lookup_local_policy",
                                      self.forbidden("local Search fallback")):
                factory = modules["azure.search.documents"].SearchClient
                search_client = factory.return_value.__enter__.return_value
                search_client.search.return_value = iter([self.search_row()])
                result = json.loads(self.agent.lookup_capital_markets_policy("CP-005 covenant", category))
                factory.assert_called_once_with("https://search.invalid", "offline-index", self.credential)
                search_client.search.assert_called_once_with(
                    search_text="CP-005 covenant", query_type="semantic",
                    semantic_configuration_name="offline-semantic", filter=expected_filter,
                    select=["id", "title", "category", "owner", "regulatory_anchor", "content"], top=4)
                self.assertEqual(result["matches"], 1)
                self.assertEqual(result["backend"], "Azure AI Search (offline-index)")
                self.assertEqual(result["results"], [{
                    key: value if key != "content" else value[:2500]
                    for key, value in self.search_row().items() if key != "@search.score"
                }])
                factory.return_value.__exit__.assert_called_once()
                self.credential.close.assert_called_once_with()
                self.assertEqual(self.credentials.call_args.args[0]["IQ_MODE"], "hybrid")
                self.credential.reset_mock()

    def test_search_no_matches_does_not_fall_back_to_local(self):
        with self.sdk(search=True) as modules, mock.patch.dict(os.environ, config("hybrid"), clear=True), \
                mock.patch.object(self.agent, "_lookup_local_policy", self.forbidden("local fallback")):
            modules["azure.search.documents"].SearchClient.return_value.__enter__.return_value.search.return_value = []
            result = json.loads(self.agent.lookup_capital_markets_policy("no match"))
        self.assertEqual(result["matches"], 0)
        self.assertEqual(result["results"], [])
        self.credential.close.assert_called_once_with()

    def test_search_failure_at_constructor_enter_search_or_iteration_propagates_and_closes_credential(self):
        for stage in ("constructor", "enter", "search", "iteration"):
            error = RuntimeError("synthetic Search service failure")

            def failing_results():
                yield self.search_row()
                raise error

            with self.subTest(stage=stage), self.sdk(search=True) as modules, \
                    mock.patch.dict(os.environ, config("hybrid"), clear=True), \
                    mock.patch.object(self.agent, "_lookup_local_policy", self.forbidden("local fallback")):
                factory = modules["azure.search.documents"].SearchClient
                if stage == "constructor":
                    factory.side_effect = error
                elif stage == "enter":
                    factory.return_value.__enter__.side_effect = error
                elif stage == "search":
                    factory.return_value.__enter__.return_value.search.side_effect = error
                else:
                    factory.return_value.__enter__.return_value.search.return_value = failing_results()
                with self.assertRaises(RuntimeError) as caught:
                    self.agent.lookup_capital_markets_policy("CP-005")
                self.assertIs(caught.exception, error)
                self.credential.close.assert_called_once_with()
                self.credential.reset_mock()


class SdkAgentTests(AgentTestCase):
    def test_client_uses_normalized_endpoint_selected_credential_after_local_validation(self):
        events = []
        with self.sdk() as modules, self.valid_local_inputs() as (validate, instructions):
            validate.side_effect = lambda values: events.append("data")
            instructions.side_effect = lambda: events.append("instructions") or INSTRUCTIONS
            self.credentials.side_effect = lambda values: events.append("credential") or self.credential
            factory = modules["azure.ai.agents"].AgentsClient
            factory.side_effect = lambda **kwargs: events.append("client") or "fake-sdk-client"
            self.assertEqual(self.agent._client(), "fake-sdk-client")
            factory.assert_called_once_with(endpoint=ENDPOINT, credential=self.credential)
            expected = {**config(), "FOUNDRY_PROJECT_ENDPOINT": ENDPOINT}
            validate.assert_called_once_with(expected)
            self.credentials.assert_called_once_with(expected)
        self.assertEqual(events, ["data", "instructions", "credential", "client"])

    def test_function_tools_have_exact_names_required_arguments_and_capacity_guardrails(self):
        definitions = self.agent._tool_defs()
        self.assertEqual(len(definitions), 4)
        self.assertEqual(set(self.agent.TOOL_FUNCTIONS), set(FUNCTIONS))
        self.assertEqual({tool["function"]["name"] for tool in definitions}, set(FUNCTIONS))
        for tool in definitions:
            fn = tool["function"]
            self.assertEqual(tool["type"], "function")
            self.assertEqual(fn["parameters"]["type"], "object")
            self.assertEqual(fn["parameters"]["required"], [FUNCTIONS[fn["name"]]])
            self.assertTrue(fn["description"])
            self.assertIs(self.agent.TOOL_FUNCTIONS[fn["name"]], getattr(self.agent, fn["name"]))
        analytics = next(tool["function"] for tool in definitions
                         if tool["function"]["name"] == "query_client_exposure_analytics")
        self.assertIn("COVENANT", analytics["description"])
        self.assertIn("SECTOR", analytics["description"])
        self.assertIn("not sufficient", analytics["description"])
        definitions[0]["function"]["name"] = "mutated"
        self.assertEqual(self.agent._tool_defs()[0]["function"]["name"], "search_client_relationship_history")

    def test_create_and_update_send_exact_request_fields_for_local_and_hybrid(self):
        for mode in ("local", "hybrid"):
            for existing in (False, True):
                client = self.mock_client()
                client.list_agents.return_value = iter([
                    types.SimpleNamespace(name="unrelated-agent", id="other"),
                    *([types.SimpleNamespace(name="offline-agent", id="matching-agent")] if existing else []),
                ])
                with self.subTest(mode=mode, existing=existing), self.valid_local_inputs(mode):
                    result = self.agent.create_or_update(client)
                expected_tools = self.agent._tool_defs()
                if mode == "hybrid":
                    expected_tools.append({
                        "type": "bing_grounding", "bing_grounding": {"search_configurations": [{
                            "connection_id": HYBRID_VALUES["BING_GROUNDING_CONNECTION_ID"], "count": 8,
                        }]},
                    })
                expected = {"name": "offline-agent", "model": "offline-model",
                            "instructions": INSTRUCTIONS, "tools": expected_tools}
                client.list_agents.assert_called_once_with()
                if existing:
                    client.update_agent.assert_called_once_with(agent_id="matching-agent", **expected)
                    client.create_agent.assert_not_called()
                    self.assertEqual(result, "updated-agent")
                else:
                    client.create_agent.assert_called_once_with(**expected)
                    client.update_agent.assert_not_called()
                    self.assertEqual(result, "created-agent")
                self.credentials.assert_not_called()

    def test_list_create_and_update_failures_propagate_without_second_write_or_fallback(self):
        for operation in ("list_agents", "create_agent", "update_agent"):
            client = self.mock_client()
            if operation == "update_agent":
                client.list_agents.return_value = [types.SimpleNamespace(name="offline-agent", id="existing")]
            error = RuntimeError("synthetic remote write failure")
            getattr(client, operation).side_effect = error
            with self.subTest(operation=operation), self.valid_local_inputs():
                with self.assertRaises(RuntimeError) as caught:
                    self.agent.create_or_update(client)
                self.assertIs(caught.exception, error)
            getattr(client, operation).assert_called_once()
            if operation != "create_agent":
                client.create_agent.assert_not_called()
            if operation != "update_agent":
                client.update_agent.assert_not_called()

    def test_main_create_manages_client_context_and_returns_success(self):
        client = self.mock_client()
        with self.valid_local_inputs(), mock.patch.object(self.agent, "_client", return_value=client), \
                mock.patch.object(self.agent, "create_or_update", return_value="saved") as create, \
                mock.patch.object(self.agent, "ask") as ask:
            self.assertEqual(self.agent.main(["--create"]), 0)
        client.__enter__.assert_called_once_with()
        client.__exit__.assert_called_once_with(None, None, None)
        create.assert_called_once_with(client)
        ask.assert_not_called()

    def test_main_ask_demo_and_trap_route_selected_dynamic_questions(self):
        for args, expected in ((["--ask", "Question supplied"], ["Question supplied"]),
                               (["--demo"], ["First dynamic question", "Second dynamic question"]),
                               (["--trap"], ["Dynamic capacity question"])):
            client = self.mock_client()
            with self.subTest(args=args), self.valid_local_inputs(), \
                    mock.patch.object(self.agent, "_client", return_value=client), \
                    mock.patch.object(self.agent, "create_or_update", return_value="saved"), \
                    mock.patch.object(self.agent, "ask") as ask, \
                    mock.patch.object(self.agent, "_demo_questions", return_value=[
                        "First dynamic question", "Second dynamic question"]) as demo, \
                    mock.patch.object(self.agent, "_trap_question", return_value="Dynamic capacity question") as trap:
                self.assertEqual(self.agent.main(args), 0)
                self.assertEqual(ask.call_args_list, [mock.call(client, "saved", question) for question in expected])
                if args == ["--demo"]:
                    demo.assert_called_once_with("JUN-01")
                if args == ["--trap"]:
                    trap.assert_called_once_with("JUN-01")

    def test_main_does_not_swallow_create_failure_and_exits_client_context(self):
        client = self.mock_client()
        error = RuntimeError("write denied")
        with self.valid_local_inputs(), mock.patch.object(self.agent, "_client", return_value=client), \
                mock.patch.object(self.agent, "create_or_update", side_effect=error):
            with self.assertRaises(RuntimeError) as caught:
                self.agent.main(["--create"])
        self.assertIs(caught.exception, error)
        self.assertIs(client.__exit__.call_args.args[1], error)


class AskLoopTests(AgentTestCase):
    def run_state(self, status, action=None):
        return types.SimpleNamespace(id="run-one", status=status, required_action=action,
                                     last_error="synthetic run error")

    def conversation(self):
        client = self.mock_client()
        client.threads.create.return_value = types.SimpleNamespace(id="thread-one")
        client.messages.list.return_value = [
            types.SimpleNamespace(role="user", text_messages=[
                types.SimpleNamespace(text=types.SimpleNamespace(value="do not print user message"))]),
            types.SimpleNamespace(role="assistant", text_messages=[]),
            types.SimpleNamespace(role="assistant", text_messages=[
                types.SimpleNamespace(text=types.SimpleNamespace(value="Earlier text")),
                types.SimpleNamespace(text=types.SimpleNamespace(value="Grounded synthetic answer"))]),
        ]
        return client

    def test_queued_in_progress_completed_preserves_question_and_prints_assistant_text(self):
        client = self.conversation()
        client.runs.create.return_value = self.run_state("queued")
        client.runs.get.side_effect = [self.run_state("in_progress"), self.run_state("completed")]
        with self.valid_local_inputs(), self.sdk(models=True) as modules, \
                mock.patch.object(time, "sleep") as sleep:
            self.agent.ask(client, "agent-one", "What is the synthetic risk?")
            order = modules["azure.ai.agents.models"].ListSortOrder.ASCENDING
        client.threads.create.assert_called_once_with()
        client.messages.create.assert_called_once_with(
            thread_id="thread-one", role="user", content="What is the synthetic risk?")
        client.runs.create.assert_called_once_with(thread_id="thread-one", agent_id="agent-one")
        self.assertEqual(client.runs.get.call_args_list, [
            mock.call(thread_id="thread-one", run_id="run-one"),
            mock.call(thread_id="thread-one", run_id="run-one"),
        ])
        self.assertEqual(sleep.call_args_list, [mock.call(1), mock.call(1)])
        client.messages.list.assert_called_once_with(thread_id="thread-one", order=order)
        self.assertIn("Grounded synthetic answer", self.stdout.getvalue())
        self.assertNotIn("do not print user message", self.stdout.getvalue())
        client.runs.submit_tool_outputs.assert_not_called()

    def test_requires_action_preserves_tool_output_strings_and_call_ids(self):
        client = self.conversation()
        with self.valid_local_inputs(), self.sdk(models=True) as modules, mock.patch.object(time, "sleep"):
            models = modules["azure.ai.agents.models"]
            calls = [models.RequiredFunctionToolCall(
                f"call-{i}", name, json.dumps({required: f"value-{i}"}))
                for i, (name, required) in enumerate(FUNCTIONS.items())]
            action = models.SubmitToolOutputsAction([*calls, object()])
            outputs = [f'{{"layer": "{i}", "exact": "évidence", "nested": [1, 2]}}\n'
                       for i in range(4)]
            functions = {name: mock.Mock(return_value=output)
                         for name, output in zip(FUNCTIONS, outputs)}
            client.runs.create.return_value = self.run_state("queued")
            client.runs.get.return_value = self.run_state("requires_action", action)
            client.runs.submit_tool_outputs.return_value = self.run_state("completed")
            with mock.patch.dict(self.agent.TOOL_FUNCTIONS, functions, clear=True):
                self.agent.ask(client, "agent-one", "Combine synthetic evidence")
            submitted = client.runs.submit_tool_outputs.call_args.kwargs
            self.assertEqual(submitted["thread_id"], "thread-one")
            self.assertEqual(submitted["run_id"], "run-one")
            self.assertEqual([row.tool_call_id for row in submitted["tool_outputs"]],
                             [f"call-{i}" for i in range(4)])
            self.assertEqual([row.output for row in submitted["tool_outputs"]], outputs)
            for i, (name, required) in enumerate(FUNCTIONS.items()):
                functions[name].assert_called_once_with(**{required: f"value-{i}"})
            client.runs.submit_tool_outputs.assert_called_once()

    def test_unknown_and_failing_tools_return_explicit_errors_not_local_fallback(self):
        client = self.conversation()
        failure = mock.Mock(side_effect=RuntimeError("synthetic lookup failed"))
        with self.valid_local_inputs(), self.sdk(models=True) as modules, mock.patch.object(time, "sleep"):
            models = modules["azure.ai.agents.models"]
            action = models.SubmitToolOutputsAction([
                models.RequiredFunctionToolCall("unknown-id", "missing_tool", ""),
                models.RequiredFunctionToolCall("failed-id", "failed_tool", "{}"),
            ])
            client.runs.create.return_value = self.run_state("in_progress")
            client.runs.get.return_value = self.run_state("requires_action", action)
            client.runs.submit_tool_outputs.return_value = self.run_state("completed")
            with mock.patch.dict(self.agent.TOOL_FUNCTIONS, {"failed_tool": failure}, clear=True):
                self.agent.ask(client, "agent-one", "Offline tool errors")
            outputs = client.runs.submit_tool_outputs.call_args.kwargs["tool_outputs"]
            self.assertEqual([(row.tool_call_id, json.loads(row.output)) for row in outputs], [
                ("unknown-id", {"error": "unknown tool"}),
                ("failed-id", {"error": "synthetic lookup failed"}),
            ])
            failure.assert_called_once_with()

    def test_failed_run_reports_error_without_reading_messages(self):
        client = self.conversation()
        client.runs.create.return_value = self.run_state("failed")
        with self.valid_local_inputs(), self.sdk(models=True), mock.patch.object(time, "sleep") as sleep:
            self.agent.ask(client, "agent-one", "Offline failure")
        self.assertIn("run failed: synthetic run error", self.stdout.getvalue())
        client.messages.list.assert_not_called()
        client.runs.get.assert_not_called()
        sleep.assert_not_called()

    def test_sdk_run_and_submission_errors_are_not_swallowed(self):
        for stage in ("create", "get", "submit_tool_outputs"):
            client = self.conversation()
            error = RuntimeError("synthetic SDK failure")
            with self.subTest(stage=stage), self.valid_local_inputs(), self.sdk(models=True) as modules, \
                    mock.patch.object(time, "sleep"):
                client.runs.create.return_value = self.run_state("queued")
                models = modules["azure.ai.agents.models"]
                client.runs.get.return_value = self.run_state(
                    "requires_action", models.SubmitToolOutputsAction([]))
                getattr(client.runs, stage).side_effect = error
                with self.assertRaises(RuntimeError) as caught:
                    self.agent.ask(client, "agent-one", "Offline service failure")
                self.assertIs(caught.exception, error)
            client.messages.list.assert_not_called()


if __name__ == "__main__":
    with mock.patch.dict(os.environ, {}, clear=True):
        unittest.main()
