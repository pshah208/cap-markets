# Capital Markets Client Intelligence — delivery app

A configurable web front end for the Foundry agent. Split-screen: a guided narrative on
the left, the live agent on the right, with the four Microsoft IQ layers lighting
up from the agent's **actual tool calls**.

> **SYNTHETIC DEMO DATA.** Your selected bank's name is a presentation label only. No client,
> exposure, limit, covenant, revenue or policy shown here reflects real bank
> information. Gibson Energy Inc. (TSX:GEI), Keyera Corp. and the other TSX-listed
> issuers named here are real public companies, named only so that live Web IQ
> grounding returns genuine public news; every internal figure is invented.

---

## Choose your bank first

Before running or deploying the UI, follow the [root README](../README.md). From the
standalone repository root:

```powershell
.\setup-bank.ps1 -BankName 'Example Bank' -BankShortName 'Example' -PrimaryColor '#164E63' -AccentColor '#B45309'
```

The narrative and agent responses refer to **the Bank**. Bank setup does not select
a tenant, grant permissions, seed data or provision cloud resources. Use the root
README for current local-run and deployment steps, configuration and governance checks.
This document describes the application modules, not a completed deployment.

## Why this exists (beyond looking better than the playground)

**1. Work IQ only works if the *user* is signed in.**
Work IQ is a delegated data source — it grounds on what the signed-in user can see.
If the app called the agent with its own managed identity, Work IQ would resolve
against an identity that is in no mailbox and no Teams channel, and return nothing.
So the browser signs the user in with MSAL, and the BFF performs an **On-Behalf-Of**
exchange before calling the agent. SSO here is a functional requirement, not
decoration.

**2. It keeps citation markers out of numbers.**
Inserting citation markers by character offset can corrupt digits inside numbers
and identifiers — for example, `92.9%` becoming `[14]2.9%` or `CP-005` becoming
`CP-[12]0[12]`. This demo depends on precise numbers. The app keeps answer text and its
citations strictly separate: text renders as-is, sources are listed underneath.
Numbers cannot be corrupted because nothing is ever substituted into the string.

**3. The IQ panel is evidence, not animation.**
The BFF polls the agent's run steps and classifies each tool call onto a layer, so
a card lighting up means that layer genuinely ran.

---

## The story it tells

Twelve chapters in `src/bff/app/story.json`, editable without touching code.

| # | Chapter | Layout | Shows |
|---|---|---|---|
| 01 | Thursday, 10:00, Calgary | persona | three business lines, one meeting, no reconciliation |
| 02 | The board, before anyone reasons over it | metrics | six governed indicators, every one green |
| 03 | Everything above is true. The conclusion is wrong. | reveal | the covenant and the Control Room are what bind |
| 04 | Four layers, one shared understanding | architecture | where each layer's evidence lives |
| 05 | How the pieces connect | diagram | SPA → BFF → OBO → agent → four layers |
| 06 | What the team already knows | Work IQ | Control Room reference `CR-2026-0184` |
| 07 | The number nobody checked | Fabric IQ | covenant 4.18x of 4.50x · 0.32 turns · 92.9% |
| 08 | The escape that is not one | Foundry IQ | CP-005 pro-forma · CP-008 restricted list |
| 09 | The one layer that is real | Web IQ | live ratings and news, cited and dated |
| 10 | The question that decides the meeting | all four | the trap, and the correct refusal |
| 11 | What just happened | reveal | search tool vs grounded agent |
| 12 | What it costs to run | telemetry | Foundry-traced tokens + actual Azure bill |

