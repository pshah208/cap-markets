// =============================================================================
// Capital Markets Client Intelligence Agent - Azure control-plane infrastructure
// =============================================================================
// SYNTHETIC DEMO DATA. BMO Capital Markets is used only as a branding label.
// Gibson Energy Inc. is a real public company used only so the Web IQ layer's
// live grounding returns genuine public news; every internal exposure, limit,
// revenue, rating, covenant and policy in this solution is invented for a demo.
//
// SCOPE OF THIS TEMPLATE
// Bicep can only express ARM control-plane resources. This template deploys:
//
//   * Azure AI Search service        (Foundry IQ store)
//   * Azure AI Foundry account       (agent host)
//   * Foundry project                (agent container)
//   * Model deployment               (the reasoning model)
//   * Grounding with Bing Search     (Web IQ)  + its Foundry connection
//   * Microsoft Fabric capacity      (Fabric IQ compute)      -- optional
//   * Role assignments               (least-privilege access)
//
// The following are DATA-PLANE or Microsoft Graph objects with no ARM provider,
// and are created by the scripts in ../data and ../agent instead:
//
//   * Fabric workspace, lakehouse, notebooks, Delta tables, semantic model
//                                    -> data/fabric-iq/deploy_fabric.py
//   * AI Search index + the 14 policy documents
//                                    -> data/foundry-iq/index_cm_policies.py
//   * Entra app registration + Graph permission grants
//                                    -> data/work-iq/provision_seeder_app.py
//   * M365 mail, Teams messages, SharePoint files, persona job titles
//                                    -> data/work-iq/seed_work_iq.py
//   * The Foundry agent and its four function tools
//                                    -> agent/create_agent.py
//
// Every `create*` flag can be set false to REFERENCE an existing resource rather
// than create one, so the template can be pointed at an estate stood up by hand.
//
// PRE-FLIGHT NOTES (MCAPS tenant, subscription ME-M365CPI65678641-shahpar-1)
//   * MCAPSGovDenyPolicies blocks classic resource types and OpenAI PROVISIONED
//     capacity. The model deployment below uses GlobalStandard, which is allowed.
//   * Microsoft.Bing/accounts is a GLOBAL resource type - see bing-grounding.bicep.
//   * The Fabric capacity fabcap26 already exists in rg-Fabric (Central US) and is
//     referenced rather than recreated; it must be in the Active state.
// =============================================================================

targetScope = 'resourceGroup'

// ---------------------------------------------------------------- naming ----
@description('Workload name used in CAF-style resource names.')
param workload string = 'cmintel'

@description('Environment: dev | test | prod.')
@allowed([ 'dev', 'test', 'prod' ])
param environmentName string = 'dev'

@description('Azure region for resources created by this template.')
param location string = resourceGroup().location

@description('Additional tags merged onto every resource.')
param extraTags object = {}

// ------------------------------------------------------------ AI Search ----
@description('Create a new Azure AI Search service. False = reference an existing one.')
param createSearch bool = true

@description('Search service name. Required when createSearch = false.')
param searchServiceName string = ''

@description('Search SKU.')
@allowed([ 'free', 'basic', 'standard', 'standard2', 'standard3' ])
param searchSku string = 'basic'

@description('Semantic ranker tier. MUST NOT be "disabled" - the agent issues semantic queries.')
@allowed([ 'free', 'standard' ])
param searchSemanticTier string = 'free'

@description('''
Create a CognitiveSearch connection on the Foundry account pointing at the search
service. Custom function tools cannot execute in the Foundry portal playground, so
attaching the index as a portal-native knowledge source is what makes a portal
demo path possible at all. The scripted agent uses a function tool against the
same index, so this changes nothing about how the CLI path behaves.
''')
param createSearchConnection bool = true

@description('Name of the AI Search connection as it appears in the Foundry portal.')
param searchConnectionName string = 'srchcminteldevy5rrn4c55tgi7'

// --------------------------------------------------------------- Foundry ----
@description('Create a new Foundry (AIServices) account. False = reference an existing one.')
param createFoundry bool = true

@description('Foundry account name. Required when createFoundry = false.')
param foundryAccountName string = 'cmintel-foundry'

@description('Foundry project name.')
param foundryProjectName string = 'proj-client-intelligence'

@description('Deploy the reasoning model. False if it already exists or quota is short.')
param deployModel bool = true

