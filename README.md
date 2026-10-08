# Capital Markets Client Intelligence

A bank-neutral demonstration of a capital-markets coverage workspace, built with React, FastAPI, Microsoft Entra ID, Microsoft Foundry, Azure AI Search, Microsoft Fabric and Microsoft 365.

**Choose your bank before running or deploying the UI.** No real-bank presets, logos or customer tenant configuration are distributed. Branding changes presentation only; it does not load a bank's real data, policies, users or permissions.

**SYNTHETIC DEMO DATA:** All internal exposures, limits, revenue, policies, colleagues and client relationships are invented. Publicly listed company names are retained so public-news grounding can find real sources. This repository does not represent or endorse any bank and is not a production banking system.

## 1. Choose the bank for your UI

Prerequisites for setup: Git, PowerShell 7 and Node.js 22 or later.

```powershell
git clone https://github.com/pshah208/cap-markets.git
Set-Location cap-markets

# Interactive: enter your bank's name and presentation settings.
.\setup-bank.ps1
```

For repeatable setup, supply the values explicitly:

```powershell
.\setup-bank.ps1 `
  -BankName "Example Bank Capital Markets" `
  -BankShortName "Example Bank" `
  -PrimaryColor "#164E63" `
  -AccentColor "#B45309"

.\setup-bank.ps1 -Check
```

Use a logo only if you have permission to use it. Append `-LogoPath 'C:\branding\logo.png'` to supply a local PNG; otherwise the UI uses text initials. The generated branding configuration and supplied logo are local deployment artifacts, excluded from Git. They are public UI content, **not a place for credentials**. Rerun setup and rebuild the frontend to change the bank.

## 2. Run a local synthetic-data preview

Use Python 3.11 or 3.12 and Node.js 22 or later. The local preview does not require an Azure subscription, Microsoft 365 tenant or a live agent. It does not demonstrate live connectors or access-control enforcement.

From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt -r app\src\bff\requirements.txt

Set-Location app\src\web
npm ci
Set-Location ..\..\..
```

In the first terminal, from the repository root:

```powershell
.\.venv\Scripts\Activate.ps1
$env:MOCK_MODE = "true"
Set-Location app\src\bff
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In a second terminal:

```powershell
Set-Location app\src\web
npm run dev -- --host 127.0.0.1
```

Open `http://127.0.0.1:5173`. Vite proxies `/api` to the local backend. Missing or invalid bank configuration blocks startup/build with setup instructions. Mock mode must remain local; do not use it for a shared deployment.

## 3. Prepare your own cloud environment

Live deployment is a separate, administrator-reviewed workflow. Nothing in bank setup creates cloud resources, signs in to a tenant or grants permissions.

| Prerequisite | Required preparation |
| --- | --- |
| Azure | Select your own subscription, resource group and approved regions; install Azure CLI and Bicep. |
| Governance | Review inherited policy assignments, current compliance, allowed resource types/SKUs/regions, naming and effective control/data-plane permissions. Resolve every deny or missing permission before deployment. |
| Entra ID | Separate SPA and confidential API registrations; delegated API scope, redirect URIs, downstream consent and user access. |
| Foundry | A supported project, approved model deployment/quota and the named agents/connections used by the application. |
| Fabric | An active, approved Fabric capacity and access to create/use the workspace, lakehouse, tables and semantic model. |
| Microsoft 365 | A dedicated demo tenant, licensed test users, explicit persona mapping and approved Graph permissions for optional seeding. Never seed production mailboxes. |
| Network and operations | Review ingress, private connectivity, diagnostic settings, retention and secret handling for your environment. |

Before provisioning, record a target-specific **Pre-Flight Report**:

| Field | Required evidence |
| --- | --- |
| Target scope | Your subscription and resource group |
| Relevant policies | Applicable Deny, DeployIfNotExists, Modify and Audit assignments, including inherited assignments |
| Compliance | Current non-compliant policies and design implications |
| Caller identity and roles | Effective roles at the target scope, including deny assignments and active PIM roles |
| Permissions sufficient? | Required control-plane and data-plane actions confirmed; stop if any are missing |
| Naming standard | Your organization's approved naming rules; otherwise review CAF naming |
| SKU/region allow-list | Your organization's approved values, including model availability and quota |
| Design adjustments | Required changes reviewed before applying the reference templates |

This standalone repository does not ship an approval for any tenant. A prior demo's policy exceptions, role grants or allowed regions do not apply to your environment. The reference templates require security and governance review; they are not a production landing zone.

