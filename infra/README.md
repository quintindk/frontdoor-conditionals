# Optional Azure Lab

These templates deploy a synthetic origin and test routes. They contain no subscription, tenant, live hostname or deployed parameter values. Nothing is provisioned by installing the Python package or running local tests.

## Resources and Prerequisites

| Template | Purpose |
|---|---|
| `registry.bicep` | Basic ACR, user-assigned image-pull identity and registry-scoped AcrPull |
| `main.bicep` | Log Analytics, Container Apps environment/app and Front Door Standard |
| `test-endpoints.bicep` | Fixed no-cache and gzip endpoints on the same profile/origin group |
| `route-control.bicep` | Change one existing route's cache/compression settings |
| `example.bicepparam` | Reads your deployment values from environment variables |

Use a dedicated non-production resource group and an approved subscription, region, spend and review date. The origin, registry and workspace are regional; Front Door is global.

Bring a dedicated, unused subnet in the same subscription and region, `/27` or larger, delegated to `Microsoft.App/environments`. Review its address allocation, DNS, NSG, routing and egress with its owner. The templates do not create or change the VNet. Register the required providers and verify policy, regional quota and role-assignment permission before deployment.

The design uses one Consumption replica, 0.25 vCPU and 0.5 GiB memory. External HTTPS ingress is intentional for direct-origin controls. The app uses a digest-pinned private image and a managed identity, with no registry admin credentials. There is no WAF, Private Link or authentication on the synthetic fixture path.

Native Blob testing and private-origin authentication are not provided by these templates. An earlier public Blob control was blocked by policy; do not weaken security controls to recreate it.

## Cost and Lifecycle

Budget for Front Door, requests and transfer, ACR, the running replica, Log Analytics, and the load balancer/public IPs created for VNet-integrated Container Apps. A Consumption profile does not make managed networking free.

The workspace has 30-day retention and a 1 GB daily ingestion cap. A cap can interrupt evidence collection and is not a hard monetary ceiling. `expiresOn` is a review tag, not an automatic deletion job. No cleanup command is included, and shared network resources must not be deleted with the lab.

## Deploy

Use Bash from the repository root. Set your own values locally; do not commit populated parameters or command output. Use the same lab name and region for both templates.

```bash
set -euo pipefail
: "${LAB_SUBSCRIPTION_ID:?Set the approved subscription UUID}"
: "${LAB_RESOURCE_GROUP:?Set the dedicated resource group}"
: "${LAB_LOCATION:?Set the approved Azure region}"
: "${LAB_OWNER:?Set the resource owner tag}"
: "${LAB_EXPIRES_ON:?Set the review date as YYYY-MM-DD}"
: "${LAB_SUBNET_ID:?Set the dedicated subnet resource ID}"
LAB_NAME=conditional

az account show --subscription "$LAB_SUBSCRIPTION_ID" --query '{name:name,id:id}'
az network vnet subnet show --subscription "$LAB_SUBSCRIPTION_ID" --ids "$LAB_SUBNET_ID"
```

Confirm the returned identities and subnet requirements before continuing. Never switch or inherit the default Azure CLI subscription implicitly.

```bash
az group create --subscription "$LAB_SUBSCRIPTION_ID" --name "$LAB_RESOURCE_GROUP" \
  --location "$LAB_LOCATION" \
  --tags workload=frontdoor-conditionals environment=lab owner="$LAB_OWNER" expiresOn="$LAB_EXPIRES_ON"

SCOPE=(--subscription "$LAB_SUBSCRIPTION_ID" --resource-group "$LAB_RESOURCE_GROUP")
COMMON=(labName="$LAB_NAME" location="$LAB_LOCATION" owner="$LAB_OWNER" expiresOn="$LAB_EXPIRES_ON")
az deployment group what-if "${SCOPE[@]}" --name registry \
  --template-file infra/registry.bicep --parameters "${COMMON[@]}"
```

Review the what-if before each create operation. Use incremental mode, never complete mode against a shared group.

