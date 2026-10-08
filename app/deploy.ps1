<#
.SYNOPSIS
    Preflight, deploy Bicep, remotely build images in ACR, then update the apps.
.DESCRIPTION
    setup-bank.ps1 -Check must succeed before any Azure CLI invocation.
    All modes require ResourceGroup, SubscriptionId, Location and AadTenantId.
    Infra/all also require BFF client ID/scope, Foundry account/project/endpoint/
    named Responses agent, and Fabric workspace/lakehouse/semantic model GUIDs.
    FabricCapacityResourceId is optional; capacity control requires it AND either
    FabricCapacityOperators (comma-separated UPNs) or AllowAllFabricCapacityOperators.
    An ID alone is informational and grants no capacity control permissions.
    AssignFoundryRole and ConnectFoundryAppInsights default to true; use :$false
    to skip either optional Foundry change. A real infrastructure deployment
    requires AadClientSecret. Images/all require explicit SpaClientId.

    Every invocation prints current read-only governance information. Mutation
    additionally requires GovernanceApproved AND a deployer-authored *.local.json:
      subscriptionId, tenantId, resourceGroup, location: exact target strings
       deploymentMode: exactly infra, images or all, matching Only
       planSha256: identical to the reported digest of the ordered non-secret plan
         JSON (compressed UTF-8, no BOM), including every app infra *.bicep hash
      reviewed: true (JSON boolean)
      namingStandard, allowedSkusAndRegions, policyReview, permissionReview:
        nonempty review strings
    If project docs/naming.md or docs/allowed.md is missing, the corresponding
    review string must start with "external:" followed by a reviewed standard
    reference. Missing docs are not implicit approval. Review must cover the
    exact reported inputs, actions and any enabled external Fabric scope. Image-only/demo
    approval cannot authorize infrastructure. No automatic policy/RBAC proof
    is attempted; the switch acknowledges a PRIOR manual review, not this run.
    The digest binds targets/template contents, NOT proof of governance approval.
    WhatIf, GovernanceApproved, review path, secret value AND secret presence are
    excluded so a secret-free preview can provide the real execution's digest.
    Changed targets, optional controls or Bicep files require a fresh review.

    WhatIf never creates a group, deploys, builds, pushes or updates. Without a
    BFF secret it prints an infrastructure preview only; with a secret it can run
    ARM what-if on an existing group. Image-only preview needs no BFF secret.
    An existing resource group is required for real deployments too.
    SPA redirect registration/consent is a separate manually reviewed task.
    Secrets are not printed, but Azure CLI receives AadClientSecret as an
    argument: use a trusted host without command-line/process tracing.
#>

[CmdletBinding()]
param(
    [string]$ResourceGroup,
    [Alias('Subscription')]
    [string]$SubscriptionId,
    [string]$Location,
    [string]$NamePrefix = 'cmci',
    [string]$DeploymentName = 'cmci-app',
    [string]$AadTenantId,
    [string]$AadClientId,
    [string]$AadClientSecret,
    [string]$AadApiScope,
    [string]$SpaClientId,
    [string]$FoundryProjectEndpoint,
    [string]$FoundryAccountName,
    [string]$FoundryProjectName,
    [string]$FoundryAgentName,
    [string]$ScenarioAgentName = '',
    [string]$MissionAgentName = '',
    [string]$BarrierAgentName = '',
    [bool]$AssignFoundryRole = $true,
    [bool]$ConnectFoundryAppInsights = $true,
    [string]$FabricCapacityResourceId = '',
    [string]$FabricCapacityOperators = '',
    [switch]$AllowAllFabricCapacityOperators,
    [string]$FabricWorkspaceId,
    [string]$FabricLakehouseId,
    [string]$FabricSemanticModelId,
    [string]$GovernanceReviewPath,
    [switch]$GovernanceApproved,
    [ValidateSet('infra', 'images', 'all')]
    [string]$Only = 'all',
    [switch]$WhatIf
)

$repoRoot = Split-Path -Parent $PSScriptRoot
$global:LASTEXITCODE = 0
& (Join-Path $repoRoot 'setup-bank.ps1') -Check
$bankCheckSucceeded = $?
$bankCheckExitCode = $LASTEXITCODE
if (-not $bankCheckSucceeded -or $bankCheckExitCode -ne 0) {
    throw 'setup-bank.ps1 -Check is required and must succeed. No Azure commands were run.'
}

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$hasInfra = $Only -in @('infra', 'all')
$hasImages = $Only -in @('images', 'all')

# ACR's Python/colorama build log otherwise fails on cp1252 consoles.
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$env:PYTHONIOENCODING = 'utf-8'

