# Fabric notebook: load the Capital Markets Client Intelligence CSVs into Delta.
#
# Run inside the lakehouse lh_client_intel. deploy_fabric.py wraps this file into
# a notebook definition and runs it as a job.
#
# Reads   Files/client-intel/*.csv
# Writes  10 base Delta tables + 3 curated tables the semantic model and the
#         agent's Fabric IQ tool query directly.
#
# SYNTHETIC DEMO DATA. BMO Capital Markets is a branding label only. Gibson Energy
# Inc. is a real public company referenced only so live web grounding returns real
# public news; every figure loaded here is invented for a demo.

from pyspark.sql import functions as F
from pyspark.sql.window import Window
from pyspark.sql.types import (
    BooleanType, DoubleType, IntegerType, StringType, StructField, StructType,
)

BASE = "Files/client-intel"

# Explicit schemas. Inferring them works until a column happens to be empty in the
# sample and silently lands as string, which then breaks a measure at query time.
SCHEMAS = {
    "clients": StructType([
        StructField("client_id", StringType()), StructField("client_name", StringType()),
        StructField("ticker", StringType()), StructField("sector", StringType()),
        StructField("sub_sector", StringType()), StructField("hq_city", StringType()),
        StructField("coverage_tier", StringType()),
        StructField("relationship_since", IntegerType()),
        StructField("relationship_years", IntegerType()),
        StructField("public_ratings", StringType()),
        StructField("internal_risk_rating", StringType()),
        StructField("internal_risk_rating_prior", StringType()),
        StructField("risk_trend", StringType()), StructField("watchlist_flag", StringType()),
        StructField("products_held", IntegerType()),
        StructField("products_available", IntegerType()),
        StructField("last_meeting_date", StringType()),
        StructField("kyc_refresh_due", StringType()),
        StructField("relationship_owner_alias", StringType()),
        StructField("coverage_banker_alias", StringType()),
    ]),
    "coverage_team": StructType([
        StructField("client_id", StringType()), StructField("client_name", StringType()),
        StructField("alias", StringType()), StructField("display_name", StringType()),
        StructField("job_title", StringType()), StructField("department", StringType()),
        StructField("coverage_role", StringType()), StructField("coverage_type", StringType()),
        StructField("interactions_90d", IntegerType()),
        StructField("last_interaction_date", StringType()),
        StructField("wall_status", StringType()), StructField("responsibility", StringType()),
    ]),
    "credit_facilities": StructType([
        StructField("client_id", StringType()), StructField("client_name", StringType()),
        StructField("facility_id", StringType()), StructField("facility_type", StringType()),
        StructField("product_id", StringType()),
        StructField("commitment_cad_m", DoubleType()), StructField("drawn_cad_m", DoubleType()),
        StructField("undrawn_cad_m", DoubleType()), StructField("utilisation_pct", DoubleType()),
        StructField("maturity_date", StringType()), StructField("pricing", StringType()),
        StructField("bmo_role", StringType()), StructField("status", StringType()),
        StructField("revolving_flag", StringType()),
    ]),
    "exposures": StructType([
        StructField("client_id", StringType()), StructField("client_name", StringType()),
        StructField("product_id", StringType()), StructField("product_name", StringType()),
        StructField("business_line", StringType()), StructField("exposure_type", StringType()),
        StructField("current_exposure_cad_m", DoubleType()),
        StructField("peak_12m_exposure_cad_m", DoubleType()),
        StructField("tenor_note", StringType()), StructField("as_of_date", StringType()),
    ]),
    "limits_utilization": StructType([
        StructField("client_id", StringType()), StructField("client_name", StringType()),
        StructField("limit_id", StringType()), StructField("limit_type", StringType()),
        StructField("limit_cad_m", DoubleType()), StructField("utilised_cad_m", DoubleType()),
        StructField("headroom_cad_m", DoubleType()), StructField("utilisation_pct", DoubleType()),
        StructField("status", StringType()), StructField("limit_owner", StringType()),
        StructField("next_review_date", StringType()), StructField("as_of_date", StringType()),
    ]),
    "revenue_by_product": StructType([
        StructField("client_id", StringType()), StructField("client_name", StringType()),
        StructField("product_id", StringType()), StructField("product_name", StringType()),
        StructField("business_line", StringType()),
        StructField("fy26_ytd_revenue_cad_k", DoubleType()),
        StructField("fy25_same_period_revenue_cad_k", DoubleType()),
        StructField("fy25_full_year_revenue_cad_k", DoubleType()),
        StructField("yoy_change_pct", DoubleType()),
        StructField("fiscal_year", StringType()), StructField("as_of_date", StringType()),
    ]),
    "wallet_share": StructType([
        StructField("client_id", StringType()), StructField("client_name", StringType()),
        StructField("product_id", StringType()), StructField("product_name", StringType()),
        StructField("bmo_revenue_cad_k", DoubleType()),
        StructField("estimated_street_wallet_cad_k", DoubleType()),
        StructField("bmo_wallet_share_pct", DoubleType()), StructField("bmo_rank", IntegerType()),
        StructField("lead_competitor", StringType()), StructField("whitespace_flag", StringType()),
        StructField("gap_to_25pct_target_cad_k", DoubleType()),
        StructField("as_of_date", StringType()),
    ]),
    "trades": StructType([
        StructField("client_id", StringType()), StructField("client_name", StringType()),
        StructField("trade_id", StringType()), StructField("trade_date", StringType()),
        StructField("product_id", StringType()), StructField("product_name", StringType()),
        StructField("description", StringType()), StructField("notional_cad_m", DoubleType()),
        StructField("revenue_cad_k", DoubleType()), StructField("desk", StringType()),
        StructField("status", StringType()), StructField("maturity_date", StringType()),
    ]),
    "covenants": StructType([
        StructField("client_id", StringType()), StructField("client_name", StringType()),
        StructField("covenant", StringType()), StructField("test_type", StringType()),
        StructField("threshold", DoubleType()), StructField("actual", DoubleType()),
        StructField("prior_quarter_actual", DoubleType()), StructField("unit", StringType()),
        StructField("headroom", DoubleType()), StructField("utilisation_pct", DoubleType()),
        StructField("status", StringType()), StructField("test_frequency", StringType()),
        StructField("source_facility", StringType()),
        StructField("last_tested_date", StringType()), StructField("next_test_date", StringType()),
    ]),
    "risk_ratings": StructType([
        StructField("client_id", StringType()), StructField("client_name", StringType()),
        StructField("as_of_date", StringType()),
        StructField("internal_risk_rating", StringType()), StructField("trend", StringType()),
        StructField("watchlist_flag", StringType()),
        StructField("net_debt_to_ebitda", DoubleType()),
        StructField("public_ratings", StringType()), StructField("analyst_note", StringType()),
    ]),
}

