"""Single source of truth for the Capital Markets Client Intelligence demo.

Every generator, every seeded email, every policy document and every meeting
record reconciles to the constants in this file. If a covenant threshold, a
commitment amount, a limit utilisation or a meeting date needs to change, change
it *here* and re-run the generators — never edit a generated CSV by hand.

    from scenario_facts import FACTS, CLIENTS, PEOPLE

--------------------------------------------------------------------------------
SYNTHETIC DEMO DATA
--------------------------------------------------------------------------------
BMO Capital Markets is used only as a branding label. Gibson Energy Inc. and the
other TSX-listed issuers named here are real public companies, used *only* so
that the Web IQ layer's live web grounding returns genuine public news. Every
internal figure in this dataset -- every exposure, commitment, limit, revenue
number, wallet-share estimate, internal risk rating, covenant headroom, trade,
colleague, email, Teams message, meeting and internal policy -- is invented for
this demo and reflects no real bank, no real client relationship and no real
credit position. Public credit ratings and public filings are referenced by name
only. Do not present any of this as real information about any institution.
"""

from __future__ import annotations

# --------------------------------------------------------------------------
# Scenario spine
# --------------------------------------------------------------------------

FACTS = {
    "institution": "BMO Capital Markets",
    "institution_short": "BMO",
    "as_of": "2026-08-10",
    "fiscal_year": "FY26",
    "fiscal_year_start": "2025-11-01",   # BMO's fiscal year runs Nov 1 - Oct 31
    "currency": "CAD",
    "random_seed": 26_08_10,

    # The hero client
    "hero_client_id": "CLI-1001",
    "hero_client_name": "Gibson Energy Inc.",
    "hero_ticker": "TSX:GEI",

    # The meeting the whole demo prepares for
    "meeting": {
        "id": "MTG-GEI-2026-08-13",
        "date": "2026-08-13",
        "time_local": "10:00-11:30 MT",
        "location": "Gibson Energy head office, Calgary (in person)",
        "title": "Gibson Energy - CFO / Treasurer coverage meeting",
        "bmo_attendees": ["sydney.mattos", "sasha.ouellet", "quinn.campbell", "vance.deleon"],
        "client_attendees": [
            "Chief Financial Officer (client)",
            "VP & Treasurer (client)",
            "Director, Capital Markets (client)",
        ],
        "agenda": [
            "FY26 year-to-date relationship review and FY27 wallet ambition",
            "Revolving credit facility: upsize to CAD 1.35bn and one-year extension",
            "Commodity + FX hedging overlay for the Chauvin volumes",
            "Follow-on DCM: potential 2027 maturity refinancing window",
            "Sustainability-linked structure options",
        ],
    },

    # The three asks on the table
    "opportunities": {
        "revolver_upsize": {
            "id": "OPP-4471",
            "name": "Revolver upsize + 1-year extension",
            "current_commitment_total_m": 1_100.0,
            "proposed_commitment_total_m": 1_350.0,
            "bmo_current_hold_m": 165.0,
            "bmo_proposed_hold_m": 210.0,
            "bmo_role": "Co-Lead Arranger and Joint Bookrunner",
            "estimated_fees_k": 1_850.0,
            "decision_needed_by": "2026-09-30",
        },
        "hedging_overlay": {
            "id": "OPP-4472",
            "name": "Chauvin commodity + FX hedging overlay",
            "notional_m": 240.0,
            "tenor_months": 24,
            "estimated_revenue_k": 940.0,
            "products": ["WTI-WCS differential swap", "CAD/USD forward strip"],
            "decision_needed_by": "2026-10-15",
        },
        "dcm_followon": {
            "id": "OPP-4473",
            "name": "2027 maturity refinancing - follow-on senior unsecured",
            "indicative_size_m": 350.0,
            "estimated_fees_k": 1_120.0,
            "bmo_role": "Joint Bookrunner (sought; active bookrunner on the July 2026 deal)",
            "decision_needed_by": "2027-01-31",
        },
    },

    # Fabric IQ headline numbers for the hero client (CAD millions unless noted)
    "hero_metrics": {
        "total_committed_m": 465.0,
        "total_drawn_m": 288.4,
        "total_exposure_m": 341.7,          # drawn + derivative MTM + settlement
        "single_name_limit_m": 500.0,
        "limit_utilisation_pct": 68.3,
        "fy26_ytd_revenue_k": 8_420.0,
        "fy25_full_year_revenue_k": 9_960.0,
        "fy25_same_period_revenue_k": 7_140.0,
        "revenue_yoy_pct": 17.9,
        "wallet_share_pct": 21.4,
        "wallet_share_prior_pct": 18.9,
        "estimated_street_wallet_k": 39_350.0,
        "wallet_rank": 2,
        "wallet_rank_prior": 3,
        "products_held": 7,
        "products_available": 11,
        "internal_risk_rating": "IG-6",
        "internal_risk_rating_prior": "IG-6",
        "internal_risk_rating_2q_ago": "IG-7",
        "risk_trend": "improving",
        "watchlist": False,
        "public_ratings": "S&P BBB- (stable) / DBRS BBB (low) (stable)",
        "relationship_since": 2011,
        "last_meeting_date": "2026-05-21",
        "last_credit_review_date": "2026-03-18",
        "next_credit_review_due": "2027-03-31",
        "kyc_refresh_due": "2026-09-30",
        "kyc_status": "Due - 51 days",
    },

    # The one number the whole demo turns on
    "covenant_tension": {
        "covenant": "Total Net Debt to Adjusted EBITDA",
        "threshold": 4.50,
        "actual": 4.18,
        "headroom_turns": 0.32,
        "prior_quarter_actual": 3.94,
        "note": (
            "Post-Chauvin leverage sits 0.32 turns inside the covenant. The proposed "
            "revolver upsize adds committed capacity but the internal Credit view is "
            "that incremental drawn debt inside two quarters of the reporting date "
            "needs a pro-forma test before the pitch is delivered."
        ),
    },

    # The client's own balance sheet, at the covenant test date.
    #
    # These two figures exist so the CP-005 pro-forma test can be COMPUTED rather
    # than asserted: leverage = total_net_debt_m / adjusted_ebitda_ltm_m, and a
    # fully-drawn incremental commitment moves only the numerator. They reconcile
    # exactly to covenant_tension["actual"] -- 2558.2 / 612.0 = 4.18 -- and
    # validate_dataset.py asserts that, so the two can never drift apart.
    #
    # Consequences worth knowing before changing them:
    #   * the proposed +250m of committed capacity (1,100 -> 1,350) takes
    #     pro-forma leverage to 4.59x, through the 4.50x maximum;
    #   * the largest incremental commitment that still clears 4.50x fully drawn
    #     is 195.8m, so the deal has to shrink by ~54m to be deliverable.
    "client_financials": {
        "adjusted_ebitda_ltm_m": 612.0,
        "total_net_debt_m": 2_558.2,
        "as_of": "2026-06-30",
        "basis": (
            "Last twelve months to the 2026-06-30 compliance certificate. "
            "Adjusted EBITDA is the credit-agreement definition, after the "
            "add-backs CP-005 permits."
        ),
    },

    # The deliberate cross-layer conflict the agent must SURFACE, not resolve
    "mnpi_tension": {
        "id": "CR-2026-0184",
        "raised_by": "Control Room (Compliance)",
        "raised_on": "2026-08-06",
        "summary": (
            "Two BMO staff were wall-crossed on 2026-08-04 in connection with a "
            "potential Gibson Energy corporate action. The public-side coverage team "
            "is NOT wall-crossed and must not be. Research is restricted from "
            "publishing on the name and Corporate Sales may not solicit new "
            "derivative business tied to the unannounced transaction."
        ),
        "restricted_persons": ["sasha.ouellet", "vance.deleon"],
        "public_side": ["sydney.mattos", "robin.kline", "quinn.campbell"],
        "expires": "2026-09-15",
        "effect": (
            "The revolver upsize pitch may proceed on public information only. The "
            "hedging overlay solicitation must be cleared by the Control Room before "
            "Thursday. Research may not publish or update the target price."
        ),
    },
}

