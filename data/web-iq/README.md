# Web IQ — live external intelligence

> **This layer has no synthetic data and no offline cache. By design.**

Every other layer in this demo is invented. Web IQ is the one layer that returns **real
public information about a real company** — which is exactly why the hero client is
Gibson Energy Inc. (TSX:GEI), a genuine TSX-listed Canadian mid-cap, rather than a fictional
issuer that would return nothing.

## Why live only

A cached news file would be stale the moment it was written and would make the demo look
convincing while proving nothing. Live grounding proves the actual capability: the agent
reaches the open web, retrieves current information about the client, and cites it.

The trade-off is a hard dependency. If the Bing grounding connection is not configured, the
tool returns:

```json
{ "status": "unavailable", "layer": "Web IQ", "reason": "..." }
```

and the agent is instructed to **say so plainly** rather than answer from model memory. An
agent that quietly substitutes its training data for live retrieval is worse than one that
admits the gap.

## The guardrail that matters most

Three of the four layers are synthetic. One is real. The agent must never let them bleed.

| Never do this | Why |
|---|---|
| Quote a synthetic internal figure as if it were public | It would be a false statement about a real public company |
| Attribute an internal credit view to a news source | Same problem, plus it fabricates a citation |
| Present a public figure as BMO's internal position | Corrupts the internal record |
| Reconcile a public/internal contradiction silently | The contradiction is often the most valuable finding |

The agent instructions enforce this: external claims require a citation from the grounding
tool; internal claims are attributed to Fabric IQ, Work IQ or a named policy document.

## Provisioning

Web IQ needs a **Grounding with Bing Search** resource and a connection on the Foundry
project.

```powershell
az account set --subscription a7d3b871-d2a9-4d67-9704-8792a5d3db99

# 1. The Bing grounding resource (Bicep: infra/modules/bing-grounding.bicep)
az deployment group create `
  --resource-group rg-cmintel-demo `
  --template-file ..\..\infra\main.bicep `
  --parameters ..\..\infra\main.parameters.json

# 2. Confirm the connection is visible to the project
$env:FOUNDRY_PROJECT_ENDPOINT = "https://cmintel-foundry.services.ai.azure.com/api/projects/proj-client-intelligence"
$env:BING_GROUNDING_CONNECTION = "bing-grounding-cmintel"
```

Then verify end to end:

```powershell
cd ..\..\agent
python create_agent.py --ask "What has happened externally with Gibson Energy in the last 30 days?" --role analyst
```

A correct answer cites real, dated sources. An answer with no citations means the connection
is not wired — check the connection name before believing the output.

## Query design

`web_iq_queries.json` holds eight topics, each with query templates and a stated reason it
matters. Topics are selected by **role**, so the same client returns a different external
picture depending on who is asking:

| Role | Default topics |
|---|---|
| Relationship Manager | news & earnings · financing and M&A activity · leadership changes · ESG |
| Trader | commodity & differential moves · news & earnings · sector and peers |
| Research Analyst | news & earnings · sector and peers · rating actions · ESG |
| Credit / Risk | rating actions · regulatory and enforcement · news & earnings · commodity |

`{client}`, `{ticker}` and `{peer_list}` are substituted from `scenario_facts.py`, so
pointing the demo at a different issuer is a one-line change.

## Interaction with the restriction scenario

The demo deliberately places the hero client on a (synthetic) restricted list, `CR-2026-0184`.
That creates the cross-layer tension the agent must **surface rather than resolve**:

- **Web IQ** returns genuinely public, genuinely current news about the client.
- **Foundry IQ** returns CP-008, which permits a pitch on public information only, and which
  says whether a given pitch touches the restricted subject matter is the **Control Room's**
  determination — not the business's.

A good answer uses the public news *and* repeats the caveat. An answer that uses the news to
argue the restriction does not apply has failed the demo.

## Cost note

Grounding with Bing Search is billed per query. The agent issues one query per selected
topic, so a four-topic role view is four queries. Keep `max_results_per_query` at 8 and
`lookback_days` at 30 unless a specific ask needs more.
