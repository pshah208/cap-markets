# BMO Capital Markets Client Intelligence — delivery app

A branded web front end for the Foundry agent. Split-screen: a guided narrative on
the left, the live agent on the right, with the four Microsoft IQ layers lighting
up from the agent's **actual tool calls**.

> **SYNTHETIC DEMO DATA.** BMO Capital Markets is a branding label only. No client,
> exposure, limit, covenant, revenue or policy shown here reflects real BMO
> information. Gibson Energy Inc. (TSX:GEI), Keyera Corp. and the other TSX-listed
> issuers named here are real public companies, named only so that live Web IQ
> grounding returns genuine public news; every internal figure is invented.

---

## Why this exists (beyond looking better than the playground)

**1. Work IQ only works if the *user* is signed in.**
Work IQ is a delegated data source — it grounds on what the signed-in user can see.
If the app called the agent with its own managed identity, Work IQ would resolve
against an identity that is in no mailbox and no Teams channel, and return nothing.
So the browser signs the user in with MSAL, and the BFF performs an **On-Behalf-Of**
exchange before calling the agent. SSO here is a functional requirement, not
decoration.

**2. It fixes the citation corruption.**
The Foundry playground splices citation markers into the answer by character
offset, which mangles digits inside numbers and identifiers — `92.9%` renders as
`[14]2.9%`, `CP-005` as `CP-[12]0[12]`. That is fatal for this demo, where the
whole point is a set of precise numbers. This app keeps the answer text and its
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
to the Application Insights component connected to it, and `app/telemetry.py`
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

### Tokens are the small half of the bill

The same slide also shows **what Azure actually charged**, from Cost Management
(`app/cost.py`), grouped by resource and split into *provisioned* versus
*metered*. This matters because on this workload the token bill is not the cost:

| | 30-day actual |
|---|---|
| Azure AI Search (Basic, the Foundry IQ index) | ~72% of the invoice |
| Azure AI Foundry (tokens) | ~12% |
| everything else (Container Apps, ACR, Log Analytics) | ~16% |

AI Search is provisioned capacity billed by the hour, so it costs the same
whether the agent answers nine questions or nine thousand. Roughly **88% of the
bill is fixed**, which is why the panel reports an all-in cost per question
(~45x the token cost at demo volume) and notes that this figure *falls* as
adoption rises while token cost per question stays flat.

Needs `COST_SCOPE` (the resource group id) and Cost Management Reader on that
scope; `COST_WINDOW_DAYS` defaults to 30. Results are cached for an hour and
stale-served on failure, because the Cost Management query API is aggressively
rate limited. Two things make that reliable and are easy to get wrong:

* **Send a distinctive `User-Agent`.** Cost Management meters one quota bucket
  per *client type*. Callers that do not identify themselves share a single
  `DefaultQuota` bucket that unrelated tools in the tenant routinely exhaust —
  the same request returns 429 without a custom agent and 200 with one.
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
not leak wall-crossed context to a public-side user. Because every call runs
On-Behalf-Of the signed-in banker, that trimming is enforced by the sources
themselves rather than by the prompt.

Each IQ chapter carries an **Ask the agent →** button that sends its prompt to the
live agent, plus a *what a good answer contains* checklist so the audience knows
what to look for.

The left panel is deterministic and the right is live — so if the agent has an off
moment, the story still lands. Arrow keys move between chapters.

---

## Architecture

```
Browser (React + MSAL)
  │  access token for api://<bff>/access_as_user
  ▼
ca-cmci-web   nginx + SPA        EXTERNAL ingress
  │  /api proxied inside the Container Apps environment
  ▼
ca-cmci-bff   FastAPI            INTERNAL ingress only
  │  On-Behalf-Of exchange -> token for Foundry, as the user
  ▼
Foundry agent (proj-client-intelligence)
  ├─ Work IQ     6× agent365 MCP connections   as the user
  ├─ Fabric IQ   smclientintel              as the user
  ├─ Foundry IQ  kb-knowledgebase201           AI Search
  └─ Web IQ      bing_grounding / web_search   live, no cache
```