Chapter 12 is the only slide whose numbers are not authored — and none of them
are produced by this app. The Foundry project writes OpenTelemetry gen-AI spans
to the Application Insights component connected to it, and `src/bff/app/telemetry.py`
reads them back out of the Log Analytics workspace (`GET /api/metrics/agent`):
`invoke_agent` gives one row per question with its duration and outcome, its
`chat` child carries `gen_ai.usage.input_tokens` / `output_tokens`, and its
`execute_tool` children say which IQ layers were reached. Nothing is
synthesised: if the traces cannot be read the slide says so and shows an empty
state. The single derived figure is **cost** — measured tokens at list price,
labelled as an estimate and overridable with `TOKEN_PRICE_INPUT_PER_1K` /
`TOKEN_PRICE_OUTPUT_PER_1K`. Application Insights ingests a span a minute or two
after the run, so the slide also reports how many runs the BFF has served that
the traces have not caught up with yet.

Required for the slide: `LOG_ANALYTICS_WORKSPACE_ID` (the workspace customer id)
and Monitoring Reader for the app's managed identity on that workspace — both
wired by `infra/main.bicep`. `TELEMETRY_WINDOW_DAYS` (default 7) sets the window.

### Token cost is not the whole bill

The same slide also shows **what Azure actually charged**, from Cost Management
(`src/bff/app/cost.py`), grouped by resource and split into *provisioned* versus
*metered*, when your configured scope and permissions allow retrieval.

AI Search capacity, Fabric capacity and application hosting can incur costs
independently of how many questions the agent answers. The panel distinguishes
all-in cost per question from token-only estimates. There is no reusable invoice
or guaranteed cost ratio: use your own measured usage, billing scope and prices.

Needs `COST_SCOPE` (the resource group id) and Cost Management Reader on that
scope; `COST_WINDOW_DAYS` defaults to 30. Results are cached for an hour and
stale-served on failure, because the Cost Management query API is aggressively
rate limited. Two things make that reliable and are easy to get wrong:

* **Send a distinctive `User-Agent`.** Client-type quota buckets can be shared;
  identifying the client helps distinguish its requests but does not guarantee
  quota or a successful response.
* **Read the cooldown from `x-ms-ratelimit-microsoft.costmanagement-*retry-after`**,
  not just `Retry-After`. The client-type bucket asks for ~30 seconds; assuming
  a flat five minutes blanks the panel for ten times longer than necessary.

Chapters 02 and 03 are the device the whole demo turns on. **02 lets the audience
form a conclusion** from six correct, green indicators — the single-name limit is
68.3% used with CAD 158.3m of headroom against a 45m ask, so of course we can take
the hold from 165 to 210. **03 takes it away**: the binding constraints are the
Total Net Debt / Adjusted EBITDA covenant at 4.18x of a 4.50x maximum — 0.32 turns,
92.9% utilised and *deteriorating* from 3.94x — the Energy sector envelope at 85.8%
amber, and an open Control Room restriction, `CR-2026-0184`, that two of the four
meeting attendees are subject to. Nobody in the room checked any of them, and
neither does a naive agent.

The MNPI dimension is what makes this demo different from a pure limits story: the
agent must reason about a constraint that lives in nobody's limit system, and must
not leak wall-crossed context to a public-side user. In live mode, On-Behalf-Of
passes the signed-in banker's identity downstream. Information barriers still
require correctly configured source permissions; neither a prompt nor a role
label establishes that those permissions have been enforced.

Each IQ chapter carries an **Ask the agent →** button that sends its prompt to the
live agent, plus a *what a good answer contains* checklist so the audience knows
what to look for.

The left panel is deterministic and the right is live — so if the agent has an off
moment, the story still lands. Arrow keys move between chapters.

---

## Dashboard: agent vs API

The Dashboard's numbers (exposure, limits, covenants, the shocked covenant, pro-formas, wallet share) are
deterministic and labelled as such. The "Snapshot lookup" panel and the recorded evidence cards are lookups,
not an agent. What an API cannot do is reconcile the business lines, so the Selected relationship view runs
**agent missions** (`cm_missions.py`, `/api/missions/*`) for Prepare briefing, Explore opportunities and
Review risks. "Explain maturities" stays a lookup.

