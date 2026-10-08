# Synthetic dataset — Capital Markets Client Intelligence Agent

> ⚠️ **Everything internal in this dataset is synthetic.** Your selected bank's name is used
> only as a presentation label. Gibson Energy Inc. and the other TSX-listed issuers named
> are **real public companies**, used *only* so that the Web IQ layer's live web grounding
> returns genuine public news. Every exposure, commitment, limit, revenue figure,
> wallet-share estimate, internal risk rating, covenant, trade, colleague, email, Teams
> message, meeting and internal policy in this dataset was generated for a demonstration and
> reflects no real institution, client relationship, credit position or compliance matter.
> Regulatory instruments (OSFI B-3/B-7/B-8/B-15/E-21, NI 31-103, NI 51-102, CIRO rules,
> PCMLTFA/FINTRAC) are real and are cited **by name only**; the policy text around them is
> invented. Do not present any of this as real bank or client information.

---

## Choose your bank first

Before running or deploying the UI, follow the [root README](../README.md). From the
standalone repository root, configure your selected bank:

```powershell
.\setup-bank.ps1 -BankName 'Example Bank' -BankShortName 'Example' -PrimaryColor '#164E63' -AccentColor '#B45309'
```

Bank setup changes presentation, not these synthetic facts, identity mappings or permissions.
The narrative refers to **the Bank**. The root README is the source for current setup and
deployment steps; no tenant, subscription, capacity, licence or approval is supplied here.

## The scenario

**The Bank**, as at **5 October 2026**. A coverage team is preparing for an
**8 October CFO / Treasurer meeting** with **Gibson Energy Inc. (TSX:GEI)** — a real Calgary
midstream issuer — to discuss three things: a revolver upsize from CAD 1.10bn to CAD 1.35bn,
a commodity and FX hedging overlay, and positioning for a 2027 refinancing.

> **Re-dated.** The scenario was moved forward 56 days (weekday-preserving) from an
> original 10 August 2026 as-at date. Financial period ends (LTM to 2026-06-30, covenant
> test dates, quarterly rating reviews), policy effective dates and contract maturities
> were deliberately kept. The CP-005 pro-forma is consistent across every layer: the full
> CAD 1.35bn upsize is **4.59x against 4.50x — a breach**; the largest increase that clears
> fully drawn is CAD 195.8m. Teams posts dated after the seeding moment are compressed to
> just before "now" by the migration workflow, because Graph rejects future timestamps.
> Review the current seeder options and root README before importing any content.

The demo answers the five questions the persona actually has:

| Question | Layer | Tool |
|---|---|---|
| What is happening with the client **externally**? | **Web IQ** | `research_client_external_intelligence` (live) |
| What **internal relationship history** exists? | **Work IQ** | `search_client_relationship_history` |
| What **exposure, revenue, limits and risk** do we have? | **Fabric IQ** | `query_client_exposure_analytics` |
| What **policies and constraints** apply? | **Foundry IQ** | `lookup_capital_markets_policy` |
| What is the **recommended next action**? | all four, reconciled | — |

### Role-aware views

One agent, four lenses. Same grounded facts, different lead section and next-action bias.

| Role | Leads with | Next-action bias |
|---|---|---|
| Relationship Manager | wallet share, revenue, whitespace, relationship map | pitch, cross-sell, agenda ownership |
| Trader | derivative positions, margin/collateral, market moves | pricing and execution readiness |
| Research Analyst | earnings, guidance, sector comps, thesis drivers | note or thesis update |
| Credit / Risk | exposure, limits, covenants, rating trend | limit action, covenant test, escalation |

### The tension the agent must surface, not resolve

A live (synthetic) restriction — **CR-2026-0184** — sits on the name. Two of the four
meeting attendees are wall-crossed. Web IQ returns genuinely public news that supports the
pitch; Foundry IQ returns CP-008, which says whether a pitch touches the restricted subject
matter is the **Control Room's** determination, not the business's.

A good answer uses the public news *and* repeats the caveat. An answer that uses the news to
argue the restriction does not apply has failed the demo.

---

## Layout

