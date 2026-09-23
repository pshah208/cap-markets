"""Demo facts the chat skills render. GENERATED -- do not edit by hand.

Produced by `generate_skill_data.py` from `data/scenario_facts.py` and
`data/fabric-iq/*.csv`. The BFF image copies only `src/bff`, so the figures are
baked in here rather than read from the dataset at runtime. Re-run the generator
after any dataset change.

Generated 2026-08-18.
"""

from __future__ import annotations

from typing import Any

SKILL_DATA: dict[str, Any] = {
    "client": {
        "id": "CLI-1001",
        "name": "Gibson Energy Inc.",
        "ticker": "TSX:GEI",
        "as_of": "2026-08-10",
        "currency": "CAD"
    },
    "financials": {
        "adjusted_ebitda_ltm_m": 612.0,
        "total_net_debt_m": 2558.2,
        "as_of": "2026-06-30",
        "basis": "Last twelve months to the 2026-06-30 compliance certificate. Adjusted EBITDA is the credit-agreement definition, after the add-backs CP-005 permits."
    },
    "covenant": {
        "name": "Total Net Debt to Adjusted EBITDA",
        "threshold": 4.5,
        "actual": 4.18,
        "prior": 3.94,
        "headroom_turns": 0.32,
        "next_test": "2026-09-30",
        "source_facility": "FAC-10011 / FAC-10012"
    },
    "covenants_all": [
        {
            "covenant": "Total Net Debt to Adjusted EBITDA",
            "test": "maximum",
            "threshold": 4.5,
            "actual": 4.18,
            "prior": 3.94,
            "unit": "x",
            "headroom": 0.32,
            "utilisation_pct": 92.9,
            "status": "Amber"
        },
        {
            "covenant": "Senior Secured Net Debt to Adjusted EBITDA",
            "test": "maximum",
            "threshold": 3.5,
            "actual": 2.61,
            "prior": 2.44,
            "unit": "x",
            "headroom": 0.89,
            "utilisation_pct": 74.6,
            "status": "Green"
        },
        {
            "covenant": "Interest Coverage (Adjusted EBITDA / Interest)",
            "test": "minimum",
            "threshold": 2.5,
            "actual": 4.12,
            "prior": 4.38,
            "unit": "x",
            "headroom": 1.62,
            "utilisation_pct": 60.7,
            "status": "Green"
        },
        {
            "covenant": "Minimum Tangible Net Worth",
            "test": "minimum",
            "threshold": 1150.0,
            "actual": 1486.0,
            "prior": 1402.0,
            "unit": "CAD m",
            "headroom": 336.0,
            "utilisation_pct": 77.4,
            "status": "Green"
        },
        {
            "covenant": "Restricted Payments Basket Utilisation",
            "test": "maximum",
            "threshold": 100.0,
            "actual": 63.4,
            "prior": 58.1,
            "unit": "%",
            "headroom": 36.6,
            "utilisation_pct": 63.4,
            "status": "Green"
        },
        {
            "covenant": "Asset Disposal Threshold (trailing 12m)",
            "test": "maximum",
            "threshold": 250.0,
            "actual": 41.0,
            "prior": 41.0,
            "unit": "CAD m",
            "headroom": 209.0,
            "utilisation_pct": 16.4,
            "status": "Green"
        }
    ],
    "limits": [
        {
            "id": "LIM-1001-SN",
            "type": "Single-name credit limit",
            "limit": 500.0,
            "utilised": 341.7,
            "headroom": 158.3,
            "utilisation_pct": 68.3,
            "status": "Green",
            "owner": "Credit Committee"
        },
        {
            "id": "LIM-1001-DV",
            "type": "Derivative pre-settlement limit",
            "limit": 90.0,
            "utilised": 69.2,
            "headroom": 20.8,
            "utilisation_pct": 76.9,
            "status": "Amber",
            "owner": "Credit Risk - Global Markets"
        },
        {
            "id": "LIM-1001-TN",
            "type": "Tenor limit - max remaining maturity",
            "limit": 7.0,
            "utilised": 3.6,
            "headroom": 3.4,
            "utilisation_pct": 51.4,
            "status": "Green",
            "owner": "Credit Committee"
        },
        {
            "id": "LIM-1001-UW",
            "type": "Underwriting commitment limit",
            "limit": 250.0,
            "utilised": 0.0,
            "headroom": 250.0,
            "utilisation_pct": 0.0,
            "status": "Green",
            "owner": "Underwriting Committee"
        }
    ],
    "sector_limit": {
        "name": "Energy sector (all clients)",
        "limit": 3200.0,
        "utilised": 2744.0,
        "headroom": 456.0,
        "utilisation_pct": 85.8,
        "status": "Amber",
        "owner": "Chief Risk Officer"
    },
    "facilities": [
        {
            "id": "FAC-10011",
            "type": "Revolving Credit Facility",
            "commitment": 165.0,
            "drawn": 96.0,
            "maturity": "2029-06-30",
            "role": "Co-Lead Arranger / Joint Bookrunner"
        },
        {
            "id": "FAC-10012",
            "type": "Term Loan B (Chauvin bridge take-out)",
            "commitment": 140.0,
            "drawn": 140.0,
            "maturity": "2030-03-31",
            "role": "Joint Lead Arranger"
        },
        {
            "id": "FAC-10013",
            "type": "Letter of Credit Facility",
            "commitment": 60.0,
            "drawn": 32.4,
            "maturity": "2027-12-31",
            "role": "Issuing Bank"
        },
        {
            "id": "FAC-10014",
            "type": "Uncommitted Bilateral Operating Line",
            "commitment": 40.0,
            "drawn": 0.0,
            "maturity": "2027-06-30",
            "role": "Sole Lender"
        },
        {
            "id": "FAC-10015",
            "type": "Derivative Settlement / Pre-Settlement Line",
            "commitment": 60.0,
            "drawn": 20.0,
            "maturity": "2028-06-30",
            "role": "Counterparty"
        }
    ],
    "leverage_history": [
        {
            "as_of": "2024-10-31",
            "leverage": 4.61,
            "rating": "IG-8"
        },
        {
            "as_of": "2025-01-31",
            "leverage": 4.48,
            "rating": "IG-8"
        },
        {
            "as_of": "2025-04-30",
            "leverage": 4.22,
            "rating": "IG-7"
        },
        {
            "as_of": "2025-07-31",
            "leverage": 4.05,
            "rating": "IG-7"
        },
        {
            "as_of": "2025-10-31",
            "leverage": 3.88,
            "rating": "IG-7"
        },
        {
            "as_of": "2026-01-31",
            "leverage": 4.31,
            "rating": "IG-7"
        },
        {
            "as_of": "2026-04-30",
            "leverage": 3.94,
            "rating": "IG-6"
        },
        {
            "as_of": "2026-07-31",
            "leverage": 4.18,
            "rating": "IG-6"
        }
    ],
    "opportunities": {
        "revolver_upsize": {
            "id": "OPP-4471",
            "name": "Revolver upsize + 1-year extension",
            "current_commitment_total_m": 1100.0,
            "proposed_commitment_total_m": 1350.0,
            "bmo_current_hold_m": 165.0,
            "bmo_proposed_hold_m": 210.0,
            "bmo_role": "Co-Lead Arranger and Joint Bookrunner",
            "estimated_fees_k": 1850.0,
            "decision_needed_by": "2026-09-30"
        },
        "hedging_overlay": {
            "id": "OPP-4472",
            "name": "Chauvin commodity + FX hedging overlay",
            "notional_m": 240.0,
            "tenor_months": 24,
            "estimated_revenue_k": 940.0,
            "products": [
                "WTI-WCS differential swap",
                "CAD/USD forward strip"
            ],
            "decision_needed_by": "2026-10-15"
        },
        "dcm_followon": {
            "id": "OPP-4473",
            "name": "2027 maturity refinancing - follow-on senior unsecured",
            "indicative_size_m": 350.0,
            "estimated_fees_k": 1120.0,
            "bmo_role": "Joint Bookrunner (sought; active bookrunner on the July 2026 deal)",
            "decision_needed_by": "2027-01-31"
        }
    },
    "meeting": {
        "id": "MTG-GEI-2026-08-13",
        "date": "2026-08-13",
        "time_local": "10:00-11:30 MT",
        "location": "Gibson Energy head office, Calgary (in person)",
        "title": "Gibson Energy - CFO / Treasurer coverage meeting",
        "agenda": [
            "FY26 year-to-date relationship review and FY27 wallet ambition",
            "Revolving credit facility: upsize to CAD 1.35bn and one-year extension",
            "Commodity + FX hedging overlay for the Chauvin volumes",
            "Follow-on DCM: potential 2027 maturity refinancing window",
            "Sustainability-linked structure options"
        ],
        "client_attendees": [
            "Chief Financial Officer (client)",
            "VP & Treasurer (client)",
            "Director, Capital Markets (client)"
        ],
        "attendees": [
            {
                "alias": "sydney.mattos",
                "name": "Sydney Mattos",
                "title": "Managing Director, Corporate Coverage - Energy",
                "department": "Corporate Banking",
                "wall_status": "public_side",
                "restricted": False
            },
            {
                "alias": "sasha.ouellet",
                "name": "Sasha Ouellet",
                "title": "Director, Corporate Banking & DCM Origination",
                "department": "Corporate Banking",
                "wall_status": "wall_crossed",
                "restricted": True
            },
            {
                "alias": "quinn.campbell",
                "name": "Quinn Campbell",
                "title": "Director, Commodities & FX Corporate Sales",
                "department": "Global Markets",
                "wall_status": "public_side",
                "restricted": False
            },
            {
                "alias": "vance.deleon",
                "name": "Vance DeLeon",
                "title": "Director, Credit Risk - Energy & Midstream",
                "department": "Credit Risk Management",
                "wall_status": "wall_crossed",
                "restricted": True
            }
        ]
    },
    "restriction": {
        "id": "CR-2026-0184",
        "raised_by": "Control Room (Compliance)",
        "raised_on": "2026-08-06",
        "expires": "2026-09-15",
        "effect": "The revolver upsize pitch may proceed on public information only. The hedging overlay solicitation must be cleared by the Control Room before Thursday. Research may not publish or update the target price."
    },
    "radar": [
        {
            "client_id": "CLI-1005",
            "client": "Stella-Jones Inc.",
            "threshold": 4.0,
            "actual": 3.96,
            "prior": 3.96,
            "headroom": 0.04,
            "utilisation_pct": 99.0,
            "status": "Amber",
            "next_test": "2026-09-30"
        },
        {
            "client_id": "CLI-1006",
            "client": "Russel Metals Inc.",
            "threshold": 4.0,
            "actual": 3.86,
            "prior": 3.86,
            "headroom": 0.14,
            "utilisation_pct": 96.5,
            "status": "Amber",
            "next_test": "2026-09-30"
        },
        {
            "client_id": "CLI-1001",
            "client": "Gibson Energy Inc.",
            "threshold": 4.5,
            "actual": 4.18,
            "prior": 3.94,
            "headroom": 0.32,
            "utilisation_pct": 92.9,
            "status": "Amber",
            "next_test": "2026-09-30"
        },
        {
            "client_id": "CLI-1003",
            "client": "Whitecap Resources Inc.",
            "threshold": 4.0,
            "actual": 3.42,
            "prior": 3.42,
            "headroom": 0.58,
            "utilisation_pct": 85.5,
            "status": "Green",
            "next_test": "2026-09-30"
        },
        {
            "client_id": "CLI-1007",
            "client": "Cascades Inc.",
            "threshold": 4.0,
            "actual": 3.35,
            "prior": 3.35,
            "headroom": 0.65,
            "utilisation_pct": 83.8,
            "status": "Green",
            "next_test": "2026-09-30"
        },
        {
            "client_id": "CLI-1002",
            "client": "Keyera Corp.",
            "threshold": 4.0,
            "actual": 3.27,
            "prior": 3.27,
            "headroom": 0.73,
            "utilisation_pct": 81.8,
            "status": "Green",
            "next_test": "2026-09-30"
        },
        {
            "client_id": "CLI-1010",
            "client": "Superior Plus Corp.",
            "threshold": 4.0,
            "actual": 3.19,
            "prior": 3.19,
            "headroom": 0.81,
            "utilisation_pct": 79.8,
            "status": "Green",
            "next_test": "2026-09-30"
        },
        {
            "client_id": "CLI-1004",
            "client": "Secure Waste Infrastructure",
            "threshold": 4.0,
            "actual": 2.93,
            "prior": 2.93,
            "headroom": 1.07,
            "utilisation_pct": 73.2,
            "status": "Green",
            "next_test": "2026-09-30"
        },
        {
            "client_id": "CLI-1009",
            "client": "North West Company Inc.",
            "threshold": 4.0,
            "actual": 2.9,
            "prior": 2.9,
            "headroom": 1.1,
            "utilisation_pct": 72.5,
            "status": "Green",
            "next_test": "2026-09-30"
        },
        {
            "client_id": "CLI-1008",
            "client": "Ag Growth International Inc.",
            "threshold": 4.0,
            "actual": 2.63,
            "prior": 2.63,
            "headroom": 1.37,
            "utilisation_pct": 65.8,
            "status": "Green",
            "next_test": "2026-09-30"
        }
    ],
    "metrics": {
        "total_committed_m": 465.0,
        "total_drawn_m": 288.4,
        "total_exposure_m": 341.7,
        "single_name_limit_m": 500.0,
        "limit_utilisation_pct": 68.3,
        "fy26_ytd_revenue_k": 8420.0,
        "fy25_full_year_revenue_k": 9960.0,
        "fy25_same_period_revenue_k": 7140.0,
        "revenue_yoy_pct": 17.9,
        "wallet_share_pct": 21.4,
        "wallet_share_prior_pct": 18.9,
        "estimated_street_wallet_k": 39350.0,
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
        "kyc_status": "Due - 51 days"
    }
}