## 4. Deploy the core infrastructure

The commands below are a deployment guide, not authorization to provision. Stop on policy conflicts or missing permissions; request the appropriate PIM activation, role assignment or administrator handoff.

Sign in and explicitly select your target. Keep these variables in the same PowerShell session:

```powershell
$tenantId = Read-Host "Your Entra tenant ID"
$subscriptionId = Read-Host "Your Azure subscription ID"
$resourceGroup = Read-Host "Your approved resource group name"
$location = Read-Host "Your approved Azure region"

az login --tenant $tenantId
az account set --subscription $subscriptionId

Copy-Item infra\main.parameters.example.json infra\main.parameters.local.json
```

Edit `infra\main.parameters.local.json` before continuing. Supply the same `location`, globally unique Foundry/Bing names, a project name, supported model/version/capacity, and your approved Search/Fabric settings. Sample SKUs and model names are illustrative, not approved or guaranteed available. Empty principal arrays grant nobody access; populate them only with explicitly reviewed object IDs. Existing local configuration is never distributed.

```powershell
$core = @{
  ResourceGroup = $resourceGroup
  SubscriptionId = $subscriptionId
  TenantId = $tenantId
  Location = $location
  Only = "bicep"
}
.\deploy.ps1 @core -WhatIf
```

The script prints policy, compliance, role and permissions evidence plus `planSha256`. A nonexistent resource group is **not** created by `-WhatIf`; in that case the ARM change preview is skipped. Review the template and target before approving the real group creation.

### Record the governance review

Both deployment scripts require a deployer-owned file ending in `.local.json`. Create a separate review for each script/stage after examining its current report. Required fields:

```json
{
  "subscriptionId": "your selected subscription GUID",
  "tenantId": "your selected tenant GUID",
  "resourceGroup": "your selected resource group",
  "location": "your selected region",
  "deploymentMode": "bicep",
  "planSha256": "copy the digest printed by this exact invocation",
  "reviewed": false,
  "namingStandard": "external: reference your reviewed naming standard",
  "allowedSkusAndRegions": "external: reference your reviewed SKU and region allow-list",
  "policyReview": "Record applicable policies, exemptions and required adjustments",
  "permissionReview": "Record effective permissions, exact scopes and reviewer"
}
```

Save your completed evidence as `core-governance.local.json`; set `reviewed` to `true` **only after approval**. If you provide local `docs\naming.md` and `docs\allowed.md`, the scripts display them. Otherwise the corresponding review fields must cite an `external:` standard. A matching digest and acknowledgement are not proof of effective permissions.

```powershell
.\deploy.ps1 @core `
  -GovernanceReviewPath .\core-governance.local.json `
  -GovernanceApproved
```

The real `bicep` stage can create the selected resource group and deploy the reviewed templates. Changes to targets, parameters, environment inputs or Bicep files invalidate the digest and require another review.

## 5. Populate the data layers and configure agents

`.env.example` documents environment variables; root helpers **do not automatically load it**. Export your reviewed values to the process or use your organization's secret-management tooling.

| Stage | Invocation and requirements |
| --- | --- |
| Fabric | `.\deploy.ps1` with the explicit target arguments, `-Only fabric`, `-FabricCapacity` and `-FabricCapacityResourceGroup`. Set all five `FABRIC_*_NAME` workspace/lakehouse/notebook/model variables in `.env.example`. The capacity name must match local infrastructure parameters and the capacity must be active. |
| Foundry IQ | `.\deploy.ps1` with the explicit target arguments and `-Only foundry-iq`. Set `SEARCH_SEMANTIC_CONFIGURATION` to your chosen semantic configuration name. Search/Foundry endpoints are recovered from the selected `cmintel-infra` deployment, not an old environment. |
| Work IQ, optional | Copy `data\work-iq\user_mapping.example.json` to local `user_mapping.json` and map every synthetic persona to your own licensed test users. Set `WORKIQ_USER_MAPPING_FILE` and `WORKIQ_RESTORE_FILE` to absolute private paths, plus tenant/client credentials. `driver_alias` belongs in the mapping. `-Only work-iq` modifies test-user profiles and seeds mail, Teams and files; review those writes separately. |
| Seeder registration, optional | `-Only work-iq -ProvisionWorkIqApp` provisions only the explicitly named seeder registration. Review Graph grants and secure the issued credentials before a separate seeding run. |
| Classic agent, optional | `-Only agent` runs `agent\create_agent.py`. Set `FOUNDRY_AGENT_NAME`, a synthetic `CM_CLIENT_ID` such as `CLI-1001`, and `IQ_MODE=local` or `hybrid`. Hybrid additionally needs `SEARCH_SEMANTIC_CONFIGURATION` and the full `BING_GROUNDING_CONNECTION_ID`. This creates a **classic agent**, not the named Responses agent used by the web application. |

