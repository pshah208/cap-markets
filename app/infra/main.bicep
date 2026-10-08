// =============================================================================
// Capital Markets Client Intelligence - frontend delivery app
// =============================================================================
// SYNTHETIC DEMO DATA. Deploys into the explicitly selected resource group:
//
//   * Container Registry
//   * Log Analytics + Application Insights
//   * Container Apps environment
//   * ca-<prefix>-bff   FastAPI, INTERNAL ingress, performs the OBO exchange
//   * ca-<prefix>-web   nginx + React SPA, EXTERNAL ingress, proxies /api -> bff
//
// Entra app registrations are NOT ARM resources. Pass their explicitly selected
// tenant, client ID, scope and secret as parameters; no caller is auto-granted.
// =============================================================================
targetScope = 'resourceGroup'

@description('Base name used in resource names.')
@minLength(1)
param namePrefix string = 'cmci'

@description('Explicit Azure region.')
@minLength(1)
param location string

@description('Extra tags merged onto every resource.')
param extraTags object = {}

@description('Container image for the SPA. Placeholder until the first build+push.')
param webImage string = 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'

@description('Container image for the BFF.')
param bffImage string = 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'

// --- Entra (from provision_app_registrations.py) ---
@description('Explicit Entra tenant ID. Must match the selected deployment tenant.')
@minLength(1)
param aadTenantId string

@description('BFF app registration client ID.')
@minLength(1)
param aadClientId string

@description('BFF client secret. Supply securely; never store in a tracked parameter file.')
@secure()
@minLength(1)
param aadClientSecret string

@description('API scope the SPA requests, e.g. api://<bff-client-id>/access_as_user.')
@minLength(1)
param aadApiScope string

// --- Foundry ---
@description('Explicit Foundry project endpoint. Must match foundryAccountName and foundryProjectName.')
@minLength(1)
param foundryProjectEndpoint string

@description('Explicit Foundry account name.')
@minLength(2)
param foundryAccountName string

@description('Required named Responses agent to invoke. A classic assistant ID is not a named agent.')
@minLength(1)
param foundryAgentName string

@description('Optional named Responses agents. Empty disables the corresponding live feature.')
param scenarioAgentName string = ''
param missionAgentName string = ''
param barrierAgentName string = ''

@description('Explicit Foundry project name.')
@minLength(2)
param foundryProjectName string

@description('Grant the app managed identity Azure AI User on the selected Foundry account. False preserves the option to skip this grant.')
param assignFoundryRole bool = true

@description('Connect the selected Foundry project to this deployment Application Insights component. False skips the connection.')
param connectFoundryAppInsights bool = true

@description('Run the BFF without Azure calls. UI development only.')
param mockMode bool = false

// --- Fabric ---
@description('Explicit Fabric workspace ID.')
@minLength(1)
param fabricWorkspaceId string

@description('Explicit Fabric lakehouse ID.')
@minLength(1)
param fabricLakehouseId string

@description('Explicit Fabric semantic model ID.')
@minLength(1)
param fabricSemanticModelId string

@description('Full ARM resource ID of the existing Fabric capacity. Blank disables capacity control and its role assignment.')
param fabricCapacityResourceId string = ''

@description('Comma-separated UPNs allowed to pause/resume the capacity. Blank disables control unless allowAllFabricCapacityOperators is explicitly true.')
param fabricCapacityOperators string = ''

@description('Explicitly allow every signed-in app user to pause/resume the capacity. Default false; prefer an operator allow-list.')
param allowAllFabricCapacityOperators bool = false

var tags = union({
  workload: namePrefix
  solution: 'capital-markets-client-intelligence'
  component: 'frontend'
  dataClassification: 'synthetic-demo-data'
  managedBy: 'bicep'
}, extraTags)

var hasFabricCapacityOperators = !empty(filter(split(fabricCapacityOperators, ','), operator => !empty(trim(operator))))
var fabricCapacityControlEnabled = !empty(fabricCapacityResourceId) && (hasFabricCapacityOperators || allowAllFabricCapacityOperators)

module observability 'modules/observability.bicep' = {
  name: 'observability'
  params: { namePrefix: namePrefix, location: location, tags: tags }
}

module registry 'modules/registry.bicep' = {
  name: 'registry'
  params: { namePrefix: namePrefix, location: location, tags: tags }
}

module apps 'modules/container-apps.bicep' = {
  name: 'container-apps'
  params: {
    namePrefix: namePrefix
    location: location
    tags: tags
    logAnalyticsCustomerId: observability.outputs.customerId
    logAnalyticsSharedKey: observability.outputs.sharedKey
    logAnalyticsWorkspaceName: observability.outputs.workspaceName
    appInsightsConnectionString: observability.outputs.connectionString
    acrLoginServer: registry.outputs.loginServer
    acrName: registry.outputs.name
    webImage: webImage
    bffImage: bffImage
    aadTenantId: aadTenantId
    aadClientId: aadClientId
    aadClientSecret: aadClientSecret
    aadApiScope: aadApiScope
    foundryProjectEndpoint: foundryProjectEndpoint
    foundryAccountName: assignFoundryRole ? foundryAccountName : ''
    foundryAgentName: foundryAgentName
    scenarioAgentName: scenarioAgentName
    missionAgentName: missionAgentName
    barrierAgentName: barrierAgentName
    mockMode: mockMode
    fabricWorkspaceId: fabricWorkspaceId
    fabricLakehouseId: fabricLakehouseId
    fabricSemanticModelId: fabricSemanticModelId
    fabricCapacityResourceId: fabricCapacityResourceId
    fabricCapacityOperators: fabricCapacityOperators
    allowAllFabricCapacityOperators: allowAllFabricCapacityOperators
  }
}

// Capacity-only read/suspend/resume, optionally in another resource group.
module fabricCapacityControl 'modules/fabric-capacity-control.bicep' = if (fabricCapacityControlEnabled) {
  name: 'fabric-capacity-control'
  scope: resourceGroup(split(fabricCapacityResourceId, '/')[2], split(fabricCapacityResourceId, '/')[4])
  params: {
    capacityName: last(split(fabricCapacityResourceId, '/'))
    principalId: apps.outputs.identityPrincipalId
  }
}

// The project's telemetry and the app's telemetry share one component.
module foundryAppInsights 'modules/foundry-appinsights-connection.bicep' = if (connectFoundryAppInsights) {
  name: 'foundry-appinsights-connection'
  params: {
    foundryAccountName: foundryAccountName
    foundryProjectName: foundryProjectName
    appInsightsName: observability.outputs.appInsightsName
  }
}

output acrName string = registry.outputs.name
output acrLoginServer string = registry.outputs.loginServer
output webUrl string = apps.outputs.webUrl
output webFqdn string = apps.outputs.webFqdn
output bffFqdn string = apps.outputs.bffFqdn
output identityPrincipalId string = apps.outputs.identityPrincipalId
output foundryAccountName string = foundryAccountName
output foundryProjectName string = foundryProjectName
output foundryAgentName string = foundryAgentName
output fabricCapacityResourceId string = fabricCapacityResourceId
output fabricWorkspaceId string = fabricWorkspaceId
output fabricLakehouseId string = fabricLakehouseId
output fabricSemanticModelId string = fabricSemanticModelId
output fabricCapacityControlEnabled bool = fabricCapacityControlEnabled

@description('Add this to the SPA app registration as a redirect URI.')
output redirectUriToAdd string = apps.outputs.webUrl
