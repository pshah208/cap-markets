// Microsoft Fabric capacity - the compute behind the Fabric IQ layer.
//
// Only the *capacity* is an ARM resource. The workspace, lakehouse, notebooks,
// Delta tables and semantic model are Fabric data-plane objects with no ARM
// provider - create them with data/fabric-iq/deploy_fabric.py.
//
// Capacity bills while Active. Suspend it between demos:
//   az rest --method post --url "https://management.azure.com<id>/suspend?api-version=2023-11-01"

@description('Capacity name (lowercase alphanumeric, 3-63 chars).')
param name string

@description('Azure region.')
param location string

@description('Resource tags.')
param tags object

@description('Fabric SKU. F2 suits a single-presenter demo; F4+ for concurrency.')
@allowed([ 'F2', 'F4', 'F8', 'F16', 'F32', 'F64' ])
param skuName string = 'F2'

@description('Entra object IDs (users or groups) set as capacity administrators. Must contain at least one.')
param adminMembers array

resource capacity 'Microsoft.Fabric/capacities@2023-11-01' = {
  name: name
  location: location
  tags: tags
  sku: { name: skuName, tier: 'Fabric' }
  properties: {
    administration: { members: adminMembers }
  }
}

output name string = capacity.name
output id string = capacity.id
output sku string = skuName
