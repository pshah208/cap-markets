// Container Apps environment + the web (SPA/nginx) and BFF apps.
//
// Ingress topology: the web app is external; the BFF is INTERNAL only and is
// reached via nginx inside the environment. That keeps the BFF and its client
// secret off the public internet, and removes CORS from the picture entirely.

@minLength(1)
param namePrefix string
@minLength(1)
param location string
param tags object

param logAnalyticsCustomerId string
@secure()
param logAnalyticsSharedKey string
param appInsightsConnectionString string

param acrLoginServer string
param acrName string
param webImage string
param bffImage string

// --- Entra / OBO ---
@minLength(1)
param aadTenantId string
@minLength(1)
param aadClientId string
@secure()
@minLength(1)
param aadClientSecret string
@minLength(1)
param aadApiScope string

// --- Foundry ---
@minLength(1)
param foundryProjectEndpoint string
param foundryAccountName string = ''
@minLength(1)
param foundryAgentName string
param scenarioAgentName string = ''
param missionAgentName string = ''
param barrierAgentName string = ''
param mockMode bool = false

@description('Log Analytics workspace name, so the BFF can read the Foundry traces it holds.')
param logAnalyticsWorkspaceName string = ''

@description('Days of Foundry traces the agent-economics slide reports on.')
param telemetryWindowDays int = 7

@description('Days of billed Azure cost the agent-economics slide reports on.')
param costWindowDays int = 30

@description('Explicit Fabric workspace ID.')
@minLength(1)
param fabricWorkspaceId string

@description('Explicit Fabric lakehouse ID.')
@minLength(1)
param fabricLakehouseId string

@description('Explicit Fabric semantic model ID.')
@minLength(1)
param fabricSemanticModelId string

@description('Full ARM resource ID of the Fabric capacity. Blank hides the control.')
param fabricCapacityResourceId string = ''

@description('Comma-separated UPNs allowed to pause/resume. Blank disables control unless all-user access is explicitly enabled.')
param fabricCapacityOperators string = ''

@description('Explicit opt-in to let all signed-in app users operate the capacity.')
param allowAllFabricCapacityOperators bool = false

var hasFabricCapacityOperators = !empty(filter(split(fabricCapacityOperators, ','), operator => !empty(trim(operator))))
var fabricCapacityControlEnabled = !empty(fabricCapacityResourceId) && (hasFabricCapacityOperators || allowAllFabricCapacityOperators)

resource uami 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-${namePrefix}'
  location: location
  tags: tags
}

resource acr 'Microsoft.ContainerRegistry/registries@2023-11-01-preview' existing = {
  name: acrName
}

var acrPullRoleId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d')
resource acrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acr.id, uami.id, acrPullRoleId)
  scope: acr
  properties: {
    principalId: uami.properties.principalId
    roleDefinitionId: acrPullRoleId
    principalType: 'ServicePrincipal'
  }
}

// Azure AI User on the Foundry account. Only used for the optional app-identity
// fallback and for health checks - user requests go through On-Behalf-Of.
resource foundry 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' existing = if (!empty(foundryAccountName)) {
  name: foundryAccountName
}
var azureAiUserRoleId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '53ca6127-db72-4b80-b1b0-d745d6d5456d')
resource aiUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(foundryAccountName)) {
  name: guid(foundryAccountName, uami.id, azureAiUserRoleId)
  scope: foundry
  properties: {
    principalId: uami.properties.principalId
    roleDefinitionId: azureAiUserRoleId
    principalType: 'ServicePrincipal'
  }
}

// Monitoring Reader on the workspace, so chapter 12 can read the Foundry
// project's own gen-AI traces (token usage, latency, tool spans) rather than
// this app inventing telemetry of its own. Read-only, workspace-scoped.
resource law 'Microsoft.OperationalInsights/workspaces@2023-09-01' existing = if (!empty(logAnalyticsWorkspaceName)) {
  name: logAnalyticsWorkspaceName
}
var monitoringReaderRoleId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '43d0d8ad-25c7-4714-9337-8ba259a9fe05')
resource monitoringReader 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(logAnalyticsWorkspaceName)) {
  name: guid(logAnalyticsWorkspaceName, uami.id, monitoringReaderRoleId)
  scope: law
  properties: {
    principalId: uami.properties.principalId
    roleDefinitionId: monitoringReaderRoleId
    principalType: 'ServicePrincipal'
  }
}

// Cost Management Reader on the resource group, so chapter 12 can show what
// Azure actually billed alongside the token estimate. Read-only, and scoped to
// this resource group rather than the subscription.
var costReaderRoleId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '72fafb9e-0641-4937-9268-a91bfd8191a3')
resource costReader 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(resourceGroup().id, uami.id, costReaderRoleId)
  properties: {
    principalId: uami.properties.principalId
    roleDefinitionId: costReaderRoleId
    principalType: 'ServicePrincipal'
  }
}

