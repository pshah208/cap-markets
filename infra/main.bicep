// =============================================================================
// Capital Markets Client Intelligence Agent - Azure control-plane infrastructure
// =============================================================================
// SYNTHETIC DEMO DATA. All internal exposures, limits, revenues, ratings,
// covenants and policies in this solution are invented for a demo.
//
// SCOPE OF THIS TEMPLATE
// Bicep can only express ARM control-plane resources. This template deploys:
//
//   * Azure AI Search service        (Foundry IQ store)
//   * Azure AI Foundry account       (agent host)
//   * Foundry project                (agent container)
//   * Model deployment               (the reasoning model)
//   * Grounding with Bing Search     (Web IQ) + its Foundry connection
//   * Microsoft Fabric capacity      (Fabric IQ compute) -- optional
//   * Role assignments               (explicitly selected principals)
//
// DATA-PLANE and Microsoft Graph objects are created by separate scripts:
//   * Fabric workspace, lakehouse, notebooks, Delta tables, semantic model
//                                    -> data/fabric-iq/deploy_fabric.py
//   * AI Search index and policy documents
//                                    -> data/foundry-iq/index_cm_policies.py
//   * Entra app registration and Graph permission grants
//                                    -> data/work-iq/provision_seeder_app.py
//   * M365 mail, Teams messages, SharePoint files, persona job titles
//                                    -> data/work-iq/seed_work_iq.py
//   * Classic Foundry agent and function tools
//                                    -> agent/create_agent.py
//
// Packaging only: validate policy, RBAC, naming, region and SKU against the
// selected target before deployment. No tenant-specific approval is implied.
// Microsoft.Bing/accounts is global; all regional resources use location.
// =============================================================================
targetScope = 'resourceGroup'

@minLength(1)
type principalObjectId = string

// ---------------------------------------------------------------- naming ----
@description('Workload name used in CAF-style resource names.')
@minLength(1)
param workload string = 'cmintel'

@description('Environment: dev | test | prod.')
@allowed([ 'dev', 'test', 'prod' ])
param environmentName string = 'dev'

@description('Explicit Azure region for resources created by this template.')
@minLength(1)
param location string

@description('Additional tags merged onto every resource.')
param extraTags object = {}

// ------------------------------------------------------------ AI Search ----
@description('Create a new Azure AI Search service. False = reference an existing one.')
param createSearch bool = true