The BFF is never exposed publicly. That keeps its client secret off the internet
and removes CORS from the picture.

### Work IQ: managed connections, not A2A

Work IQ is wired as **six per-service managed MCP connections** — `WorkIQMail`,
`WorkIQTeams`, `WorkIQSharePoint`, `WorkIQOneDrive`, `WorkIQWord`,
`WorkIQCopilot` — all targeting `agent365.svc.cloud.microsoft` with
`UserEntraToken`.

Deliberately **not** the single `WorkIQ` **RemoteA2A** tool. That one targets
`workiq.svc.cloud.microsoft/a2a/`, which is **metered against Copilot Credits**
and returns `NoPolicy` unless the tenant has a usage-based billing policy with
the user assigned to it. The managed connections are not metered.

### Operational scripts

| Script | Use |
|---|---|
| `push_agent_instructions.py --apply` | push `agent_instructions.portal.md` onto the agent. A portal-built agent starts with **empty instructions** and will fail the trap. |
| `set_tool_autoapprove.py --apply` | set `require_approval: never` on every MCP tool. Portal-added connections default to requiring a human approval that an API call can never supply — the run just appears to hang. **Re-run after adding any connection.** |
| `diag_fabric.py` | query the semantic model directly, bypassing Foundry, to prove whether a Fabric IQ failure is the model or the capacity. |
| `diag_workiq.py` | call the Work IQ A2A endpoint directly to see the real error behind Foundry's generic wrapper. |

---

## Layout

```
app/
├── deploy.ps1                      build → push → deploy
├── infra/
│   ├── provision_app_registrations.py   SPA + BFF Entra apps (run first)
│   ├── main.bicep · main.json
│   └── modules/  registry · observability · container-apps
└── src/
    ├── bff/          FastAPI
    │   └── app/  main.py · auth.py (OBO) · agent_client.py · iq.py · telemetry.py · story.json
    └── web/          React + Vite + MSAL
        ├── public/brand/  cm-logo · cm-logo-white · cm-lockup · favicon
        └── src/  App.tsx · api.ts · auth.ts · styles.css · types.ts
                   components/  StoryPanel · ChatPanel · IQPanel · Markdown
```

---

## Setup

### 1. Entra app registrations

Two apps are required for OBO — a public SPA client and a confidential BFF that
holds the secret and performs the exchange.

```powershell
cd app
pip install azure-identity requests
az login          # as an Application Administrator

python infra\provision_app_registrations.py --spa-redirect http://localhost:5173
```

It prints the BFF secret **once**. The script also pre-consents the delegated
scopes, so users are not prompted.

### 2. Run locally

```powershell
# BFF
cd src\bff
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

$env:AAD_TENANT_ID     = "<tenant>"
$env:AAD_CLIENT_ID     = "<bff-client-id>"
$env:AAD_CLIENT_SECRET = "<secret>"
$env:AAD_API_SCOPE     = "api://<bff-client-id>/access_as_user"
$env:FOUNDRY_PROJECT_ENDPOINT = "https://cmintel-foundry.services.ai.azure.com/api/projects/proj-client-intelligence"
$env:FOUNDRY_AGENT_NAME = "<the agent you built in the portal>"
uvicorn app.main:app --reload --port 8000
```

```powershell
# SPA (second terminal)
cd src\web
npm install
"VITE_AAD_TENANT_ID=<tenant>`nVITE_AAD_CLIENT_ID=<spa-client-id>`nVITE_API_SCOPE=api://<bff-client-id>/access_as_user" | Set-Content .env
npm run dev
```

Open <http://localhost:5173> and sign in as
**`SydneyM@M365CPI65678641.OnMicrosoft.com`** (Sydney Mattos, MD Corporate
Coverage — Energy) — the driver persona whose mailbox, Teams membership and
Fabric access the demo data was seeded against.