resource env 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: 'cae-${namePrefix}'
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalyticsCustomerId
        sharedKey: logAnalyticsSharedKey
      }
    }
  }
}

// ---------------------------------------------------------------- BFF ----- //
resource bff 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'ca-${namePrefix}-bff'
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${uami.id}': {} }
  }
  properties: {
    managedEnvironmentId: env.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        // Internal only. nginx in the web app proxies /api to it.
        external: false
        targetPort: 8000
        transport: 'auto'
        allowInsecure: false
      }
      registries: [
        { server: acrLoginServer, identity: uami.id }
      ]
      secrets: [
        { name: 'aad-client-secret', value: aadClientSecret }
      ]
    }
    template: {
      containers: [
        {
          name: 'bff'
          image: bffImage
          resources: { cpu: json('0.5'), memory: '1Gi' }
          env: [
            { name: 'AAD_TENANT_ID', value: aadTenantId }
            { name: 'AAD_CLIENT_ID', value: aadClientId }
            { name: 'AAD_CLIENT_SECRET', secretRef: 'aad-client-secret' }
            { name: 'AAD_API_SCOPE', value: aadApiScope }
            { name: 'FOUNDRY_PROJECT_ENDPOINT', value: foundryProjectEndpoint }
            { name: 'FOUNDRY_AGENT_NAME', value: foundryAgentName }
            { name: 'SCENARIO_AGENT_NAME', value: scenarioAgentName }
            { name: 'MISSION_AGENT_NAME', value: missionAgentName }
            { name: 'BARRIER_AGENT_NAME', value: barrierAgentName }
            { name: 'MOCK_MODE', value: string(mockMode) }
            { name: 'AZURE_CLIENT_ID', value: uami.properties.clientId }
            { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: appInsightsConnectionString }
            { name: 'LOG_ANALYTICS_WORKSPACE_ID', value: logAnalyticsCustomerId }
            { name: 'TELEMETRY_WINDOW_DAYS', value: string(telemetryWindowDays) }
            { name: 'COST_SCOPE', value: resourceGroup().id }
            { name: 'COST_WINDOW_DAYS', value: string(costWindowDays) }
            { name: 'FABRIC_WORKSPACE_ID', value: fabricWorkspaceId }
            { name: 'FABRIC_LAKEHOUSE_ID', value: fabricLakehouseId }
            { name: 'FABRIC_SEMANTIC_MODEL_ID', value: fabricSemanticModelId }
            { name: 'FABRIC_CAPACITY_ID', value: fabricCapacityControlEnabled ? fabricCapacityResourceId : '' }
            { name: 'FABRIC_CAPACITY_OPERATORS', value: fabricCapacityOperators }
          ]
          probes: [
            {
              type: 'Liveness'
              httpGet: { path: '/health', port: 8000 }
              initialDelaySeconds: 10
              periodSeconds: 30
            }
          ]
        }
      ]
      scale: { minReplicas: 1, maxReplicas: 3 }
    }
  }
}

// ---------------------------------------------------------------- web ----- //
resource web 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'ca-${namePrefix}-web'
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${uami.id}': {} }
  }
  properties: {
    managedEnvironmentId: env.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 8080
        transport: 'auto'
        allowInsecure: false
        corsPolicy: {
          allowedOrigins: [ '*' ]
          allowedMethods: [ 'GET', 'POST', 'OPTIONS' ]
          allowedHeaders: [ '*' ]
        }
      }
      registries: [
        { server: acrLoginServer, identity: uami.id }
      ]
    }
    template: {
      containers: [
        {
          name: 'web'
          image: webImage
          resources: { cpu: json('0.25'), memory: '0.5Gi' }
          env: [
            // Intra-environment call by app name over plain HTTP. Using the
            // internal HTTPS FQDN instead requires SNI configuration in nginx
            // (proxy_ssl_server_name) and otherwise fails the TLS handshake,
            // which surfaces as a 502 on every /api request.
            { name: 'BFF_URL', value: 'http://${bff.name}' }
          ]
        }
      ]
      scale: { minReplicas: 1, maxReplicas: 3 }
    }
  }
}

output webFqdn string = web.properties.configuration.ingress.fqdn
output webUrl string = 'https://${web.properties.configuration.ingress.fqdn}'
output bffFqdn string = bff.properties.configuration.ingress.fqdn
output identityPrincipalId string = uami.properties.principalId
output identityClientId string = uami.properties.clientId
output environmentName string = env.name
