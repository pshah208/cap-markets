# Fabric notebook - build the Direct Lake semantic model for the Capital Markets
# Client Intelligence Agent, then add the business measures on top.
#
# SYNTHETIC DEMO DATA. The Bank is a branding label only. Gibson Energy
# Inc. is a real public company referenced only so live web grounding returns real
# public news; every figure modelled here is invented for a demo.
#
# Run AFTER nb_load_client_intel has created the Delta tables.
#   Automated:  python deploy_fabric.py --only semantic-model
#
# Direct Lake means the model reads the Delta/Parquet files in OneLake directly -
# no import, no refresh schedule, no data duplication. The measures defined here
# are what make the model useful to Fabric IQ: they encode the business
# definitions (exposure, utilisation band, wallet share, covenant headroom) once
# in the semantic layer rather than in every query the agent composes.
#
# The whole body is wrapped so a full traceback is written to
# Files/_deploy/semantic_model_log.txt in the lakehouse - notebook job failures
# are otherwise opaque from the REST API.

import os
import re
import traceback
import uuid

LOG: list[str] = []


def log(msg: object) -> None:
    print(msg)
    LOG.append(str(msg))


def flush_log(config) -> None:
    try:
        from notebookutils import mssparkutils

        mssparkutils.fs.put(
            f"abfss://{config['FABRIC_WORKSPACE_ID']}@onelake.dfs.fabric.microsoft.com/"
            f"{config['FABRIC_LAKEHOUSE_ID']}/Files/_deploy/semantic_model_log.txt",
            "\n".join(LOG), True
        )
    except Exception as exc:  # noqa: BLE001
        print(f"could not write log: {exc}")


REQUIRED_ENV = ("FABRIC_WORKSPACE_ID", "FABRIC_LAKEHOUSE_ID", "FABRIC_SEMANTIC_MODEL_NAME")