print("Loading base tables")
counts = {}
for name, schema in SCHEMAS.items():
    df = (spark.read.format("csv")
          .option("header", "true")
          .schema(schema)
          .load(f"{BASE}/{name}.csv"))
    df.write.mode("overwrite").option("overwriteSchema", "true").format("delta").saveAsTable(name)
    counts[name] = df.count()
    print(f"  {name:<22} {counts[name]:>4} rows")

# ---------------------------------------------------------------------------
# Curated tables. These exist so the agent's Fabric IQ tool answers the three
# questions it is asked most without composing joins at query time.
# ---------------------------------------------------------------------------
print("\nBuilding curated tables")

# 1. client_360 - one row per client, the shape of a pre-meeting brief.
clients = spark.table("clients")

exposure_roll = (spark.table("exposures")
                 .groupBy("client_id")
                 .agg(F.round(F.sum("current_exposure_cad_m"), 1).alias("total_exposure_cad_m"),
                      F.round(F.sum("peak_12m_exposure_cad_m"), 1).alias("peak_exposure_cad_m")))

facility_roll = (spark.table("credit_facilities")
                 .groupBy("client_id")
                 .agg(F.round(F.sum("commitment_cad_m"), 1).alias("total_committed_cad_m"),
                      F.round(F.sum("drawn_cad_m"), 1).alias("total_drawn_cad_m"),
                      F.count("*").alias("facility_count")))

