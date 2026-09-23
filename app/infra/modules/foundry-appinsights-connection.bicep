// Application Insights connection on the Foundry PROJECT.
//
// This is what lets the Foundry portal show tracing and evaluation telemetry for
// the project alongside the app's own telemetry, rather than the two living in
// separate places. RBC's project has the equivalent connection; without it the
// Monitoring blade in the portal has nothing to bind to.
//
// Note the scope: unlike the AI Search connection (which hangs off the ACCOUNT),
// this one hangs off the PROJECT - `accounts/projects/connections`. Creating it
// on the account instead silently produces a connection the project cannot see.
//
// AUTH. ApiKey. The credential is the component's own connection string - the
// portal sends the same thing. It reads back as null because the service masks
// it, which is why copying a GET response into Bicep produces
// "Credentials Property can't be empty for auth type ApiKey" on create.

@description('Foundry (AIServices) account name.')
param foundryAccountName string

@description('Foundry project name the connection is created on.')
param foundryProjectName string

@description('Application Insights component name.')
param appInsightsName string

@description('Connection name as it appears in the Foundry portal.')
param connectionName string = appInsightsName

resource appInsights 'Microsoft.Insights/components@2020-02-02' existing = {
  name: appInsightsName
}

resource project 'Microsoft.CognitiveServices/accounts/projects@2025-04-01-preview' existing = {
  name: '${foundryAccountName}/${foundryProjectName}'
}

resource connection 'Microsoft.CognitiveServices/accounts/projects/connections@2025-04-01-preview' = {
  parent: project
  name: connectionName
  properties: {
    category: 'AppInsights'
    target: appInsights.id
    authType: 'ApiKey'
    isSharedToAll: false
    credentials: {
      key: appInsights.properties.ConnectionString
    }
    metadata: {
      ApiType: 'Azure'
      ResourceId: appInsights.id
    }
  }
}

output connectionName string = connection.name
output connectionId string = connection.id