# --------------------------------------------------------------------------
# The coverage portfolio - 10 real TSX-listed Canadian mid-caps
#
# Real tickers so that Web IQ live grounding returns genuine public news.
# EVERY financial figure attached to them below is synthetic.
# --------------------------------------------------------------------------

CLIENTS = [
    # id, name, ticker, sector, sub_sector, hq, coverage_tier, since
    ("CLI-1001", "Gibson Energy Inc.",            "TSX:GEI",  "Energy",      "Midstream / Infrastructure", "Calgary, AB",   "Tier 1", 2011),
    ("CLI-1002", "Keyera Corp.",                  "TSX:KEY",  "Energy",      "Midstream / NGL",            "Calgary, AB",   "Tier 1", 2009),
    ("CLI-1003", "Whitecap Resources Inc.",       "TSX:WCP",  "Energy",      "E&P - Light Oil",            "Calgary, AB",   "Tier 2", 2014),
    ("CLI-1004", "Secure Waste Infrastructure",   "TSX:SES",  "Energy",      "Energy Services",            "Calgary, AB",   "Tier 2", 2016),
    ("CLI-1005", "Stella-Jones Inc.",             "TSX:SJ",   "Materials",   "Wood Products",              "Montreal, QC",  "Tier 2", 2013),
    ("CLI-1006", "Russel Metals Inc.",            "TSX:RUS",  "Materials",   "Metals Distribution",        "Mississauga, ON","Tier 2", 2010),
    ("CLI-1007", "Cascades Inc.",                 "TSX:CAS",  "Materials",   "Packaging / Tissue",         "Kingsey Falls, QC","Tier 3", 2012),
    ("CLI-1008", "Ag Growth International Inc.",  "TSX:AFN",  "Industrials", "Agricultural Equipment",     "Winnipeg, MB",  "Tier 3", 2017),
    ("CLI-1009", "North West Company Inc.",       "TSX:NWC",  "Industrials", "Retail Distribution",        "Winnipeg, MB",  "Tier 3", 2015),
    ("CLI-1010", "Superior Plus Corp.",           "TSX:SPB",  "Energy",      "Energy Distribution",        "Toronto, ON",   "Tier 2", 2011),
]