@description('Model deployment name the agent calls.')
param modelDeploymentName string = 'gpt-5.4'

@description('Model name.')
param modelName string = 'gpt-5.4'

@description('Model version. Blank = platform default.')
param modelVersion string = ''

@description('Model capacity in thousands of tokens per minute.')
param modelCapacity int = 125

@description('Responsible AI policy applied to the model deployment.')
param raiPolicyName string = 'Microsoft.DefaultV2'

@description('Version upgrade behaviour for the model deployment.')
@allowed([ 'OnceNewDefaultVersionAvailable', 'OnceCurrentVersionExpired', 'NoAutoUpgrade' ])
param versionUpgradeOption string = 'OnceNewDefaultVersionAvailable'

// ---------------------------------------------------------------- Web IQ ----
@description('Create the Grounding with Bing Search account and its Foundry connection.')
param createBingGrounding bool = true

@description('Bing grounding account name. Global resource - must be globally unique.')
param bingAccountName string = ''

@description('Connection name the agent resolves at run time. Set as BING_GROUNDING_CONNECTION.')
param bingConnectionName string = 'bing-grounding-cmintel'

// ---------------------------------------------------------------- Fabric ----
@description('Create a Microsoft Fabric capacity. False = use an existing capacity (the default - fabcap26).')
param createFabricCapacity bool = false

@description('Fabric capacity name. Required when createFabricCapacity = true.')
param fabricCapacityName string = ''

@description('Fabric SKU.')
@allowed([ 'F2', 'F4', 'F8', 'F16', 'F32', 'F64' ])
param fabricSkuName string = 'F4'

@description('Entra object IDs set as Fabric capacity admins. Required when createFabricCapacity = true.')
param fabricAdminMembers array = []

// ------------------------------------------------------------------ RBAC ----
@description('Entra object ID of the principal that will run the agent. Blank = skip role assignments.')
param agentPrincipalId string = ''

@description('Principal type for the role assignments.')
@allowed([ 'User', 'Group', 'ServicePrincipal' ])
param agentPrincipalType string = 'User'

@description('''
Entra object IDs of the Work IQ demo personas. Each is granted Foundry User at
project scope so they can sign in to the Foundry portal and run the agent. The
demo driver must be in this list - Work IQ only grounds on content the signed-in
user can access, so the demo is driven as the relationship owner, not as admin.
''')
param demoUserPrincipalIds array = []

// ============================================================== variables ====
var tags = union({
  workload: workload
  environment: environmentName
  solution: 'capital-markets-client-intelligence'
  dataClassification: 'synthetic-demo-data'
  managedBy: 'bicep'
}, extraTags)

var suffix = uniqueString(resourceGroup().id)
var resolvedSearchName = createSearch ? toLower('srch-${workload}-${environmentName}-${suffix}') : searchServiceName
var resolvedFoundryName = createFoundry ? foundryAccountName : foundryAccountName
var resolvedBingName = empty(bingAccountName) ? toLower('bing-${workload}-${environmentName}-${suffix}') : bingAccountName

// ============================================================== resources ====

module search 'modules/search.bicep' = if (createSearch) {
  name: 'search'
  params: {
    name: resolvedSearchName
    location: location
    tags: tags
    sku: searchSku
    semanticSearch: searchSemanticTier
  }
}

module foundry 'modules/foundry.bicep' = if (createFoundry) {
  name: 'foundry'
  params: {
    accountName: resolvedFoundryName
    projectName: foundryProjectName
    projectDisplayName: 'Capital Markets Client Intelligence'
    projectDescription: 'SYNTHETIC DEMO DATA. Client meeting preparation agent grounded across Work IQ, Fabric IQ, Foundry IQ and Web IQ for a Capital Markets coverage relationship.'
    location: location
    tags: tags
    deployModel: deployModel
    modelDeploymentName: modelDeploymentName
    modelName: modelName
    modelVersion: modelVersion
    modelCapacity: modelCapacity
    raiPolicyName: raiPolicyName
    versionUpgradeOption: versionUpgradeOption
  }
}

// Model deployment onto an existing (not template-created) Foundry account.
resource existingFoundry 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' existing = if (!createFoundry) {
  name: foundryAccountName
}