revenue_roll = (spark.table("revenue_by_product")
                .groupBy("client_id")
                .agg(F.round(F.sum("fy26_ytd_revenue_cad_k"), 1).alias("fy26_ytd_revenue_cad_k"),
                     F.round(F.sum("fy25_same_period_revenue_cad_k"), 1).alias("fy25_same_period_revenue_cad_k"),
                     F.round(F.sum("fy25_full_year_revenue_cad_k"), 1).alias("fy25_full_year_revenue_cad_k")))

wallet_roll = (spark.table("wallet_share")
               .groupBy("client_id")
               .agg(F.round(F.sum("bmo_revenue_cad_k"), 1).alias("wallet_bmo_cad_k"),
                    F.round(F.sum("estimated_street_wallet_cad_k"), 1).alias("street_wallet_cad_k"),
                    F.sum(F.when(F.col("whitespace_flag") == "Y", 1).otherwise(0)).alias("whitespace_products")))

# The single-name limit is the one that matters for a coverage conversation.
single_name = (spark.table("limits_utilization")
               .filter(F.col("limit_type") == "Single-name credit limit")
               .select(F.col("client_id"),
                       F.col("limit_cad_m").alias("single_name_limit_cad_m"),
                       F.col("utilisation_pct").alias("single_name_utilisation_pct"),
                       F.col("status").alias("single_name_status"),
                       F.col("headroom_cad_m").alias("single_name_headroom_cad_m")))

# Tightest covenant = highest utilisation of its threshold.
cov = spark.table("covenants")
tightest = (cov.withColumn("rn",
                           F.row_number().over(
                               Window.partitionBy("client_id")
                               .orderBy(F.col("utilisation_pct").desc())))
            .filter(F.col("rn") == 1)
            .select("client_id",
                    F.col("covenant").alias("tightest_covenant"),
                    F.col("threshold").alias("tightest_threshold"),
                    F.col("actual").alias("tightest_actual"),
                    F.col("headroom").alias("tightest_headroom"),
                    F.col("unit").alias("tightest_unit"),
                    F.col("status").alias("tightest_covenant_status"),
                    F.col("next_test_date").alias("covenant_next_test_date")))

client_360 = (clients
              .join(facility_roll, "client_id", "left")
              .join(exposure_roll, "client_id", "left")
              .join(revenue_roll, "client_id", "left")
              .join(wallet_roll, "client_id", "left")
              .join(single_name, "client_id", "left")
              .join(tightest, "client_id", "left")
              .withColumn("revenue_yoy_pct",
                          F.round((F.col("fy26_ytd_revenue_cad_k") - F.col("fy25_same_period_revenue_cad_k"))
                                  / F.col("fy25_same_period_revenue_cad_k") * 100, 1))
              .withColumn("wallet_share_pct",
                          F.round(F.col("wallet_bmo_cad_k") / F.col("street_wallet_cad_k") * 100, 1))
              .withColumn("product_penetration_pct",
                          F.round(F.col("products_held") / F.col("products_available") * 100, 1)))

client_360.write.mode("overwrite").option("overwriteSchema", "true").format("delta").saveAsTable("client_360")
print(f"  client_360             {client_360.count():>4} rows")

