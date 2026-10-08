// Least-privilege control of the Fabric capacity from the app.
//
// The web app's top bar can pause and resume the capacity Fabric IQ runs on, so
// an F-SKU does not bill while the demo is idle. The BFF's managed identity gets
// a custom role that can ONLY read, suspend and resume capacities - not scale,
// reassign or delete them, which built-in Contributor would allow - and only on
// the one capacity.
//
// The parent explicitly selects the capacity's subscription and resource group.
// No capacity name or operator principal is inferred from the current caller.

targetScope = 'resourceGroup'

@description('Name of the existing Microsoft.Fabric/capacities resource.')
@minLength(3)
@maxLength(63)
param capacityName string

@description('Object (principal) id of the BFF managed identity.')
@minLength(1)
param principalId string

resource capacity 'Microsoft.Fabric/capacities@2023-11-01' existing = {
  name: capacityName
}

var roleName = 'Fabric Capacity Operator (${resourceGroup().name})'

resource operatorRole 'Microsoft.Authorization/roleDefinitions@2022-04-01' = {
  name: guid(resourceGroup().id, 'fabric-capacity-operator')
  properties: {
    roleName: roleName
    description: 'Read, pause (suspend) and resume Microsoft Fabric capacities. Cannot scale, reassign or delete.'
    type: 'CustomRole'
    permissions: [
      {
        actions: [
          'Microsoft.Fabric/capacities/read'
          'Microsoft.Fabric/capacities/suspend/action'
          'Microsoft.Fabric/capacities/resume/action'
        ]
        notActions: []
      }
    ]
    assignableScopes: [
      resourceGroup().id
    ]
  }
}

resource assignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(capacity.id, principalId, operatorRole.id)
  scope: capacity
  properties: {
    roleDefinitionId: operatorRole.id
    principalId: principalId
    principalType: 'ServicePrincipal'
  }
}

output capacityId string = capacity.id
output roleDefinitionId string = operatorRole.id