# --------------------------------------------------------------------------
# The BMO deal team - mapped onto real licensed accounts in the demo tenant
# --------------------------------------------------------------------------

PEOPLE = [
    {
        "alias": "sydney.mattos",
        "displayName": "Sydney Mattos",
        "title": "Managing Director, Corporate Coverage - Energy",
        "department": "Corporate Banking",
        "role": "relationship_owner",
        "persona_view": "relationship_manager",
        "upn_seed": "SydneyM",
        "is_driver": True,
        "wall_status": "public_side",
    },
    {
        "alias": "sasha.ouellet",
        "displayName": "Sasha Ouellet",
        "title": "Director, Corporate Banking & DCM Origination",
        "department": "Corporate Banking",
        "role": "relationship_manager",
        "persona_view": "relationship_manager",
        "upn_seed": "SashaO",
        "is_driver": False,
        "wall_status": "wall_crossed",
    },
    {
        "alias": "robin.kline",
        "displayName": "Robin Kline",
        "title": "Executive Director, Equity Research - Energy Infrastructure",
        "department": "Research",
        "role": "research_analyst",
        "persona_view": "analyst",
        "upn_seed": "RobinK",
        "is_driver": False,
        "wall_status": "public_side",
    },
    {
        "alias": "quinn.campbell",
        "displayName": "Quinn Campbell",
        "title": "Director, Commodities & FX Corporate Sales",
        "department": "Global Markets",
        "role": "trader",
        "persona_view": "trader",
        "upn_seed": "QuinnC",
        "is_driver": False,
        "wall_status": "public_side",
    },
    {
        "alias": "vance.deleon",
        "displayName": "Vance DeLeon",
        "title": "Director, Credit Risk - Energy & Midstream",
        "department": "Credit Risk Management",
        "role": "credit_risk",
        "persona_view": "credit_risk",
        "upn_seed": "VanceD",
        "is_driver": False,
        "wall_status": "wall_crossed",
    },
]

# Voices that appear in content but have no tenant account.
NON_ACCOUNT_VOICES = {
    "control.room":    "Control Room (Compliance)",
    "syndicate.desk":  "Loan Syndications Desk",
    "client.cfo":      "Chief Financial Officer, Gibson Energy (client)",
    "client.treasurer": "VP & Treasurer, Gibson Energy (client)",
    "kyc.ops":         "Client Onboarding & KYC Operations",
}

# --------------------------------------------------------------------------
# Role-aware views - drives the agent's lead section and next-action bias
# --------------------------------------------------------------------------

ROLE_VIEWS = {
    "relationship_manager": {
        "label": "Relationship Manager / Coverage",
        "leads_with": ["wallet_share", "revenue_by_product", "whitespace", "relationship_map"],
        "next_action_bias": "pitch, cross-sell, meeting agenda and follow-up ownership",
    },
    "trader": {
        "label": "Trader / Corporate Sales",
        "leads_with": ["derivative_positions", "margin_collateral", "market_moves", "hedge_ratio"],
        "next_action_bias": "pricing and execution readiness, credit line pre-clearance",
    },
    "analyst": {
        "label": "Research Analyst",
        "leads_with": ["earnings", "guidance", "sector_comps", "thesis_drivers"],
        "next_action_bias": "note or thesis update and model driver changes",
    },
    "credit_risk": {
        "label": "Credit / Risk Associate",
        "leads_with": ["exposure", "limits", "covenants", "risk_rating_trend", "breaches"],
        "next_action_bias": "limit action, covenant test, watchlist and escalation",
    },
}

# Product taxonomy used consistently across exposures, revenue and trades.
PRODUCTS = [
    ("PRD-01", "Corporate Loan - Revolving Credit Facility", "Corporate Banking"),
    ("PRD-02", "Corporate Loan - Term Loan",                 "Corporate Banking"),
    ("PRD-03", "Letters of Credit",                          "Corporate Banking"),
    ("PRD-04", "Debt Capital Markets - Underwriting",        "Investment Banking"),
    ("PRD-05", "Equity Capital Markets - Underwriting",      "Investment Banking"),
    ("PRD-06", "M&A Advisory",                               "Investment Banking"),
    ("PRD-07", "FX - Forwards and Options",                  "Global Markets"),
    ("PRD-08", "Interest Rate Derivatives",                  "Global Markets"),
    ("PRD-09", "Commodity Derivatives",                      "Global Markets"),
    ("PRD-10", "Cash Management & Treasury Services",        "Transaction Banking"),
    ("PRD-11", "Trade Finance",                              "Transaction Banking"),
]

DISCLAIMER = (
    "SYNTHETIC DEMO DATA. BMO Capital Markets is a branding label only. The issuers "
    "named are real public companies, used only so live web grounding returns real "
    "public news; every internal exposure, limit, revenue, wallet-share, risk rating, "
    "covenant, trade, colleague, message, meeting and policy here is invented for a "
    "demo and reflects no real institution, client relationship or credit position."
)