# 2. product_penetration - revenue and wallet joined per client/product, so
#    "where are we weak?" is one scan.
product_penetration = (spark.table("wallet_share").alias("w")
                       .join(spark.table("revenue_by_product").alias("r"),
                             ["client_id", "product_id"], "outer")
                       .select(F.coalesce(F.col("w.client_name"), F.col("r.client_name")).alias("client_name"),
                               F.col("client_id"), F.col("product_id"),
                               F.coalesce(F.col("w.product_name"), F.col("r.product_name")).alias("product_name"),
                               F.col("r.business_line").alias("business_line"),
                               F.coalesce(F.col("r.fy26_ytd_revenue_cad_k"), F.lit(0.0)).alias("fy26_ytd_revenue_cad_k"),
                               F.coalesce(F.col("r.fy25_same_period_revenue_cad_k"), F.lit(0.0)).alias("fy25_same_period_revenue_cad_k"),
                               F.col("w.estimated_street_wallet_cad_k").alias("street_wallet_cad_k"),
                               F.col("w.bmo_wallet_share_pct").alias("wallet_share_pct"),
                               F.col("w.bmo_rank").alias("rank"),
                               F.col("w.lead_competitor").alias("lead_competitor"),
                               F.col("w.whitespace_flag").alias("whitespace_flag"),
                               F.col("w.gap_to_25pct_target_cad_k").alias("gap_to_target_cad_k")))

product_penetration.write.mode("overwrite").option("overwriteSchema", "true").format("delta").saveAsTable("product_penetration")
print(f"  product_penetration    {product_penetration.count():>4} rows")

# 3. risk_summary - latest rating per client plus covenant and limit state, which
#    is what a credit associate asks for first.
latest_rating = (spark.table("risk_ratings")
                 .withColumn("rn", F.row_number().over(
                     Window.partitionBy("client_id").orderBy(F.col("as_of_date").desc())))                 .filter(F.col("rn") == 1)
                 .drop("rn"))

risk_summary = (latest_rating
                .join(single_name, "client_id", "left")
                .join(tightest, "client_id", "left")
                .join(exposure_roll, "client_id", "left")
                .select("client_id", "client_name",
                        F.col("as_of_date").alias("rating_as_of"),
                        "internal_risk_rating", "trend", "watchlist_flag",
                        "net_debt_to_ebitda", "public_ratings",
                        "total_exposure_cad_m", "single_name_limit_cad_m",
                        "single_name_utilisation_pct", "single_name_status",
                        "tightest_covenant", "tightest_threshold", "tightest_actual",
                        "tightest_headroom", "tightest_unit", "tightest_covenant_status",
                        "covenant_next_test_date"))

risk_summary.write.mode("overwrite").option("overwriteSchema", "true").format("delta").saveAsTable("risk_summary")
print(f"  risk_summary           {risk_summary.count():>4} rows")

# ---------------------------------------------------------------------------
# Reconciliation. The demo depends on these figures matching what the emails,
# meeting minutes and policy documents say. Fail loudly here rather than let the
# agent contradict itself on stage.
# ---------------------------------------------------------------------------
print("\nReconciling the hero client against the narrative")
hero = client_360.filter(F.col("client_id") == "CLI-1001").collect()[0]

expected = {
    "total_committed_cad_m": 465.0,
    "total_drawn_cad_m": 288.4,
    "total_exposure_cad_m": 341.7,
    "fy26_ytd_revenue_cad_k": 8420.0,
    "fy25_same_period_revenue_cad_k": 7140.0,
    "revenue_yoy_pct": 17.9,
    "wallet_share_pct": 21.4,
    "single_name_limit_cad_m": 500.0,
    "single_name_utilisation_pct": 68.3,
    "tightest_actual": 4.18,
    "tightest_threshold": 4.5,
    "tightest_headroom": 0.32,
}

failures = []
for field, want in expected.items():
    got = hero[field]
    ok = got is not None and abs(float(got) - want) < 0.051
    print(f"  {'OK  ' if ok else 'FAIL'} {field:<32} got {got}  want {want}")
    if not ok:
        failures.append(field)

assert hero["tightest_covenant"] == "Total Net Debt to Adjusted EBITDA", \
    f"tightest covenant drifted: {hero['tightest_covenant']}"
assert hero["internal_risk_rating"] == "IG-6", \
    f"hero rating drifted: {hero['internal_risk_rating']}"

if failures:
    raise AssertionError(f"Fabric load does not reconcile with the narrative: {failures}")

print(f"\nLoaded {len(SCHEMAS)} base + 3 curated tables. All hero figures reconcile.")