| Step | What runs |
|---|---|
| Governed packet | the client's figures + each business line's stance (`line_positions`, Fabric IQ) + the rules view |
| Agent | `cm-mission-agent` (Work, Foundry, Web, Fabric IQ), with every tool call traced |
| Guardrails | code: figures traced, CP ids exist, no autonomous action, layers used, no barrier/internal content, commitments or wall-crossed names in client text, no restricted subject for CR-2026-0184 |
| Review | `cm-barrier-reviewer` (CP-008/009/010/014/017) over any client text |
| Decision | the banker approves, sends back or escalates; one `MISSION_AUDIT {json}` line per decision |

The table's **Business lines** column flags clients whose lines disagree. The **Agent changed the answer** KPI
counts decided missions whose call differed from the rules view, read from Log Analytics
(`ContainerAppConsoleLogs_CL`), so it is correct across replicas.

Data: repository-root `data/mission_data.py` writes `line_positions.csv` (Fabric), `line_data.py` (BFF), `mission_emails.json`
(Work IQ - seed with `data/work-iq/seed_mission_mail.py`) and CP-016 / CP-017 (Foundry IQ). Agents:
[agent definitions](../agent/cm_agents.md) and `agent/create_cm_agents.py`.
Use the root README before provisioning, seeding or changing agents.

---

## Architecture

```
Browser (React + MSAL)
  │  access token for api://<bff>/access_as_user
  ▼
Web container app   nginx + SPA        EXTERNAL ingress
  │  /api proxied inside the Container Apps environment
  ▼
BFF container app   FastAPI            INTERNAL ingress only
  │  On-Behalf-Of exchange -> token for Foundry, as the user
  ▼
Foundry agent (your configured project)
  ├─ Work IQ     6× agent365 MCP connections   as the user
  ├─ Fabric IQ   your semantic model          as the user
  ├─ Foundry IQ  your policy knowledge base   AI Search
  └─ Web IQ      bing_grounding / web_search   live, no cache
```

In this topology the BFF has no direct public ingress; the web container proxies
`/api` requests to it. Authentication remains mandatory on those routes, and the
BFF secret must stay server-side. Same-origin proxying avoids browser CORS setup.

### Work IQ: managed connections, not A2A

Work IQ is wired as **six per-service managed MCP connections** — `WorkIQMail`,
`WorkIQTeams`, `WorkIQSharePoint`, `WorkIQOneDrive`, `WorkIQWord`,
`WorkIQCopilot` — all targeting `agent365.svc.cloud.microsoft` with
`UserEntraToken`.

Deliberately **not** the single `WorkIQ` **RemoteA2A** tool. That one targets
`workiq.svc.cloud.microsoft/a2a/`, which is **metered against Copilot Credits**
and can return `NoPolicy` if the tenant lacks the required usage-based billing
configuration for that user. Verify licensing, billing and service availability
for your environment; the connection choice alone does not establish entitlement.

### Operational scripts

| Script | Use |
|---|---|
| `push_agent_instructions.py` | synchronise the portal instruction source; verify it is present before testing the reasoning scenario |
| `set_tool_allowlist.py` / `set_tool_autoapprove.py` | configure tool exposure and approval behaviour; review the allow-list and approval policy before any change |
| `diag_fabric.py` | query the semantic model directly, bypassing Foundry, to prove whether a Fabric IQ failure is the model or the capacity. |
| `diag_workiq.py` | call the Work IQ A2A endpoint directly to see the real error behind Foundry's generic wrapper. |

These scripts live at the repository root. Consult the root README and their current
help before use. Listing a script here does not approve its execution or tool access.

---

## Layout

