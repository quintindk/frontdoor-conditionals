targetScope = 'resourceGroup'

@description('Use the same lab name for both templates. Lower-case letters, digits and hyphens only.')
@minLength(3)
@maxLength(12)
param labName string = 'conditional'

param location string

param owner string

@description('Review/teardown date (YYYY-MM-DD), or unscheduled when no date is agreed. A tag, not automatic deletion.')
param expiresOn string

var tags = {
  workload: 'frontdoor-conditionals'
  environment: 'lab'
  owner: owner
  expiresOn: expiresOn
}

resource registry 'Microsoft.ContainerRegistry/registries@2025-04-01' = {
  name: 'acr${uniqueString(resourceGroup().id, labName)}'
  location: location
  tags: tags
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: false
    anonymousPullEnabled: false
    publicNetworkAccess: 'Enabled'
    policies: {
      azureADAuthenticationAsArmPolicy: {
        status: 'enabled'
      }
    }
  }
}

resource imagePullIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: '${labName}-pull'
  location: location
  tags: tags
}

var acrPullRoleId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d')

resource acrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(registry.id, imagePullIdentity.id, acrPullRoleId)
  scope: registry
  properties: {
    roleDefinitionId: acrPullRoleId
    principalId: imagePullIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

output registryName string = registry.name
output registryLoginServer string = registry.properties.loginServer
output imagePullIdentityName string = imagePullIdentity.name
