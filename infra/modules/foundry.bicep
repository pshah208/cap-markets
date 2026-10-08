// Azure AI Foundry account + project + model deployment.
//
// The account uses the AIServices kind of Cognitive Services, which is what backs
// Azure AI Foundry. `allowProjectManagement: true` enables the project experience.
//
// The *agent* and its three function tools are data-plane objects created at run
// time by agent/create_agent.py - they cannot be expressed in Bicep.

@description('Foundry (AIServices) account name.')
@minLength(2)
param accountName string

@description('Project name under the account.')
@minLength(2)
param projectName string

@description('Azure region.')
@minLength(1)
param location string

@description('Resource tags.')
param tags object

@description('Project display name shown in the Foundry portal.')
param projectDisplayName string = 'Capital Markets Client Intelligence'

@description('Project description.')
param projectDescription string = 'SYNTHETIC DEMO DATA. Client meeting preparation agent grounded across Work IQ, Fabric IQ, Foundry IQ and Web IQ for a Capital Markets coverage relationship.'

@description('Model deployment name the agent calls.')
param modelDeploymentName string = 'gpt-5.4'

@description('Model name.')
param modelName string = 'gpt-5.4'

@description('Model version. Leave blank to let the platform pick the default.')
param modelVersion string = ''

@description('Deployment SKU.')
@allowed([ 'GlobalStandard', 'DataZoneStandard', 'Standard' ])
param modelSku string = 'GlobalStandard'

@description('Capacity in thousands of tokens per minute.')
param modelCapacity int = 100

@description('Responsible AI policy applied to the deployment.')
param raiPolicyName string = 'Microsoft.DefaultV2'

@description('Version upgrade behaviour.')
@allowed([ 'OnceNewDefaultVersionAvailable', 'OnceCurrentVersionExpired', 'NoAutoUpgrade' ])
param versionUpgradeOption string = 'OnceNewDefaultVersionAvailable'

@description('Deploy the model. Set false if the deployment already exists or quota is unavailable.')
param deployModel bool = true

resource account 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' = {
  name: accountName
  location: location
  tags: tags
  kind: 'AIServices'
  sku: { name: 'S0' }
  identity: { type: 'SystemAssigned' }
  properties: {
    allowProjectManagement: true
    customSubDomainName: accountName
    publicNetworkAccess: 'Enabled'
  }
}

resource project 'Microsoft.CognitiveServices/accounts/projects@2025-04-01-preview' = {
  parent: account
  name: projectName
  location: location
  tags: tags
  identity: { type: 'SystemAssigned' }
  properties: {
    displayName: projectDisplayName
    description: projectDescription
  }
}

resource modelDeployment 'Microsoft.CognitiveServices/accounts/deployments@2025-04-01-preview' = if (deployModel) {
  parent: account
  name: modelDeploymentName
  sku: { name: modelSku, capacity: modelCapacity }
  properties: {
    model: union(
      { format: 'OpenAI', name: modelName },
      empty(modelVersion) ? {} : { version: modelVersion }
    )
    raiPolicyName: raiPolicyName
    versionUpgradeOption: versionUpgradeOption
  }
}

output accountName string = account.name
output accountId string = account.id
output accountEndpoint string = account.properties.endpoint
output projectName string = project.name
output projectEndpoint string = 'https://${account.name}.services.ai.azure.com/api/projects/${project.name}'
output modelDeploymentName string = deployModel ? modelDeployment.name : modelDeploymentName
output accountPrincipalId string = account.identity.principalId
