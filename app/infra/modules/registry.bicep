// Container registry for the web and BFF images.
param namePrefix string
param location string
param tags object

@allowed([ 'Basic', 'Standard', 'Premium' ])
param sku string = 'Basic'

resource acr 'Microsoft.ContainerRegistry/registries@2023-11-01-preview' = {
  // Registry names are alphanumeric only, max 50 chars.
  name: toLower(replace('cr${namePrefix}${uniqueString(resourceGroup().id)}', '-', ''))
  location: location
  tags: tags
  sku: { name: sku }
  properties: {
    adminUserEnabled: false
    publicNetworkAccess: 'Enabled'
  }
}

output name string = acr.name
output loginServer string = acr.properties.loginServer
output id string = acr.id