```
data/
├── scenario_facts.py          ← SINGLE SOURCE OF TRUTH for every figure
├── validate_dataset.py        ← cross-layer consistency checks
├── fabric-iq/                 Microsoft Fabric — OneLake lakehouse
│   ├── generate_fabric_data.py    deterministic, re-runnable, self-reconciling
│   ├── clients.csv                10 real TSX mid-caps, synthetic attributes
│   ├── coverage_team.csv          50 rows — who covers whom, incl. wall status
│   ├── credit_facilities.csv      32 facilities — commitment, drawn, maturity, role
│   ├── exposures.csv              52 rows — funded, contingent, derivative MTM + PSE
│   ├── limits_utilization.csv     14 limits — single-name, PSE, tenor, underwriting, sector
│   ├── revenue_by_product.csv     72 rows — FY26 YTD vs FY25, by product
│   ├── wallet_share.csv           47 rows — the Bank vs estimated street wallet, rank, whitespace
│   ├── trades.csv                 59 trades — 12-month blotter
│   ├── covenants.csv              24 covenants — threshold, actual, headroom, band
│   └── risk_ratings.csv           44 rows — 8-quarter internal rating trend
├── foundry-iq/                Azure AI Search knowledge index
│   └── cm_policies.json           14 documents, CP-001 … CP-014
├── work-iq/                   Microsoft 365 — Exchange, Teams, SharePoint
│   ├── user_mapping.json          5 synthetic personas; explicit local account mapping required
│   ├── emails.json                30 emails (22 CLI-1001, 4 CLI-1002, 4 CLI-1007), 5 personas, 5 categories
│   ├── teams_messages.json        1 team, 4 channels, 13 threads, 32 replies
│   ├── meetings/                  5 records — call report, minutes ×3, transcript
│   └── files/                     pre-meeting brief + pitch book v3 extract
└── web-iq/                    LIVE ONLY — no cache, by design
    ├── web_iq_queries.json        8 topics, role-mapped query templates
    └── README.md                  wiring, guardrails, cost note
```

---

## Everything reconciles — and that is enforced

The whole value of this dataset is that a number quoted in an email matches the Fabric
table, which matches the policy threshold, which matches the meeting minutes. `scenario_facts.py`
is the single source of truth; the generators derive from it and `validate_dataset.py`
proves it.

```powershell
# From the standalone repository root
Set-Location data
python fabric-iq\generate_fabric_data.py --check   # regenerate + self-reconcile
python validate_dataset.py                      # cross-layer checks
```

**Never hand-edit a generated CSV.** Change `scenario_facts.py` and re-run.

The spine of pinned figures every layer must agree on:

| Figure | Value |
|---|---|
| Total committed / drawn / exposure | CAD 465.0m / 288.4m / **341.7m** |
| Single-name limit · utilisation | CAD 500.0m · **68.3% GREEN** |
| Derivative PSE line | CAD 90.0m · 69.2m used · **76.9% AMBER** (75% trigger, CP-004) |
| Energy sector concentration | CAD 2,744m of 3,200m · **85.8% AMBER** |
| FY26 YTD revenue vs prior | CAD 8.42m vs 7.14m · **+17.9%** |
| Wallet share · rank | **21.4%** (from 18.9%) · **2nd** (from 3rd) |
| Tightest covenant | Net debt/EBITDA **4.18x of 4.50x · 0.32 turns · TIGHT** |
| Internal rating | **IG-6** improving (IG-7 two quarters ago) |
| Revolver upsize | CAD 1.10bn → **1.35bn**, hold 165m → **210m** |
| KYC refresh due | **25 November 2026** — no grace period (CP-006) |
| Restriction | **CR-2026-0184**, expected expiry 10 Nov 2026 |

---

## Feed plan — how each dataset reaches its system

### Work IQ → Microsoft 365

Choose a dedicated demo tenant and map the five synthetic personas to licensed test
accounts you are authorised to use. No shipped persona is an existing user or proof of
access. The **Coverage Lead** is the driver; Work IQ sees only that signed-in user's
authorised mailbox, Teams and document content.