resource existingAccountModel 'Microsoft.CognitiveServices/accounts/deployments@2025-04-01-preview' = if (!createFoundry && deployModel) {
  parent: existingFoundry
  name: modelDeploymentName
  sku: { name: 'GlobalStandard', capacity: modelCapacity }
  properties: {
    model: union(
      { format: 'OpenAI', name: modelName },
      empty(modelVersion) ? {} : { version: modelVersion }
    )
    raiPolicyName: raiPolicyName
    versionUpgradeOption: versionUpgradeOption
  }
}

// Web IQ. Depends on the Foundry account existing, because the connection is a
// child of it.
module bingGrounding 'modules/bing-grounding.bicep' = if (createBingGrounding) {
  name: 'bing-grounding'
  params: {
    name: resolvedBingName
    tags: tags
    foundryAccountName: resolvedFoundryName
    connectionName: bingConnectionName
  }
  dependsOn: [ foundry ]
}

module fabricCapacity 'modules/fabric-capacity.bicep' = if (createFabricCapacity) {
  name: 'fabric-capacity'
  params: {
    name: fabricCapacityName
    location: location
    tags: tags
    skuName: fabricSkuName
    adminMembers: fabricAdminMembers
  }
}

// The AI Search connection is what makes a portal-native demo path possible. The
// scripted agent uses a function tool instead; both point at the same index.
module searchConnection 'modules/search-connection.bicep' = if (createSearchConnection && createSearch) {
  name: 'search-connection'
  params: {
    foundryAccountName: resolvedFoundryName
    searchServiceName: resolvedSearchName
    connectionName: searchConnectionName
  }
  dependsOn: [ search, foundry ]
}

module rbac 'modules/rbac.bicep' = if (!empty(agentPrincipalId)) {
  name: 'rbac'
  params: {
    principalId: agentPrincipalId
    principalType: agentPrincipalType
    foundryAccountName: resolvedFoundryName
    foundryProjectName: foundryProjectName
    searchServiceName: resolvedSearchName
    demoUserPrincipalIds: demoUserPrincipalIds
  }
  dependsOn: [ search, foundry ]
}

// ================================================================ outputs ====
// These feed the environment variables the data-plane scripts and the agent read.

@description('Set as SEARCH_ENDPOINT.')
output searchEndpoint string = createSearch ? search!.outputs.endpoint : 'https://${searchServiceName}.search.windows.net'

output searchServiceName string = resolvedSearchName

@description('''
AI Search connection name. Attach this as a knowledge source in the Foundry portal
to demo Foundry IQ natively - custom function tools cannot execute in the portal
playground, so this is the portal path. The scripted agent uses a function tool
against the same index.
''')
output searchConnectionName string = createSearchConnection && createSearch ? searchConnection!.outputs.connectionName : 'not-deployed'

@description('Set as SEARCH_INDEX. Created by index_cm_policies.py, not by Bicep.')
output searchIndexName string = 'cm-client-policies'

@description('Set as FOUNDRY_PROJECT_ENDPOINT.')
output foundryProjectEndpoint string = createFoundry
  ? foundry!.outputs.projectEndpoint
  : 'https://${foundryAccountName}.services.ai.azure.com/api/projects/${foundryProjectName}'

output foundryAccountName string = resolvedFoundryName

@description('Set as FOUNDRY_MODEL.')
output modelDeploymentName string = modelDeploymentName

@description('Set as BING_GROUNDING_CONNECTION. Web IQ is live only - no data is seeded.')
output bingConnectionName string = createBingGrounding ? bingGrounding!.outputs.connectionName : 'not-deployed'

output bingAccountName string = createBingGrounding ? bingGrounding!.outputs.bingAccountName : 'not-deployed'

output fabricCapacityName string = createFabricCapacity ? fabricCapacity!.outputs.name : fabricCapacityName

@description('Fabric workspace/lakehouse/semantic model are data plane - run deploy_fabric.py next.')
output nextSteps array = [
  'python data/fabric-iq/deploy_fabric.py --capacity fabcap26'
  'python data/foundry-iq/index_cm_policies.py'
  'python data/work-iq/provision_seeder_app.py'
  'python data/work-iq/seed_work_iq.py --auth cli --map-users'
  'python data/work-iq/seed_work_iq.py --only mail'
  'python data/work-iq/seed_work_iq.py --only teams'
  'python data/work-iq/seed_work_iq.py --only files'
  'python agent/create_agent.py --create'
]