function Require-Text([string]$Name, [string]$Value) {
    if ([string]::IsNullOrWhiteSpace($Value) -or $Value -ne $Value.Trim()) {
        throw "Supply an explicit, nonblank -$Name without surrounding whitespace."
    }
}

function Require-Guid([string]$Name, [string]$Value) {
    Require-Text $Name $Value
    $parsed = [guid]::Empty
    if ($Value -notmatch '^[0-9a-fA-F-]{36}$' -or
        -not [guid]::TryParseExact($Value, 'D', [ref]$parsed) -or $parsed -eq [guid]::Empty) {
        throw "-$Name must be a nonempty GUID."
    }
}

function Invoke-Az {
    param([string[]]$Arguments, [string]$Label, [switch]$Json)
    $global:LASTEXITCODE = 0
    $PSNativeCommandUseErrorActionPreference = $false
    try {
        $lines = & az @Arguments --subscription $SubscriptionId --only-show-errors 2>&1
        $succeeded = $?
        $exitCode = $LASTEXITCODE
    }
    catch {
        throw "$Label failed to execute; CLI details suppressed to protect credentials."
    }
    if (-not $succeeded -or $exitCode -ne 0) {
        throw "$Label failed (exit $exitCode); CLI details suppressed to protect credentials."
    }
    $text = ($lines | ForEach-Object { "$_" }) -join [Environment]::NewLine
    if ($Json) {
        if ([string]::IsNullOrWhiteSpace($text)) { throw "$Label returned no JSON." }
        if (-not $text.TrimStart().StartsWith('{')) { throw "$Label must return a JSON object." }
        try { $result = ConvertFrom-Json -InputObject $text -ErrorAction Stop }
        catch { throw "$Label returned invalid JSON; output suppressed." }
        if ($null -eq $result) { throw "$Label returned null JSON." }
        return $result
    }
    return $text
}

function Write-RawReport([string]$Label, [string[]]$Arguments) {
    Write-Host "`n--- $Label (complete raw output; manual review required) ---"
    $raw = Invoke-Az -Arguments $Arguments -Label $Label
    if ([string]::IsNullOrWhiteSpace($raw)) { throw "$Label returned no output." }
    Write-Host $raw
}

function Get-OutputValue($Outputs, [string]$Name, [switch]$Optional) {
    $property = $Outputs.PSObject.Properties[$Name]
    if ($null -eq $property -or $property.Value.value -isnot [string] -or
        [string]::IsNullOrWhiteSpace($property.Value.value)) {
        if ($Optional) { return $null }
        throw "Deployment output '$Name' is missing or empty."
    }
    return $property.Value.value
}

function Test-TargetLocation($Actual) {
    return $Actual -is [string] -and $Actual.Replace(' ', '') -ieq $Location
}

function Get-AppState([string]$Name) {
    $query = "{id:id,name:name,location:location,state:properties.provisioningState,fqdn:properties.configuration.ingress.fqdn,image:properties.template.containers[0].image,tenantId:properties.template.containers[0].env[?name=='AAD_TENANT_ID'].value | [0],apiScope:properties.template.containers[0].env[?name=='AAD_API_SCOPE'].value | [0]}"
    $app = Invoke-Az -Label "Read app $Name" -Json -Arguments @(
        'containerapp', 'show', '--resource-group', $ResourceGroup, '--name', $Name,
        '--query', $query, '--output', 'json'
    )
    if ($app.id -ine "$scope/providers/Microsoft.App/containerApps/$Name" -or
        $app.name -ine $Name -or -not (Test-TargetLocation $app.location) -or $app.state -ne 'Succeeded') {
        throw "App '$Name' does not match the selected scope/region or is not successfully provisioned."
    }
    return $app
}

