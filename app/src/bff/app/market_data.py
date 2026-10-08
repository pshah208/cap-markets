"""Coverage-workflow data (market scenario + per-client extras). GENERATED - do not edit.

Produced by `generate_market_data.py` from `data/market-scenario/scenario.json`,
`data/fabric-iq/*.csv` and `data/work-iq/`. SYNTHETIC DEMO DATA.

Generated 2026-10-08.
"""

from __future__ import annotations

from typing import Any

MARKET_DATA: dict[str, Any] = {
    "scenario": {
        "id": "SCN-2026-10-05-OIL",
        "as_of": "2026-10-05",
        "time_local": "08:15 ET",
        "title": "Overnight oil supply shock",
        "headline": "OPEC+ surprise supply increase: WTI -14.2% overnight, WCS-WTI differential wider by US$4.1, energy credit spreads +62 bp.",
        "alert": "Crude fell 14.2% overnight on an unexpected OPEC+ supply increase. Energy credit is repricing and the WCS discount has widened.",
        "pulse": [
            {
                "panel": "Equities",
                "rows": [
                    {
                        "name": "S&P/TSX Composite",
                        "level": "25,980",
                        "change": "-2.6%",
                        "dir": "down"
                    },
                    {
                        "name": "S&P/TSX Capped Energy",
                        "level": "286.4",
                        "change": "-7.9%",
                        "dir": "down"
                    },
                    {
                        "name": "S&P 500",
                        "level": "6,180",
                        "change": "-1.1%",
                        "dir": "down"
                    },
                    {
                        "name": "Cdn integrated oil peers",
                        "level": "100.0",
                        "change": "-8.5%",
                        "dir": "down"
                    }
                ]
            },
            {
                "panel": "Rates",
                "rows": [
                    {
                        "name": "GoC 2Y",
                        "level": "3.02%",
                        "change": "-6 bp",
                        "dir": "down"
                    },
                    {
                        "name": "GoC 10Y",
                        "level": "3.18%",
                        "change": "-9 bp",
                        "dir": "down"
                    },
                    {
                        "name": "UST 10Y",
                        "level": "3.74%",
                        "change": "-7 bp",
                        "dir": "down"
                    },
                    {
                        "name": "Canada 2s10s",
                        "level": "+16 bp",
                        "change": "-3 bp",
                        "dir": "down"
                    }
                ]
            },
            {
                "panel": "Credit",
                "rows": [
                    {
                        "name": "CAD IG OAS",
                        "level": "132 bp",
                        "change": "+14 bp",
                        "dir": "up",
                        "bad": True
                    },
                    {
                        "name": "CAD HY OAS",
                        "level": "452 bp",
                        "change": "+38 bp",
                        "dir": "up",
                        "bad": True
                    },
                    {
                        "name": "US Energy HY OAS",
                        "level": "548 bp",
                        "change": "+62 bp",
                        "dir": "up",
                        "bad": True
                    },
                    {
                        "name": "CDX IG",
                        "level": "71 bp",
                        "change": "+6 bp",
                        "dir": "up",
                        "bad": True
                    }
                ]
            },
            {
                "panel": "Commodities & FX",
                "rows": [
                    {
                        "name": "WTI (US$/bbl)",
                        "level": "61.40",
                        "change": "-14.2%",
                        "dir": "down"
                    },
                    {
                        "name": "WCS-WTI diff (US$/bbl)",
                        "level": "-17.20",
                        "change": "-4.10",
                        "dir": "down"
                    },
                    {
                        "name": "AECO (C$/mmbtu)",
                        "level": "1.98",
                        "change": "-4.0%",
                        "dir": "down"
                    },
                    {
                        "name": "USD/CAD",
                        "level": "1.392",
                        "change": "+1.4%",
                        "dir": "up"
                    }
                ]
            }
        ],
        "clients": {
            "CLI-1001": {
                "ebitda_shock_pct": -3.0,
                "pse_change_m": -4.1,
                "driver": "Fee-based infrastructure cushions the hit; crude marketing margin and the Chauvin volumes are exposed to the wider WCS differential.",
                "pending_transaction": "Revolver upsize CAD 1.10bn -> 1.35bn (OPP-4471) in approval",
                "contact_role": "VP & Treasurer",
                "channel": "video",
                "channel_detail": "Teams video",
                "slot": "10:30 ET",
                "response": {
                    "status": "accepted",
                    "detail": "Accepted the Teams video call at 10:30 ET."
                }
            },
            "CLI-1002": {
                "ebitda_shock_pct": -3.5,
                "pse_change_m": 0.0,
                "driver": "NGL margins and producer activity soften; the fee-for-service base is resilient.",
                "contact_role": "VP & Treasurer",
                "channel": "chat",
                "channel_detail": "Teams chat",
                "slot": "13:00 ET",
                "response": {
                    "status": "awaiting",
                    "detail": "Message delivered; awaiting reply."
                }
            },
            "CLI-1003": {
                "ebitda_shock_pct": -14.5,
                "pse_change_m": 0.0,
                "driver": "Light-oil producer: realised prices fall with WTI; the hedge book covers only part of the next 12 months.",
                "contact_role": "Chief Financial Officer",
                "channel": "phone",
                "channel_detail": "Phone",
                "slot": "11:00 ET",
                "response": {
                    "status": "accepted",
                    "detail": "Confirmed a call at 11:00 ET."
                }
            },
            "CLI-1004": {
                "ebitda_shock_pct": -5.0,
                "pse_change_m": 0.0,
                "driver": "Activity-linked energy-services volumes soften; waste and industrial services are steadier.",
                "contact_role": "Chief Financial Officer",
                "channel": "phone",
                "channel_detail": "Phone",
                "slot": "15:00 ET",
                "response": {
                    "status": "awaiting",
                    "detail": "Voicemail left; awaiting call back."
                }
            },
            "CLI-1005": {
                "ebitda_shock_pct": 0.5,
                "pse_change_m": 0.0,
                "driver": "Lower diesel and input costs and USD revenue translation help modestly.",
                "contact_role": "Chief Financial Officer",
                "channel": "email",
                "channel_detail": "Email",
                "slot": "Today",
                "response": {
                    "status": "awaiting",
                    "detail": "Email delivered; awaiting reply."
                }
            },
            "CLI-1006": {
                "ebitda_shock_pct": -4.0,
                "pse_change_m": 0.0,
                "driver": "Energy tubular product demand and industrial sentiment weaken; CAD weakness partly offsets on USD-priced sales.",
                "contact_role": "VP Finance",
                "channel": "email",
                "channel_detail": "Email",
                "slot": "Today",
                "response": {
                    "status": "tomorrow",
                    "detail": "Replied: available tomorrow at 09:00 ET."
                }
            },
            "CLI-1007": {
                "ebitda_shock_pct": 0.5,
                "pse_change_m": 0.0,
                "driver": "Lower energy, freight and input costs offset demand worries.",
                "contact_role": "Chief Financial Officer",
                "channel": "video",
                "channel_detail": "Teams video",
                "slot": "14:00 ET",
                "response": {
                    "status": "accepted",
                    "detail": "Accepted the Teams video call at 14:00 ET."
                }
            },
            "CLI-1008": {
                "ebitda_shock_pct": 0.0,
                "pse_change_m": 0.0,
                "driver": "Broadly neutral near term: mixed FX and input-cost effects.",
                "contact_role": "Chief Financial Officer",
                "channel": "email",
                "channel_detail": "Email",
                "slot": "Today",
                "response": {
                    "status": "awaiting",
                    "detail": "Email delivered; awaiting reply."
                }
            },
            "CLI-1009": {
                "ebitda_shock_pct": 0.0,
                "pse_change_m": 0.0,
                "driver": "Fuel and freight relief is offset by a weaker CAD on imported merchandise.",
                "contact_role": "VP & Treasurer",
                "channel": "email",
                "channel_detail": "Email",
                "slot": "Today",
                "response": {
                    "status": "awaiting",
                    "detail": "Email delivered; awaiting reply."
                }
            },
            "CLI-1010": {
                "ebitda_shock_pct": -1.0,
                "pse_change_m": 0.0,
                "driver": "Propane distribution margins are modestly lower; volumes remain weather-driven.",
                "contact_role": "Chief Financial Officer",
                "channel": "phone",
                "channel_detail": "Phone",
                "slot": "16:00 ET",
                "response": {
                    "status": "awaiting",
                    "detail": "Awaiting call back."
                }
            }
        },
        "house_view": {
            "id": "HV-2026-10-05",
            "committee": "Credit & Markets Committee (synthetic)",
            "date": "2026-10-05",
            "positions": [
                {
                    "topic": "Oil",
                    "view": "Treat the move as supply-driven, not a demand shock. Base case is a partial retracement over two quarters; do not anchor client conversations on spot."
                },
                {
                    "topic": "Energy credit",
                    "view": "Expect energy high-yield spreads to stay wide near term; investment-grade midstream remains resilient. No change to midstream appetite."
                },
                {
                    "topic": "Lending posture",
                    "view": "No new term exposure to producers in the Tight or Breach band without a CP-005 pro-forma at a 15% EBITDA stress. Energy sector envelope is Amber: route new requests through Portfolio Management (CP-002)."
                },
                {
                    "topic": "Hedging",
                    "view": "Offer hedge-programme reviews to producers, subject to CP-010 appropriateness and pre-settlement capacity. No solicitation on restricted names."
                },
                {
                    "topic": "Covenants",
                    "view": "Raise covenant conversations early and attach them to any facility discussion now, not after the next compliance certificate."
                }
            ],
            "approved_framing": [
                "Today's move looks supply-driven; our committee's base case is a partial retracement over the next two quarters.",
                "We are not changing our support for well-structured midstream and infrastructure credits.",
                "Any change to facility size or terms is subject to our internal approval; we will come back with something firm.",
                "If it would help, we can review your hedge programme with you - any recommendation follows our appropriateness process."
            ],
            "needs_disclaimer": [
                "Any view on commodity prices or spreads (forward-looking; not a forecast or advice).",
                "Any illustration of covenant sensitivity (based on your reported figures; illustrative only)."
            ],
            "needs_approval": [
                "Any indicative facility size, hold or pricing (CP-003).",
                "Any specific hedge structure or notional (CP-010, and CP-008 where a restriction applies)."
            ],
            "never_say": [
                "Our internal risk rating, single-name limit or its utilisation (CP-014).",
                "Our sector capacity position or that it constrains us (CP-002).",
                "Wallet share or competitor rankings (CP-014).",
                "Anything touching a restricted subject, or that a wall-crossing exists (CP-008)."
            ]
        },
        "severity": {
            "note": "Deterministic 0-100. Weights reviewed by a second model; the derivative factor is replaced by shock magnitude (only one client carries derivatives) and events include live transactions. Threshold 41 flags five of ten, as the reviewer suggested.",
            "covenant": {
                "breach": 45,
                "lt5": 35,
                "lt10": 25,
                "lt20": 15,
                "else": 5
            },
            "limit": {
                "gt90": 20,
                "gt80": 15,
                "gt70": 10,
                "else": 0
            },
            "rating": {
                "watchlist_or_negative": 15,
                "stable": 5,
                "improving": 0
            },
            "events_cap": 10,
            "events": {
                "meeting_7d": 3,
                "kyc_60d": 3,
                "maturity_12m": 4,
                "pending_transaction": 4
            },
            "shock": {
                "ge10": 10,
                "ge3": 6,
                "ge1": 3,
                "else": 0
            },
            "threshold": 41
        }
    },
    "extra": {
        "CLI-1001": {
            "exposure_by_product": [
                {
                    "product": "Corporate Loan - Revolving Credit Facility",
                    "business_line": "Corporate Banking",
                    "type": "Funded - drawn revolver",
                    "current": 96.0
                },
                {
                    "product": "Corporate Loan - Term Loan",
                    "business_line": "Corporate Banking",
                    "type": "Funded - term loan",
                    "current": 140.0
                },
                {
                    "product": "Letters of Credit",
                    "business_line": "Corporate Banking",
                    "type": "Contingent - letters of credit",
                    "current": 32.4
                },
                {
                    "product": "Commodity Derivatives",
                    "business_line": "Global Markets",
                    "type": "Derivative - commodity MTM + PSE",
                    "current": 41.2
                },
                {
                    "product": "FX - Forwards and Options",
                    "business_line": "Global Markets",
                    "type": "Derivative - FX forward MTM + PSE",
                    "current": 18.6
                },
                {
                    "product": "Interest Rate Derivatives",
                    "business_line": "Global Markets",
                    "type": "Derivative - interest rate swap MTM",
                    "current": 9.4
                },
                {
                    "product": "Cash Management & Treasury Services",
                    "business_line": "Transaction Banking",
                    "type": "Intraday settlement / daylight",
                    "current": 4.1
                }
            ],
            "trades": [
                {
                    "date": "2026-09-01",
                    "product": "Debt Capital Markets - Underwriting",
                    "description": "Senior unsecured notes - joint bookrunner",
                    "notional_m": 400.0,
                    "status": "Settled"
                },
                {
                    "date": "2026-08-19",
                    "product": "Commodity Derivatives",
                    "description": "WTI-WCS differential swap - 12m strip",
                    "notional_m": 75.0,
                    "status": "Live"
                },
                {
                    "date": "2026-08-06",
                    "product": "FX - Forwards and Options",
                    "description": "CAD/USD forward - 6m",
                    "notional_m": 60.0,
                    "status": "Live"
                },
                {
                    "date": "2026-07-14",
                    "product": "Interest Rate Derivatives",
                    "description": "SOFR fixed-pay swap - 5y",
                    "notional_m": 100.0,
                    "status": "Live"
                },
                {
                    "date": "2026-04-28",
                    "product": "Commodity Derivatives",
                    "description": "WCS crude collar - 18m",
                    "notional_m": 55.0,
                    "status": "Live"
                },
                {
                    "date": "2026-03-31",
                    "product": "Corporate Loan - Term Loan",
                    "description": "Chauvin bridge take-out term loan",
                    "notional_m": 140.0,
                    "status": "Settled"
                }
            ],
            "engagement": [
                {
                    "date": "2026-10-05",
                    "kind": "email",
                    "title": "Credit summary for the brief - final figures",
                    "source": "Work IQ"
                },
                {
                    "date": "2026-10-05",
                    "kind": "email",
                    "title": "Thursday logistics and the one thing I want us to get right",
                    "source": "Work IQ"
                },
                {
                    "date": "2026-10-05",
                    "kind": "email",
                    "title": "Control Room response on the agenda - partial clearance",
                    "source": "Work IQ"
                },
                {
                    "date": "2026-10-04",
                    "kind": "email",
                    "title": "Cash management comparison - closed",
                    "source": "Work IQ"
                },
                {
                    "date": "2026-10-04",
                    "kind": "email",
                    "title": "Still no Control Room clearance on the hedging item",
                    "source": "Work IQ"
                },
                {
                    "date": "2026-10-04",
                    "kind": "email",
                    "title": "Pre-meeting brief - what has to be in it, and what happens if it is not",
                    "source": "Work IQ"
                },
                {
                    "date": "2026-10-03",
                    "kind": "email",
                    "title": "Thursday - what we are actually going to say, and what we are not",
                    "source": "Work IQ"
                },
                {
                    "date": "2026-10-03",
                    "kind": "email",
                    "title": "Sector position - why the upsize is harder than the single-name number suggests",
                    "source": "Work IQ"
                }
            ],
            "revenue_ytd_m": 8.42,
            "revenue_markets_ytd_m": 2.325,
            "revenue_prior_ytd_m": 7.14,
            "wallet_share_pct": 21.4,
            "limit_reviews": [
                {
                    "type": "Single-name credit limit",
                    "next_review": "2027-03-31"
                },
                {
                    "type": "Derivative pre-settlement limit",
                    "next_review": "2027-03-31"
                },
                {
                    "type": "Tenor limit - max remaining maturity",
                    "next_review": "2027-03-31"
                },
                {
                    "type": "Underwriting commitment limit",
                    "next_review": "2026-12-31"
                }
            ]
        },
        "CLI-1002": {
            "exposure_by_product": [
                {
                    "product": "Corporate Loan - Revolving Credit Facility",
                    "business_line": "Corporate Banking",
                    "type": "Funded",
                    "current": 122.7
                },
                {
                    "product": "Corporate Loan - Term Loan",
                    "business_line": "Corporate Banking",
                    "type": "Funded",
                    "current": 123.0
                },
                {
                    "product": "Letters of Credit",
                    "business_line": "Corporate Banking",
                    "type": "Contingent",
                    "current": 27.0
                },
                {
                    "product": "FX - Forwards and Options",
                    "business_line": "Global Markets",
                    "type": "Derivative - MTM + PSE",
                    "current": 22.7
                },
                {
                    "product": "Interest Rate Derivatives",
                    "business_line": "Global Markets",
                    "type": "Derivative - MTM + PSE",
                    "current": 12.2
                }
            ],
            "trades": [
                {
                    "date": "2026-07-19",
                    "product": "FX - Forwards and Options",
                    "description": "FX - Forwards and Options - client transaction",
                    "notional_m": 264.7,
                    "status": "Settled"
                },
                {
                    "date": "2026-04-17",
                    "product": "Debt Capital Markets - Underwriting",
                    "description": "Debt Capital Markets - Underwriting - client transaction",
                    "notional_m": 297.6,
                    "status": "Live"
                },
                {
                    "date": "2026-04-10",
                    "product": "Debt Capital Markets - Underwriting",
                    "description": "Debt Capital Markets - Underwriting - client transaction",
                    "notional_m": 57.0,
                    "status": "Matured"
                },
                {
                    "date": "2026-03-01",
                    "product": "FX - Forwards and Options",
                    "description": "FX - Forwards and Options - client transaction",
                    "notional_m": 121.4,
                    "status": "Live"
                },
                {
                    "date": "2026-02-18",
                    "product": "Interest Rate Derivatives",
                    "description": "Interest Rate Derivatives - client transaction",
                    "notional_m": 57.6,
                    "status": "Live"
                }
            ],
            "engagement": [
                {
                    "date": "2026-10-02",
                    "kind": "email",
                    "title": "Keyera FX - why we are down 17.3 per cent, and what I would not do about it",
                    "source": "Work IQ"
                },
                {
                    "date": "2026-10-01",
                    "kind": "email",
                    "title": "Keyera - Tier 1 on paper, and where the FY27 ask actually is",
                    "source": "Work IQ"
                },
                {
                    "date": "2026-09-29",
                    "kind": "email",
                    "title": "Keyera single-name limit is amber at 85.8 per cent - nothing new until it is forecast",
                    "source": "Work IQ"
                },
                {
                    "date": "2026-09-18",
                    "kind": "email",
                    "title": "Call report - Keyera treasury, 18 September - DCM pipeline and the FX book",
                    "source": "Work IQ"
                },
                {
                    "date": "2026-05-06",
                    "kind": "meeting",
                    "title": "Coverage meeting (last recorded)",
                    "source": "Fabric IQ"
                }
            ],
            "revenue_ytd_m": 8.58,
            "revenue_markets_ytd_m": 1.973,
            "revenue_prior_ytd_m": 7.938,
            "wallet_share_pct": 17.1,
            "limit_reviews": [
                {
                    "type": "Single-name credit limit",
                    "next_review": "2027-07-25"
                }
            ]
        },
        "CLI-1003": {
            "exposure_by_product": [
                {
                    "product": "Corporate Loan - Revolving Credit Facility",
                    "business_line": "Corporate Banking",
                    "type": "Funded",
                    "current": 59.7
                },
                {
                    "product": "Corporate Loan - Term Loan",
                    "business_line": "Corporate Banking",
                    "type": "Funded",
                    "current": 51.7
                },
                {
                    "product": "Letters of Credit",
                    "business_line": "Corporate Banking",
                    "type": "Contingent",
                    "current": 24.4
                },
                {
                    "product": "FX - Forwards and Options",
                    "business_line": "Global Markets",
                    "type": "Derivative - MTM + PSE",
                    "current": 10.9
                },
                {
                    "product": "Interest Rate Derivatives",
                    "business_line": "Global Markets",
                    "type": "Derivative - MTM + PSE",
                    "current": 7.6
                }
            ],
            "trades": [
                {
                    "date": "2026-05-12",
                    "product": "FX - Forwards and Options",
                    "description": "FX - Forwards and Options - client transaction",
                    "notional_m": 300.3,
                    "status": "Settled"
                },
                {
                    "date": "2026-03-14",
                    "product": "Debt Capital Markets - Underwriting",
                    "description": "Debt Capital Markets - Underwriting - client transaction",
                    "notional_m": 109.3,
                    "status": "Matured"
                },
                {
                    "date": "2026-02-03",
                    "product": "Commodity Derivatives",
                    "description": "Commodity Derivatives - client transaction",
                    "notional_m": 25.5,
                    "status": "Live"
                },
                {
                    "date": "2025-12-20",
                    "product": "Interest Rate Derivatives",
                    "description": "Interest Rate Derivatives - client transaction",
                    "notional_m": 49.9,
                    "status": "Live"
                },
                {
                    "date": "2025-11-29",
                    "product": "Interest Rate Derivatives",
                    "description": "Interest Rate Derivatives - client transaction",
                    "notional_m": 208.9,
                    "status": "Live"
                },
                {
                    "date": "2025-11-27",
                    "product": "Debt Capital Markets - Underwriting",
                    "description": "Debt Capital Markets - Underwriting - client transaction",
                    "notional_m": 109.7,
                    "status": "Matured"
                }
            ],
            "engagement": [
                {
                    "date": "2026-09-11",
                    "kind": "meeting",
                    "title": "Coverage meeting (last recorded)",
                    "source": "Fabric IQ"
                }
            ],
            "revenue_ytd_m": 6.169,
            "revenue_markets_ytd_m": 1.419,
            "revenue_prior_ytd_m": 5.536,
            "wallet_share_pct": 17.9,
            "limit_reviews": [
                {
                    "type": "Single-name credit limit",
                    "next_review": "2026-12-16"
                }
            ]
        },
        "CLI-1004": {
            "exposure_by_product": [
                {
                    "product": "Corporate Loan - Revolving Credit Facility",
                    "business_line": "Corporate Banking",
                    "type": "Funded",
                    "current": 46.5
                },
                {
                    "product": "Corporate Loan - Term Loan",
                    "business_line": "Corporate Banking",
                    "type": "Funded",
                    "current": 40.0
                },
                {
                    "product": "Letters of Credit",
                    "business_line": "Corporate Banking",
                    "type": "Contingent",
                    "current": 14.2
                },
                {
                    "product": "FX - Forwards and Options",
                    "business_line": "Global Markets",
                    "type": "Derivative - MTM + PSE",
                    "current": 7.8
                },
                {
                    "product": "Interest Rate Derivatives",
                    "business_line": "Global Markets",
                    "type": "Derivative - MTM + PSE",
                    "current": 7.0
                }
            ],
            "trades": [
                {
                    "date": "2026-08-16",
                    "product": "Commodity Derivatives",
                    "description": "Commodity Derivatives - client transaction",
                    "notional_m": 281.4,
                    "status": "Matured"
                },
                {
                    "date": "2026-06-27",
                    "product": "Interest Rate Derivatives",
                    "description": "Interest Rate Derivatives - client transaction",
                    "notional_m": 20.3,
                    "status": "Settled"
                },
                {
                    "date": "2026-04-14",
                    "product": "Commodity Derivatives",
                    "description": "Commodity Derivatives - client transaction",
                    "notional_m": 80.3,
                    "status": "Settled"
                },
                {
                    "date": "2026-04-08",
                    "product": "FX - Forwards and Options",
                    "description": "FX - Forwards and Options - client transaction",
                    "notional_m": 208.1,
                    "status": "Settled"
                },
                {
                    "date": "2026-02-14",
                    "product": "Corporate Loan - Revolving Credit Facility",
                    "description": "Corporate Loan - Revolving Credit Facility - client transaction",
                    "notional_m": 244.2,
                    "status": "Settled"
                }
            ],
            "engagement": [
                {
                    "date": "2026-05-04",
                    "kind": "meeting",
                    "title": "Coverage meeting (last recorded)",
                    "source": "Fabric IQ"
                }
            ],
            "revenue_ytd_m": 2.646,
            "revenue_markets_ytd_m": 0.609,
            "revenue_prior_ytd_m": 2.523,
            "wallet_share_pct": 24.7,
            "limit_reviews": [
                {
                    "type": "Single-name credit limit",
                    "next_review": "2027-05-14"
                }
            ]
        },
        "CLI-1005": {
            "exposure_by_product": [
                {
                    "product": "Corporate Loan - Revolving Credit Facility",
                    "business_line": "Corporate Banking",
                    "type": "Funded",
                    "current": 71.5
                },
                {
                    "product": "Corporate Loan - Term Loan",
                    "business_line": "Corporate Banking",
                    "type": "Funded",
                    "current": 42.5
                },
                {
                    "product": "Letters of Credit",
                    "business_line": "Corporate Banking",
                    "type": "Contingent",
                    "current": 18.1
                },
                {
                    "product": "FX - Forwards and Options",
                    "business_line": "Global Markets",
                    "type": "Derivative - MTM + PSE",
                    "current": 11.2
                },
                {
                    "product": "Interest Rate Derivatives",
                    "business_line": "Global Markets",
                    "type": "Derivative - MTM + PSE",
                    "current": 7.4
                }
            ],
            "trades": [
                {
                    "date": "2026-09-07",
                    "product": "Interest Rate Derivatives",
                    "description": "Interest Rate Derivatives - client transaction",
                    "notional_m": 105.5,
                    "status": "Settled"
                },
                {
                    "date": "2026-07-04",
                    "product": "Corporate Loan - Revolving Credit Facility",
                    "description": "Corporate Loan - Revolving Credit Facility - client transaction",
                    "notional_m": 126.5,
                    "status": "Matured"
                },
                {
                    "date": "2026-03-24",
                    "product": "Interest Rate Derivatives",
                    "description": "Interest Rate Derivatives - client transaction",
                    "notional_m": 288.1,
                    "status": "Settled"
                },
                {
                    "date": "2026-01-02",
                    "product": "Corporate Loan - Revolving Credit Facility",
                    "description": "Corporate Loan - Revolving Credit Facility - client transaction",
                    "notional_m": 102.2,
                    "status": "Matured"
                },
                {
                    "date": "2025-12-25",
                    "product": "Commodity Derivatives",
                    "description": "Commodity Derivatives - client transaction",
                    "notional_m": 71.6,
                    "status": "Matured"
                }
            ],
            "engagement": [
                {
                    "date": "2026-09-02",
                    "kind": "meeting",
                    "title": "Coverage meeting (last recorded)",
                    "source": "Fabric IQ"
                }
            ],
            "revenue_ytd_m": 2.952,
            "revenue_markets_ytd_m": 0.679,
            "revenue_prior_ytd_m": 3.034,
            "wallet_share_pct": 21.2,
            "limit_reviews": [
                {
                    "type": "Single-name credit limit",
                    "next_review": "2028-01-23"
                }
            ]
        },
        "CLI-1006": {
            "exposure_by_product": [
                {
                    "product": "Corporate Loan - Revolving Credit Facility",
                    "business_line": "Corporate Banking",
                    "type": "Funded",
                    "current": 93.1
                },
                {
                    "product": "Corporate Loan - Term Loan",
                    "business_line": "Corporate Banking",
                    "type": "Funded",
                    "current": 62.8
                },
                {
                    "product": "Letters of Credit",
                    "business_line": "Corporate Banking",
                    "type": "Contingent",
                    "current": 15.3
                },
                {
                    "product": "FX - Forwards and Options",
                    "business_line": "Global Markets",
                    "type": "Derivative - MTM + PSE",
                    "current": 13.9
                },
                {
                    "product": "Interest Rate Derivatives",
                    "business_line": "Global Markets",
                    "type": "Derivative - MTM + PSE",
                    "current": 6.3
                }
            ],
            "trades": [
                {
                    "date": "2026-09-10",
                    "product": "Commodity Derivatives",
                    "description": "Commodity Derivatives - client transaction",
                    "notional_m": 165.8,
                    "status": "Matured"
                },
                {
                    "date": "2026-06-13",
                    "product": "Corporate Loan - Revolving Credit Facility",
                    "description": "Corporate Loan - Revolving Credit Facility - client transaction",
                    "notional_m": 260.4,
                    "status": "Matured"
                },
                {
                    "date": "2026-06-06",
                    "product": "Debt Capital Markets - Underwriting",
                    "description": "Debt Capital Markets - Underwriting - client transaction",
                    "notional_m": 99.4,
                    "status": "Settled"
                },
                {
                    "date": "2026-05-18",
                    "product": "Commodity Derivatives",
                    "description": "Commodity Derivatives - client transaction",
                    "notional_m": 197.4,
                    "status": "Matured"
                },
                {
                    "date": "2026-03-24",
                    "product": "Debt Capital Markets - Underwriting",
                    "description": "Debt Capital Markets - Underwriting - client transaction",
                    "notional_m": 45.4,
                    "status": "Settled"
                },
                {
                    "date": "2026-01-05",
                    "product": "Interest Rate Derivatives",
                    "description": "Interest Rate Derivatives - client transaction",
                    "notional_m": 63.0,
                    "status": "Live"
                }
            ],
            "engagement": [
                {
                    "date": "2026-07-26",
                    "kind": "meeting",
                    "title": "Coverage meeting (last recorded)",
                    "source": "Fabric IQ"
                }
            ],
            "revenue_ytd_m": 3.41,
            "revenue_markets_ytd_m": 0.784,
            "revenue_prior_ytd_m": 3.483,
            "wallet_share_pct": 14.7,
            "limit_reviews": [
                {
                    "type": "Single-name credit limit",
                    "next_review": "2027-10-20"
                }
            ]
        },
        "CLI-1007": {
            "exposure_by_product": [
                {
                    "product": "Corporate Loan - Revolving Credit Facility",
                    "business_line": "Corporate Banking",
                    "type": "Funded",
                    "current": 53.1
                },
                {
                    "product": "Corporate Loan - Term Loan",
                    "business_line": "Corporate Banking",
                    "type": "Funded",
                    "current": 42.8
                },
                {
                    "product": "Letters of Credit",
                    "business_line": "Corporate Banking",
                    "type": "Contingent",
                    "current": 8.9
                },
                {
                    "product": "FX - Forwards and Options",
                    "business_line": "Global Markets",
                    "type": "Derivative - MTM + PSE",
                    "current": 6.5
                },
                {
                    "product": "Interest Rate Derivatives",
                    "business_line": "Global Markets",
                    "type": "Derivative - MTM + PSE",
                    "current": 5.9
                }
            ],
            "trades": [
                {
                    "date": "2026-07-15",
                    "product": "Interest Rate Derivatives",
                    "description": "Interest Rate Derivatives - client transaction",
                    "notional_m": 72.2,
                    "status": "Settled"
                },
                {
                    "date": "2026-06-22",
                    "product": "Commodity Derivatives",
                    "description": "Commodity Derivatives - client transaction",
                    "notional_m": 253.7,
                    "status": "Matured"
                },
                {
                    "date": "2026-04-11",
                    "product": "Interest Rate Derivatives",
                    "description": "Interest Rate Derivatives - client transaction",
                    "notional_m": 34.7,
                    "status": "Matured"
                },
                {
                    "date": "2026-02-18",
                    "product": "Corporate Loan - Revolving Credit Facility",
                    "description": "Corporate Loan - Revolving Credit Facility - client transaction",
                    "notional_m": 217.5,
                    "status": "Matured"
                },
                {
                    "date": "2025-12-24",
                    "product": "Debt Capital Markets - Underwriting",
                    "description": "Debt Capital Markets - Underwriting - client transaction",
                    "notional_m": 258.7,
                    "status": "Matured"
                }
            ],
            "engagement": [
                {
                    "date": "2026-10-01",
                    "kind": "email",
                    "title": "Cascades commodity flow is down 21.5 per cent - suitability before revenue",
                    "source": "Work IQ"
                },
                {
                    "date": "2026-09-30",
                    "kind": "email",
                    "title": "Cascades - a Tier 3 name absorbing Tier 1 credit time",
                    "source": "Work IQ"
                },
                {
                    "date": "2026-09-28",
                    "kind": "email",
                    "title": "Call report - Cascades treasury, 28 September - LC utilisation and a revolver question I deflected",
                    "source": "Work IQ"
                },
                {
                    "date": "2026-09-23",
                    "kind": "email",
                    "title": "Cascades stays on the watchlist - the covenant is the constraint, not the limit",
                    "source": "Work IQ"
                },
                {
                    "date": "2026-03-23",
                    "kind": "meeting",
                    "title": "Coverage meeting (last recorded)",
                    "source": "Fabric IQ"
                }
            ],
            "revenue_ytd_m": 3.008,
            "revenue_markets_ytd_m": 0.692,
            "revenue_prior_ytd_m": 2.883,
            "wallet_share_pct": 14.8,
            "limit_reviews": [
                {
                    "type": "Single-name credit limit",
                    "next_review": "2027-12-12"
                }
            ]
        },
        "CLI-1008": {
            "exposure_by_product": [
                {
                    "product": "Corporate Loan - Revolving Credit Facility",
                    "business_line": "Corporate Banking",
                    "type": "Funded",
                    "current": 24.4
                },
                {
                    "product": "Corporate Loan - Term Loan",
                    "business_line": "Corporate Banking",
                    "type": "Funded",
                    "current": 23.2
                },
                {
                    "product": "Letters of Credit",
                    "business_line": "Corporate Banking",
                    "type": "Contingent",
                    "current": 10.1
                },
                {
                    "product": "FX - Forwards and Options",
                    "business_line": "Global Markets",
                    "type": "Derivative - MTM + PSE",
                    "current": 4.7
                },
                {
                    "product": "Interest Rate Derivatives",
                    "business_line": "Global Markets",
                    "type": "Derivative - MTM + PSE",
                    "current": 4.8
                }
            ],
            "trades": [
                {
                    "date": "2026-07-21",
                    "product": "FX - Forwards and Options",
                    "description": "FX - Forwards and Options - client transaction",
                    "notional_m": 187.3,
                    "status": "Settled"
                },
                {
                    "date": "2026-05-15",
                    "product": "Corporate Loan - Revolving Credit Facility",
                    "description": "Corporate Loan - Revolving Credit Facility - client transaction",
                    "notional_m": 186.1,
                    "status": "Live"
                },
                {
                    "date": "2026-03-19",
                    "product": "Interest Rate Derivatives",
                    "description": "Interest Rate Derivatives - client transaction",
                    "notional_m": 191.5,
                    "status": "Matured"
                },
                {
                    "date": "2026-03-05",
                    "product": "Debt Capital Markets - Underwriting",
                    "description": "Debt Capital Markets - Underwriting - client transaction",
                    "notional_m": 18.6,
                    "status": "Matured"
                },
                {
                    "date": "2026-03-03",
                    "product": "FX - Forwards and Options",
                    "description": "FX - Forwards and Options - client transaction",
                    "notional_m": 271.7,
                    "status": "Matured"
                }
            ],
            "engagement": [
                {
                    "date": "2026-08-25",
                    "kind": "meeting",
                    "title": "Coverage meeting (last recorded)",
                    "source": "Fabric IQ"
                }
            ],
            "revenue_ytd_m": 1.512,
            "revenue_markets_ytd_m": 0.348,
            "revenue_prior_ytd_m": 1.588,
            "wallet_share_pct": 14.6,
            "limit_reviews": [
                {
                    "type": "Single-name credit limit",
                    "next_review": "2027-04-11"
                }
            ]
        },
        "CLI-1009": {
            "exposure_by_product": [
                {
                    "product": "Corporate Loan - Revolving Credit Facility",
                    "business_line": "Corporate Banking",
                    "type": "Funded",
                    "current": 35.2
                },
                {
                    "product": "Corporate Loan - Term Loan",
                    "business_line": "Corporate Banking",
                    "type": "Funded",
                    "current": 24.9
                },
                {
                    "product": "Letters of Credit",
                    "business_line": "Corporate Banking",
                    "type": "Contingent",
                    "current": 11.8
                },
                {
                    "product": "FX - Forwards and Options",
                    "business_line": "Global Markets",
                    "type": "Derivative - MTM + PSE",
                    "current": 6.2
                },
                {
                    "product": "Interest Rate Derivatives",
                    "business_line": "Global Markets",
                    "type": "Derivative - MTM + PSE",
                    "current": 3.7
                }
            ],
            "trades": [
                {
                    "date": "2026-09-09",
                    "product": "Interest Rate Derivatives",
                    "description": "Interest Rate Derivatives - client transaction",
                    "notional_m": 112.6,
                    "status": "Settled"
                },
                {
                    "date": "2026-07-07",
                    "product": "Corporate Loan - Revolving Credit Facility",
                    "description": "Corporate Loan - Revolving Credit Facility - client transaction",
                    "notional_m": 237.5,
                    "status": "Matured"
                },
                {
                    "date": "2026-05-22",
                    "product": "FX - Forwards and Options",
                    "description": "FX - Forwards and Options - client transaction",
                    "notional_m": 104.7,
                    "status": "Matured"
                },
                {
                    "date": "2026-01-29",
                    "product": "Interest Rate Derivatives",
                    "description": "Interest Rate Derivatives - client transaction",
                    "notional_m": 275.1,
                    "status": "Live"
                },
                {
                    "date": "2025-12-18",
                    "product": "Commodity Derivatives",
                    "description": "Commodity Derivatives - client transaction",
                    "notional_m": 196.8,
                    "status": "Settled"
                },
                {
                    "date": "2025-10-28",
                    "product": "Commodity Derivatives",
                    "description": "Commodity Derivatives - client transaction",
                    "notional_m": 171.5,
                    "status": "Live"
                }
            ],
            "engagement": [
                {
                    "date": "2026-08-19",
                    "kind": "meeting",
                    "title": "Coverage meeting (last recorded)",
                    "source": "Fabric IQ"
                }
            ],
            "revenue_ytd_m": 2.276,
            "revenue_markets_ytd_m": 0.524,
            "revenue_prior_ytd_m": 2.108,
            "wallet_share_pct": 16.4,
            "limit_reviews": [
                {
                    "type": "Single-name credit limit",
                    "next_review": "2028-01-15"
                }
            ]
        },
        "CLI-1010": {
            "exposure_by_product": [
                {
                    "product": "Corporate Loan - Revolving Credit Facility",
                    "business_line": "Corporate Banking",
                    "type": "Funded",
                    "current": 72.3
                },
                {
                    "product": "Corporate Loan - Term Loan",
                    "business_line": "Corporate Banking",
                    "type": "Funded",
                    "current": 85.7
                },
                {
                    "product": "Letters of Credit",
                    "business_line": "Corporate Banking",
                    "type": "Contingent",
                    "current": 19.3
                },
                {
                    "product": "FX - Forwards and Options",
                    "business_line": "Global Markets",
                    "type": "Derivative - MTM + PSE",
                    "current": 13.1
                },
                {
                    "product": "Interest Rate Derivatives",
                    "business_line": "Global Markets",
                    "type": "Derivative - MTM + PSE",
                    "current": 13.0
                }
            ],
            "trades": [
                {
                    "date": "2026-09-05",
                    "product": "FX - Forwards and Options",
                    "description": "FX - Forwards and Options - client transaction",
                    "notional_m": 83.0,
                    "status": "Matured"
                },
                {
                    "date": "2026-04-02",
                    "product": "Debt Capital Markets - Underwriting",
                    "description": "Debt Capital Markets - Underwriting - client transaction",
                    "notional_m": 143.4,
                    "status": "Live"
                },
                {
                    "date": "2026-02-15",
                    "product": "Corporate Loan - Revolving Credit Facility",
                    "description": "Corporate Loan - Revolving Credit Facility - client transaction",
                    "notional_m": 293.5,
                    "status": "Live"
                },
                {
                    "date": "2026-02-13",
                    "product": "Debt Capital Markets - Underwriting",
                    "description": "Debt Capital Markets - Underwriting - client transaction",
                    "notional_m": 192.0,
                    "status": "Live"
                },
                {
                    "date": "2026-02-09",
                    "product": "Commodity Derivatives",
                    "description": "Commodity Derivatives - client transaction",
                    "notional_m": 36.9,
                    "status": "Live"
                },
                {
                    "date": "2025-12-12",
                    "product": "Interest Rate Derivatives",
                    "description": "Interest Rate Derivatives - client transaction",
                    "notional_m": 179.5,
                    "status": "Live"
                }
            ],
            "engagement": [
                {
                    "date": "2026-09-14",
                    "kind": "meeting",
                    "title": "Coverage meeting (last recorded)",
                    "source": "Fabric IQ"
                }
            ],
            "revenue_ytd_m": 4.356,
            "revenue_markets_ytd_m": 1.002,
            "revenue_prior_ytd_m": 4.633,
            "wallet_share_pct": 13.2,
            "limit_reviews": [
                {
                    "type": "Single-name credit limit",
                    "next_review": "2027-02-11"
                }
            ]
        }
    },
    "people": {
        "sydney.mattos": {
            "name": "Sydney Mattos",
            "title": "Managing Director, Corporate Coverage - Energy",
            "department": "Corporate Banking",
            "wall_status": "public_side"
        },
        "sasha.ouellet": {
            "name": "Sasha Ouellet",
            "title": "Director, Corporate Banking & DCM Origination",
            "department": "Corporate Banking",
            "wall_status": "wall_crossed"
        },
        "robin.kline": {
            "name": "Robin Kline",
            "title": "Executive Director, Equity Research - Energy Infrastructure",
            "department": "Research",
            "wall_status": "public_side"
        },
        "quinn.campbell": {
            "name": "Quinn Campbell",
            "title": "Director, Commodities & FX Corporate Sales",
            "department": "Global Markets",
            "wall_status": "public_side"
        },
        "vance.deleon": {
            "name": "Vance DeLeon",
            "title": "Director, Credit Risk - Energy & Midstream",
            "department": "Credit Risk Management",
            "wall_status": "wall_crossed"
        }
    },
    "owners": {
        "CLI-1001": {
            "owner": "sydney.mattos",
            "banker": "sasha.ouellet"
        },
        "CLI-1002": {
            "owner": "sydney.mattos",
            "banker": "sasha.ouellet"
        },
        "CLI-1003": {
            "owner": "sydney.mattos",
            "banker": "sasha.ouellet"
        },
        "CLI-1004": {
            "owner": "sydney.mattos",
            "banker": "sasha.ouellet"
        },
        "CLI-1005": {
            "owner": "sydney.mattos",
            "banker": "sasha.ouellet"
        },
        "CLI-1006": {
            "owner": "sydney.mattos",
            "banker": "sasha.ouellet"
        },
        "CLI-1007": {
            "owner": "sydney.mattos",
            "banker": "sasha.ouellet"
        },
        "CLI-1008": {
            "owner": "sydney.mattos",
            "banker": "sasha.ouellet"
        },
        "CLI-1009": {
            "owner": "sydney.mattos",
            "banker": "sasha.ouellet"
        },
        "CLI-1010": {
            "owner": "sydney.mattos",
            "banker": "sasha.ouellet"
        }
    },
    "sensitivity": {
        "factors": [
            {
                "id": "oil_pct",
                "label": "Crude oil (WTI)",
                "unit": "%",
                "min": -40,
                "max": 40,
                "step": 1
            },
            {
                "id": "gas_pct",
                "label": "Natural gas (AECO)",
                "unit": "%",
                "min": -40,
                "max": 40,
                "step": 1
            },
            {
                "id": "rates_bp",
                "label": "GoC 10Y rates",
                "unit": "bp",
                "min": -150,
                "max": 150,
                "step": 5
            },
            {
                "id": "spreads_bp",
                "label": "CAD IG credit spreads",
                "unit": "bp",
                "min": -50,
                "max": 150,
                "step": 5
            },
            {
                "id": "usdcad_pct",
                "label": "USD/CAD",
                "unit": "%",
                "min": -8,
                "max": 8,
                "step": 0.5
            },
            {
                "id": "demand_pct",
                "label": "Industrial demand (GDP proxy)",
                "unit": "%",
                "min": -8,
                "max": 6,
                "step": 0.5
            },
            {
                "id": "tariff_pct",
                "label": "US tariff on Canadian goods",
                "unit": "%",
                "min": 0,
                "max": 40,
                "step": 2.5
            }
        ],
        "presets": [
            {
                "id": "oil-shock",
                "name": "Overnight oil supply shock",
                "note": "Today's scenario (SCN-2026-10-05-OIL).",
                "factors": {
                    "oil_pct": -14.2,
                    "gas_pct": -4.0,
                    "rates_bp": -9,
                    "spreads_bp": 14,
                    "usdcad_pct": 1.4,
                    "demand_pct": 0,
                    "tariff_pct": 0.0
                },
                "group": "market"
            },
            {
                "id": "oil-rebound",
                "name": "Oil rebound",
                "note": "Supply discipline returns; crude recovers.",
                "factors": {
                    "oil_pct": 18.0,
                    "gas_pct": 6.0,
                    "rates_bp": 6,
                    "spreads_bp": -8,
                    "usdcad_pct": -1.5,
                    "demand_pct": 0.5,
                    "tariff_pct": 0.0
                },
                "group": "market"
            },
            {
                "id": "recession",
                "name": "Canadian recession",
                "note": "Demand contraction, oil lower, spreads wider, BoC eases.",
                "factors": {
                    "oil_pct": -25.0,
                    "gas_pct": -10.0,
                    "rates_bp": -75,
                    "spreads_bp": 60,
                    "usdcad_pct": 4.0,
                    "demand_pct": -4.0,
                    "tariff_pct": 0.0
                },
                "group": "market"
            },
            {
                "id": "higher-for-longer",
                "name": "Rates higher for longer",
                "note": "Sticky inflation; no cuts.",
                "factors": {
                    "oil_pct": 0.0,
                    "gas_pct": 0.0,
                    "rates_bp": 100,
                    "spreads_bp": 25,
                    "usdcad_pct": -1.0,
                    "demand_pct": -1.0,
                    "tariff_pct": 0.0
                },
                "group": "market"
            },
            {
                "id": "spread-shock",
                "name": "Credit spread shock",
                "note": "Risk-off repricing across credit.",
                "factors": {
                    "oil_pct": -5.0,
                    "gas_pct": 0.0,
                    "rates_bp": -20,
                    "spreads_bp": 80,
                    "usdcad_pct": 2.0,
                    "demand_pct": -1.5,
                    "tariff_pct": 0.0
                },
                "group": "market"
            },
            {
                "id": "mideast-war",
                "name": "Middle East conflict escalation",
                "group": "world",
                "note": "Supply-route risk lifts crude and gas; risk-off widens credit; CAD firms with oil.",
                "web_query": "military conflict or escalation in the Middle East affecting oil supply, shipping or the Strait of Hormuz",
                "channels": "Oil and gas up, spreads wider, inflation premium in rates, CAD stronger, softer global demand.",
                "factors": {
                    "oil_pct": 22.0,
                    "gas_pct": 10.0,
                    "rates_bp": 15,
                    "spreads_bp": 35,
                    "usdcad_pct": -1.5,
                    "demand_pct": -1.5,
                    "tariff_pct": 0.0
                }
            },
            {
                "id": "japan-rate-spike",
                "name": "Japan interest rate spike",
                "group": "world",
                "note": "JGB yields jump and the yen carry trade unwinds; global term premium and spreads reprice.",
                "web_query": "Japanese government bond yields, Bank of Japan rate hikes, or yen carry trade unwinding",
                "channels": "Global term premium lifts rates, risk-off widens spreads, USD/CAD up, commodities soften.",
                "factors": {
                    "oil_pct": -6.0,
                    "gas_pct": 0.0,
                    "rates_bp": 45,
                    "spreads_bp": 50,
                    "usdcad_pct": 2.5,
                    "demand_pct": -1.0,
                    "tariff_pct": 0.0
                }
            },
            {
                "id": "extreme-weather",
                "name": "Extreme weather disruption",
                "group": "world",
                "note": "Hurricanes, wildfires or a severe winter shut in production and spike gas demand.",
                "web_query": "extreme weather such as hurricanes, wildfires, floods or cold snaps disrupting North American energy production or infrastructure",
                "channels": "Gas sharply higher, crude modestly higher on shut-ins, industrial activity and rail/logistics disrupted.",
                "factors": {
                    "oil_pct": 7.0,
                    "gas_pct": 28.0,
                    "rates_bp": 0,
                    "spreads_bp": 12,
                    "usdcad_pct": 0.0,
                    "demand_pct": -1.5,
                    "tariff_pct": 0.0
                }
            },
            {
                "id": "food-shortage",
                "name": "Global food supply shock",
                "group": "world",
                "note": "Crop failures and export bans push food inflation; fertiliser and diesel demand rise.",
                "web_query": "global food shortages, crop failures, grain export bans or food price inflation",
                "channels": "Food inflation keeps rates higher, gas (fertiliser feedstock) and diesel up, consumer demand squeezed.",
                "factors": {
                    "oil_pct": 6.0,
                    "gas_pct": 15.0,
                    "rates_bp": 30,
                    "spreads_bp": 20,
                    "usdcad_pct": 0.5,
                    "demand_pct": -2.0,
                    "tariff_pct": 0.0
                }
            },
            {
                "id": "pandemic",
                "name": "Deadly disease outbreak",
                "group": "world",
                "note": "A fast-spreading outbreak triggers travel curbs and a demand collapse; central banks ease.",
                "web_query": "deadly infectious disease outbreaks, epidemics or WHO public health emergency declarations",
                "channels": "Demand and crude collapse, spreads gap wider, rates rally hard, USD/CAD up on risk-off.",
                "factors": {
                    "oil_pct": -30.0,
                    "gas_pct": -10.0,
                    "rates_bp": -90,
                    "spreads_bp": 95,
                    "usdcad_pct": 5.0,
                    "demand_pct": -6.0,
                    "tariff_pct": 0.0
                }
            },
            {
                "id": "us-canada-tariffs",
                "name": "US-Canada tariff escalation",
                "group": "world",
                "note": "Broad US tariffs on Canadian goods with retaliation; CAD weakens and trade-exposed names re-rate.",
                "web_query": "United States tariffs on Canadian goods, Canada retaliatory tariffs, CUSMA/USMCA trade negotiations",
                "channels": "Tariff hits exporters' EBITDA, CAD weaker, cross-border demand softer, spreads wider, BoC leans dovish.",
                "factors": {
                    "oil_pct": -4.0,
                    "gas_pct": 0.0,
                    "rates_bp": -15,
                    "spreads_bp": 20,
                    "usdcad_pct": 3.0,
                    "demand_pct": -1.5,
                    "tariff_pct": 25.0
                }
            }
        ],
        "valuation": {
            "horizon_years": 3,
            "base_discount_rate_pct": 9.0,
            "cet1_ratio_pct": 11.5,
            "cost_of_equity_pct": 12.0,
            "lgd_pct": 40.0,
            "base_rate_bp": 550,
            "notch_per_turn": 3,
            "breach_extra_notches": 1,
            "max_notches": 3,
            "drawdown_trigger_ebitda_pct": -5.0,
            "drawdown_share_of_undrawn": 0.15,
            "revenue_elasticity_to_ebitda": 0.4,
            "markets_vol_uplift_per_pct_oil": 0.5,
            "pd_by_rating_pct": {
                "IG-1": 0.03,
                "IG-2": 0.05,
                "IG-3": 0.08,
                "IG-4": 0.12,
                "IG-5": 0.18,
                "IG-6": 0.27,
                "IG-7": 0.4,
                "IG-8": 0.6,
                "IG-9": 1.0,
                "IG-10": 1.8,
                "IG-11": 3.5,
                "IG-12": 7.0
            },
            "rw_by_rating_pct": {
                "IG-1": 20,
                "IG-2": 30,
                "IG-3": 40,
                "IG-4": 50,
                "IG-5": 60,
                "IG-6": 70,
                "IG-7": 85,
                "IG-8": 100,
                "IG-9": 115,
                "IG-10": 130,
                "IG-11": 150,
                "IG-12": 150
            }
        },
        "world_severity": {
            "dormant": 0.25,
            "low": 0.5,
            "elevated": 0.75,
            "high": 1.0,
            "severe": 1.3
        },
        "betas": {
            "CLI-1001": {
                "client_id": "CLI-1001",
                "client_name": "Gibson Energy Inc.",
                "beta_oil": 0.240845,
                "beta_gas": 0.0,
                "beta_fx": 0.3,
                "beta_demand": 0.2,
                "beta_tariff": -0.05,
                "floating_debt_share": 0.45,
                "business_model": "Fee-based midstream with a crude-marketing segment; USD-linked revenue.",
                "oil_shock_ebitda_pct": -3.0,
                "as_of_date": "2026-10-05"
            },
            "CLI-1002": {
                "client_id": "CLI-1002",
                "client_name": "Keyera Corp.",
                "beta_oil": 0.18169,
                "beta_gas": 0.3,
                "beta_fx": 0.2,
                "beta_demand": 0.3,
                "beta_tariff": -0.04,
                "floating_debt_share": 0.35,
                "business_model": "NGL midstream; frac spreads tie it to gas.",
                "oil_shock_ebitda_pct": -3.5,
                "as_of_date": "2026-10-05"
            },
            "CLI-1003": {
                "client_id": "CLI-1003",
                "client_name": "Whitecap Resources Inc.",
                "beta_oil": 1.057746,
                "beta_gas": 0.15,
                "beta_fx": 0.8,
                "beta_demand": 0.2,
                "beta_tariff": -0.12,
                "floating_debt_share": 0.5,
                "business_model": "Light-oil producer; USD-priced barrels, CAD costs.",
                "oil_shock_ebitda_pct": -14.5,
                "as_of_date": "2026-10-05"
            },
            "CLI-1004": {
                "client_id": "CLI-1004",
                "client_name": "Secure Waste Infrastructure",
                "beta_oil": 0.315493,
                "beta_gas": 0.2,
                "beta_fx": 0.2,
                "beta_demand": 0.8,
                "beta_tariff": -0.03,
                "floating_debt_share": 0.55,
                "business_model": "Energy services and waste; activity-linked.",
                "oil_shock_ebitda_pct": -5.0,
                "as_of_date": "2026-10-05"
            },
            "CLI-1005": {
                "client_id": "CLI-1005",
                "client_name": "Stella-Jones Inc.",
                "beta_oil": -0.015493,
                "beta_gas": 0.0,
                "beta_fx": 0.2,
                "beta_demand": 0.6,
                "beta_tariff": -0.35,
                "floating_debt_share": 0.4,
                "business_model": "Utility poles and rail ties; diesel and fibre inputs.",
                "oil_shock_ebitda_pct": 0.5,
                "as_of_date": "2026-10-05"
            },
            "CLI-1006": {
                "client_id": "CLI-1006",
                "client_name": "Russel Metals Inc.",
                "beta_oil": 0.311268,
                "beta_gas": 0.0,
                "beta_fx": 0.3,
                "beta_demand": 1.5,
                "beta_tariff": 0.06,
                "floating_debt_share": 0.6,
                "business_model": "Metals service centres with an energy-tubulars segment.",
                "oil_shock_ebitda_pct": -4.0,
                "as_of_date": "2026-10-05"
            },
            "CLI-1007": {
                "client_id": "CLI-1007",
                "client_name": "Cascades Inc.",
                "beta_oil": 0.012676,
                "beta_gas": -0.1,
                "beta_fx": 0.2,
                "beta_demand": 0.8,
                "beta_tariff": -0.25,
                "floating_debt_share": 0.5,
                "business_model": "Packaging and tissue; energy and fibre are inputs.",
                "oil_shock_ebitda_pct": 0.5,
                "as_of_date": "2026-10-05"
            },
            "CLI-1008": {
                "client_id": "CLI-1008",
                "client_name": "Ag Growth International Inc.",
                "beta_oil": 0.039437,
                "beta_gas": 0.0,
                "beta_fx": 0.4,
                "beta_demand": 1.2,
                "beta_tariff": -0.4,
                "floating_debt_share": 0.55,
                "business_model": "Agricultural equipment; farm-income cycle.",
                "oil_shock_ebitda_pct": 0.0,
                "as_of_date": "2026-10-05"
            },
            "CLI-1009": {
                "client_id": "CLI-1009",
                "client_name": "North West Company Inc.",
                "beta_oil": -0.049296,
                "beta_gas": 0.0,
                "beta_fx": -0.5,
                "beta_demand": 0.3,
                "beta_tariff": -0.02,
                "floating_debt_share": 0.3,
                "business_model": "Remote retail; imported goods, fuel and freight costs.",
                "oil_shock_ebitda_pct": 0.0,
                "as_of_date": "2026-10-05"
            },
            "CLI-1010": {
                "client_id": "CLI-1010",
                "client_name": "Superior Plus Corp.",
                "beta_oil": 0.023944,
                "beta_gas": 0.2,
                "beta_fx": 0.1,
                "beta_demand": 0.5,
                "beta_tariff": -0.08,
                "floating_debt_share": 0.45,
                "business_model": "Propane distribution; weather-driven volumes.",
                "oil_shock_ebitda_pct": -1.0,
                "as_of_date": "2026-10-05"
            }
        },
        "revolver_undrawn_m": {
            "CLI-1001": 69.0,
            "CLI-1002": 173.9,
            "CLI-1003": 54.0,
            "CLI-1004": 66.2,
            "CLI-1005": 22.7,
            "CLI-1006": 101.6,
            "CLI-1007": 39.8,
            "CLI-1008": 19.3,
            "CLI-1009": 43.5,
            "CLI-1010": 33.0
        }
    }
}
