targetScope = 'resourceGroup'

@description('Use the same lab name as registry.bicep. Lower-case letters, digits and hyphens only.')
@minLength(3)
@maxLength(12)
param labName string = 'conditional'

@description('Region for the origin resources. Must match the existing subnet.')
param location string

param owner string

@description('Review/teardown date (YYYY-MM-DD), or unscheduled when no date is agreed. Does not stop billing or delete resources.')
param expiresOn string

@description('Existing dedicated subnet in this subscription and region, /27 or larger, delegated to Microsoft.App/environments.')
param infrastructureSubnetId string

@description('Registry created by registry.bicep in this resource group.')
param registryName string

@description('User-assigned identity created by registry.bicep, with AcrPull already granted.')
param imagePullIdentityName string

@description('Immutable SHA-256 digest of the linux/amd64 frontdoor-origin image, including sha256:.')
@minLength(71)
@maxLength(71)
param originImageDigest string

param cachingEnabled bool = true
param compressionEnabled bool = false

var tags = {
  workload: 'frontdoor-conditionals'
  environment: 'lab'
  owner: owner
  expiresOn: expiresOn
}

resource registry 'Microsoft.ContainerRegistry/registries@2025-04-01' existing = {
  name: registryName
}

resource imagePullIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' existing = {
  name: imagePullIdentityName
}

resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: '${labName}-logs'
  location: location
  tags: tags
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
    workspaceCapping: {
      dailyQuotaGb: 1
    }
  }
}

resource environment 'Microsoft.App/managedEnvironments@2025-01-01' = {
  name: '${labName}-env'
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logs.properties.customerId
        sharedKey: logs.listKeys().primarySharedKey
      }
    }
    vnetConfiguration: {
      infrastructureSubnetId: infrastructureSubnetId
      internal: false
    }
    workloadProfiles: [
      {
        name: 'Consumption'
        workloadProfileType: 'Consumption'
      }
    ]
    zoneRedundant: false
  }
}

resource originApp 'Microsoft.App/containerApps@2025-01-01' = {
  name: '${labName}-origin'
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${imagePullIdentity.id}': {}
    }
  }
  properties: {
    environmentId: environment.id
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        allowInsecure: false
        targetPort: 8080
        transport: 'http'
        stickySessions: {
          affinity: 'none'
        }
        traffic: [
          {
            latestRevision: true
            weight: 100
          }
        ]
      }
      registries: [
        {
          server: registry.properties.loginServer
          identity: imagePullIdentity.id
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'origin'
          image: '${registry.properties.loginServer}/frontdoor-origin@${originImageDigest}'
          resources: {
            cpu: json('0.25')
            memory: '0.5Gi'
          }
          probes: [
            {
              type: 'Readiness'
              httpGet: {
                path: '/health'
                port: 8080
                scheme: 'HTTP'
              }
              initialDelaySeconds: 1
              periodSeconds: 10
            }
            {
              type: 'Liveness'
              httpGet: {
                path: '/health'
                port: 8080
                scheme: 'HTTP'
              }
              initialDelaySeconds: 5
              periodSeconds: 30
            }
          ]
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 1
      }
    }
  }
}

resource frontDoor 'Microsoft.Cdn/profiles@2024-09-01' = {
  name: '${labName}-afd'
  location: 'global'
  tags: tags
  sku: {
    name: 'Standard_AzureFrontDoor'
  }
  properties: {
    originResponseTimeoutSeconds: 30
  }
}

resource endpoint 'Microsoft.Cdn/profiles/afdEndpoints@2024-09-01' = {
  parent: frontDoor
  name: '${labName}-${uniqueString(resourceGroup().id)}'
  location: 'global'
  tags: tags
  properties: {
    enabledState: 'Enabled'
  }
}

resource originGroup 'Microsoft.Cdn/profiles/originGroups@2024-09-01' = {
  parent: frontDoor
  name: 'fixture'
  properties: {
    sessionAffinityState: 'Disabled'
    healthProbeSettings: {
      probePath: '/health'
      probeRequestType: 'GET'
      probeProtocol: 'Https'
      probeIntervalInSeconds: 240
    }
    loadBalancingSettings: {
      sampleSize: 4
      successfulSamplesRequired: 3
      additionalLatencyInMilliseconds: 50
    }
  }
}

resource origin 'Microsoft.Cdn/profiles/originGroups/origins@2024-09-01' = {
  parent: originGroup
  name: 'container-app'
  properties: {
    hostName: originApp.properties.configuration.ingress.fqdn
    originHostHeader: originApp.properties.configuration.ingress.fqdn
    httpPort: 80
    httpsPort: 443
    priority: 1
    weight: 1000
    enabledState: 'Enabled'
    enforceCertificateNameCheck: true
  }
}

resource route 'Microsoft.Cdn/profiles/afdEndpoints/routes@2024-09-01' = {
  parent: endpoint
  name: 'objects'
  properties: {
    originGroup: {
      id: originGroup.id
    }
    supportedProtocols: [
      'Https'
    ]
    patternsToMatch: [
      '/objects/*'
    ]
    forwardingProtocol: 'HttpsOnly'
    httpsRedirect: 'Disabled'
    linkToDefaultDomain: 'Enabled'
    enabledState: 'Enabled'
    ruleSets: []
    // Omitting cacheConfiguration disables caching. No rules override origin TTL.
    ...(cachingEnabled ? {
      cacheConfiguration: {
        queryStringCachingBehavior: 'UseQueryString'
        compressionSettings: {
          isCompressionEnabled: compressionEnabled
          contentTypesToCompress: [
            'application/json'
          ]
        }
      }
    } : {})
  }
  dependsOn: [
    origin
  ]
}

output originUrl string = 'https://${originApp.properties.configuration.ingress.fqdn}'
output edgeUrl string = 'https://${endpoint.properties.hostName}'
output logAnalyticsCustomerId string = logs.properties.customerId
output containerAppName string = originApp.name
output frontDoorProfileName string = frontDoor.name
output frontDoorEndpointName string = endpoint.name
output configuration object = {
  location: location
  sku: frontDoor.sku.name
  cachingEnabled: cachingEnabled
  compressionEnabled: cachingEnabled && compressionEnabled
  imageDigest: originImageDigest
  infrastructureSubnetId: infrastructureSubnetId
}