foreach ($name in @('ResourceGroup', 'SubscriptionId', 'Location', 'AadTenantId', 'DeploymentName')) {
    Require-Text $name (Get-Variable -Name $name -ValueOnly)
}
Require-Guid 'SubscriptionId' $SubscriptionId
Require-Guid 'AadTenantId' $AadTenantId
if ($ResourceGroup -notmatch '^[\w().-]{1,90}$' -or $ResourceGroup.EndsWith('.')) {
    throw 'ResourceGroup must be an Azure resource group name, not a resource ID.'
}
if ($Location -notmatch '^[a-z0-9]+$') { throw 'Location must be a canonical Azure region, e.g. eastus2.' }
if ($DeploymentName -notmatch '^[a-zA-Z0-9_.()-]{1,64}$') { throw 'Invalid DeploymentName.' }
if ($NamePrefix -notmatch '^[a-z]([a-z0-9-]{0,22}[a-z0-9])?$') { throw 'Invalid NamePrefix (1-24 lowercase name characters).' }
Require-Text 'AadApiScope' $AadApiScope
if ($AadApiScope -notmatch '^api://[^\s/]+/\S+$') {
    throw 'AadApiScope must be an explicit api:// application delegated scope.'
}
if ($hasImages) { Require-Guid 'SpaClientId' $SpaClientId }
foreach ($name in @('FabricWorkspaceId', 'FabricLakehouseId', 'FabricSemanticModelId')) {
    $value = Get-Variable -Name $name -ValueOnly
    if ($hasInfra -or -not [string]::IsNullOrEmpty($value)) { Require-Guid $name $value }
}
$fabricScope = $null
if (-not [string]::IsNullOrEmpty($FabricCapacityResourceId)) {
    Require-Text 'FabricCapacityResourceId' $FabricCapacityResourceId
    if ($FabricCapacityResourceId -notmatch '\A/subscriptions/([0-9a-fA-F-]{36})/resourceGroups/([\w().-]{1,90})/providers/Microsoft\.Fabric/capacities/([a-zA-Z0-9]+)\z') {
        throw 'FabricCapacityResourceId must identify one Microsoft.Fabric/capacities ARM resource.'
    }
    $capacitySubscriptionId = $Matches[1]
    $capacityResourceGroup = $Matches[2]
    Require-Guid 'Fabric capacity subscription' $capacitySubscriptionId
    if ($capacityResourceGroup.EndsWith('.')) { throw 'Invalid Fabric capacity resource group name.' }
    $fabricScope = "/subscriptions/$capacitySubscriptionId/resourceGroups/$capacityResourceGroup"
}
$hasFabricCapacityOperators = @($FabricCapacityOperators.Split(',') | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }).Count -gt 0
if (($hasFabricCapacityOperators -or $AllowAllFabricCapacityOperators) -and -not $fabricScope) {
    throw 'FabricCapacityResourceId is required when FabricCapacityOperators or AllowAllFabricCapacityOperators enables capacity control.'
}
$fabricCapacityControlEnabled = [bool]($fabricScope -and ($hasFabricCapacityOperators -or $AllowAllFabricCapacityOperators))
if ($hasInfra) {
    Require-Guid 'AadClientId' $AadClientId
    foreach ($name in @('FoundryProjectEndpoint', 'FoundryAccountName', 'FoundryProjectName',
            'FoundryAgentName')) {
        Require-Text $name (Get-Variable -Name $name -ValueOnly)
    }
    $endpoint = $null
    $expectedEndpoint = "https://$FoundryAccountName.services.ai.azure.com/api/projects/$FoundryProjectName"
    if ($FoundryAccountName -notmatch '\A[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\z' -or
        $FoundryProjectName -notmatch '\A[a-zA-Z0-9][a-zA-Z0-9_.-]*\z' -or
        $FoundryProjectEndpoint -cne $expectedEndpoint -or
        -not [uri]::TryCreate($FoundryProjectEndpoint, [UriKind]::Absolute, [ref]$endpoint) -or
        $endpoint.Scheme -ne 'https' -or $endpoint.UserInfo -or $endpoint.Query -or $endpoint.Fragment -or
        $endpoint.Host -ine "$FoundryAccountName.services.ai.azure.com" -or
        $endpoint.AbsolutePath -cne "/api/projects/$FoundryProjectName") {
        throw 'FoundryProjectEndpoint must be exactly https://<FoundryAccountName>.services.ai.azure.com/api/projects/<FoundryProjectName>.'
    }
    if ($FoundryAgentName -match '^asst_') { throw 'Pass a named Responses agent, not a classic asst_ ID.' }
}

