// Role assignments the agent operator needs across the three IQ layers.
//
// Scoped per-resource rather than at the resource group, so the principal gets
// only what it needs (least privilege).

@description('Entra object ID of the principal running the agent (user or managed identity).')
param principalId string

@description('Principal type. Use ServicePrincipal for managed identities.')
@allowed([ 'User', 'Group', 'ServicePrincipal' ])
param principalType string = 'User'

@description('Foundry (AIServices) account name to grant data-plane access on.')
param foundryAccountName string

@description('Search service name. Blank to skip the search grants.')
param searchServiceName string = ''

@description('Foundry project name. Its managed identity also needs read access to Search.')
param foundryProjectName string = ''

@description('''
Entra object IDs of the Work IQ demo personas who sign in to the Foundry portal to
drive the agent. Each is granted Foundry User at PROJECT scope - the role a human
needs to open the project, create a thread and run the agent. Granting at project
rather than account scope keeps the personas out of the account's other projects.
''')
param demoUserPrincipalIds array = []

// Azure AI User - create threads, run agents, call tools on a Foundry project.
var azureAiUserRoleId = '53ca6127-db72-4b80-b1b0-d745d6d5456d'
// Search Index Data Reader - query an index with Entra auth instead of a key.
var searchIndexDataReaderRoleId = '1407120a-92aa-4202-b7e9-c0e197c71c8f'
// Search Index Data Contributor - upload/merge/delete documents in an index.
// Required by index_cm_policies.py; the Reader role can query but not write, and
// the failure surfaces as a bare 403 on upload_documents rather than as an
// obviously permission-shaped error.
var searchIndexDataContributorRoleId = '8ebe5a00-799e-43f5-93ac-243d3dce84a7'
// Search Service Contributor - create/update indexes with Entra auth.
var searchServiceContributorRoleId = '7ca78c08-252a-4471-8644-bb5ff32d4ba0'
// Cognitive Services OpenAI User - call chat/completions on a model deployment.
var openAiUserRoleId = '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'

resource foundryAccount 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' existing = {
  name: foundryAccountName
}

resource search 'Microsoft.Search/searchServices@2024-06-01-preview' existing = if (!empty(searchServiceName)) {
  name: searchServiceName
}

resource foundryRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: foundryAccount
  name: guid(foundryAccount.id, principalId, azureAiUserRoleId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', azureAiUserRoleId)
    principalId: principalId
    principalType: principalType
  }
}

resource searchReaderRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(searchServiceName)) {
  scope: search
  name: guid(search.id, principalId, searchIndexDataReaderRoleId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', searchIndexDataReaderRoleId)
    principalId: principalId
    principalType: principalType
  }
}

resource searchContributorRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(searchServiceName)) {
  scope: search
  name: guid(search.id, principalId, searchServiceContributorRoleId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', searchServiceContributorRoleId)
    principalId: principalId
    principalType: principalType
  }
}

resource searchDataContributorRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(searchServiceName)) {
  scope: search
  name: guid(search.id, principalId, searchIndexDataContributorRoleId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', searchIndexDataContributorRoleId)
    principalId: principalId
    principalType: principalType
  }
}

// ---------------------------------------------------------------------------
// Service-to-service grants.
//
// Foundry IQ knowledge bases are NOT a one-way call. When the agent invokes
// `knowledge_base_retrieve`, the SEARCH service calls back into the model
// deployment to plan and rerank the query. If the Search service's managed
// identity has no data action on the Foundry account, retrieval fails at run
// time with a 401 that names the Search MI - which looks like an agent problem
// but is a Search-to-Foundry problem:
//
//   The principal `<search-mi>` lacks the required data action
//   `Microsoft.CognitiveServices/accounts/OpenAI/deployments/chat/completions/action`
//
// The reverse direction (Foundry -> Search) works over the connection's API key,
// but is granted here as well so the setup keeps working if that connection is
// ever switched to Entra auth.
// ---------------------------------------------------------------------------

resource foundryProject 'Microsoft.CognitiveServices/accounts/projects@2025-04-01-preview' existing = if (!empty(foundryProjectName)) {
  parent: foundryAccount
  name: foundryProjectName
}

// Search -> Foundry: lets knowledge_base_retrieve call chat/completions.
resource searchToFoundry 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(searchServiceName)) {
  scope: foundryAccount
  name: guid(foundryAccount.id, search!.id, openAiUserRoleId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', openAiUserRoleId)
    principalId: search!.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// Foundry account -> Search: query the index with Entra auth.
resource foundryToSearch 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(searchServiceName)) {
  scope: search
  name: guid(search!.id, foundryAccount.id, searchIndexDataReaderRoleId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', searchIndexDataReaderRoleId)
    principalId: foundryAccount.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// Foundry PROJECT -> Search. The project carries its own managed identity,
// separate from the account's, and it is the one the agent runs as.
resource projectToSearch 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(searchServiceName) && !empty(foundryProjectName)) {
  scope: search
  name: guid(search!.id, foundryProject!.id, searchIndexDataReaderRoleId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', searchIndexDataReaderRoleId)
    principalId: foundryProject!.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// Work IQ demo personas -> Foundry project.
//
// Foundry User is the role a HUMAN needs to sign in to the project, create a
// thread and run the agent. It is distinct from the service-to-service grants
// above: those let the resources call each other, this lets a person drive the
// demo. The driver in particular must be able to sign in, because Work IQ only
// grounds on content the signed-in user can access.
resource demoUserProjectAccess 'Microsoft.Authorization/roleAssignments@2022-04-01' = [
  for pid in demoUserPrincipalIds: if (!empty(foundryProjectName)) {
    scope: foundryProject
    name: guid(foundryProject!.id, pid, azureAiUserRoleId)
    properties: {
      roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', azureAiUserRoleId)
      principalId: pid
      principalType: 'User'
    }
  }
]