def load_config(environ=None):
    environ = os.environ if environ is None else environ
    config = {}
    for name in REQUIRED_ENV:
        value = environ.get(name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} is required and must not be blank.")
        config[name] = value.strip()
    for name in ("FABRIC_WORKSPACE_ID", "FABRIC_LAKEHOUSE_ID"):
        value = config[name]
        if not re.fullmatch(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", value) or not uuid.UUID(value).int:
            raise ValueError(f"{name} must be a nonzero GUID.")
        config[name] = str(uuid.UUID(value))
    name = config["FABRIC_SEMANTIC_MODEL_NAME"]
    if len(name) > 256 or any(ord(c) < 32 or ord(c) == 127 for c in name):
        raise ValueError("FABRIC_SEMANTIC_MODEL_NAME must be 1–256 characters without controls.")
    return config


def main(environ=None):
    """Requires REQUIRED_ENV, plus semantic-link-labs preinstalled in Fabric."""
    config = load_config(environ)
    LOG.clear()
    build_model(config)

# client_360 is the grain the agent asks about most - one row per client, with
# exposure, revenue, wallet and covenant state already rolled up.
FACT = "client_360"

TABLES = [
    "client_360",
    "product_penetration",
    "risk_summary",
    "credit_facilities",
    "exposures",
    "limits_utilization",
    "covenants",
    "trades",
    "coverage_team",
    "risk_ratings",
    "scenario_sensitivity",
    "market_scenarios",
    "line_positions",
]

def build_model(config):
    DATASET = config["FABRIC_SEMANTIC_MODEL_NAME"]
    LAKEHOUSE = config["FABRIC_LAKEHOUSE_ID"]
    workspace = config["FABRIC_WORKSPACE_ID"]
    try:
        import sempy_labs as labs
        from sempy_labs.tom import connect_semantic_model
    except ImportError as exc:
        raise RuntimeError("Install semantic-link-labs in the Fabric notebook environment before running this entrypoint.") from exc
    try:
        log(f"sempy_labs {getattr(labs, '__version__', 'unknown')}")

        # ----------------------------------------------------------------------- #
        # 1. Generate the Direct Lake model over the curated tables.
        #    The signature of generate_direct_lake_semantic_model has changed across
        #    releases (0.17 requires both `tables` and `source`; earlier builds used
        #    `lakehouse` / `lakehouse_tables`). Introspect it and bind by alias rather
        #    than hard-coding, so this survives a library upgrade.
        # ----------------------------------------------------------------------- #
        import inspect

        gen = labs.directlake.generate_direct_lake_semantic_model
        sig = inspect.signature(gen)
        log(f"signature: generate_direct_lake_semantic_model{sig}")

        ALIASES = {
            "dataset": DATASET,
            "semantic_model": DATASET,
            "tables": TABLES,
            "lakehouse_tables": TABLES,
            "source": LAKEHOUSE,
            "lakehouse": LAKEHOUSE,
            "source_type": "Lakehouse",
            "workspace": workspace,
            "source_workspace": workspace,
            "overwrite": True,
            "refresh": True,
        }
        kwargs = {name: ALIASES[name] for name in sig.parameters if name in ALIASES}

        missing = [
            n for n, p in sig.parameters.items()
            if p.default is inspect.Parameter.empty
            and p.kind not in (p.VAR_POSITIONAL, p.VAR_KEYWORD)
            and n not in kwargs
        ]
        if missing:
            raise RuntimeError(f"unmapped required parameters {missing} - signature: {sig}")
        if not {"workspace", "source_workspace"} <= kwargs.keys():
            raise RuntimeError("Installed semantic-link-labs must support explicit workspace and source_workspace; upgrade it before deployment.")

        log(f"calling with: { {k: (v if not isinstance(v, list) else f'{len(v)} tables') for k, v in kwargs.items()} }")
        gen(**kwargs)
        log(f"semantic model '{DATASET}' generated")

        # ----------------------------------------------------------------------- #
        # 2. Relationships + measures.
        # ----------------------------------------------------------------------- #

        # (from_table, from_column, to_table, to_column)
        # client_360 is the one-side on client_id; the detail tables are the many-side.
        RELATIONSHIPS = [
            ("product_penetration", "client_id", "client_360", "client_id"),
            ("risk_summary",        "client_id", "client_360", "client_id"),
            ("credit_facilities",   "client_id", "client_360", "client_id"),
            ("exposures",           "client_id", "client_360", "client_id"),
            ("limits_utilization",  "client_id", "client_360", "client_id"),
            ("covenants",           "client_id", "client_360", "client_id"),
            ("trades",              "client_id", "client_360", "client_id"),
            ("coverage_team",       "client_id", "client_360", "client_id"),
            ("risk_ratings",        "client_id", "client_360", "client_id"),
            ("scenario_sensitivity", "client_id", "client_360", "client_id"),
            ("line_positions",      "client_id", "client_360", "client_id"),
        ]

        MEASURES = [
            # (table, name, DAX, format string, description)

            # --- Relationship / coverage ------------------------------------- #
            (FACT, "Clients Covered",
             f"COUNTROWS('{FACT}')", "#,0",
             "Number of clients in the coverage book."),

            (FACT, "FY26 YTD Revenue",
             f"SUM('{FACT}'[fy26_ytd_revenue_cad_k])", '"CAD "#,0" k"',
             "Fiscal year to date revenue across all products."),

            (FACT, "FY25 Same Period Revenue",
             f"SUM('{FACT}'[fy25_same_period_revenue_cad_k])", '"CAD "#,0" k"',
             "Prior-year revenue for the equivalent period - the only fair comparison."),

            (FACT, "Revenue YoY Pct",
             f"DIVIDE([FY26 YTD Revenue] - [FY25 Same Period Revenue], "
             f"[FY25 Same Period Revenue]) * 100", "0.0",
             "Year-on-year revenue growth, same period basis."),

            (FACT, "Estimated Street Wallet",
             f"SUM('{FACT}'[street_wallet_cad_k])", '"CAD "#,0" k"',
             "Estimated total fee pool the client pays the street. An estimate, and internal only."),

            (FACT, "Wallet Share Pct",
             f"DIVIDE([FY26 YTD Revenue], [Estimated Street Wallet]) * 100", "0.0",
             "The Bank's share of the estimated street wallet. INTERNAL - never disclosed to a client."),

            (FACT, "Whitespace Products",
             f"SUM('{FACT}'[whitespace_products])", "#,0",
             "Count of products where the Bank has zero revenue but the client pays the street."),

            (FACT, "Product Penetration Pct",
             f"DIVIDE(SUM('{FACT}'[products_held]), SUM('{FACT}'[products_available])) * 100", "0.0",
             "Share of the available product set the client actually holds."),

            # --- Exposure and limits ------------------------------------------ #
            (FACT, "Total Committed",
             f"SUM('{FACT}'[total_committed_cad_m])", '"CAD "#,0.0" m"',
             "Total committed credit across all facilities."),

            (FACT, "Total Drawn",
             f"SUM('{FACT}'[total_drawn_cad_m])", '"CAD "#,0.0" m"',
             "Drawn balance across all facilities."),

            (FACT, "Total Exposure",
             f"SUM('{FACT}'[total_exposure_cad_m])", '"CAD "#,0.0" m"',
             "Measured exposure: funded, contingent, derivative MTM plus PSE, and settlement."),

            (FACT, "Undrawn Commitment",
             "[Total Committed] - [Total Drawn]", '"CAD "#,0.0" m"',
             "Committed but undrawn - available to the client and consuming limit."),

            (FACT, "Single Name Limit",
             f"SUM('{FACT}'[single_name_limit_cad_m])", '"CAD "#,0.0" m"',
             "Approved single-name credit limit (CP-001)."),

            (FACT, "Single Name Headroom",
             f"SUM('{FACT}'[single_name_headroom_cad_m])", '"CAD "#,0.0" m"',
             "Limit less measured exposure. Headroom is NOT authority - CP-001."),

            (FACT, "Limit Utilisation Pct",
             f"DIVIDE([Total Exposure], [Single Name Limit]) * 100", "0.0",
             "Single-name limit utilisation. Green below 85, Amber 85-99, Breach at 100 (CP-001)."),

            (FACT, "Limit Utilisation Band",
             "VAR u = [Limit Utilisation Pct] "
             "RETURN IF(u >= 100, \"Breach\", IF(u >= 85, \"Amber\", \"Green\"))", "",
             "CP-001 utilisation band derived from the measure rather than stored, so it "
             "cannot drift from the number it describes."),

            # --- Covenants ----------------------------------------------------- #
            (FACT, "Tightest Covenant Headroom",
             f"MIN('{FACT}'[tightest_headroom])", "0.00",
             "Headroom on the client's most constrained covenant, in the covenant's own unit."),

            (FACT, "Clients In Tight Covenant Band",
             f"CALCULATE(COUNTROWS('{FACT}'), '{FACT}'[tightest_covenant_status] = \"Amber\")", "#,0",
             "Clients whose tightest covenant is in the Tight band and require monthly "
             "monitoring plus a four-quarter projection under CP-005."),

            ("covenants", "Covenant Breaches",
             "CALCULATE(COUNTROWS('covenants'), 'covenants'[status] = \"Breach\")", "#,0",
             "Covenants currently in breach. Any non-zero value escalates under CP-001."),

            # --- Risk ---------------------------------------------------------- #
            (FACT, "Watchlisted Clients",
             f"CALCULATE(COUNTROWS('{FACT}'), '{FACT}'[watchlist_flag] = \"Y\")", "#,0",
             "Clients on the credit watchlist."),

            ("risk_summary", "Avg Net Debt to EBITDA",
             "AVERAGE('risk_summary'[net_debt_to_ebitda])", "0.00",
             "Average leverage across the book, latest reported quarter."),

            # --- Limits detail -------------------------------------------------- #
            ("limits_utilization", "Limits In Amber Or Breach",
             "CALCULATE(COUNTROWS('limits_utilization'), "
             "'limits_utilization'[status] IN {\"Amber\", \"Breach\"})", "#,0",
             "Limits at or above their amber trigger. Includes the sector concentration "
             "limit, which constrains new commitments even where single-name headroom exists."),

            ("limits_utilization", "Max Limit Utilisation Pct",
             "MAX('limits_utilization'[utilisation_pct])", "0.0",
             "The most constrained limit in scope - usually the binding constraint."),

            # --- Product / wallet detail ---------------------------------------- #
            ("product_penetration", "Whitespace Gap To Target",
             "CALCULATE(SUM('product_penetration'[gap_to_target_cad_k]), "
             "'product_penetration'[whitespace_flag] = \"Y\")", '"CAD "#,0" k"',
             "Revenue implied by closing whitespace products to a 25 percent share target."),

            # --- Trades ---------------------------------------------------------- #
            ("trades", "Trade Count",
             "COUNTROWS('trades')", "#,0",
             "Transactions in the trailing twelve-month blotter."),

            ("trades", "Trade Revenue",
             "SUM('trades'[revenue_cad_k])", '"CAD "#,0" k"',
             "Revenue booked from blotter transactions."),

            ("trades", "Live Notional",
             "CALCULATE(SUM('trades'[notional_cad_m]), 'trades'[status] = \"Live\")",
             '"CAD "#,0.0" m"',
             "Notional of positions still live - the derivative book still generating PSE."),

            # --- Coverage --------------------------------------------------------- #
            ("coverage_team", "Interactions 90d",
             "SUM('coverage_team'[interactions_90d])", "#,0",
             "Recorded interactions across the deal team in the last 90 days."),

            ("coverage_team", "Wall Crossed Team Members",
             "CALCULATE(COUNTROWS('coverage_team'), "
             "'coverage_team'[wall_status] = \"wall_crossed\")", "#,0",
             "Team members on the crossing log. Non-zero means CP-008 applies to the "
             "attendee list and the agenda must be cleared by the Control Room."),
        ]

        with connect_semantic_model(dataset=DATASET, workspace=workspace, readonly=False) as tom:
            for from_table, from_col, to_table, to_col in RELATIONSHIPS:
                try:
                    tom.add_relationship(
                        from_table=from_table, from_column=from_col,
                        to_table=to_table, to_column=to_col,
                        from_cardinality="Many", to_cardinality="One",
                        cross_filtering_behavior="OneDirection", is_active=True,
                    )
                    log(f"+ relationship {from_table} -> {to_table}")
                except Exception as exc:  # noqa: BLE001
                    log(f"= relationship {from_table} skipped: {exc}")

            existing = {m.Name for m in tom.all_measures()}
            added = 0
            for table, name, dax, fmt, desc in MEASURES:
                if name in existing:
                    log(f"= measure {name}")
                    continue
                try:
                    tom.add_measure(table_name=table, measure_name=name, expression=dax,
                                    format_string=fmt, description=desc)
                    log(f"+ measure {name}")
                    added += 1
                except Exception as exc:  # noqa: BLE001
                    log(f"! measure {name} FAILED: {exc}")

            tom.model.Description = (
                "SYNTHETIC DEMO DATA - Capital Markets Client Intelligence. Direct Lake "
                "model over the coverage book. The Bank is a branding label "
                "only; the issuers are real public companies but every exposure, limit, "
                "revenue, wallet share, rating and covenant here is invented for a demo."
            )

        log(f"semantic model '{DATASET}' ready - {added} measures added, "
            f"{len(MEASURES)} defined, {len(RELATIONSHIPS)} relationships")
        log("STATUS: SUCCESS")

    except Exception:  # noqa: BLE001
        log("STATUS: FAILED")
        log(traceback.format_exc())
        flush_log(config)
        raise
    else:
        flush_log(config)


if __name__ == "__main__":
    main()