$scope = "/subscriptions/$SubscriptionId/resourceGroups/$ResourceGroup"
if (-not [string]::IsNullOrWhiteSpace($GovernanceReviewPath)) {
    $GovernanceReviewPath = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($GovernanceReviewPath)
}
Push-Location $root
try {
    Write-Host "`n=== CURRENT READ-ONLY PRE-FLIGHT REPORT ===" -ForegroundColor Cyan
    $templateHashes = [ordered]@{}
    $infraRoot = Join-Path $root 'infra'
    if (-not (Test-Path -LiteralPath (Join-Path $infraRoot 'main.bicep') -PathType Leaf)) {
        throw 'App infra\main.bicep is required to fingerprint the reviewed template.'
    }
    [string[]]$templatePaths = @(Get-ChildItem -LiteralPath $infraRoot -Filter '*.bicep' -Recurse -File |
        ForEach-Object { $_.FullName.Substring($root.Length + 1) })
    [Array]::Sort($templatePaths, [StringComparer]::Ordinal)
    foreach ($path in $templatePaths) {
        $templateHashes[$path] = (Get-FileHash -LiteralPath (Join-Path $root $path) -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    $reviewPlan = [ordered]@{
        subscriptionId = $SubscriptionId; tenantId = $AadTenantId
        resourceGroup = $ResourceGroup; location = $Location; deploymentMode = $Only
        deploymentName = $DeploymentName; namePrefix = $NamePrefix
        aadClientId = $AadClientId; aadApiScope = $AadApiScope; spaClientId = $SpaClientId
        foundryAccountName = $FoundryAccountName; foundryProjectName = $FoundryProjectName
        foundryProjectEndpoint = $FoundryProjectEndpoint; foundryAgentName = $FoundryAgentName
        scenarioAgentName = $ScenarioAgentName; missionAgentName = $MissionAgentName
        barrierAgentName = $BarrierAgentName
        assignFoundryRole = $AssignFoundryRole; connectFoundryAppInsights = $ConnectFoundryAppInsights
        fabricCapacityResourceId = $FabricCapacityResourceId; fabricWorkspaceId = $FabricWorkspaceId
        fabricLakehouseId = $FabricLakehouseId; fabricSemanticModelId = $FabricSemanticModelId
        fabricCapacityOperators = $FabricCapacityOperators
        allowAllFabricCapacityOperators = [bool]$AllowAllFabricCapacityOperators
        fabricCapacityControlEnabled = $fabricCapacityControlEnabled
        secretReview = 'aadClientSecret value and presence excluded'
        infraBicepSha256 = $templateHashes
    }
    $planJson = ConvertTo-Json -InputObject $reviewPlan -Depth 10 -Compress
    $sha256 = [Security.Cryptography.SHA256]::Create()
    try {
        $planSha256 = [BitConverter]::ToString($sha256.ComputeHash([Text.Encoding]::UTF8.GetBytes($planJson))).Replace('-', '').ToLowerInvariant()
    }
    finally { $sha256.Dispose() }
    Write-Host (ConvertTo-Json -InputObject $reviewPlan -Depth 10)
    Write-Host "planSha256: $planSha256"
    Write-Host 'Digest binds only the reported non-secret plan and Bicep bytes; manual evidence acknowledgement is NOT governance/permission proof.'
    Write-Host @'
Effective permissions: NOT automatically proven. No policy evaluator is used.
Review Deny, DeployIfNotExists, Modify and Audit assignments, initiative definitions,
parameters, exemptions, conditions, deny assignments, PIM and actual template changes.
Control-plane RBAC CANNOT prove Fabric workspace/item, Foundry data-plane, Graph,
OBO delegated scopes, application consent or SPA redirect grants.
No group creation, app registration provisioning or tenant/Graph writes occur here.
SPA redirect registration is a separate, manually reviewed task in every mode.
'@
    if ($hasInfra) {
        Write-Host @'
Required infrastructure actions (review at each applicable resource scope):
  Microsoft.Resources/deployments/read
  Microsoft.Resources/deployments/write
  Microsoft.Resources/deployments/validate/action
  Microsoft.Resources/deployments/whatIf/action
  Microsoft.ContainerRegistry/registries/read
  Microsoft.ContainerRegistry/registries/write
  Microsoft.OperationalInsights/workspaces/read
  Microsoft.OperationalInsights/workspaces/write
  Microsoft.OperationalInsights/workspaces/sharedKeys/action
  Microsoft.Insights/components/read
  Microsoft.Insights/components/write
  Microsoft.ManagedIdentity/userAssignedIdentities/read
  Microsoft.ManagedIdentity/userAssignedIdentities/write
  Microsoft.ManagedIdentity/userAssignedIdentities/assign/action
  Microsoft.App/managedEnvironments/read
  Microsoft.App/managedEnvironments/write
  Microsoft.App/managedEnvironments/join/action
  Microsoft.App/containerApps/read
  Microsoft.App/containerApps/write
  Microsoft.Authorization/roleAssignments/read
  Microsoft.Authorization/roleAssignments/write
  Microsoft.Authorization/roleDefinitions/read
  Microsoft.Authorization/roleDefinitions/write (if Fabric capacity control enabled)
  Microsoft.CognitiveServices/accounts/read
  Microsoft.CognitiveServices/accounts/projects/read
  Microsoft.CognitiveServices/accounts/projects/connections/write (if connectFoundryAppInsights)
Review the optional Foundry role grant only if assignFoundryRole is true.
Also review the BFF identity's Foundry/Fabric/OBO grants; these are NOT deployer proof.
Template defaults remain in force, including SKU, network access, images and scaling.
Review the actual template against the naming and SKU/region standards.
'@
        if ($fabricCapacityControlEnabled) {
            Write-Host "FABRIC CAPACITY SCOPE REVIEW REQUIRED: $fabricScope"
            Write-Host "Exact capacity: $FabricCapacityResourceId"
            Write-Host 'Review Microsoft.Fabric/capacities/read and the BFF runtime capacities/read, suspend/action and resume/action permissions.'
            Write-Host 'The report below covers the app group only. permissionReview/policyReview must also cover the exact Fabric capacity and its parent scopes, including any external tenant/subscription.'
        }
        elseif ($fabricScope) {
            Write-Host "Informational capacity only: $FabricCapacityResourceId. No capacity control or grant; no capacity-scope deployment."
        }
        else {
            Write-Host 'Fabric capacity control disabled: no capacity target, grant or capacity-scope deployment.'
        }
    }
    if ($hasImages) {
        Write-Host @'
Required image-stage actions:
  Microsoft.Resources/deployments/read; Microsoft.ContainerRegistry/registries/read
  Microsoft.ContainerRegistry/registries/scheduleRun/action
  Microsoft.ContainerRegistry/registries/listBuildSourceUploadUrl/action
  Microsoft.ContainerRegistry/registries/runs/read
  Microsoft.ContainerRegistry/registries/runs/listLogSasUrl/action
  Microsoft.App/containerApps/read
  Microsoft.App/containerApps/write
Separately review registry build/push/pull permissions, repository ABAC, managed
identity image pull, and current BFF/SPA authentication. No grant is inferred.
'@
    }

    $account = Invoke-Az -Label 'Target account' -Json -Arguments @('account', 'show', '--output', 'json')
    Write-Host "`n--- Target account ---"
    Write-Host ($account | ConvertTo-Json -Depth 20)
    if ($account.id -ine $SubscriptionId -or $account.tenantId -ine $AadTenantId -or
        $account.state -ne 'Enabled' -or [string]::IsNullOrWhiteSpace($account.user.name)) {
        throw 'Selected subscription/tenant/identity is not the explicit enabled target.'
    }
    Write-RawReport 'Inherited policy assignments' @(
        'policy', 'assignment', 'list', '--scope', $scope, '--disable-scope-strict-match', '--output', 'json'
    )
    Write-RawReport 'Current policy compliance summary' @(
        'policy', 'state', 'summarize', '--resource-group', $ResourceGroup, '--top', '5', '--output', 'json'
    )
    if ($account.user.type -eq 'user') {
        $identity = Invoke-Az -Label 'Signed-in object ID' -Json -Arguments @(
            'ad', 'signed-in-user', 'show', '--query', '{id:id,userPrincipalName:userPrincipalName}', '--output', 'json'
        )
    }
    elseif ($account.user.type -eq 'servicePrincipal') {
        $identity = Invoke-Az -Label 'Signed-in service principal' -Json -Arguments @(
            'ad', 'sp', 'show', '--id', $account.user.name, '--query', '{id:id,appId:appId}', '--output', 'json'
        )
    }
    else { throw 'Unsupported signed-in identity type; obtain an independently reviewable identity first.' }
    Require-Guid 'Signed-in object ID' $identity.id
    Write-Host "`n--- Caller identity ---"
    Write-Host ($identity | ConvertTo-Json -Depth 10)
    $roleArgs = @('role', 'assignment', 'list', '--assignee', $identity.id, '--scope', $scope,
        '--include-inherited', '--output', 'json')
    if ($account.user.type -eq 'user') { $roleArgs += '--include-groups' }
    Write-RawReport 'Role assignments including inherited roles' $roleArgs

    $permissionUrl = "https://management.azure.com$scope/providers/Microsoft.Authorization/permissions?api-version=2022-04-01"
    $permissionBase = $permissionUrl.Split('?')[0]
    $seenPages = @{}
    try {
        do {
            if ($seenPages.ContainsKey($permissionUrl)) { throw 'Repeated permissions page.' }
            $seenPages[$permissionUrl] = $true
            $raw = Invoke-Az -Label 'Effective permissions endpoint' -Arguments @(
                'rest', '--method', 'get', '--url', $permissionUrl, '--output', 'json'
            )
            Write-Host "`n--- Effective permissions endpoint (raw; NOT proof) ---"
            Write-Host $raw
            if (-not $raw.TrimStart().StartsWith('{')) { throw 'Permissions response must be a JSON object.' }
            $page = ConvertFrom-Json -InputObject $raw -ErrorAction Stop
            if ($page.value -isnot [array]) { throw 'Permissions response has no array value collection.' }
            foreach ($permission in $page.value) {
                if ($permission -isnot [pscustomobject]) { throw 'Invalid permission entry.' }
                foreach ($field in @('actions', 'notActions', 'dataActions', 'notDataActions')) {
                    if ($permission.$field -isnot [array]) { throw "Permission '$field' must be an array." }
                    foreach ($action in $permission.$field) {
                        if ($action -isnot [string] -or [string]::IsNullOrWhiteSpace($action)) { throw "Invalid permission '$field' entry." }
                    }
                }
            }
            if ($null -ne $page.nextLink -and $page.nextLink -isnot [string]) { throw 'Permissions nextLink must be a URL string.' }
            $permissionUrl = $page.nextLink
            if ($permissionUrl -and -not $permissionUrl.StartsWith("${permissionBase}?", [StringComparison]::OrdinalIgnoreCase)) {
                throw 'Permissions pagination left the selected scope.'
            }
        } while ($permissionUrl)
    }
    catch {
        throw 'Effective permissions evidence is unavailable/incomplete. Stop and escalate; neither a review string nor GovernanceApproved can bypass failed evidence retrieval.'
    }

    $standards = @{
        namingStandard = Join-Path $repoRoot 'docs\naming.md'
        allowedSkusAndRegions = Join-Path $repoRoot 'docs\allowed.md'
    }
    foreach ($key in $standards.Keys) {
        if (Test-Path -LiteralPath $standards[$key] -PathType Leaf) {
            Write-Host "`n--- Standard: $($standards[$key]) ---"
            Write-Host (Get-Content -LiteralPath $standards[$key] -Raw)
        }
        else {
            Write-Host "MISSING: $($standards[$key]); no approval without an explicit external: reviewed standard reference." -ForegroundColor Yellow
        }
    }
    Write-Host @'
Governance evidence plan: create your own *.local.json AFTER manual review.
Required: subscriptionId, tenantId, resourceGroup, location, deploymentMode matching
this invocation; planSha256 identical to the printed digest; reviewed: true;
nonempty namingStandard, allowedSkusAndRegions,
policyReview, permissionReview strings. Cover ALL exact reported resources/actions,
applicable external scopes and unproven grants. Never include secrets in the review.
Changed plan inputs/controls or Bicep files require fresh review and a new digest.
The digest is NOT proof of approval, policy compliance or effective permissions.
No previous image-only/demo approval is reusable
for infrastructure. -GovernanceApproved acknowledges that PRIOR review.
'@
    if ($WhatIf) {
        Write-Host 'WHATIF: preview only; NO AUTHORIZATION to mutate, regardless of evidence or acknowledgement.' -ForegroundColor Yellow
    }
    else {
        Require-Text 'GovernanceReviewPath' $GovernanceReviewPath
        if ($GovernanceReviewPath -notmatch '\.local\.json$' -or
            -not (Test-Path -LiteralPath $GovernanceReviewPath -PathType Leaf)) {
            throw 'GovernanceReviewPath must be an existing deployer-created *.local.json file.'
        }
        try { $review = Get-Content -LiteralPath $GovernanceReviewPath -Raw | ConvertFrom-Json -ErrorAction Stop }
        catch { throw 'Governance evidence is unreadable or invalid JSON.' }
        if ($review.reviewed -isnot [bool] -or $review.reviewed -ne $true) {
            throw 'Governance evidence must contain reviewed: true as a JSON boolean.'
        }
        foreach ($key in @('subscriptionId', 'tenantId', 'resourceGroup', 'location', 'deploymentMode')) {
            if ($review.$key -isnot [string] -or $review.$key -ine $reviewPlan[$key]) {
                throw "Governance evidence '$key' does not match this invocation."
            }
        }
        if ($review.planSha256 -isnot [string] -or $review.planSha256 -cne $planSha256) {
            throw "Governance evidence 'planSha256' does not match the exact current plan/templates. Perform a fresh manual review."
        }
        foreach ($key in @('namingStandard', 'allowedSkusAndRegions', 'policyReview', 'permissionReview')) {
            if ($review.$key -isnot [string] -or [string]::IsNullOrWhiteSpace($review.$key)) {
                throw "Governance evidence requires a nonempty '$key' review string."
            }
        }
        foreach ($key in $standards.Keys) {
            if (-not (Test-Path -LiteralPath $standards[$key] -PathType Leaf) -and
                $review.$key -notmatch '^external:\s*\S.+') {
                throw "Missing local standard: '$key' must explicitly reference an external: reviewed standard."
            }
        }
        if (-not $GovernanceApproved) {
            throw 'Manual evidence alone is insufficient; pass -GovernanceApproved to acknowledge the prior review.'
        }
        Write-Host 'Prior manual review acknowledged for this exact plan/templates. Effective permissions remain NOT automatically proven.'
    }

    $group = Invoke-Az -Label 'Existing target resource group' -Json -Arguments @(
        'group', 'show', '--name', $ResourceGroup, '--query', '{id:id,name:name,location:location}', '--output', 'json'
    )
    if ($group.id -ine $scope -or $group.name -ine $ResourceGroup) { throw 'Resource group does not match the selected scope.' }
    Write-Host "Existing target group: $($group.id) (group metadata region: $($group.location))"

    if ($hasInfra) {
        if ($WhatIf -and [string]::IsNullOrWhiteSpace($AadClientSecret)) {
            Write-Host 'WHATIF: Bicep -> ACR remote builds -> app updates (only requested stages). No commands in this plan were executed.'
            Write-Host 'ARM what-if skipped: its secure aadClientSecret parameter was not supplied. No dummy secret is substituted.'
            return
        }
        Require-Text 'AadClientSecret' $AadClientSecret
        $verb = 'create'
        if ($WhatIf) { $verb = 'what-if' }
        $infraArgs = @('deployment', 'group', $verb, '--resource-group', $ResourceGroup,
            '--name', $DeploymentName, '--template-file', (Convert-Path -LiteralPath 'infra\main.bicep'), '--parameters',
            "namePrefix=$NamePrefix", "location=$Location", "aadTenantId=$AadTenantId",
            "aadClientId=$AadClientId", "aadClientSecret=$AadClientSecret", "aadApiScope=$AadApiScope",
            "foundryProjectEndpoint=$FoundryProjectEndpoint", "foundryAccountName=$FoundryAccountName",
            "foundryProjectName=$FoundryProjectName", "foundryAgentName=$FoundryAgentName",
            "scenarioAgentName=$ScenarioAgentName", "missionAgentName=$MissionAgentName",
            "barrierAgentName=$BarrierAgentName",
            "assignFoundryRole=$($AssignFoundryRole.ToString().ToLowerInvariant())",
            "connectFoundryAppInsights=$($ConnectFoundryAppInsights.ToString().ToLowerInvariant())",
            "fabricCapacityResourceId=$FabricCapacityResourceId", "fabricWorkspaceId=$FabricWorkspaceId",
            "fabricLakehouseId=$FabricLakehouseId", "fabricSemanticModelId=$FabricSemanticModelId",
            "fabricCapacityOperators=$FabricCapacityOperators",
            "allowAllFabricCapacityOperators=$($AllowAllFabricCapacityOperators.IsPresent.ToString().ToLowerInvariant())",
            '--output', 'json')
        if ($WhatIf) {
            $infraArgs += @('--result-format', 'ResourceIdOnly', '--no-pretty-print')
            $preview = Invoke-Az -Label 'ARM what-if' -Json -Arguments $infraArgs
            if ($preview.status -ne 'Succeeded' -or $null -eq $preview.changes) { throw 'ARM what-if did not return a successful change report.' }
            foreach ($change in $preview.changes) { Write-Host "$($change.changeType): $($change.resourceId)" }
            Write-Host 'WHATIF complete. No deployment/build/push/update or authorization occurred.'
            return
        }
        Write-Host "`n1. Deploy Bicep (template defaults preserved)" -ForegroundColor Cyan
        $deploymentResult = Invoke-Az -Label 'Bicep deployment' -Json -Arguments $infraArgs
        if ($deploymentResult.properties.provisioningState -ne 'Succeeded') { throw 'Bicep deployment did not succeed.' }
    }

    $deployment = Invoke-Az -Label 'Named app deployment' -Json -Arguments @(
        'deployment', 'group', 'show', '--resource-group', $ResourceGroup, '--name', $DeploymentName,
        '--query', '{id:id,properties:{provisioningState:properties.provisioningState,outputs:properties.outputs,parameters:{namePrefix:properties.parameters.namePrefix}}}',
        '--output', 'json'
    )
    if ($deployment.id -ine "$scope/providers/Microsoft.Resources/deployments/$DeploymentName" -or
        $deployment.properties.provisioningState -ne 'Succeeded' -or $null -eq $deployment.properties.outputs) {
        throw 'Named app deployment is missing, in another scope, or not successfully provisioned. No fallback is permitted.'
    }
    $out = $deployment.properties.outputs
    $acr = Get-OutputValue $out 'acrName'
    $server = Get-OutputValue $out 'acrLoginServer'
    $webUrl = Get-OutputValue $out 'webUrl'
    $webUri = $null
    if ($acr -notmatch '^[a-zA-Z0-9]{5,50}$' -or
        -not [uri]::TryCreate($webUrl, [UriKind]::Absolute, [ref]$webUri) -or
        $webUri.Scheme -ne 'https' -or $webUri.UserInfo -or $webUri.Query -or $webUri.Fragment) {
        throw 'Deployment registry/URL outputs are invalid.'
    }

    if ($hasImages) {
        $deployedPrefix = $deployment.properties.parameters.namePrefix.value
        $appNames = @{}
        foreach ($kind in @('bff', 'web')) {
            $name = Get-OutputValue $out "${kind}AppName" -Optional
            if (-not $name) { $name = Get-OutputValue $out "${kind}Name" -Optional }
            if (-not $name) {
                if ($deployedPrefix -isnot [string] -or $deployedPrefix -notmatch '^[a-z]([a-z0-9-]{0,22}[a-z0-9])?$') {
                    throw "No $kind app-name output or verified deployment namePrefix; refusing to guess."
                }
                if ($PSBoundParameters.ContainsKey('NamePrefix') -and $NamePrefix -cne $deployedPrefix) {
                    throw 'Explicit NamePrefix differs from the selected deployment.'
                }
                $name = "ca-$deployedPrefix-$kind"
            }
            if ($name -notmatch '^[a-z][a-z0-9-]{0,30}[a-z0-9]$') { throw "Invalid $kind app-name output." }
            $appNames[$kind] = $name
        }
        if ($appNames.bff -eq $appNames.web) { throw 'BFF and web must be distinct apps.' }
        $registry = Invoke-Az -Label 'Target registry' -Json -Arguments @(
            'acr', 'show', '--resource-group', $ResourceGroup, '--name', $acr,
            '--query', '{id:id,loginServer:loginServer,location:location,provisioningState:provisioningState}', '--output', 'json'
        )
        if ($registry.id -ine "$scope/providers/Microsoft.ContainerRegistry/registries/$acr" -or
            $registry.loginServer -ine $server -or -not (Test-TargetLocation $registry.location) -or
            $registry.provisioningState -ne 'Succeeded') { throw 'Registry outputs do not match a provisioned registry in the selected scope/region.' }
        $bff = Get-AppState $appNames.bff
        $web = Get-AppState $appNames.web
        if ($bff.tenantId -ine $AadTenantId -or $bff.apiScope -cne $AadApiScope) {
            throw 'Explicit tenant/API scope does not match the deployed BFF; refusing to build an incompatible SPA.'
        }
        if ($web.fqdn -ine $webUri.Host) { throw 'Web URL output does not match the deployed web app.' }
        if ($WhatIf) {
            Write-Host "WHATIF: would remotely build BFF/web in $server and update $($appNames.bff), $($appNames.web)."
            Write-Host 'No build, push or update executed. Preview provides NO authorization.'
            return
        }

        Write-Host "`n2. ACR remote builds (both must succeed)" -ForegroundColor Cyan
        $tag = (Get-Date).ToUniversalTime().ToString('yyyyMMddHHmmss') + '-' + [guid]::NewGuid().ToString('N').Substring(0, 8)
        $null = Invoke-Az -Label 'BFF remote build' -Arguments @(
            'acr', 'build', '--registry', $acr, '--image', "cmci/bff:$tag", '--image', 'cmci/bff:latest',
            '--file', (Convert-Path -LiteralPath 'src\bff\Dockerfile'), (Convert-Path -LiteralPath 'src\bff'), '--output', 'none'
        )
        $null = Invoke-Az -Label 'Web remote build' -Arguments @(
            'acr', 'build', '--registry', $acr, '--image', "cmci/web:$tag", '--image', 'cmci/web:latest',
            '--file', (Convert-Path -LiteralPath 'src\web\Dockerfile'), (Convert-Path -LiteralPath 'src\web'), '--build-arg', "VITE_AAD_TENANT_ID=$AadTenantId",
            '--build-arg', "VITE_AAD_CLIENT_ID=$SpaClientId", '--build-arg', "VITE_API_SCOPE=$AadApiScope",
            '--output', 'none'
        )
        Write-Host "`n3. Update Container Apps" -ForegroundColor Cyan
        foreach ($kind in @('bff', 'web')) {
            $image = "$server/cmci/${kind}:$tag"
            $null = Invoke-Az -Label "Update $kind app" -Arguments @(
                'containerapp', 'update', '--resource-group', $ResourceGroup, '--name', $appNames[$kind],
                '--image', $image, '--output', 'none'
            )
            $updated = Get-AppState $appNames[$kind]
            if ($updated.image -cne $image) { throw "$kind app did not adopt the requested image." }
        }
        Write-Host "Deployed and verified tag $tag."
    }
    Write-Host "`nSPA redirect registration is a SEPARATE, manually reviewed task: $webUrl" -ForegroundColor Yellow
    Write-Host 'No app registration, Graph consent or redirect changes were made by this script.'
    Write-Host 'Requested stages completed successfully.' -ForegroundColor Green
}
finally {
    Pop-Location
}
