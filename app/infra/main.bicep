// =============================================================================
// BMO Capital Markets Client Intelligence - frontend delivery app
// =============================================================================
// SYNTHETIC DEMO DATA. BMO Capital Markets is a branding label only.
//
// Deploys into rg-cmintel-demo alongside the existing Foundry account/project:
//
//   * Container Registry
//   * Log Analytics + Application Insights
//   * Container Apps environment
//   * ca-<prefix>-bff   FastAPI, INTERNAL ingress, performs the OBO exchange
//   * ca-<prefix>-web   nginx + React SPA, EXTERNAL ingress, proxies /api -> bff
//
// The two Entra app registrations are NOT ARM resources - create them first with
//   python infra/provision_app_registrations.py
// and pass the resulting ids/secret in as parameters.
// =============================================================================

targetScope = 'resourceGroup'

@description('Base name used in resource names.')
param namePrefix string = 'cmci'

@description('Azure region.')
param location string = resourceGroup().location

@description('Extra tags merged onto every resource.')
param extraTags object = {}

@description('Container image for the SPA. Placeholder until the first build+push.')
param webImage string = 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'

@description('Container image for the BFF.')
param bffImage string = 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'

// --- Entra (from provision_app_registrations.py) ---
@description('Tenant id.')
param aadTenantId string = subscription().tenantId

@description('BFF app registration client id.')
param aadClientId string

@description('BFF client secret.')
@secure()
param aadClientSecret string

@description('API scope the SPA requests, e.g. api://<bff-client-id>/access_as_user')
param aadApiScope string

// --- Foundry ---
@description('Foundry project endpoint the agent lives in.')
param foundryProjectEndpoint string

@description('Foundry account name, for the role assignment. Blank to skip.')
param foundryAccountName string = ''

@description('Agent name to invoke.')
param foundryAgentName string = 'Agent-cap-market'

@description('''
Foundry project name. Used only to create the Application Insights connection on
the project, so Foundry portal tracing and the app's own telemetry land in one
component. Blank to skip.
''')
param foundryProjectName string = 'proj-client-intelligence'

@description('Run the BFF without Azure calls. UI development only.')
param mockMode bool = false

var tags = union({
  workload: namePrefix
  solution: 'capital-markets-client-intelligence'
  component: 'frontend'
  dataClassification: 'synthetic-demo-data'
  managedBy: 'bicep'
}, extraTags)

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
    foundryAccountName: foundryAccountName
    foundryAgentName: foundryAgentName
    mockMode: mockMode
  }
}

// Point the Foundry project's telemetry at the same component the apps write to,
// so a run's trace and the request that produced it are in one place.
module foundryAppInsights 'modules/foundry-appinsights-connection.bicep' = if (!empty(foundryAccountName) && !empty(foundryProjectName)) {
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

@description('Add this to the SPA app registration as a redirect URI.')
output redirectUriToAdd string = apps.outputs.webUrl