```
app/
├── deploy.ps1                      build → push → deploy
├── infra/
│   ├── provision_app_registrations.py   SPA + BFF Entra registration helper
│   ├── main.bicep
│   └── modules/  registry · observability · container-apps
└── src/
    ├── bff/          FastAPI
    │   └── app/  main.py · auth.py (OBO) · agent_client.py · iq.py · telemetry.py · story.json
    └── web/          React + Vite + MSAL
        ├── public/brand/  locally configured presentation assets
        └── src/  App.tsx · api.ts · auth.ts · styles.css · types.ts
                   components/  StoryPanel · ChatPanel · IQPanel · Markdown
```

---

## Setup

### Local preview and live configuration

After bank setup, follow the [root README](../README.md) for the current commands.
For live OBO, the architecture requires a public SPA client and a confidential
BFF registration. The BFF performs the token exchange using server-side credentials;
the browser must never receive its secret. Configure your own tenant, client IDs,
API scope, Foundry project endpoint and agent name. Administrative consent and
downstream access must be verified in your environment, not assumed.

Sign in with your locally mapped **Coverage Lead** test account for the guided
scenario, or another mapped persona to test its authorised view. No user or
permission is pre-provisioned by these docs.

**UI work without Azure:** the root README describes a local-only `MOCK_MODE=true`
preview with synthetic responses. It bypasses authentication and must not be used
for a shared deployment or as proof of live connectivity or security trimming.

### Dashboard workspace

The **Dashboard** workspace includes an offline synthetic portfolio snapshot.
Guided provides the narrative; Explore retains the live conversation. Snapshot
lookups are deterministic, while the agent missions described above require live
configuration. Company selections, filters, drafts and
per-company local conversations survive workspace toggles (not page reloads).
Collapse the chat for a full-width portfolio; use the divider's arrow keys,
Home/End or Enter to resize/reset it. `?scoutTheme=light` or `dark` overrides the
system theme for the dashboard only.

Amounts are **CAD millions**, with FY26 YTD relationship revenue, estimated
wallet shares, and facility-amount maturity buckets—not issuer-wide debt.
Unavailable evidence and source mismatches are disclosed. No live news or M365
retrieval is implied. From the project root, regenerate/verify the snapshot with
`python data\generate_dashboard_snapshot.py` / the same command plus `--check`.
From `app\src\web`, run `node --test dashboard.test.mjs` and `npm run build`.
No Azure access is needed to inspect the local synthetic snapshot.

### Deploy to Azure

Use the root README for full deployment steps and the required governance review.
The application deployment modules cover the registry, observability, container
apps and identity integration; root infrastructure covers the data and agent services.
Supply your own approved targets, secrets and redirect URIs. Verify health,
authentication, source permissions and telemetry after deployment; this document
does not attest that any of them have succeeded.

---

## Who can sign in

Authentication depends on your app registration, assignment and tenant policies;
what users *see* is governed by downstream sources under their own identity.
Map the five personas to authorised test accounts. The story adapts to the role —
`personaByRole` in `story.json` reframes the goal and objectives for Coverage, Corporate Banking,
Global Markets, Credit Risk and Research.

| Persona | Role claim | Wall status |
|---|---|---|
| Coverage Lead — Corporate Coverage, Energy (driver) | `Coverage` | public side |
| Corporate Banking Lead — Corporate Banking & DCM | `CorporateBanking` | **wall-crossed** |
| Markets Lead — Commodities & FX Sales | `GlobalMarkets` | public side |
| Credit Risk Lead — Credit Risk, Energy | `CreditRisk` | **wall-crossed** |
| Research Analyst — Equity Research | `Research` | public side |

Use separately permissioned Corporate Banking Lead and Coverage Lead test accounts
to compare answers about `CR-2026-0184`. A persona label alone is not an information
barrier; verify source permissions and OBO before presenting this as security trimming.

| Access | Why |
|---|---|
| Azure AI User on your configured Foundry resource | invoke the agent |
| Search Index Data Reader for the configured retrieval identity | Foundry IQ retrieval |
| Workspace and semantic-model permissions in your Fabric workspace | Fabric semantic model |
| Recipient on the seeded emails | Work IQ mail grounding |
| Member of *Capital Markets - Gibson Energy Coverage* | Work IQ document grounding |