**UI work without Azure:** set `MOCK_MODE=true` on the BFF and omit the `VITE_*`
values. Auth is bypassed and canned answers are returned.

### Dashboard workspace

The **Dashboard** workspace is a separate, offline synthetic portfolio cache.
Guided remains the default; Explore retains the live conversation. Dashboard
questions never call the chat API. Company selections, filters, drafts and
per-company cached conversations survive workspace toggles (not page reloads).
Collapse cached chat for a full-width portfolio; use the divider's arrow keys,
Home/End or Enter to resize/reset it. `?scoutTheme=light` or `dark` overrides the
system theme for the dashboard only.

Amounts are **CAD millions**, with FY26 YTD relationship revenue, estimated
wallet shares, and facility-amount maturity buckets—not issuer-wide debt.
Unavailable evidence and source mismatches are disclosed. No live news or M365
retrieval is implied. From the project root, regenerate/verify the cache with
`python data\generate_dashboard_snapshot.py` / the same command plus `--check`.
From `app\src\web`, run `node --test dashboard.test.mjs` and `npm run build`.
No Azure or authentication changes are needed for this workspace.

### 3. Deploy to Azure

```powershell
cd app
.\deploy.ps1 -ResourceGroup rg-cmintel-demo `
             -AadClientId <bff-client-id> `
             -AadClientSecret <secret> `
             -AadApiScope api://<bff-client-id>/access_as_user