| Persona | Role view | Wall status |
|---|---|---|
| Coverage Lead — Corporate Coverage, Energy | relationship_manager · **driver** | public side |
| Corporate Banking Lead — Corporate Banking & DCM | relationship_manager | **wall-crossed** |
| Research Analyst — Equity Research, Energy Infrastructure | analyst | public side |
| Markets Lead — Commodities & FX Sales | trader | public side |
| Credit Risk Lead — Credit Risk, Energy | credit_risk | **wall-crossed** |

> Keep real UPNs and object IDs in your untracked local mapping. Review the seeder's
> planned account changes and preserve any restore snapshot securely. Do not seed
> production mailboxes or reuse accounts from unrelated demonstrations.

| Artifact | Target | Graph mechanism |
|---|---|---|
| `emails.json` | each persona's Inbox | `POST /users/{id}/messages` preserving original sender + `sentDateTime`, then move to Inbox. The **driver is cc'd on every message** — Work IQ only grounds on what the signed-in user can access. |
| `teams_messages.json` | team + 4 channels | `POST /teams` → `/channels` → `/messages` (+ `/replies`) |
| `meetings/*.md` | team SharePoint → `Meeting Notes/` | `PUT /drives/{id}/root:/…:/content` |
| `files/*.md` | team SharePoint → `Client Files/` | same upload path |
| `user_mapping.json` | Entra directory | `PATCH /users/{id}` jobTitle + department; originals snapshotted first |

> ⚠️ Teams posting and migration require the appropriate Microsoft Graph permissions and
> supported authentication flow. Follow the root README and review the seeder's current
> options with your administrator. No application permission, migration permission or
> delegated consent is implied by this dataset.

**Non-account voices** (Control Room, Syndicate desk, KYC Ops, the client's CFO and
Treasurer) appear in body text and attendee lists only. They have no mailbox and are never
seeded as senders.

### Fabric IQ → Microsoft Fabric

Use your own approved, active Fabric capacity and workspace. The data-loading modules
describe a lakehouse and a semantic model; their names and deployment targets must come
from your local configuration, not a previous demonstration.

1. CSVs uploaded to OneLake `Files/client-intel/` via the ADLS Gen2 API.
2. Notebook `nb_load_client_intel` → 10 base + curated Delta tables.
3. Notebook `nb_create_semantic_model` → Direct Lake model `sm_client_intel` with
   relationships on `client_id` / `product_id` and measures for exposure, utilisation,
   revenue, YoY, wallet share and covenant headroom.

### Foundry IQ → Azure AI Search

`cm_policies.json` → index **`cm-client-policies`** (`index_cm_policies.py`). Fields:
`id`, `title`, `category`, `effective_date`, `owner`, `applies_to`, `regulatory_anchor`,
`content`. Semantic ranking on `title` + `content`; `category` is filterable.

### Web IQ → live grounding

**No data is seeded.** A Grounding-with-Bing connection on the Foundry project. If absent,
the tool returns `{"status":"unavailable"}` and the agent says so rather than inventing
external facts about a real company. See [`web-iq/README.md`](web-iq/README.md).

---

## Deployment targets you must supply

| Item | Required choice |
|---|---|
| Subscription and tenant | Your authorised environment; keep identifiers in local configuration |
| Resource group and regions | Your naming rules and approved regions |
| Foundry | Your account, project, model deployment and connections |
| AI Search | Your search service and policy index |
| Fabric capacity and workspace | Your approved SKU, active capacity and workspace access |
| Microsoft 365 | Dedicated test users, mailboxes and a demo coverage team |

Complete the root README's governance and permission checks before provisioning or
seeding. This document describes the data flow, not a successful deployment or approval.

---

## Changing the scenario

Everything keys off `scenario_facts.py`:

- **Different hero client** — change `hero_client_name` / `hero_ticker` and the first entry
  in `CLIENTS`. Web IQ query templates substitute `{client}` and `{ticker}` automatically.
  Pick a **real** listed company or live grounding returns nothing.
- **Different figures** — edit `FACTS["hero_metrics"]`, re-run the generator, then fix the
  narrative text `validate_dataset.py` flags as no longer matching.
- **Different people** — edit `PEOPLE` and `user_mapping.json` together; validation asserts
  they agree. Keep role names synthetic and review your local account mapping before
  seeding; dataset validation does not grant permission to modify a tenant.
