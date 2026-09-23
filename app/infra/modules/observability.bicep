// Log Analytics workspace + Application Insights for the Container Apps.
param namePrefix string
param location string
param tags object

resource law 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'log-${namePrefix}'
  location: location
  tags: tags
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: 'appi-${namePrefix}'
  location: location
  tags: tags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: law.id
  }
}

output customerId string = law.properties.customerId
#disable-next-line outputs-should-not-contain-secrets
output sharedKey string = law.listKeys().primarySharedKey
output connectionString string = appInsights.properties.ConnectionString
output workspaceName string = law.name
output appInsightsName string = appInsights.name