For **each** stage, use the same preview/review/apply sequence as section 4, with its exact `deploymentMode` (`fabric`, `foundry-iq`, `work-iq` or `agent`), current digest and its own review file. Include `-SubscriptionId`, `-TenantId`, `-ResourceGroup` and `-Location`; do not reuse a `bicep` approval for data-plane writes.

Application-only Microsoft 365 seeding does not complete delegated Teams channel-message posting. Follow the seeder's help and review a separate delegated run where required. Do not reuse another tenant's mapping or restore snapshot.

**Required for the live UI:** Configure a named Responses agent in your Foundry project using `agent\agent_instructions.portal.md`. Attach your own supported Work IQ/Microsoft 365, Fabric, policy-retrieval and web-grounding connections, with appropriate delegated authentication. Use that agent's **name**, not an `asst_` ID, for `FoundryAgentName`. Connection creation, service-specific consent and feature availability are tenant prerequisites, not performed by the classic-agent stage.

Additional scenario and mission agent definitions are under `agent`; their creation helpers require your project configuration, source agent name and explicit apply options. These are optional features, not substitutes for the primary Responses agent. Supply `-ScenarioAgentName`, `-MissionAgentName` and `-BarrierAgentName` to application deployment after creating those agents; omitted names leave those live features unavailable.

## 6. Deploy the web application

Review the Entra helpers under `app\infra` and configure separate SPA/API registrations, a delegated API scope and downstream consent in your tenant. `provision_app_registrations.py --help` describes the required inputs. Provisioning registrations and granting consent are separate administrative operations, not part of `app\deploy.ps1`. Keep the API secret in a secret store or the local process.

The registration helpers require `AZURE_TENANT_ID`, `INFRA_SPA_NAME` and `INFRA_BFF_NAME` in the process environment. Use the complete per-script environment reference in [`agent\operations_environment.json`](agent/operations_environment.json) for operational helpers and optional integrations; no helper infers the original author's tenant.

Collect the Fabric workspace, lakehouse and semantic-model GUIDs from your deployed items, and your Foundry account/project/agent names. The application resource group must already exist.

```powershell
$app = @{
  ResourceGroup = $resourceGroup
  SubscriptionId = $subscriptionId
  AadTenantId = $tenantId
  Location = $location
  NamePrefix = "cmci"
  Only = "all"
  AadClientId = Read-Host "BFF application client ID"
  AadApiScope = Read-Host "API scope, api://<BFF-client-id>/access_as_user"
  SpaClientId = Read-Host "SPA application client ID"
  FoundryAccountName = Read-Host "Foundry account name"
  FoundryProjectName = Read-Host "Foundry project name"
  FoundryAgentName = Read-Host "Primary named Responses agent"
  FabricWorkspaceId = Read-Host "Fabric workspace GUID"
  FabricLakehouseId = Read-Host "Fabric lakehouse GUID"
  FabricSemanticModelId = Read-Host "Fabric semantic-model GUID"
}
$app.FoundryProjectEndpoint = "https://$($app.FoundryAccountName).services.ai.azure.com/api/projects/$($app.FoundryProjectName)"
.\app\deploy.ps1 @app -WhatIf
```

A secret-free application preview prints the deployment plan and governance report but skips ARM what-if. For a full ARM preview, supply `-AadClientSecret` securely on a trusted host; never substitute a dummy secret.

Create `app-governance.local.json` using the same review schema with `deploymentMode: "all"` and the app report's digest. After approval:

```powershell
# AAD_CLIENT_SECRET must already be supplied securely to this process.
if (-not $env:AAD_CLIENT_SECRET) { throw "Set the BFF secret securely first." }
.\app\deploy.ps1 @app `
  -AadClientSecret $env:AAD_CLIENT_SECRET `
  -GovernanceReviewPath .\app-governance.local.json `
  -GovernanceApproved