```bash
az deployment group create "${SCOPE[@]}" --name registry --mode Incremental \
  --template-file infra/registry.bicep --parameters "${COMMON[@]}" --output none
export LAB_REGISTRY=$(az deployment group show "${SCOPE[@]}" --name registry --query properties.outputs.registryName.value -o tsv)
export LAB_PULL_IDENTITY=$(az deployment group show "${SCOPE[@]}" --name registry --query properties.outputs.imagePullIdentityName.value -o tsv)

IMAGE_TAG="lab-$(date -u +%Y%m%dT%H%M%SZ)"
az acr build --subscription "$LAB_SUBSCRIPTION_ID" --registry "$LAB_REGISTRY" \
  --platform linux/amd64 --image "frontdoor-origin:$IMAGE_TAG" .
export LAB_IMAGE_DIGEST=$(az acr repository show --subscription "$LAB_SUBSCRIPTION_ID" \
  --name "$LAB_REGISTRY" --image "frontdoor-origin:$IMAGE_TAG" --query digest -o tsv)

export LAB_LOCATION LAB_OWNER LAB_EXPIRES_ON LAB_SUBNET_ID
az deployment group what-if "${SCOPE[@]}" --name origin-edge --parameters infra/example.bicepparam
```

After reviewing that plan and allowing identity permissions to propagate:

```bash
az deployment group create "${SCOPE[@]}" --name origin-edge --mode Incremental \
  --parameters infra/example.bicepparam --output none
az deployment group show "${SCOPE[@]}" --name origin-edge --query properties.outputs
```

The example parameters use `labName=conditional`. If you choose a different name, update your local ignored parameter file consistently. Do not enable the registry admin account as an image-pull workaround.

## Fixed Controls

Use separate endpoints rather than changing settings during a run. Route updates can propagate unevenly; control-plane success alone does not prove which configuration handled a request.

```bash
az deployment group what-if "${SCOPE[@]}" --name fixed-controls \
  --template-file infra/test-endpoints.bicep \
  --parameters labName="$LAB_NAME" profileName="$LAB_NAME-afd" originGroupName=fixture
```

After review, deploy with the same parameters and obtain the endpoint URLs from deployment outputs. Before testing, verify real data-plane behaviour with fresh disposable paths: `CONFIG_NOCACHE` for the pass-through control and an actual compressed 200 response for the gzip control. Keep the original baseline route unchanged.

## Logs and Verification

Check the actual app revision, response bytes and direct 200/304 behaviour. Verify both direct and edge request IDs in origin logs. A healthy resource status without a working hostname/response is not sufficient.

Record your resource configuration, image digest and test timestamps privately. Collect every replica's logs and wait for ingestion. Do not infer an absent origin request from a bounded console tail or a partially successful query.

The analysis command consumes the workspace ARM query response format, including query-status tables. Substitute your workspace and app name, and choose a time range covering the full run:

```bash
: "${LAB_WORKSPACE:?Set the workspace resource name}"
az rest --subscription "$LAB_SUBSCRIPTION_ID" --method post \
  --url "https://management.azure.com/subscriptions/$LAB_SUBSCRIPTION_ID/resourceGroups/$LAB_RESOURCE_GROUP/providers/Microsoft.OperationalInsights/workspaces/$LAB_WORKSPACE/api/query?api-version=2020-08-01" \
  --body "{\"query\":\"ContainerAppConsoleLogs_CL | where ContainerAppName_s == '$LAB_NAME-origin' | where TimeGenerated > ago(2h) | project TimeGenerated, RevisionName_s, ContainerGroupName_s, Log_s | order by TimeGenerated asc\"}" \
  > evidence/origin-logs.json

frontdoor-analyse --logs evidence/origin-logs.json evidence/baseline.jsonl > evidence/analysis.json
```

Create `evidence/` with private permissions first. Query access still requires the relevant authorisation and network policy. Do not modify shared DNS, Private Link or security policy implicitly to obtain logs. Origin records can contain adjacent JSON objects from concurrent prints; the analyser preserves all complete objects and rejects malformed content.

## Local Template Validation

```bash
az bicep lint --file infra/main.bicep
az bicep lint --file infra/registry.bicep
az bicep lint --file infra/test-endpoints.bicep
az bicep lint --file infra/route-control.bicep
```

Compilation/linting is not proof of regional availability or deployment success. No Azure operation runs in CI.

## References

- [Container Apps networking requirements and managed-resource costs](https://learn.microsoft.com/en-us/azure/container-apps/custom-virtual-networks)
- [Managed-identity image pulls](https://learn.microsoft.com/en-us/azure/container-apps/managed-identity-image-pull)
- [Front Door caching](https://learn.microsoft.com/en-us/azure/frontdoor/front-door-caching)
- [Front Door route schema](https://learn.microsoft.com/en-us/azure/templates/microsoft.cdn/profiles/afdendpoints/routes)
- [Container Apps logs](https://learn.microsoft.com/en-us/azure/container-apps/log-monitoring)