@description('Search service name. Blank generates a workload-based name only when createSearch = true; otherwise required.')
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
attaching the index as a portal-native knowledge source enables the portal path.
The scripted agent uses a function tool against the same index.
''')
param createSearchConnection bool = true

@description('AI Search connection name. Blank uses the resolved Search service name, never a preselected service.')
param searchConnectionName string = ''

// --------------------------------------------------------------- Foundry ----
@description('Create a new Foundry (AIServices) account. False = reference an existing one.')
param createFoundry bool = true

@description('Explicit Foundry account name, for both creation and reuse.')
@minLength(2)
param foundryAccountName string

@description('Explicit Foundry project name.')
@minLength(2)
param foundryProjectName string

@description('Deploy the reasoning model. False if it already exists or quota is short.')
param deployModel bool = true

@description('Model deployment name the agent calls.')
@minLength(1)
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

@description('Bing grounding account name. Blank generates a globally unique workload-based name.')
param bingAccountName string = ''

@description('Connection name the agent resolves at run time. Set as BING_GROUNDING_CONNECTION.')
@minLength(1)
param bingConnectionName string = 'bing-grounding-${workload}'

// ---------------------------------------------------------------- Fabric ----
@description('Create a Microsoft Fabric capacity. False = use an explicitly selected existing capacity for Fabric stages.')
param createFabricCapacity bool = false

@description('Explicit Fabric capacity name. Required for creation or any downstream Fabric stage; blank only when Fabric is not used.')
param fabricCapacityName string = ''

@description('Fabric SKU.')
@allowed([ 'F2', 'F4', 'F8', 'F16', 'F32', 'F64' ])
param fabricSkuName string = 'F4'

@description('Entra object IDs set as Fabric capacity admins. At least one is required when createFabricCapacity = true.')
param fabricAdminMembers principalObjectId[] = []

// ------------------------------------------------------------------ RBAC ----
@description('Entra object ID of the principal that will run the agent. Blank skips operator grants; no signed-in caller is selected automatically.')
param agentPrincipalId string = ''

@description('Principal type for the operator role assignments.')
@allowed([ 'User', 'Group', 'ServicePrincipal' ])
param agentPrincipalType string = 'User'

@description('''
Explicit Entra object IDs of Work IQ demo personas. Each is granted Foundry User
at project scope. An empty array grants no persona access. Work IQ only grounds
on content accessible to the signed-in user.
''')
param demoUserPrincipalIds principalObjectId[] = []

// ============================================================== variables ====
var tags = union({
  workload: workload
  environment: environmentName
  solution: 'capital-markets-client-intelligence'
  dataClassification: 'synthetic-demo-data'
  managedBy: 'bicep'
}, extraTags)

var suffix = uniqueString(resourceGroup().id)
var resolvedSearchName = createSearch && empty(searchServiceName) ? toLower('srch-${workload}-${environmentName}-${suffix}') : searchServiceName
var resolvedSearchConnectionName = empty(searchConnectionName) ? resolvedSearchName : searchConnectionName
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
    accountName: foundryAccountName
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

// The connection is a child of the Foundry account.
module bingGrounding 'modules/bing-grounding.bicep' = if (createBingGrounding) {
  name: 'bing-grounding'
  params: {
    name: resolvedBingName
    tags: tags
    foundryAccountName: foundryAccountName
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

// The portal-native path and scripted function tool use the same Search index.
module searchConnection 'modules/search-connection.bicep' = if (createSearchConnection && createSearch) {
  name: 'search-connection'
  params: {
    foundryAccountName: foundryAccountName
    searchServiceName: resolvedSearchName
    connectionName: resolvedSearchConnectionName
  }
  dependsOn: [ search, foundry ]
}

module rbac 'modules/rbac.bicep' = if (!empty(agentPrincipalId) || !empty(demoUserPrincipalIds)) {
  name: 'rbac'
  params: {
    principalId: agentPrincipalId
    principalType: agentPrincipalType
    foundryAccountName: foundryAccountName
    foundryProjectName: foundryProjectName
    searchServiceName: resolvedSearchName
    demoUserPrincipalIds: demoUserPrincipalIds
  }
  dependsOn: [ search, foundry ]
}

// ================================================================ outputs ====
@description('Set as SEARCH_ENDPOINT.')
output searchEndpoint string = createSearch ? search!.outputs.endpoint : 'https://${searchServiceName}.search.windows.net'

output searchServiceName string = resolvedSearchName

@description('AI Search connection name for the portal-native knowledge source. The scripted agent uses a function tool against the same index.')
output searchConnectionName string = createSearchConnection && createSearch ? searchConnection!.outputs.connectionName : 'not-deployed'

@description('Set as SEARCH_INDEX. Created by index_cm_policies.py, not by Bicep.')
output searchIndexName string = 'cm-client-policies'

@description('Set as FOUNDRY_PROJECT_ENDPOINT.')
output foundryProjectEndpoint string = createFoundry
  ? foundry!.outputs.projectEndpoint
  : 'https://${foundryAccountName}.services.ai.azure.com/api/projects/${foundryProjectName}'

output foundryAccountName string = foundryAccountName
output foundryProjectName string = foundryProjectName

@description('Set as FOUNDRY_MODEL.')
output modelDeploymentName string = modelDeploymentName

@description('Set as BING_GROUNDING_CONNECTION. Web IQ is live only - no data is seeded.')
output bingConnectionName string = createBingGrounding ? bingGrounding!.outputs.connectionName : 'not-deployed'

output bingAccountName string = createBingGrounding ? bingGrounding!.outputs.bingAccountName : 'not-deployed'
output fabricCapacityName string = createFabricCapacity ? fabricCapacity!.outputs.name : fabricCapacityName

@description('Data-plane follow-up commands. Run only after target governance and required environment values are validated.')
output nextSteps array = concat(
  empty(fabricCapacityName) ? [] : [
    'python data/fabric-iq/deploy_fabric.py --capacity ${fabricCapacityName}'
  ],
  [
    'python data/foundry-iq/index_cm_policies.py'
    'python data/work-iq/provision_seeder_app.py'
    'python data/work-iq/seed_work_iq.py --auth cli --map-users'
    'python data/work-iq/seed_work_iq.py --only mail'
    'python data/work-iq/seed_work_iq.py --only teams'
    'python data/work-iq/seed_work_iq.py --only files'
    'python agent/create_agent.py --create'
  ]
)
