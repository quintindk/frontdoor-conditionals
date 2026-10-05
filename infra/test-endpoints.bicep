targetScope = 'resourceGroup'

// Fixed controls avoid mixing old/new route settings during global propagation.
@minLength(3)
@maxLength(12)
param labName string = 'conditional'
param profileName string
param originGroupName string = 'fixture'

resource profile 'Microsoft.Cdn/profiles@2024-09-01' existing = {
  name: profileName
}

resource group 'Microsoft.Cdn/profiles/originGroups@2024-09-01' existing = {
  parent: profile
  name: originGroupName
}

var controls = [
  { name: 'pass', cache: false }
  { name: 'gzip', cache: true }
]

resource endpoints 'Microsoft.Cdn/profiles/afdEndpoints@2024-09-01' = [for control in controls: {
  parent: profile
  name: '${labName}-${control.name}-${uniqueString(resourceGroup().id)}'
  location: 'global'
  properties: {
    enabledState: 'Enabled'
  }
}]

resource routes 'Microsoft.Cdn/profiles/afdEndpoints/routes@2024-09-01' = [for (control, index) in controls: {
  parent: endpoints[index]
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
    ...(control.cache ? {
      cacheConfiguration: {
        queryStringCachingBehavior: 'UseQueryString'
        compressionSettings: {
          isCompressionEnabled: true
          contentTypesToCompress: ['application/json']
        }
      }
    } : {})
  }
}]

output endpoints array = [for (control, index) in controls: {
  control: control.name
  name: endpoints[index].name
  url: 'https://${endpoints[index].properties.hostName}'
}]
