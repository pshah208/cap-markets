"""Demo facts the chat skills render. GENERATED -- do not edit by hand.

Produced by `generate_skill_data.py` from `data/scenario_facts.py` and
`data/fabric-iq/*.csv`. The BFF image copies only `src/bff`, so the figures are
baked in here rather than read from the dataset at runtime. Re-run the generator
after any dataset change.

Generated 2026-10-08.
"""

from __future__ import annotations

from typing import Any

SKILL_DATA: dict[str, Any] = {
    "client": {
        "id": "CLI-1001",
        "name": "Gibson Energy Inc.",
        "ticker": "TSX:GEI",
        "as_of": "2026-10-05",
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
            "utilised": 3.5,
            "headroom": 3.5,
            "utilisation_pct": 50.0,
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
            "bank_current_hold_m": 165.0,
            "bank_proposed_hold_m": 210.0,
            "bank_role": "Co-Lead Arranger and Joint Bookrunner",
            "estimated_fees_k": 1850.0,
            "decision_needed_by": "2026-11-25"
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
            "decision_needed_by": "2026-12-10"
        },
        "dcm_followon": {
            "id": "OPP-4473",
            "name": "2027 maturity refinancing - follow-on senior unsecured",
            "indicative_size_m": 350.0,
            "estimated_fees_k": 1120.0,
            "bank_role": "Joint Bookrunner (sought; active bookrunner on the September 2026 deal)",
            "decision_needed_by": "2027-01-31"
        }
    },
    "meeting": {
        "id": "MTG-GEI-2026-10-08",
        "date": "2026-10-08",
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
        "raised_on": "2026-10-01",
        "expires": "2026-11-10",
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
    "clients": {
        "CLI-1001": {
            "id": "CLI-1001",
            "name": "Gibson Energy Inc.",
            "ticker": "TSX:GEI",
            "sector": "Energy",
            "sub_sector": "Midstream / Infrastructure",
            "tier": "Tier 1",
            "rating": "IG-6",
            "rating_prior": "IG-6",
            "trend": "improving",
            "watchlist": False,
            "kyc_refresh_due": "2026-11-25",
            "last_meeting": "2026-07-16",
            "covenants": [
                {
                    "covenant": "Total Net Debt to Adjusted EBITDA",
                    "test": "maximum",
                    "threshold": 4.5,
                    "actual": 4.18,
                    "prior": 3.94,
                    "unit": "x",
                    "headroom": 0.32,
                    "status": "Amber",
                    "last_tested": "2026-06-30",
                    "next_test": "2026-09-30"
                },
                {
                    "covenant": "Senior Secured Net Debt to Adjusted EBITDA",
                    "test": "maximum",
                    "threshold": 3.5,
                    "actual": 2.61,
                    "prior": 2.44,
                    "unit": "x",
                    "headroom": 0.89,
                    "status": "Green",
                    "last_tested": "2026-06-30",
                    "next_test": "2026-09-30"
                },
                {
                    "covenant": "Interest Coverage (Adjusted EBITDA / Interest)",
                    "test": "minimum",
                    "threshold": 2.5,
                    "actual": 4.12,
                    "prior": 4.38,
                    "unit": "x",
                    "headroom": 1.62,
                    "status": "Green",
                    "last_tested": "2026-06-30",
                    "next_test": "2026-09-30"
                },
                {
                    "covenant": "Minimum Tangible Net Worth",
                    "test": "minimum",
                    "threshold": 1150.0,
                    "actual": 1486.0,
                    "prior": 1402.0,
                    "unit": "CAD m",
                    "headroom": 336.0,
                    "status": "Green",
                    "last_tested": "2026-06-30",
                    "next_test": "2026-09-30"
                },
                {
                    "covenant": "Restricted Payments Basket Utilisation",
                    "test": "maximum",
                    "threshold": 100.0,
                    "actual": 63.4,
                    "prior": 58.1,
                    "unit": "%",
                    "headroom": 36.6,
                    "status": "Green",
                    "last_tested": "2026-06-30",
                    "next_test": "2026-09-30"
                },
                {
                    "covenant": "Asset Disposal Threshold (trailing 12m)",
                    "test": "maximum",
                    "threshold": 250.0,
                    "actual": 41.0,
                    "prior": 41.0,
                    "unit": "CAD m",
                    "headroom": 209.0,
                    "status": "Green",
                    "last_tested": "2026-06-30",
                    "next_test": "2026-09-30"
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
                    "utilised": 3.5,
                    "headroom": 3.5,
                    "utilisation_pct": 50.0,
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
            "facilities": [
                {
                    "id": "FAC-10011",
                    "type": "Revolving Credit Facility",
                    "commitment": 165.0,
                    "drawn": 96.0,
                    "maturity": "2029-06-30"
                },
                {
                    "id": "FAC-10012",
                    "type": "Term Loan B (Chauvin bridge take-out)",
                    "commitment": 140.0,
                    "drawn": 140.0,
                    "maturity": "2030-03-31"
                },
                {
                    "id": "FAC-10013",
                    "type": "Letter of Credit Facility",
                    "commitment": 60.0,
                    "drawn": 32.4,
                    "maturity": "2027-12-31"
                },
                {
                    "id": "FAC-10014",
                    "type": "Uncommitted Bilateral Operating Line",
                    "commitment": 40.0,
                    "drawn": 0.0,
                    "maturity": "2027-06-30"
                },
                {
                    "id": "FAC-10015",
                    "type": "Derivative Settlement / Pre-Settlement Line",
                    "commitment": 60.0,
                    "drawn": 20.0,
                    "maturity": "2028-06-30"
                }
            ],
            "opportunity": "Scenario proposals (not approved): OPP-4471 Revolver upsize + 1-year extension (decision needed by 2026-11-25); OPP-4472 Chauvin commodity + FX hedging overlay (decision needed by 2026-12-10); OPP-4473 2027 maturity refinancing - follow-on senior unsecured (decision needed by 2027-01-31). Revolver pitch requires Credit pro-forma testing; hedging solicitation requires Control Room clearance.",
            "risk": "Single-name limit status Green: 68.3% utilised, CAD 341.7m of CAD 500.0m. Internal synthetic rating IG-6; trend improving; watchlist flag N. KYC refresh due 2026-11-25 (relative to the snapshot date, not today). Headroom is not approval for new commitments. Scenario covenant Total Net Debt to Adjusted EBITDA: 4.18x against 4.50x; 0.32 turns headroom. CR-2026-0184: The revolver upsize pitch may proceed on public information only. The hedging overlay solicitation must be cleared by the Control Room before Thursday. Research may not publish or update the target price.",
            "data_quality": []
        },
        "CLI-1002": {
            "id": "CLI-1002",
            "name": "Keyera Corp.",
            "ticker": "TSX:KEY",
            "sector": "Energy",
            "sub_sector": "Midstream / NGL",
            "tier": "Tier 1",
            "rating": "IG-5",
            "rating_prior": "IG-5",
            "trend": "stable",
            "watchlist": False,
            "kyc_refresh_due": "2027-12-02",
            "last_meeting": "2026-05-06",
            "covenants": [
                {
                    "covenant": "Total Net Debt to Adjusted EBITDA",
                    "test": "maximum",
                    "threshold": 4.0,
                    "actual": 3.27,
                    "prior": 3.27,
                    "unit": "x",
                    "headroom": 0.73,
                    "status": "Green",
                    "last_tested": "2026-06-30",
                    "next_test": "2026-09-30"
                },
                {
                    "covenant": "Interest Coverage (Adjusted EBITDA / Interest)",
                    "test": "minimum",
                    "threshold": 2.5,
                    "actual": 5.13,
                    "prior": 5.13,
                    "unit": "x",
                    "headroom": 2.63,
                    "status": "Green",
                    "last_tested": "2026-06-30",
                    "next_test": "2026-09-30"
                }
            ],
            "limits": [
                {
                    "id": "LIM-1002-SN",
                    "type": "Single-name credit limit",
                    "limit": 600.0,
                    "utilised": 514.8,
                    "headroom": 85.2,
                    "utilisation_pct": 85.8,
                    "status": "Amber",
                    "owner": "Credit Committee"
                }
            ],
            "facilities": [
                {
                    "id": "FAC-10021",
                    "type": "Revolving Credit Facility",
                    "commitment": 286.0,
                    "drawn": 112.1,
                    "maturity": "2030-05-09"
                },
                {
                    "id": "FAC-10022",
                    "type": "Term Loan",
                    "commitment": 156.0,
                    "drawn": 57.1,
                    "maturity": "2028-01-21"
                },
                {
                    "id": "FAC-10023",
                    "type": "Letter of Credit Facility",
                    "commitment": 78.0,
                    "drawn": 32.3,
                    "maturity": "2028-07-23"
                }
            ],
            "opportunity": "Review Corporate Loan - Revolving Credit Facility: largest recorded gap to the 25% wallet target is CAD 3.3462m in wallet_share.csv. This is an analytical lead, not an approved opportunity or revenue forecast.",
            "risk": "Single-name limit status Amber: 85.8% utilised, CAD 514.8m of CAD 600.0m. Internal synthetic rating IG-5; trend stable; watchlist flag N. KYC refresh due 2027-12-02 (relative to the snapshot date, not today). Headroom is not approval for new commitments.",
            "data_quality": [
                "Exposure rows total CAD 307.6m, but the single-name limit reports CAD 514.8m utilised. The source mismatch is unresolved; utilization uses the limit row, not exposure divided by limit.",
                "Wallet-table revenue CAD 13.208m differs from FY26 YTD revenue CAD 8.58m. Wallet share uses only wallet-table numerator and estimated street denominator; these sources are not reconciled."
            ]
        },
        "CLI-1003": {
            "id": "CLI-1003",
            "name": "Whitecap Resources Inc.",
            "ticker": "TSX:WCP",
            "sector": "Energy",
            "sub_sector": "E&P - Light Oil",
            "tier": "Tier 2",
            "rating": "IG-8",
            "rating_prior": "IG-8",
            "trend": "improving",
            "watchlist": False,
            "kyc_refresh_due": "2027-03-07",
            "last_meeting": "2026-09-11",
            "covenants": [
                {
                    "covenant": "Total Net Debt to Adjusted EBITDA",
                    "test": "maximum",
                    "threshold": 4.0,
                    "actual": 3.42,
                    "prior": 3.42,
                    "unit": "x",
                    "headroom": 0.58,
                    "status": "Green",
                    "last_tested": "2026-06-30",
                    "next_test": "2026-09-30"
                },
                {
                    "covenant": "Interest Coverage (Adjusted EBITDA / Interest)",
                    "test": "minimum",
                    "threshold": 2.5,
                    "actual": 3.97,
                    "prior": 3.97,
                    "unit": "x",
                    "headroom": 1.47,
                    "status": "Green",
                    "last_tested": "2026-06-30",
                    "next_test": "2026-09-30"
                }
            ],
            "limits": [
                {
                    "id": "LIM-1003-SN",
                    "type": "Single-name credit limit",
                    "limit": 375.0,
                    "utilised": 194.6,
                    "headroom": 180.4,
                    "utilisation_pct": 51.9,
                    "status": "Green",
                    "owner": "Credit Committee"
                }
            ],
            "facilities": [
                {
                    "id": "FAC-10031",
                    "type": "Revolving Credit Facility",
                    "commitment": 170.5,
                    "drawn": 116.5,
                    "maturity": "2028-09-12"
                },
                {
                    "id": "FAC-10032",
                    "type": "Term Loan",
                    "commitment": 93.0,
                    "drawn": 50.5,
                    "maturity": "2029-01-02"
                },
                {
                    "id": "FAC-10033",
                    "type": "Letter of Credit Facility",
                    "commitment": 46.5,
                    "drawn": 40.3,
                    "maturity": "2029-05-24"
                }
            ],
            "opportunity": "Review Corporate Loan - Revolving Credit Facility: largest recorded gap to the 25% wallet target is CAD 1.5682m in wallet_share.csv. This is an analytical lead, not an approved opportunity or revenue forecast.",
            "risk": "Single-name limit status Green: 51.9% utilised, CAD 194.6m of CAD 375.0m. Internal synthetic rating IG-8; trend improving; watchlist flag N. KYC refresh due 2027-03-07 (relative to the snapshot date, not today). Headroom is not approval for new commitments.",
            "data_quality": [
                "Exposure rows total CAD 154.3m, but the single-name limit reports CAD 194.6m utilised. The source mismatch is unresolved; utilization uses the limit row, not exposure divided by limit.",
                "Wallet-table revenue CAD 6.789m differs from FY26 YTD revenue CAD 6.169m. Wallet share uses only wallet-table numerator and estimated street denominator; these sources are not reconciled."
            ]
        },
        "CLI-1004": {
            "id": "CLI-1004",
            "name": "Secure Waste Infrastructure",
            "ticker": "TSX:SES",
            "sector": "Energy",
            "sub_sector": "Energy Services",
            "tier": "Tier 2",
            "rating": "IG-9",
            "rating_prior": "IG-9",
            "trend": "stable",
            "watchlist": False,
            "kyc_refresh_due": "2026-11-25",
            "last_meeting": "2026-05-04",
            "covenants": [
                {
                    "covenant": "Total Net Debt to Adjusted EBITDA",
                    "test": "maximum",
                    "threshold": 4.0,
                    "actual": 2.93,
                    "prior": 2.93,
                    "unit": "x",
                    "headroom": 1.07,
                    "status": "Green",
                    "last_tested": "2026-06-30",
                    "next_test": "2026-09-30"
                },
                {
                    "covenant": "Interest Coverage (Adjusted EBITDA / Interest)",
                    "test": "minimum",
                    "threshold": 2.5,
                    "actual": 3.77,
                    "prior": 3.77,
                    "unit": "x",
                    "headroom": 1.27,
                    "status": "Green",
                    "last_tested": "2026-06-30",
                    "next_test": "2026-09-30"
                }
            ],
            "limits": [
                {
                    "id": "LIM-1004-SN",
                    "type": "Single-name credit limit",
                    "limit": 250.0,
                    "utilised": 208.8,
                    "headroom": 41.2,
                    "utilisation_pct": 83.5,
                    "status": "Green",
                    "owner": "Credit Committee"
                }
            ],
            "facilities": [
                {
                    "id": "FAC-10041",
                    "type": "Revolving Credit Facility",
                    "commitment": 101.8,
                    "drawn": 35.6,
                    "maturity": "2027-12-22"
                },
                {
                    "id": "FAC-10042",
                    "type": "Term Loan",
                    "commitment": 55.5,
                    "drawn": 19.5,
                    "maturity": "2029-12-08"
                },
                {
                    "id": "FAC-10043",
                    "type": "Letter of Credit Facility",
                    "commitment": 27.8,
                    "drawn": 24.6,
                    "maturity": "2030-06-27"
                }
            ],
            "opportunity": "Review Commodity Derivatives: largest recorded gap to the 25% wallet target is CAD 0.2481m in wallet_share.csv. This is an analytical lead, not an approved opportunity or revenue forecast.",
            "risk": "Single-name limit status Green: 83.5% utilised, CAD 208.8m of CAD 250.0m. Internal synthetic rating IG-9; trend stable; watchlist flag N. KYC refresh due 2026-11-25 (relative to the snapshot date, not today). Headroom is not approval for new commitments.",
            "data_quality": [
                "Exposure rows total CAD 115.5m, but the single-name limit reports CAD 208.8m utilised. The source mismatch is unresolved; utilization uses the limit row, not exposure divided by limit.",
                "Wallet-table revenue CAD 5.0135m differs from FY26 YTD revenue CAD 2.6455m. Wallet share uses only wallet-table numerator and estimated street denominator; these sources are not reconciled."
            ]
        },
        "CLI-1005": {
            "id": "CLI-1005",
            "name": "Stella-Jones Inc.",
            "ticker": "TSX:SJ",
            "sector": "Materials",
            "sub_sector": "Wood Products",
            "tier": "Tier 2",
            "rating": "IG-5",
            "rating_prior": "IG-5",
            "trend": "stable",
            "watchlist": False,
            "kyc_refresh_due": "2027-03-04",
            "last_meeting": "2026-09-02",
            "covenants": [
                {
                    "covenant": "Total Net Debt to Adjusted EBITDA",
                    "test": "maximum",
                    "threshold": 4.0,
                    "actual": 3.96,
                    "prior": 3.96,
                    "unit": "x",
                    "headroom": 0.04,
                    "status": "Amber",
                    "last_tested": "2026-06-30",
                    "next_test": "2026-09-30"
                },
                {
                    "covenant": "Interest Coverage (Adjusted EBITDA / Interest)",
                    "test": "minimum",
                    "threshold": 2.5,
                    "actual": 3.91,
                    "prior": 3.91,
                    "unit": "x",
                    "headroom": 1.41,
                    "status": "Green",
                    "last_tested": "2026-06-30",
                    "next_test": "2026-09-30"
                }
            ],
            "limits": [
                {
                    "id": "LIM-1005-SN",
                    "type": "Single-name credit limit",
                    "limit": 300.0,
                    "utilised": 206.4,
                    "headroom": 93.6,
                    "utilisation_pct": 68.8,
                    "status": "Green",
                    "owner": "Credit Committee"
                }
            ],
            "facilities": [
                {
                    "id": "FAC-10051",
                    "type": "Revolving Credit Facility",
                    "commitment": 132.0,
                    "drawn": 109.3,
                    "maturity": "2028-04-07"
                },
                {
                    "id": "FAC-10052",
                    "type": "Term Loan",
                    "commitment": 72.0,
                    "drawn": 53.7,
                    "maturity": "2030-05-23"
                },
                {
                    "id": "FAC-10053",
                    "type": "Letter of Credit Facility",
                    "commitment": 36.0,
                    "drawn": 16.5,
                    "maturity": "2029-01-29"
                }
            ],
            "opportunity": "Review Debt Capital Markets - Underwriting: largest recorded gap to the 25% wallet target is CAD 1.0017m in wallet_share.csv. This is an analytical lead, not an approved opportunity or revenue forecast.",
            "risk": "Single-name limit status Green: 68.8% utilised, CAD 206.4m of CAD 300.0m. Internal synthetic rating IG-5; trend stable; watchlist flag N. KYC refresh due 2027-03-04 (relative to the snapshot date, not today). Headroom is not approval for new commitments.",
            "data_quality": [
                "Exposure rows total CAD 150.7m, but the single-name limit reports CAD 206.4m utilised. The source mismatch is unresolved; utilization uses the limit row, not exposure divided by limit.",
                "Wallet-table revenue CAD 6.504m differs from FY26 YTD revenue CAD 2.9519m. Wallet share uses only wallet-table numerator and estimated street denominator; these sources are not reconciled."
            ]
        },
        "CLI-1006": {
            "id": "CLI-1006",
            "name": "Russel Metals Inc.",
            "ticker": "TSX:RUS",
            "sector": "Materials",
            "sub_sector": "Metals Distribution",
            "tier": "Tier 2",
            "rating": "IG-6",
            "rating_prior": "IG-6",
            "trend": "stable",
            "watchlist": False,
            "kyc_refresh_due": "2027-05-09",
            "last_meeting": "2026-07-26",
            "covenants": [
                {
                    "covenant": "Total Net Debt to Adjusted EBITDA",
                    "test": "maximum",
                    "threshold": 4.0,
                    "actual": 3.86,
                    "prior": 3.86,
                    "unit": "x",
                    "headroom": 0.14,
                    "status": "Amber",
                    "last_tested": "2026-06-30",
                    "next_test": "2026-09-30"
                },
                {
                    "covenant": "Interest Coverage (Adjusted EBITDA / Interest)",
                    "test": "minimum",
                    "threshold": 2.5,
                    "actual": 4.51,
                    "prior": 4.51,
                    "unit": "x",
                    "headroom": 2.01,
                    "status": "Green",
                    "last_tested": "2026-06-30",
                    "next_test": "2026-09-30"
                }
            ],
            "limits": [
                {
                    "id": "LIM-1006-SN",
                    "type": "Single-name credit limit",
                    "limit": 350.0,
                    "utilised": 270.9,
                    "headroom": 79.1,
                    "utilisation_pct": 77.4,
                    "status": "Green",
                    "owner": "Credit Committee"
                }
            ],
            "facilities": [
                {
                    "id": "FAC-10061",
                    "type": "Revolving Credit Facility",
                    "commitment": 151.2,
                    "drawn": 49.6,
                    "maturity": "2027-08-28"
                },
                {
                    "id": "FAC-10062",
                    "type": "Term Loan",
                    "commitment": 82.5,
                    "drawn": 38.1,
                    "maturity": "2027-10-18"
                },
                {
                    "id": "FAC-10063",
                    "type": "Letter of Credit Facility",
                    "commitment": 41.2,
                    "drawn": 20.8,
                    "maturity": "2028-05-06"
                }
            ],
            "opportunity": "Review Debt Capital Markets - Underwriting: largest recorded gap to the 25% wallet target is CAD 2.9443m in wallet_share.csv. This is an analytical lead, not an approved opportunity or revenue forecast.",
            "risk": "Single-name limit status Green: 77.4% utilised, CAD 270.9m of CAD 350.0m. Internal synthetic rating IG-6; trend stable; watchlist flag N. KYC refresh due 2027-05-09 (relative to the snapshot date, not today). Headroom is not approval for new commitments.",
            "data_quality": [
                "Exposure rows total CAD 191.4m, but the single-name limit reports CAD 270.9m utilised. The source mismatch is unresolved; utilization uses the limit row, not exposure divided by limit.",
                "Wallet-table revenue CAD 8.69m differs from FY26 YTD revenue CAD 3.41m. Wallet share uses only wallet-table numerator and estimated street denominator; these sources are not reconciled."
            ]
        },
        "CLI-1007": {
            "id": "CLI-1007",
            "name": "Cascades Inc.",
            "ticker": "TSX:CAS",
            "sector": "Materials",
            "sub_sector": "Packaging / Tissue",
            "tier": "Tier 3",
            "rating": "IG-10",
            "rating_prior": "IG-10",
            "trend": "deteriorating",
            "watchlist": True,
            "kyc_refresh_due": "2027-10-06",
            "last_meeting": "2026-03-23",
            "covenants": [
                {
                    "covenant": "Total Net Debt to Adjusted EBITDA",
                    "test": "maximum",
                    "threshold": 4.0,
                    "actual": 3.35,
                    "prior": 3.35,
                    "unit": "x",
                    "headroom": 0.65,
                    "status": "Green",
                    "last_tested": "2026-06-30",
                    "next_test": "2026-09-30"
                },
                {
                    "covenant": "Interest Coverage (Adjusted EBITDA / Interest)",
                    "test": "minimum",
                    "threshold": 2.5,
                    "actual": 3.4,
                    "prior": 3.4,
                    "unit": "x",
                    "headroom": 0.9,
                    "status": "Green",
                    "last_tested": "2026-06-30",
                    "next_test": "2026-09-30"
                }
            ],
            "limits": [
                {
                    "id": "LIM-1007-SN",
                    "type": "Single-name credit limit",
                    "limit": 200.0,
                    "utilised": 161.2,
                    "headroom": 38.8,
                    "utilisation_pct": 80.6,
                    "status": "Green",
                    "owner": "Credit Committee"
                }
            ],
            "facilities": [
                {
                    "id": "FAC-10071",
                    "type": "Revolving Credit Facility",
                    "commitment": 88.0,
                    "drawn": 48.2,
                    "maturity": "2030-06-25"
                },
                {
                    "id": "FAC-10072",
                    "type": "Term Loan",
                    "commitment": 48.0,
                    "drawn": 31.0,
                    "maturity": "2029-09-08"
                },
                {
                    "id": "FAC-10073",
                    "type": "Letter of Credit Facility",
                    "commitment": 24.0,
                    "drawn": 16.7,
                    "maturity": "2028-04-17"
                }
            ],
            "opportunity": "Review Corporate Loan - Revolving Credit Facility: largest recorded gap to the 25% wallet target is CAD 1.3642m in wallet_share.csv. This is an analytical lead, not an approved opportunity or revenue forecast.",
            "risk": "Single-name limit status Green: 80.6% utilised, CAD 161.2m of CAD 200.0m. Internal synthetic rating IG-10; trend deteriorating; watchlist flag Y. KYC refresh due 2027-10-06 (relative to the snapshot date, not today). Headroom is not approval for new commitments.",
            "data_quality": [
                "Exposure rows total CAD 117.2m, but the single-name limit reports CAD 161.2m utilised. The source mismatch is unresolved; utilization uses the limit row, not exposure divided by limit.",
                "Wallet-table revenue CAD 4.8m differs from FY26 YTD revenue CAD 3.0081m. Wallet share uses only wallet-table numerator and estimated street denominator; these sources are not reconciled."
            ]
        },
        "CLI-1008": {
            "id": "CLI-1008",
            "name": "Ag Growth International Inc.",
            "ticker": "TSX:AFN",
            "sector": "Industrials",
            "sub_sector": "Agricultural Equipment",
            "tier": "Tier 3",
            "rating": "IG-10",
            "rating_prior": "IG-10",
            "trend": "deteriorating",
            "watchlist": True,
            "kyc_refresh_due": "2027-01-08",
            "last_meeting": "2026-08-25",
            "covenants": [
                {
                    "covenant": "Total Net Debt to Adjusted EBITDA",
                    "test": "maximum",
                    "threshold": 4.0,
                    "actual": 2.63,
                    "prior": 2.63,
                    "unit": "x",
                    "headroom": 1.37,
                    "status": "Green",
                    "last_tested": "2026-06-30",
                    "next_test": "2026-09-30"
                },
                {
                    "covenant": "Interest Coverage (Adjusted EBITDA / Interest)",
                    "test": "minimum",
                    "threshold": 2.5,
                    "actual": 5.08,
                    "prior": 5.08,
                    "unit": "x",
                    "headroom": 2.58,
                    "status": "Green",
                    "last_tested": "2026-06-30",
                    "next_test": "2026-09-30"
                }
            ],
            "limits": [
                {
                    "id": "LIM-1008-SN",
                    "type": "Single-name credit limit",
                    "limit": 150.0,
                    "utilised": 137.2,
                    "headroom": 12.8,
                    "utilisation_pct": 91.5,
                    "status": "Amber",
                    "owner": "Credit Committee"
                }
            ],
            "facilities": [
                {
                    "id": "FAC-10081",
                    "type": "Revolving Credit Facility",
                    "commitment": 66.0,
                    "drawn": 46.7,
                    "maturity": "2028-01-24"
                },
                {
                    "id": "FAC-10082",
                    "type": "Term Loan",
                    "commitment": 36.0,
                    "drawn": 20.4,
                    "maturity": "2030-08-27"
                },
                {
                    "id": "FAC-10083",
                    "type": "Letter of Credit Facility",
                    "commitment": 18.0,
                    "drawn": 16.5,
                    "maturity": "2031-03-26"
                }
            ],
            "opportunity": "Review Commodity Derivatives: largest recorded gap to the 25% wallet target is CAD 1.2201m in wallet_share.csv. This is an analytical lead, not an approved opportunity or revenue forecast.",
            "risk": "Single-name limit status Amber: 91.5% utilised, CAD 137.2m of CAD 150.0m. Internal synthetic rating IG-10; trend deteriorating; watchlist flag Y. KYC refresh due 2027-01-08 (relative to the snapshot date, not today). Headroom is not approval for new commitments.",
            "data_quality": [
                "Exposure rows total CAD 67.2m, but the single-name limit reports CAD 137.2m utilised. The source mismatch is unresolved; utilization uses the limit row, not exposure divided by limit.",
                "Wallet-table revenue CAD 3.348m differs from FY26 YTD revenue CAD 1.5119m. Wallet share uses only wallet-table numerator and estimated street denominator; these sources are not reconciled."
            ]
        },
        "CLI-1009": {
            "id": "CLI-1009",
            "name": "North West Company Inc.",
            "ticker": "TSX:NWC",
            "sector": "Industrials",
            "sub_sector": "Retail Distribution",
            "tier": "Tier 3",
            "rating": "IG-7",
            "rating_prior": "IG-7",
            "trend": "stable",
            "watchlist": False,
            "kyc_refresh_due": "2027-03-26",
            "last_meeting": "2026-08-19",
            "covenants": [
                {
                    "covenant": "Total Net Debt to Adjusted EBITDA",
                    "test": "maximum",
                    "threshold": 4.0,
                    "actual": 2.9,
                    "prior": 2.9,
                    "unit": "x",
                    "headroom": 1.1,
                    "status": "Green",
                    "last_tested": "2026-06-30",
                    "next_test": "2026-09-30"
                },
                {
                    "covenant": "Interest Coverage (Adjusted EBITDA / Interest)",
                    "test": "minimum",
                    "threshold": 2.5,
                    "actual": 3.13,
                    "prior": 3.13,
                    "unit": "x",
                    "headroom": 0.63,
                    "status": "Green",
                    "last_tested": "2026-06-30",
                    "next_test": "2026-09-30"
                }
            ],
            "limits": [
                {
                    "id": "LIM-1009-SN",
                    "type": "Single-name credit limit",
                    "limit": 200.0,
                    "utilised": 91.2,
                    "headroom": 108.8,
                    "utilisation_pct": 45.6,
                    "status": "Green",
                    "owner": "Credit Committee"
                }
            ],
            "facilities": [
                {
                    "id": "FAC-10091",
                    "type": "Revolving Credit Facility",
                    "commitment": 79.8,
                    "drawn": 36.3,
                    "maturity": "2030-08-04"
                },
                {
                    "id": "FAC-10092",
                    "type": "Term Loan",
                    "commitment": 43.5,
                    "drawn": 19.6,
                    "maturity": "2031-02-09"
                },
                {
                    "id": "FAC-10093",
                    "type": "Letter of Credit Facility",
                    "commitment": 21.8,
                    "drawn": 13.8,
                    "maturity": "2027-11-10"
                }
            ],
            "opportunity": "Review FX - Forwards and Options: largest recorded gap to the 25% wallet target is CAD 0.8938m in wallet_share.csv. This is an analytical lead, not an approved opportunity or revenue forecast.",
            "risk": "Single-name limit status Green: 45.6% utilised, CAD 91.2m of CAD 200.0m. Internal synthetic rating IG-7; trend stable; watchlist flag N. KYC refresh due 2027-03-26 (relative to the snapshot date, not today). Headroom is not approval for new commitments.",
            "data_quality": [
                "Exposure rows total CAD 81.8m, but the single-name limit reports CAD 91.2m utilised. The source mismatch is unresolved; utilization uses the limit row, not exposure divided by limit.",
                "Wallet-table revenue CAD 3.1175m differs from FY26 YTD revenue CAD 2.2765m. Wallet share uses only wallet-table numerator and estimated street denominator; these sources are not reconciled."
            ]
        },
        "CLI-1010": {
            "id": "CLI-1010",
            "name": "Superior Plus Corp.",
            "ticker": "TSX:SPB",
            "sector": "Energy",
            "sub_sector": "Energy Distribution",
            "tier": "Tier 2",
            "rating": "IG-8",
            "rating_prior": "IG-8",
            "trend": "stable",
            "watchlist": False,
            "kyc_refresh_due": "2027-10-11",
            "last_meeting": "2026-09-14",
            "covenants": [
                {
                    "covenant": "Total Net Debt to Adjusted EBITDA",
                    "test": "maximum",
                    "threshold": 4.0,
                    "actual": 3.19,
                    "prior": 3.19,
                    "unit": "x",
                    "headroom": 0.81,
                    "status": "Green",
                    "last_tested": "2026-06-30",
                    "next_test": "2026-09-30"
                },
                {
                    "covenant": "Interest Coverage (Adjusted EBITDA / Interest)",
                    "test": "minimum",
                    "threshold": 2.5,
                    "actual": 5.18,
                    "prior": 5.18,
                    "unit": "x",
                    "headroom": 2.68,
                    "status": "Green",
                    "last_tested": "2026-06-30",
                    "next_test": "2026-09-30"
                }
            ],
            "limits": [
                {
                    "id": "LIM-1010-SN",
                    "type": "Single-name credit limit",
                    "limit": 400.0,
                    "utilised": 267.2,
                    "headroom": 132.8,
                    "utilisation_pct": 66.8,
                    "status": "Green",
                    "owner": "Credit Committee"
                }
            ],
            "facilities": [
                {
                    "id": "FAC-10101",
                    "type": "Revolving Credit Facility",
                    "commitment": 181.5,
                    "drawn": 148.5,
                    "maturity": "2028-03-23"
                },
                {
                    "id": "FAC-10102",
                    "type": "Term Loan",
                    "commitment": 99.0,
                    "drawn": 79.3,
                    "maturity": "2030-11-09"
                },
                {
                    "id": "FAC-10103",
                    "type": "Letter of Credit Facility",
                    "commitment": 49.5,
                    "drawn": 19.7,
                    "maturity": "2029-12-04"
                }
            ],
            "opportunity": "Review Debt Capital Markets - Underwriting: largest recorded gap to the 25% wallet target is CAD 3.6019m in wallet_share.csv. This is an analytical lead, not an approved opportunity or revenue forecast.",
            "risk": "Single-name limit status Green: 66.8% utilised, CAD 267.2m of CAD 400.0m. Internal synthetic rating IG-8; trend stable; watchlist flag N. KYC refresh due 2027-10-11 (relative to the snapshot date, not today). Headroom is not approval for new commitments.",
            "data_quality": [
                "Exposure rows total CAD 203.4m, but the single-name limit reports CAD 267.2m utilised. The source mismatch is unresolved; utilization uses the limit row, not exposure divided by limit.",
                "Wallet-table revenue CAD 8.844m differs from FY26 YTD revenue CAD 4.356m. Wallet share uses only wallet-table numerator and estimated street denominator; these sources are not reconciled."
            ]
        }
    },
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
        "last_meeting_date": "2026-07-16",
        "last_credit_review_date": "2026-03-18",
        "next_credit_review_due": "2027-03-31",
        "kyc_refresh_due": "2026-11-25",
        "kyc_status": "Due - 51 days"
    }
}
