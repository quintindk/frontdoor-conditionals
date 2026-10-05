targetScope = 'resourceGroup'

param endpointName string
param profileName string
param originGroupName string
param cachingEnabled bool
param compressionEnabled bool = false

resource profile 'Microsoft.Cdn/profiles@2024-09-01' existing = {
  name: profileName
}

resource endpoint 'Microsoft.Cdn/profiles/afdEndpoints@2024-09-01' existing = {
  parent: profile
  name: endpointName
}

resource group 'Microsoft.Cdn/profiles/originGroups@2024-09-01' existing = {
  parent: profile
  name: originGroupName
}

resource route 'Microsoft.Cdn/profiles/afdEndpoints/routes@2024-09-01' = {
  parent: endpoint
  name: 'objects'
  properties: {
    originGroup: { id: group.id }
    supportedProtocols: ['Https']
    patternsToMatch: ['/objects/*']
    forwardingProtocol: 'HttpsOnly'
    httpsRedirect: 'Disabled'
    linkToDefaultDomain: 'Enabled'
    enabledState: 'Enabled'
    ruleSets: []
    ...(cachingEnabled ? {
      cacheConfiguration: {
        queryStringCachingBehavior: 'UseQueryString'
        compressionSettings: {
          isCompressionEnabled: compressionEnabled
          contentTypesToCompress: ['application/json']
        }
      }
    } : {})
  }
}
