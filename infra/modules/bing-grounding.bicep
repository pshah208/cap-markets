// Grounding with Bing Search - the Web IQ layer.
//
// Two resources are needed:
//   1. A Microsoft.Bing/accounts resource of kind 'Bing.Grounding'. This is a
//      GLOBAL resource - the location must be 'global', not the resource group's
//      region, or deployment fails with an unsupported-location error.
//   2. A connection on the Foundry ACCOUNT that points at it, so the agent's
//      BingGroundingTool can resolve the connection by name at run time.
//
// Unlike the other IQ layers there is no data to seed here. Web IQ is live only -
// if this connection is missing the agent's tool returns an explicit
// "unavailable" response rather than answering from model memory.

@description('Name of the Bing grounding account.')
param name string

@description('Resource tags. Note the account itself is global; tags still apply.')
param tags object

@description('Bing grounding SKU. G1 is the only tier for Grounding with Bing Search.')
@allowed([ 'G1' ])
param sku string = 'G1'

@description('Foundry (AIServices) account name the connection is created on.')
param foundryAccountName string

@description('Name of the connection as the agent will reference it.')
param connectionName string

resource bing 'Microsoft.Bing/accounts@2025-05-01-preview' = {
  name: name
  location: 'global'
  tags: tags
  kind: 'Bing.Grounding'
  sku: { name: sku }
}

resource foundryAccount 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' existing = {
  name: foundryAccountName
}

// ApiKey auth against the Bing account's key. The Foundry project reads the
// connection by name; the key never leaves the connection object.
resource connection 'Microsoft.CognitiveServices/accounts/connections@2025-04-01-preview' = {
  parent: foundryAccount
  name: connectionName
  properties: {
    category: 'GroundingWithBingSearch'
    target: bing.properties.endpoint
    authType: 'ApiKey'
    isSharedToAll: true
    credentials: {
      key: bing.listKeys().key1
    }
    metadata: {
      type: 'bing_grounding'
      ApiType: 'Azure'
      ResourceId: bing.id
      location: 'global'
    }
  }
}

output bingAccountName string = bing.name
output bingAccountId string = bing.id
output bingEndpoint string = bing.properties.endpoint
output connectionName string = connection.name
