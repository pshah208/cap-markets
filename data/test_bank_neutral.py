"""Offline data-contract tests. Run: python -m unittest discover -s data -v"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import generate_dashboard_snapshot as dashboard
import mission_data
import validate_dataset
from scenario_facts import CLIENTS, DISCLAIMER, FACTS, PEOPLE

HERE = Path(__file__).resolve().parent


def load_generator(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


fabric = load_generator("fabric_generator", HERE / "fabric-iq" / "generate_fabric_data.py")
scenarios = load_generator("scenario_generator", HERE / "market-scenario" / "generate_scenario_tables.py")


class BankNeutralDataTests(unittest.TestCase):
    def test_source_validation_never_reads_private_tenant_mapping(self):
        read_text = Path.read_text

        def public_read(path, *args, **kwargs):
            self.assertNotEqual(path.name, "user_mapping.json")
            self.assertFalse(path.name.endswith((".local.json", ".restore.json")))
            return read_text(path, *args, **kwargs)

        with patch.object(Path, "read_text", public_read), \
                patch.object(sys, "argv", ["validate_dataset.py"]), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(validate_dataset.main(), 0)

    def test_canonical_institution_and_public_issuers(self):
        self.assertEqual(FACTS["institution"], "The Bank")
        self.assertEqual(FACTS["institution_short"], "The Bank")
        self.assertIn("The Bank is a fictional institution.", DISCLAIMER)
        self.assertEqual(FACTS["hero_client_name"], "Gibson Energy Inc.")
        self.assertEqual(FACTS["hero_ticker"], "TSX:GEI")
        self.assertEqual(len(CLIENTS), 10)
        self.assertTrue(all(client[2].startswith("TSX:") for client in CLIENTS))

    def test_neutral_truth_keys_and_unchanged_hold(self):
        meeting = FACTS["meeting"]
        self.assertEqual({k for k in meeting if k.endswith("_attendees")},
                         {"bank_attendees", "client_attendees"})
        self.assertTrue(set(meeting["bank_attendees"]) <= {p["alias"] for p in PEOPLE})
        proposal = FACTS["opportunities"]["revolver_upsize"]
        self.assertEqual({k for k in proposal if k.endswith("_hold_m")},
                         {"bank_current_hold_m", "bank_proposed_hold_m"})
        self.assertEqual(proposal["bank_current_hold_m"], 165.0)
        self.assertEqual(proposal["bank_proposed_hold_m"], 210.0)
        for key in ("revolver_upsize", "dcm_followon"):
            self.assertEqual({k for k in FACTS["opportunities"][key] if k.endswith("_role")},
                             {"bank_role"})

    def test_fabric_build_is_deterministic_and_matches_owned_csvs(self):
        tables = fabric.build_tables()
        self.assertEqual(tables, fabric.build_tables())
        self.assertEqual(len(tables), 10)
        self.assertEqual(sum(len(rows) for _, rows in tables.values()), 404)
        for name, (header, rows) in tables.items():
            with self.subTest(table=name):
                self.assertEqual((fabric.HERE / name).read_bytes(), fabric._csv_bytes(header, rows))

    def test_neutral_csv_schema_and_wallet_numerator(self):
        tables = fabric.build_tables()
        facilities, _ = tables["credit_facilities.csv"]
        self.assertEqual({k for k in facilities if k.endswith("_role")}, {"bank_role"})
        wallet, rows = tables["wallet_share.csv"]
        self.assertEqual({k for k in wallet if k.endswith(("_revenue_cad_k", "_wallet_share_pct", "_rank"))},
                         {"bank_revenue_cad_k", "bank_wallet_share_pct", "bank_rank"})
        hero = [dict(zip(wallet, row)) for row in rows if row[0] == FACTS["hero_client_id"]]
        revenue = sum(row["bank_revenue_cad_k"] for row in hero)
        street = sum(row["estimated_street_wallet_cad_k"] for row in hero)
        self.assertEqual(revenue, FACTS["hero_metrics"]["fy26_ytd_revenue_k"])
        self.assertEqual(round(revenue / street * 100, 1), FACTS["hero_metrics"]["wallet_share_pct"])

    def test_fabric_check_never_writes(self):
        with patch.object(sys, "argv", ["generate_fabric_data.py", "--check"]), \
                patch.object(fabric, "_write", side_effect=AssertionError("check must not write")), \
                patch.object(Path, "write_bytes", side_effect=AssertionError("check must not write")), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(fabric.main(), 0)

    def test_fabric_check_rejects_missing_and_stale_csv(self):
        with contextlib.redirect_stdout(io.StringIO()):
            for value in (b"stale", FileNotFoundError("missing")):
                with self.subTest(value=value), patch.object(Path, "read_bytes") as read:
                    if isinstance(value, Exception):
                        read.side_effect = value
                    else:
                        read.return_value = value
                    self.assertFalse(fabric._check("clients.csv", ["client_id"], [["CLI-1001"]]))

    def test_fabric_failed_reconciliation_never_writes(self):
        for args in ([], ["--check"]):
            with self.subTest(args=args), \
                    patch.object(sys, "argv", ["generate_fabric_data.py", *args]), \
                    patch.object(fabric, "reconcile_tables", return_value=False), \
                    patch.object(fabric, "_write", side_effect=AssertionError("invalid data must not be written")), \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(fabric.main(), 1)

    def test_mission_data_only_isolated_from_work_and_app(self):
        read_text = Path.read_text

        def scoped_read(path, *args, **kwargs):
            self.assertNotIn("work-iq", path.parts)
            self.assertNotIn("app", path.parts)
            return read_text(path, *args, **kwargs)

        with patch.object(Path, "read_text", scoped_read), \
                patch.object(Path, "write_text", side_effect=AssertionError("build must not write")):
            outputs = mission_data.build_outputs(data_only=True)
        self.assertEqual(set(outputs), {
            HERE / "fabric-iq" / "line_positions.csv",
            HERE / "foundry-iq" / "cm_policies.json",
        })
        for path, content in outputs.items():
            self.assertEqual(path.read_text(encoding="utf-8"), content.replace("\r\n", "\n"))
        self.assertEqual(sum(mission_data.conflicts().values()), 9)

    def test_mission_full_build_preserves_output_contract(self):
        with patch.object(Path, "write_text", side_effect=AssertionError("build must not write")):
            outputs = mission_data.build_outputs()
        self.assertEqual(len(outputs), 4)
        mail = json.loads(outputs[HERE / "work-iq" / "mission_emails.json"])
        policy = json.loads(outputs[HERE / "foundry-iq" / "cm_policies.json"])
        self.assertEqual(mail["scenario"], policy["scenario"])
        self.assertTrue(mail["scenario"].startswith("The Bank - "))
        self.assertEqual(mail["as_of"], FACTS["as_of"])
        self.assertEqual(mail["emails"], mission_data.EMAILS)

    def test_mission_check_never_writes_and_rejects_stale_or_missing(self):
        with patch.object(sys, "argv", ["mission_data.py", "--data-only", "--check"]), \
                patch.object(Path, "write_text", side_effect=AssertionError("check must not write")), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(mission_data.main(), 0)
            outputs = mission_data.build_outputs(data_only=True)
            with patch.object(mission_data, "build_outputs", return_value=outputs):
                with patch.object(Path, "exists", return_value=False):
                    self.assertEqual(mission_data.main(), 1)
                with patch.object(Path, "read_text", return_value="stale"):
                    self.assertEqual(mission_data.main(), 1)

    def test_snapshot_uses_neutral_wallet_schema_without_writing_web(self):
        with patch.object(Path, "write_bytes", side_effect=AssertionError("build must not write")):
            snapshot = dashboard.build_snapshot()
        self.assertEqual(len(snapshot["companies"]), 10)
        hero = next(c for c in snapshot["companies"] if c["id"] == FACTS["hero_client_id"])
        self.assertEqual(hero["walletRevenueCad"], 8.42)
        self.assertEqual(hero["walletPercent"], 21.4)
        self.assertEqual(hero["exposureCad"], 341.7)
        self.assertEqual(hero["commitmentCad"], 465.0)
        self.assertEqual(hero["name"], FACTS["hero_client_name"])
        self.assertIn(FACTS["mnpi_tension"]["id"], hero["risk"])

    def test_scenario_tables_remain_coherent_and_current(self):
        sensitivity, presets = scenarios.build()
        self.assertEqual({r["client_id"] for r in sensitivity}, {c[0] for c in CLIENTS})
        self.assertEqual(len({r["scenario_id"] for r in presets}), 11)
        for name, rows in (("scenario_sensitivity.csv", sensitivity), ("market_scenarios.csv", presets)):
            self.assertEqual((fabric.HERE / name).read_text(encoding="utf-8"), scenarios.to_csv(rows))
        shock = {r["factor"]: float(r["value"]) for r in presets if r["scenario_id"] == "oil-shock"}
        for row in sensitivity:
            total = sum(row[f"beta_{factor}"] * shock[f"{factor}_pct" if factor != "fx" else "usdcad_pct"]
                        for factor in ("oil", "gas", "fx", "demand", "tariff"))
            self.assertAlmostEqual(total, row["oil_shock_ebitda_pct"], places=2)


if __name__ == "__main__":
    unittest.main()