```

Then register the deployed URL as a redirect URI:

```powershell
python infra\provision_app_registrations.py --add-redirect https://<web-fqdn>
```

Code-only redeploy afterwards: `.\deploy.ps1 -Only images`

---

## Who can sign in

Any user in the tenant can authenticate; what they *see* is governed by the
downstream sources under their own identity. The five personas hold the required
access, and the story adapts to whichever one signs in — `personaByRole` in
`story.json` reframes the goal and objectives for Coverage, Corporate Banking,
Global Markets, Credit Risk and Research.

| Persona | UPN prefix | Role claim | Wall status |
|---|---|---|---|
| Sydney Mattos — MD, Corporate Coverage – Energy (driver) | `SydneyM` | `Coverage` | public side |
| Sasha Ouellet — Director, Corporate Banking & DCM | `SashaO` | `CorporateBanking` | **wall-crossed** |
| Quinn Campbell — Director, Commodities & FX Sales | `QuinnC` | `GlobalMarkets` | public side |
| Vance DeLeon — Director, Credit Risk – Energy | `VanceD` | `CreditRisk` | **wall-crossed** |
| Robin Kline — ED, Equity Research | `RobinK` | `Research` | public side |

The wall-crossed pair is the point, not an accident: signing in as `SashaO` and
then as `SydneyM` and asking the same question about `CR-2026-0184` is the
cleanest live demonstration of security trimming in the whole demo.

| Access | Why |
|---|---|
| Azure AI User on `cmintel-foundry` | invoke the agent |
| Search Index Data Reader on `srch-cmintel-*` | Foundry IQ retrieval |
| Workspace access on `ws-capital-markets-client-intel` | Fabric semantic model |
| Recipient on the seeded emails | Work IQ mail grounding |
| Member of *Capital Markets - Gibson Energy Coverage* | Work IQ document grounding |

Anyone without these gets a thinner answer rather than an error — which is correct
behaviour, and worth demonstrating deliberately if the audience asks about
security trimming.

---

## Troubleshooting

Sign in, switch to **Explore**, open **Connection diagnostics → Run checks**. It
walks token → OBO → agent and reports the first failure, which is the actionable
one. Or call `GET /api/diag` directly.

| Symptom | Likely cause |
|---|---|
| `AADSTS65001` on the OBO exchange (BFF just deployed) | **the BFF has not been consented for Azure Machine Learning Services `user_impersonation`.** The Foundry scope `https://ai.azure.com/.default` resolves to that resource, so the OBO exchange fails even though the SPA was consented. Re-run `python infra\provision_app_registrations.py --spa-redirect …` — it now pre-registers and consents the scope. |
| `AADSTS65001` on the OBO exchange (mid-life) | admin consent missing on the BFF app. Re-run the provisioning script, or consent once interactively. |
| *"The agent ran but returned no answer"* naming a failed tool | that connection failed for this user. The detail line carries the server label and the service's own error. |
| Agent answers "yes, 158.3m of headroom" | **the agent's instructions are empty.** A portal-built agent starts with no system prompt, so it answers from arithmetic and calls no tool. Run `python push_agent_instructions.py --apply`. |
| The agent appears to hang, no error | a tool is waiting on `mcp_approval_request`. Portal-added connections default to requiring approval. Run `python set_tool_autoapprove.py --apply`. |
| `GetSemanticModelSchema: Power BI couldn't process that request right now`, or a 429 | **Fabric capacity throttling**, not a broken model. `fabcap26` is F8 and the schema call runs on every request. The BFF retries twice automatically. Prove the model is healthy with `python diag_fabric.py`, which bypasses Foundry. |
| Work IQ: `NoPolicy` / *"AI credits access is not configured for this user"* | the **A2A** connection (`workiq.svc.cloud.microsoft/a2a/`) is metered against Copilot Credits and needs a billing policy. Use the per-service **managed MCP connections** (`agent365.svc.cloud.microsoft/…`) instead — they are not metered. See `diag_workiq.py`. |
| Work IQ: *"Response size exceeds the maximum allowed size of 51200 bytes"* | the tool works — the query was too broad. Harmless; the agent usually narrows and retries. |
| Web IQ quotes *"indicative — verify via Web IQ"* as a rating | Bing grounding is not attached. That string is a deliberately unusable internal placeholder. |
| Work IQ returns nothing, other layers fine | signed in as the wrong user, or as admin. Only the five personas hold the seeded mail; only members of *Capital Markets - Gibson Energy Coverage* see the `Client Files/` and `Meeting Notes/` documents. |
| Work IQ fails right after a UPN or primary-SMTP change | the substrate and Microsoft Search index are keyed on the user's address. Sign in once to Outlook on the web **and** Teams, then allow the re-crawl to finish. |
| Fabric IQ empty | capacity `fabcap26` is paused, or the user lacks workspace access. Querying `sm_client_intel` needs **Member** (Viewer does not grant Build). |
| IQ cards never light up | SSE is being buffered. Confirm `proxy_buffering off` in `default.conf.template`. |
| All four cards light up on every question | a discovery event is being counted as an invocation. `_IGNORED` in `iq.py` must exclude `mcp_list_tools` and `mcp_approval_request`. |
| Agent repeats wall-crossed detail to a public-side user | the restriction is **not** enforced by the prompt — it is enforced by OBO. Confirm the BFF is exchanging the user's token and not falling back to the managed identity: `ALLOW_APP_IDENTITY_FALLBACK` must be `false`. |
| Sign-in loops | the current origin is not a registered redirect URI. `--add-redirect <url>`. |
| `Agent not found` | `FOUNDRY_AGENT_NAME` does not match the agent in the project (currently `Agent-cap-market`). |

**A single failing tool aborts the whole answer**, rather than degrading to the
other three layers. The BFF therefore retries transient failures (throttling,
429, 503) up to twice with backoff, buffering frames per attempt so a retry never
leaves half an answer on screen. Permanent failures — 403, `Agent not found` —
are reported immediately rather than retried.

An empty answer is never rendered as silence: if the agent produces no text the BFF
emits an `error` frame explaining why, and `done` carries a `toolErrors` array.

---

## Teardown

```powershell
python infra\provision_app_registrations.py --delete
az deployment group delete -g rg-cmintel-demo -n cmci-app
```

Container Apps scale to a minimum of one replica each, so the environment bills a
small amount continuously. Delete the resource group's container apps when the demo
is finished.
