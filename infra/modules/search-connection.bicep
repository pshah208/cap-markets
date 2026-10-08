// Azure AI Search connection on the Foundry account.
//
// WHY THIS EXISTS SEPARATELY FROM THE AGENT'S FUNCTION TOOL
//
// The agent created by agent/create_agent.py reaches AI Search through a FUNCTION
// tool, which is deliberate: a function tool forces a deterministic call and lets
// the tool shape its own response (the Fabric tool, for instance, always returns
// the covenant position alongside the single-name limit, which is the point of
// the whole demo).
//
// But custom function tools CANNOT execute in the Azure AI Foundry portal
// playground - the portal has no runtime to service `requires_action` and submit
// tool outputs, so an agent built only from function tools appears to stall there.
// Only natively-hosted tools (Bing grounding, AI Search knowledge, file search,
// code interpreter) run in the portal.
//
// This connection therefore exists so the SAME index can also be attached as a
// portal-native knowledge source. The result is two working demo paths:
//
//   * CLI   - python create_agent.py --chat   -> all four IQ layers via function tools
//   * Portal- Foundry playground              -> Foundry IQ + Web IQ natively
//
// AUTH. ApiKey, matching what the portal creates by hand. The Foundry account and
// project managed identities are separately granted Search Index Data Reader in
// rbac.bicep, so switching this connection to Entra auth later needs no new grants.

@description('Foundry (AIServices) account name the connection is created on.')
@minLength(2)
param foundryAccountName string

@description('Azure AI Search service name to connect to.')
@minLength(1)
param searchServiceName string

@description('Connection name as it will appear in the Foundry portal.')
@minLength(1)
param connectionName string

resource foundryAccount 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' existing = {
  name: foundryAccountName
}

resource search 'Microsoft.Search/searchServices@2024-06-01-preview' existing = {
  name: searchServiceName
}

resource connection 'Microsoft.CognitiveServices/accounts/connections@2025-04-01-preview' = {
  parent: foundryAccount
  name: connectionName
  properties: {
    category: 'CognitiveSearch'
    target: 'https://${searchServiceName}.search.windows.net/'
    authType: 'ApiKey'
    isSharedToAll: true
    credentials: {
      key: search.listAdminKeys().primaryKey
    }
    metadata: {
      ApiType: 'Azure'
      ResourceId: search.id
      type: 'azure_ai_search'
      displayName: searchServiceName
    }
  }
}

output connectionName string = connection.name
output connectionId string = connection.id