Missing source access can produce a thinner answer or a permission error. Test both
cases explicitly; missing evidence must not be silently replaced with invented facts.

---

## Troubleshooting

Sign in, switch to **Explore**, open **Connection diagnostics → Run checks**. It
walks token → OBO → agent and reports the first failure, which is the actionable
one. Or call `GET /api/diag` directly.

| Symptom | Likely cause |
|---|---|
| `AADSTS65001` on the OBO exchange | check the BFF's delegated downstream scopes and administrator consent, independently of SPA consent; use the root README's identity setup and have an authorised administrator review the failure |
| *"The agent ran but returned no answer"* naming a failed tool | that connection failed for this user. The detail line carries the server label and the service's own error. |
| Agent answers "yes, 158.3m of headroom" | inspect instructions and tool traces: it may have ignored the covenant or restriction; compare the deployed prompt with the repository instruction source |
| The agent appears to hang, no error | inspect run steps for `mcp_approval_request`; review tool approval handling and the allow-list rather than disabling approvals indiscriminately |
| `GetSemanticModelSchema: Power BI couldn't process that request right now`, or a 429 | inspect Fabric capacity and query diagnostics for throttling; `diag_fabric.py` bypasses Foundry to help isolate the failure |
| Work IQ: `NoPolicy` / *"AI credits access is not configured for this user"* | check the selected connection type, licensing and billing policy for your user; `diag_workiq.py` can expose the underlying A2A error |
| Work IQ: *"Response size exceeds the maximum allowed size of 51200 bytes"* | the tool works — the query was too broad. Harmless; the agent usually narrows and retries. |
| Web IQ quotes *"indicative — verify via Web IQ"* as a rating | Bing grounding is not attached. That string is a deliberately unusable internal placeholder. |
| Work IQ returns nothing, other layers fine | check the signed-in test user's mailbox contents and coverage-team document access; an administrator account is not automatically a recipient of seeded mail |
| Work IQ fails right after a UPN or primary-SMTP change | the substrate and Microsoft Search index are keyed on the user's address. Sign in once to Outlook on the web **and** Teams, then allow the re-crawl to finish. |
| Fabric IQ empty | check whether your capacity is active and the user has the semantic-model permissions required by the connector, including Build where required; do not assume a workspace role alone supplies them |
| IQ cards never light up | SSE is being buffered. Confirm `proxy_buffering off` in `default.conf.template`. |
| All four cards light up on every question | a discovery event is being counted as an invocation. `_IGNORED` in `iq.py` must exclude `mcp_list_tools` and `mcp_approval_request`. |
| Agent repeats wall-crossed detail to a public-side user | inspect source permissions and OBO token exchange; a prompt is not an access control. Confirm there is no managed-identity fallback (`ALLOW_APP_IDENTITY_FALLBACK=false`) and separately verify source-level information barriers. |
| Sign-in loops | compare the current origin with the registered redirect URIs and review identity configuration in the root README |
| `Agent not found` | compare `FOUNDRY_AGENT_NAME` with the actual agent name in your configured project |

**A single failing tool aborts the whole answer**, rather than degrading to the
other three layers. The BFF therefore retries transient failures (throttling,
429, 503) up to twice with backoff, buffering frames per attempt so a retry never
leaves half an answer on screen. Permanent failures — 403, `Agent not found` —
are reported immediately rather than retried.

An empty answer is never rendered as silence: if the agent produces no text the BFF
emits an `error` frame explaining why, and `done` carries a `toolErrors` array.

---

## Teardown

Follow the root README and your organisation's approved cleanup process. Inventory
the resources, app registrations, seeded test content and identity grants owned by
this deployment before removing anything; shared resources must not be removed.
Deleting an ARM deployment record does not delete the resources it created.
Provisioned capacity and minimum replicas may continue to incur charges until
explicitly stopped or removed.
