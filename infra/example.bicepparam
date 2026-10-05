using './main.bicep'

// Set these locally. Never commit populated deployment parameters or outputs.
param labName = 'conditional'
param location = readEnvironmentVariable('LAB_LOCATION')
param owner = readEnvironmentVariable('LAB_OWNER')
param expiresOn = readEnvironmentVariable('LAB_EXPIRES_ON')
param infrastructureSubnetId = readEnvironmentVariable('LAB_SUBNET_ID')
param registryName = readEnvironmentVariable('LAB_REGISTRY')
param imagePullIdentityName = readEnvironmentVariable('LAB_PULL_IDENTITY')
param originImageDigest = readEnvironmentVariable('LAB_IMAGE_DIGEST')
param cachingEnabled = true
param compressionEnabled = false