```

The script deploys app infrastructure, builds the BFF and configured web image remotely in ACR, then updates both Container Apps. The API secret reaches Azure CLI as an argument; use a trusted host without process/command-line tracing. The generated bank configuration and optional logo must exist in the local web build context. No Docker daemon is required for ACR remote builds.

Register the printed HTTPS web URL as a SPA redirect URI and complete required consent before signing in. `VITE_AAD_TENANT_ID`, `VITE_AAD_CLIENT_ID` and `VITE_API_SCOPE` are baked into the web image; changes require rebuilding it. Confirm the signed-in user's downstream data access before demonstrating live Work IQ.

Fabric capacity start/stop controls are disabled by default. Enabling them requires an explicit capacity resource ID, a reviewed operator allow-list and additional scoped permissions; selecting a UI bank never enables them.

### Subsequent code or branding updates

Run bank setup again if the branding changes. Use `.\app\deploy.ps1 -Only images` with explicit subscription, resource group, location, tenant, SPA client ID and API scope. Run its `-WhatIf`, record a fresh review with `deploymentMode: "images"` and pass that review plus `-GovernanceApproved`. The image-only stage updates **both** BFF and web images; it is not a frontend-only deployment.

## Troubleshooting

| Symptom | Action |
| --- | --- |
| Bank configuration missing or invalid | Run `.\setup-bank.ps1` and then `.\setup-bank.ps1 -Check` before starting Vite or building. |
| Governance digest mismatch | Preview the current exact inputs again and obtain a matching review; never copy an unrelated approval. |
| Sign-in/redirect failure | Verify SPA client ID, tenant, delegated API scope, consent and HTTPS redirect URI. Rebuild when Vite auth settings change. |
| Agent not found | Check that `FoundryAgentName` is a named Responses agent in the configured project, not a classic agent ID. |
| Missing live IQ data | Check source access, connection authentication, consent, licenses and capacity state; inspect Activity Logs, diagnostics and Azure Monitor before changing permissions. |
| Seeding configuration error | Replace the example mapping with your own licensed test users and export required process variables. Never seed with example addresses. |

## Offline source checks

After installing dependencies, run these without cloud credentials:

```powershell
python -B preflight.py
pwsh -NoProfile -NonInteractive -File tests\deployment.test.ps1
Set-Location app\src\web
npm test
npm run build
```

Source preflight validates the shipped **example** mapping, never a private tenant mapping. The deployment regressions use mocked Azure commands. The full Python test commands are listed in `agent\operations_environment.json`. These checks do not replace the target-specific governance report, container deployment or live connector validation.

## Components

| Path | Purpose |
| --- | --- |
| `setup-bank.ps1` | Required local bank-brand setup |
| `app\src\web` | React/Vite UI, coverage dashboard and scenario views |
| `app\src\bff` | FastAPI backend, authentication, agent orchestration and synthetic scenario calculations |
| `infra` / `deploy.ps1` | Core Azure infrastructure and data-layer deployment |
| `app\infra` / `app\deploy.ps1` | Application registrations, application infrastructure and container deployment |
| `agent` | Agent instructions, definitions and creation helpers |
| `data` | Synthetic source facts, generators, policy corpus and optional Microsoft 365 seeding |
| `docs` | Architecture and scenario documentation |

## Data and operational boundaries

Work IQ access depends on the signed-in user's actual permissions. Choosing a bank name does not change information barriers, tenant membership or downstream authorization. The live integrations require your own connections and supported service features; missing credentials, licenses or service permissions are not resolved by changing branding.

Local configuration, tenant mappings, restore snapshots, credentials and build output must remain untracked. Keep secrets out of frontend variables, JSON branding, container build arguments and commit history. `VITE_*` values are visible to browser users; use them only for public application identifiers and scopes.

Costs depend on region, model usage, Fabric capacity, AI Search, Container Apps, registry storage and monitoring retention. Review the [Azure pricing calculator](https://azure.microsoft.com/pricing/calculator/) before provisioning. Stop or remove unused demo resources only under your organization's approved process.

## Microsoft documentation

- [Azure naming and tagging guidance](https://learn.microsoft.com/azure/cloud-adoption-framework/ready/azure-best-practices/resource-naming)
- [Azure Policy assignments](https://learn.microsoft.com/azure/governance/policy/concepts/assignment-structure)
- [Azure role-based access control](https://learn.microsoft.com/azure/role-based-access-control/overview)
- [Microsoft identity platform on-behalf-of flow](https://learn.microsoft.com/entra/identity-platform/v2-oauth2-on-behalf-of-flow)
- [Azure Container Apps](https://learn.microsoft.com/azure/container-apps/overview)
- [Microsoft Fabric documentation](https://learn.microsoft.com/fabric/)
