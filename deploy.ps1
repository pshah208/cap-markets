<#
.SYNOPSIS
    Deploy the selected bank's synthetic Capital Markets intelligence demo.
.DESCRIPTION
    Checks setup-bank.ps1 -Check before any external command. Supply explicit
    ResourceGroup, SubscriptionId, TenantId and Location. Copy the tracked
    infra\main.parameters.example.json to infra\main.parameters.local.json and
    fill the selected targets; no caller is automatically granted a role.

    Order: bicep, fabric, foundry-iq, work-iq, agent. Use Only for one stage.
    Fabric also requires FabricCapacity, FabricCapacityResourceGroup and the
    FABRIC_* names in .env.example, exported to the process environment.
    Downstream Search/Foundry settings are recovered from the named deployment
    in the explicit target, never from ambient endpoints.

    Each invocation prints read-only policy/role/permissions evidence. Before
    mutation, a deployer must manually review it and provide GovernanceApproved
    plus a GovernanceReviewPath ending in .local.json. Required review fields:
      subscriptionId, tenantId, resourceGroup, location, deploymentMode,
      planSha256 (copy the current printed digest), reviewed: true,
      namingStandard, allowedSkusAndRegions, policyReview, permissionReview.
    Review strings must be nonempty. When project docs\naming.md or
    docs\allowed.md is missing, use an "external:" reviewed standard reference.
    Neither an acknowledgement nor a digest proves effective permissions.
    An earlier image-only demo approval does not authorize this deployment.

    WhatIf performs read-only preflight, and ARM what-if only if the group
    already exists. It NEVER creates a group, runs Python, seeds data, creates
    agents or writes to Graph. No automatic account switching is performed.
    Data-plane stages require the selected account to be the CLI default.
    Search/agent helpers use an explicit AzureCliCredential bound to this
    tenant and subscription; they do not use a fallback credential chain.
    Work IQ requires separately reviewed Graph grants and explicit credentials;
    ProvisionWorkIqApp is a separate opt-in with Only work-iq, then re-run with
    the issued credentials. It does not automatically continue seeding.

    The final agent stage uses the classic agent/create_agent.py API, NOT the
    app's named Responses agent. Configure the latter separately.
.EXAMPLE
    .\deploy.ps1 -ResourceGroup <group> -SubscriptionId <subscription-guid> `
        -TenantId <tenant-guid> -Location <region> -Only bicep -WhatIf
#>
[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$ResourceGroup,
    [Alias('Subscription')]
    [string]$SubscriptionId,
    [string]$TenantId,
    [string]$Location,
    [string]$ParametersFile = (Join-Path $PSScriptRoot 'infra\main.parameters.local.json'),
    [string]$DeploymentName = 'cmintel-infra',
    [string]$FabricCapacity,
    [string]$FabricCapacityResourceGroup,
    [ValidateSet('bicep', 'fabric', 'foundry-iq', 'work-iq', 'agent')]
    [string]$Only,
    [switch]$SkipWorkIq,
    [switch]$ProvisionWorkIqApp,
    [string]$GovernanceReviewPath,
    [switch]$GovernanceApproved
)

$repoRoot = $PSScriptRoot
$ErrorActionPreference = 'Stop'
$global:LASTEXITCODE = 0
& (Join-Path $repoRoot 'setup-bank.ps1') -Check
if (-not $? -or $LASTEXITCODE -ne 0) {
    throw 'setup-bank.ps1 -Check must succeed before deployment preflight.'
}

$stages = if ($Only) { @($Only) } else { @('bicep', 'fabric', 'foundry-iq', 'work-iq', 'agent') }
if ($SkipWorkIq) { $stages = @($stages | Where-Object { $_ -ne 'work-iq' }) }
if ($stages.Count -eq 0) { throw 'No stages selected: Only work-iq conflicts with SkipWorkIq.' }
if ($ProvisionWorkIqApp -and ($Only -ne 'work-iq' -or $SkipWorkIq)) {
    throw 'ProvisionWorkIqApp requires Only work-iq without SkipWorkIq; provisioning is a separate run.'
}

function Require-Text([string]$Name, [string]$Value) {
    if ([string]::IsNullOrWhiteSpace($Value) -or $Value -ne $Value.Trim()) {
        throw "Supply an explicit nonblank $Name without surrounding whitespace."
    }
}

function Require-Guid([string]$Name, [string]$Value) {
    Require-Text $Name $Value
    $id = [guid]::Empty
    if (-not [guid]::TryParseExact($Value, 'D', [ref]$id) -or $id -eq [guid]::Empty) {
        throw "$Name must be a nonzero GUID."
    }
}

function Invoke-Az {
    param([string[]]$Arguments, [string]$Label, [switch]$Json)
    $global:LASTEXITCODE = 0
    $PSNativeCommandUseErrorActionPreference = $false
    $lines = & az @Arguments --subscription $SubscriptionId --only-show-errors
    $succeeded = $?
    $exitCode = $LASTEXITCODE
    if (-not $succeeded -or $exitCode -ne 0) { throw "$Label failed (exit $exitCode)." }
    $text = ($lines | ForEach-Object { "$_" }) -join [Environment]::NewLine
    if ($Json) {
        if ([string]::IsNullOrWhiteSpace($text)) { throw "$Label returned no JSON." }
        if (-not $text.TrimStart().StartsWith('{')) { throw "$Label must return a JSON object." }
        try { $result = $text | ConvertFrom-Json -ErrorAction Stop }
        catch { throw "$Label returned invalid JSON." }
        if ($null -eq $result) { throw "$Label returned null JSON." }
        return ,$result
    }
    return $text
}

function Write-ReadOnlyReport([string]$Label, [string[]]$Arguments) {
    Write-Host "`n--- $Label (manual review required) ---" -ForegroundColor Cyan
    $raw = Invoke-Az -Arguments $Arguments -Label $Label
    if ([string]::IsNullOrWhiteSpace($raw)) { throw "$Label returned no evidence." }
    $null = $raw | ConvertFrom-Json -ErrorAction Stop
    Write-Host $raw
}

function Invoke-Python([string]$Directory, [string[]]$Arguments) {
    if ($WhatIfPreference) { throw 'Internal safety guard: Python is forbidden in WhatIf.' }
    Push-Location (Join-Path $repoRoot $Directory)
    try {
        $global:LASTEXITCODE = 0
        $PSNativeCommandUseErrorActionPreference = $false
        & python @Arguments
        if (-not $? -or $LASTEXITCODE -ne 0) { throw "$($Arguments[0]) failed (exit $LASTEXITCODE)." }
    }
    finally { Pop-Location }
}

function Get-DeploymentOutputs {
    $deployment = Invoke-Az -Label 'Selected infrastructure deployment' -Json -Arguments @(
        'deployment', 'group', 'show', '--resource-group', $ResourceGroup, '--name', $DeploymentName,
        '--query', '{id:id,state:properties.provisioningState,outputs:properties.outputs}', '--output', 'json'
    )
    if ($deployment.id -ine "$scope/providers/Microsoft.Resources/deployments/$DeploymentName" -or
        $deployment.state -ne 'Succeeded' -or $null -eq $deployment.outputs) {
        throw 'Selected deployment is absent, incomplete or in another scope. Run Only bicep first.'
    }
    return $deployment.outputs
}

function Set-DownstreamEnvironment($Outputs) {
    $variables = @{
        SEARCH_ENDPOINT = 'searchEndpoint'; SEARCH_INDEX = 'searchIndexName'
        FOUNDRY_PROJECT_ENDPOINT = 'foundryProjectEndpoint'; FOUNDRY_MODEL = 'modelDeploymentName'
        BING_GROUNDING_CONNECTION = 'bingConnectionName'
    }
    foreach ($key in $variables.Keys) {
        $value = $Outputs.($variables[$key]).value
        if ($value -isnot [string] -or [string]::IsNullOrWhiteSpace($value)) {
            throw "Required deployment output '$($variables[$key])' is missing."
        }
        if ($key -eq 'BING_GROUNDING_CONNECTION' -and $value -eq 'not-deployed') { $value = '' }
        Set-Item -Path "Env:$key" -Value $value
    }
    $expectedFoundry = "https://$($parameters.foundryAccountName.value).services.ai.azure.com/api/projects/$($parameters.foundryProjectName.value)"
    if ($env:FOUNDRY_PROJECT_ENDPOINT.TrimEnd('/') -cne $expectedFoundry -or
        $env:FOUNDRY_MODEL -cne $parameters.modelDeploymentName.value) {
        throw 'Deployment Foundry outputs do not match the reviewed local parameters.'
    }
    $searchName = $Outputs.searchServiceName.value
    Require-Text 'searchServiceName output' $searchName
    if ($env:SEARCH_ENDPOINT.TrimEnd('/') -ine "https://$searchName.search.windows.net") {
        throw 'Search output is not the endpoint of the selected deployment service.'
    }
    if ($parameters.createSearch.value -eq $false -and $searchName -cne $parameters.searchServiceName.value) {
        throw 'Deployment Search service does not match the reviewed existing service.'
    }
    # Never let an ambient admin key silently authenticate to a different estate.
    Remove-Item Env:SEARCH_ADMIN_KEY -ErrorAction SilentlyContinue
}

foreach ($name in @('ResourceGroup', 'Location', 'DeploymentName')) {
    Require-Text "-$name" (Get-Variable -Name $name -ValueOnly)
}
Require-Guid '-SubscriptionId' $SubscriptionId
Require-Guid '-TenantId' $TenantId
if ($ResourceGroup -notmatch '^[\w().-]{1,90}$' -or $ResourceGroup.EndsWith('.')) { throw 'Invalid ResourceGroup name.' }
if ($Location -notmatch '^[a-z0-9]+$') { throw 'Location must be a canonical Azure region name.' }
if ($DeploymentName -notmatch '^[a-zA-Z0-9_.()-]{1,64}$') { throw 'Invalid DeploymentName.' }
if ($ParametersFile -notmatch '\.local\.json$' -or -not (Test-Path -LiteralPath $ParametersFile -PathType Leaf)) {
    throw 'Create infra\main.parameters.local.json from main.parameters.example.json, fill reviewed targets, and pass -ParametersFile if using another *.local.json.'
}
$ParametersFile = (Resolve-Path -LiteralPath $ParametersFile).ProviderPath
try { $document = Get-Content -LiteralPath $ParametersFile -Raw | ConvertFrom-Json -ErrorAction Stop }
catch { throw 'ParametersFile is not valid deployment-parameters JSON.' }
$parameters = $document.parameters
if ($null -eq $parameters) { throw 'ParametersFile must contain a parameters object.' }
foreach ($name in @('location', 'foundryAccountName', 'foundryProjectName', 'modelDeploymentName')) {
    if ($parameters.$name.value -isnot [string]) { throw "parameters.$name.value must be a string." }
    Require-Text "parameters.$name.value" $parameters.$name.value
}
if ($parameters.location.value -ine $Location) { throw 'Parameter-file location must match -Location; no silent override is permitted.' }
foreach ($name in @('createSearch', 'createFoundry', 'createFabricCapacity')) {
    if ($parameters.$name.value -isnot [bool]) { throw "parameters.$name.value must be an explicit boolean." }
}
if (-not $parameters.createSearch.value) { Require-Text 'searchServiceName for an existing Search service' $parameters.searchServiceName.value }
foreach ($name in @('fabricAdminMembers', 'demoUserPrincipalIds')) {
    if ($parameters.$name.value -isnot [array]) { throw "parameters.$name.value must be an array (empty skips grants)." }
    foreach ($id in $parameters.$name.value) { Require-Guid "parameters.$name member" $id }
}
if ($parameters.agentPrincipalId.value -isnot [string]) { throw 'agentPrincipalId must be an explicit string; use empty to skip operator grants.' }
if ($parameters.agentPrincipalId.value) { Require-Guid 'agentPrincipalId' $parameters.agentPrincipalId.value }
if ($parameters.createFabricCapacity.value) {
    Require-Text 'fabricCapacityName' $parameters.fabricCapacityName.value
    if ($parameters.fabricAdminMembers.value.Count -eq 0) { throw 'Creating Fabric capacity requires explicitly reviewed fabricAdminMembers.' }
}
if ($stages -contains 'fabric') {
    Require-Text '-FabricCapacity' $FabricCapacity
    Require-Text '-FabricCapacityResourceGroup' $FabricCapacityResourceGroup
    if ($FabricCapacity -cnotmatch '^[a-z0-9]{3,63}$' -or $FabricCapacityResourceGroup -notmatch '^[\w().-]{1,90}$' -or $FabricCapacityResourceGroup.EndsWith('.')) {
        throw 'Invalid Fabric capacity/resource group name.'
    }
    if ($parameters.fabricCapacityName.value -cne $FabricCapacity) { throw '-FabricCapacity must match local fabricCapacityName.' }
    if ($parameters.createFabricCapacity.value -and $FabricCapacityResourceGroup -ine $ResourceGroup) {
        throw 'New Fabric capacity must be in the deployment resource group.'
    }
    foreach ($name in @('FABRIC_WORKSPACE_NAME', 'FABRIC_LAKEHOUSE_NAME', 'FABRIC_LOAD_NOTEBOOK_NAME',
            'FABRIC_SEMANTIC_NOTEBOOK_NAME', 'FABRIC_SEMANTIC_MODEL_NAME')) {
        Require-Text "environment variable $name" ([Environment]::GetEnvironmentVariable($name))
    }
}
if ($stages -contains 'work-iq') {
    Require-Guid 'WORKIQ_TENANT_ID' $env:WORKIQ_TENANT_ID
    if ($env:WORKIQ_TENANT_ID -ine $TenantId) { throw 'WORKIQ_TENANT_ID must match the explicitly selected TenantId.' }
    if ($ProvisionWorkIqApp) { Require-Text 'WORKIQ_SEEDER_APP_NAME' $env:WORKIQ_SEEDER_APP_NAME }
    else {
        Require-Guid 'WORKIQ_CLIENT_ID' $env:WORKIQ_CLIENT_ID
        foreach ($name in @('WORKIQ_CLIENT_SECRET', 'WORKIQ_USER_MAPPING_FILE', 'WORKIQ_RESTORE_FILE')) {
            Require-Text "environment variable $name" ([Environment]::GetEnvironmentVariable($name))
        }
        if (-not (Test-Path -LiteralPath $env:WORKIQ_USER_MAPPING_FILE -PathType Leaf)) {
            throw 'WORKIQ_USER_MAPPING_FILE must point to your existing private persona mapping.'
        }
        if (-not [IO.Path]::IsPathFullyQualified($env:WORKIQ_USER_MAPPING_FILE) -or
            -not [IO.Path]::IsPathFullyQualified($env:WORKIQ_RESTORE_FILE)) {
            throw 'Use absolute WORKIQ_USER_MAPPING_FILE and WORKIQ_RESTORE_FILE paths; the stage changes working directory.'
        }
    }
}
if ($stages -contains 'foundry-iq' -or ($stages -contains 'agent' -and $env:IQ_MODE -eq 'hybrid')) {
    Require-Text 'SEARCH_SEMANTIC_CONFIGURATION' $env:SEARCH_SEMANTIC_CONFIGURATION
}
if ($stages -contains 'agent') {
    foreach ($name in @('FOUNDRY_AGENT_NAME', 'CM_CLIENT_ID', 'IQ_MODE')) {
        Require-Text "environment variable $name" ([Environment]::GetEnvironmentVariable($name))
    }
    if ($env:IQ_MODE -notin @('local', 'hybrid')) { throw 'IQ_MODE must be local or hybrid.' }
    if ($env:IQ_MODE -eq 'hybrid') {
        Require-Text 'BING_GROUNDING_CONNECTION_ID' $env:BING_GROUNDING_CONNECTION_ID
    }
}
$scripts = @{
    fabric = @('data\fabric-iq\generate_fabric_data.py', 'data\fabric-iq\deploy_fabric.py')
    'foundry-iq' = @('data\foundry-iq\check_corpus.py', 'data\foundry-iq\index_cm_policies.py')
    'work-iq' = @('data\work-iq\seed_work_iq.py')
    agent = @('agent\create_agent.py')
}
if ($ProvisionWorkIqApp) { $scripts['work-iq'] = @('data\work-iq\provision_seeder_app.py') }
foreach ($stage in $stages) {
    foreach ($script in $scripts[$stage]) {
        if (-not (Test-Path -LiteralPath (Join-Path $repoRoot $script) -PathType Leaf)) { throw "Required stage script is missing: $script" }
    }
}

$scope = "/subscriptions/$SubscriptionId/resourceGroups/$ResourceGroup"
$reviewPlan = [ordered]@{
    subscriptionId = $SubscriptionId; tenantId = $TenantId; resourceGroup = $ResourceGroup
    location = $Location; deploymentMode = ($stages -join ','); deploymentName = $DeploymentName
    parametersSha256 = (Get-FileHash -LiteralPath $ParametersFile -Algorithm SHA256).Hash
    provisionWorkIqApp = [bool]$ProvisionWorkIqApp
    fabricCapacity = $FabricCapacity; fabricCapacityResourceGroup = $FabricCapacityResourceGroup
    fabricWorkspaceName = $env:FABRIC_WORKSPACE_NAME; fabricLakehouseName = $env:FABRIC_LAKEHOUSE_NAME
    fabricLoadNotebookName = $env:FABRIC_LOAD_NOTEBOOK_NAME
    fabricSemanticNotebookName = $env:FABRIC_SEMANTIC_NOTEBOOK_NAME
    fabricSemanticModelName = $env:FABRIC_SEMANTIC_MODEL_NAME
    workIqClientId = $env:WORKIQ_CLIENT_ID; workIqSeederAppName = $env:WORKIQ_SEEDER_APP_NAME
    workIqMappingFile = $env:WORKIQ_USER_MAPPING_FILE; workIqRestoreFile = $env:WORKIQ_RESTORE_FILE
    workIqMappingSha256 = $(if ($stages -contains 'work-iq' -and -not $ProvisionWorkIqApp) {
        (Get-FileHash -LiteralPath $env:WORKIQ_USER_MAPPING_FILE -Algorithm SHA256).Hash
    })
    searchSemanticConfiguration = $env:SEARCH_SEMANTIC_CONFIGURATION
    agentName = $env:FOUNDRY_AGENT_NAME; clientId = $env:CM_CLIENT_ID; iqMode = $env:IQ_MODE
    bingGroundingConnectionId = $env:BING_GROUNDING_CONNECTION_ID
    templates = @(Get-ChildItem -LiteralPath (Join-Path $repoRoot 'infra') -Filter '*.bicep' -Recurse |
        Sort-Object FullName | ForEach-Object { (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash })
}
$hash = [Security.Cryptography.SHA256]::Create()
try { $digest = $hash.ComputeHash([Text.Encoding]::UTF8.GetBytes(($reviewPlan | ConvertTo-Json -Depth 10 -Compress))) }
finally { $hash.Dispose() }
$planSha256 = ([BitConverter]::ToString($digest)).Replace('-', '').ToLowerInvariant()

Write-Host "`n=== CURRENT READ-ONLY PRE-FLIGHT REPORT ===" -ForegroundColor Cyan
Write-Host ($reviewPlan | ConvertTo-Json -Depth 10)
Write-Host "planSha256: $planSha256"
Write-Host 'Target parameter values (review every resource, SKU, region and optional grant):'
Write-Host ($parameters | ConvertTo-Json -Depth 20)
$account = Invoke-Az -Label 'Target account' -Json -Arguments @('account', 'show', '--output', 'json')
if ($account.id -ine $SubscriptionId -or $account.tenantId -ine $TenantId -or $account.state -ne 'Enabled') {
    throw 'Azure CLI account does not match the explicit enabled subscription/tenant.'
}
if (@($stages | Where-Object { $_ -ne 'bicep' }).Count -gt 0 -and
    ($account.isDefault -isnot [bool] -or $account.isDefault -ne $true)) {
    throw 'Data-plane helpers require this reviewed subscription/tenant to be the current CLI default. Select it explicitly in Azure CLI before rerunning; this script never switches accounts.'
}
Write-Host "Caller: $($account.user.name); tenant: $($account.tenantId); subscription: $($account.id)"
Write-ReadOnlyReport 'Inherited policy assignments' @(
    'policy', 'assignment', 'list', '--scope', $scope, '--disable-scope-strict-match', '--output', 'json'
)
Write-ReadOnlyReport 'Subscription compliance posture (top five)' @(
    'policy', 'state', 'summarize', '--top', '5', '--output', 'json'
)
Write-Host @'
Review Deny, DeployIfNotExists, Modify and Audit effects, policy/initiative definitions,
parameters, exemptions and actual resource properties against the target. No custom
policy evaluator is used. Missing standards and old image-only approvals are NOT approval.
'@
$groupState = Invoke-Az -Label 'Target group existence' -Arguments @('group', 'exists', '--name', $ResourceGroup, '--output', 'json')
if ($groupState.Trim() -cnotmatch '^(true|false)$') { throw 'Group existence check did not return a JSON boolean.' }
$groupExists = $groupState.Trim() -ceq 'true'
$readScope = if ($groupExists) { $scope } else { "/subscriptions/$SubscriptionId" }
if ($account.user.type -eq 'user') {
    $identity = Invoke-Az -Label 'Signed-in identity' -Json -Arguments @('ad', 'signed-in-user', 'show', '--output', 'json')
}
elseif ($account.user.type -eq 'servicePrincipal') {
    $identity = Invoke-Az -Label 'Signed-in service principal' -Json -Arguments @('ad', 'sp', 'show', '--id', $account.user.name, '--output', 'json')
}
else { throw 'Unsupported CLI identity type; obtain a reviewable identity before deployment.' }
Require-Guid 'Caller object ID' $identity.id
$roleArgs = @('role', 'assignment', 'list', '--assignee', $identity.id, '--scope', $readScope, '--include-inherited', '--output', 'json')
if ($account.user.type -eq 'user') { $roleArgs += '--include-groups' }
Write-ReadOnlyReport "Roles at $readScope (including inherited)" $roleArgs
$permissionsBase = "https://management.azure.com$readScope/providers/Microsoft.Authorization/permissions"
$permissionsUrl = "${permissionsBase}?api-version=2022-04-01"
$seenPages = @{}
do {
    if ($seenPages.ContainsKey($permissionsUrl)) { throw 'Repeated permissions page; evidence is incomplete.' }
    $seenPages[$permissionsUrl] = $true
    $rawPermissions = Invoke-Az -Label 'Effective permissions evidence' -Arguments @('rest', '--method', 'get', '--url', $permissionsUrl, '--output', 'json')
    if (-not $rawPermissions.TrimStart().StartsWith('{')) { throw 'Permissions response must be a JSON object.' }
    $page = $rawPermissions | ConvertFrom-Json -ErrorAction Stop
    if ($page.value -isnot [array]) { throw 'Permissions response needs an array; evidence is incomplete.' }
    foreach ($permission in $page.value) {
        if ($permission -isnot [pscustomobject]) { throw 'Invalid permission entry; evidence is incomplete.' }
        foreach ($field in @('actions', 'notActions', 'dataActions', 'notDataActions')) {
            if ($permission.$field -isnot [array]) { throw "Permission '$field' must be an array." }
            foreach ($action in $permission.$field) {
                if ($action -isnot [string] -or [string]::IsNullOrWhiteSpace($action)) { throw "Invalid permission '$field' entry." }
            }
        }
    }
    if ($null -ne $page.nextLink -and $page.nextLink -isnot [string]) { throw 'Permissions nextLink must be a URL string.' }
    Write-Host ($page | ConvertTo-Json -Depth 30)
    $permissionsUrl = $page.nextLink
    if ($permissionsUrl -and -not $permissionsUrl.StartsWith("${permissionsBase}?", [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Permissions pagination left the selected scope.'
    }
} while ($permissionsUrl)
if ($stages -contains 'fabric') {
    $capacityScope = "/subscriptions/$SubscriptionId/resourceGroups/$FabricCapacityResourceGroup"
    Write-Host "Additional Fabric scope requiring review: $capacityScope/providers/Microsoft.Fabric/capacities/$FabricCapacity"
    if ($capacityScope -ine $scope) {
        Write-ReadOnlyReport 'Fabric inherited policy assignments' @('policy', 'assignment', 'list', '--scope', $capacityScope, '--disable-scope-strict-match', '--output', 'json')
        $capacityRoleArgs = @('role', 'assignment', 'list', '--assignee', $identity.id, '--scope', $capacityScope, '--include-inherited', '--output', 'json')
        if ($account.user.type -eq 'user') { $capacityRoleArgs += '--include-groups' }
        Write-ReadOnlyReport 'Fabric role assignments' $capacityRoleArgs
    }
}
Write-Host @'
Permissions sufficient? NOT automatically proven. Manual action/scope review REQUIRED:
  bicep: Microsoft.Resources/subscriptions/resourceGroups/write (new group),
    Microsoft.Resources/deployments/read, write, validate/action, whatIf/action;
    Microsoft.Search/searchServices/read, write, listAdminKeys/action;
    Microsoft.CognitiveServices/accounts/read, write; accounts/projects/read, write;
    accounts/deployments/read, write; accounts/connections/write;
    Microsoft.Bing/accounts/read, write, listKeys/action;
    Microsoft.Fabric/capacities/read, write (if created);
    Microsoft.Authorization/roleAssignments/read, write; roleDefinitions/read
    only for the exact optional principals/scopes in the template.
  foundry-iq: Search index/schema/document data-plane writes; chosen Entra roles.
  fabric: capacity read; Fabric workspace creation/binding, lakehouse, OneLake,
    notebook execution and semantic model rights on the exact selected items.
  work-iq: separately review Graph tenant consent, application/delegated grants,
    persona/mapping restoration, mailbox/Teams/files write scope and identity.
    ProvisionWorkIqApp additionally creates an Entra application/secret and grants.
  agent: Foundry project data-plane agent creation/update and tool permissions.
RBAC listings cannot prove Fabric, Graph, Foundry data-plane grants or account for
all deny assignments, conditional access, PIM and service restrictions. STOP and
escalate if any required permission is missing. The acknowledgement is NOT proof.
'@
$standards = @{
    namingStandard = Join-Path $repoRoot 'docs\naming.md'
    allowedSkusAndRegions = Join-Path $repoRoot 'docs\allowed.md'
}
foreach ($key in $standards.Keys) {
    if (Test-Path -LiteralPath $standards[$key] -PathType Leaf) {
        Write-Host "`n--- $($standards[$key]) ---"
        Write-Host (Get-Content -LiteralPath $standards[$key] -Raw)
    }
    else { Write-Warning "Missing $($standards[$key]); provide an explicit external: reviewed standard, not assumed approval." }
}

if ($WhatIfPreference) {
    Write-Host "WHATIF: requested stages $($stages -join ', '); no group, Python, data-plane or Graph writes."
    if ($stages -contains 'bicep' -and $groupExists) {
        $preview = Invoke-Az -Label 'ARM what-if' -Json -Arguments @(
            'deployment', 'group', 'what-if', '--resource-group', $ResourceGroup, '--name', $DeploymentName,
            '--template-file', (Join-Path $repoRoot 'infra\main.bicep'), '--parameters', $ParametersFile,
            '--result-format', 'ResourceIdOnly', '--no-pretty-print', '--output', 'json'
        )
        if ($preview.status -ne 'Succeeded' -or $null -eq $preview.changes) { throw 'ARM what-if did not return a successful change report.' }
        foreach ($change in $preview.changes) { Write-Host "$($change.changeType): $($change.resourceId)" }
    }
    elseif ($stages -contains 'bicep') { Write-Host 'Group is absent: ARM what-if skipped. No group will be created in preview.' }
    Write-Host 'Preview is not authorization. Review the evidence and matching planSha256 before creating governance evidence.'
    return
}

if ($GovernanceReviewPath -notmatch '\.local\.json$' -or -not (Test-Path -LiteralPath $GovernanceReviewPath -PathType Leaf)) {
    throw 'After manual preflight review, supply -GovernanceReviewPath pointing to deployer-created *.local.json evidence. See Get-Help .\deploy.ps1 -Full.'
}
try { $review = Get-Content -LiteralPath $GovernanceReviewPath -Raw | ConvertFrom-Json -ErrorAction Stop }
catch { throw 'GovernanceReviewPath contains invalid JSON.' }
if ($review.reviewed -isnot [bool] -or -not $review.reviewed) { throw 'Governance evidence requires reviewed: true.' }
foreach ($key in @('subscriptionId', 'tenantId', 'resourceGroup', 'location', 'deploymentMode')) {
    if ($review.$key -isnot [string] -or $review.$key -ine $reviewPlan[$key]) { throw "Governance evidence '$key' does not match this target/stage." }
}
if ($review.planSha256 -cne $planSha256) { throw 'Governance planSha256 mismatch: review the current target, parameters, stages and templates again.' }
foreach ($key in @('namingStandard', 'allowedSkusAndRegions', 'policyReview', 'permissionReview')) {
    if ($review.$key -isnot [string]) { throw "Governance evidence requires a '$key' review string." }
    Require-Text "review.$key" $review.$key
}
foreach ($key in $standards.Keys) {
    if (-not (Test-Path -LiteralPath $standards[$key] -PathType Leaf) -and $review.$key -notmatch '^external:\s*\S.+') {
        throw "Missing local standard: '$key' must reference an external: reviewed standard."
    }
}
if (-not $GovernanceApproved) { throw 'Pass -GovernanceApproved only after the documented target-specific manual review.' }
Write-Host 'Prior manual review acknowledged. Effective permissions remain NOT automatically proven.'
if (-not $PSCmdlet.ShouldProcess($scope, "Run reviewed stages: $($stages -join ', ')")) {
    Write-Host 'Deployment declined; no mutation stages ran.'
    return
}

# Bind helper credentials to this reviewed target, and restore ambient settings on exit.
$environmentNames = @('AZURE_TENANT_ID', 'AZURE_SUBSCRIPTION_ID', 'AZURE_AUTH_MODE', 'AZURE_CLIENT_ID',
    'AZURE_CLIENT_SECRET', 'AZURE_CLIENT_CERTIFICATE_PATH', 'SEARCH_ENDPOINT', 'SEARCH_INDEX', 'SEARCH_ADMIN_KEY',
    'FOUNDRY_PROJECT_ENDPOINT', 'FOUNDRY_MODEL', 'BING_GROUNDING_CONNECTION', 'FABRIC_CAPACITY_NAME')
$savedEnvironment = @{}
foreach ($name in $environmentNames) { $savedEnvironment[$name] = [Environment]::GetEnvironmentVariable($name) }
try {
    $env:AZURE_TENANT_ID = $TenantId
    $env:AZURE_SUBSCRIPTION_ID = $SubscriptionId
    $env:AZURE_AUTH_MODE = 'azure_cli'
    foreach ($name in @('AZURE_CLIENT_ID', 'AZURE_CLIENT_SECRET', 'AZURE_CLIENT_CERTIFICATE_PATH')) {
        Remove-Item -Path "Env:$name" -ErrorAction SilentlyContinue
    }
    if ($stages -contains 'bicep') {
        if (-not $groupExists) {
            $null = Invoke-Az -Label 'Create resource group' -Arguments @('group', 'create', '--name', $ResourceGroup,
                '--location', $Location, '--tags', 'solution=capital-markets-client-intelligence',
                'dataClassification=synthetic-demo-data', 'managedBy=bicep', '--output', 'none')
        }
        $result = Invoke-Az -Label 'Bicep deployment' -Json -Arguments @(
            'deployment', 'group', 'create', '--resource-group', $ResourceGroup, '--name', $DeploymentName,
            '--template-file', (Join-Path $repoRoot 'infra\main.bicep'), '--parameters', $ParametersFile, '--output', 'json'
        )
        if ($result.properties.provisioningState -ne 'Succeeded') { throw 'Bicep deployment did not succeed.' }
    }
    if ($stages -contains 'foundry-iq' -or $stages -contains 'agent') {
        Set-DownstreamEnvironment (Get-DeploymentOutputs)
    }
    if ($stages -contains 'fabric') {
        $capacityId = "/subscriptions/$SubscriptionId/resourceGroups/$FabricCapacityResourceGroup/providers/Microsoft.Fabric/capacities/$FabricCapacity"
        $capacity = Invoke-Az -Label 'Selected Fabric capacity' -Json -Arguments @(
            'resource', 'show', '--ids', $capacityId, '--api-version', '2023-11-01', '--output', 'json'
        )
        if ($capacity.id -ine $capacityId -or $capacity.properties.state -ne 'Active') { throw 'Explicit Fabric capacity is missing or not Active. No resume is attempted.' }
        $env:FABRIC_CAPACITY_NAME = $FabricCapacity
        Invoke-Python 'data\fabric-iq' @('generate_fabric_data.py', '--check')
        Invoke-Python 'data\fabric-iq' @('deploy_fabric.py', '--capacity', $FabricCapacity)
    }
    if ($stages -contains 'foundry-iq') {
        Invoke-Python 'data\foundry-iq' @('check_corpus.py')
        Invoke-Python 'data\foundry-iq' @('index_cm_policies.py')
    }
    if ($stages -contains 'work-iq') {
        if ($ProvisionWorkIqApp) {
            Invoke-Python 'data\work-iq' @('provision_seeder_app.py')
            Write-Host 'Seeder provisioning completed only. Export the issued WORKIQ credentials securely and rerun Only work-iq without ProvisionWorkIqApp after reviewing its plan.'
            return
        }
        Invoke-Python 'data\work-iq' @('seed_work_iq.py', '--auth', 'cli', '--check-users')
        Invoke-Python 'data\work-iq' @('seed_work_iq.py', '--auth', 'cli', '--map-users')
        foreach ($kind in @('mail', 'teams', 'files')) {
            Invoke-Python 'data\work-iq' @('seed_work_iq.py', '--only', $kind)
        }
        Write-Warning 'Teams channel messages require a separately reviewed delegated-auth run; application-only seeding is not channel-message completion.'
    }
    if ($stages -contains 'agent') {
        Invoke-Python 'agent' @('create_agent.py', '--create')
        Write-Warning 'Classic agent created/updated. The app requires a separately configured named Responses agent; these are not interchangeable.'
    }
    Write-Host 'Requested deployment stages completed successfully. Use the explicitly configured demo driver, not an administrator.' -ForegroundColor Green
}
finally {
    foreach ($name in $environmentNames) {
        if ($null -eq $savedEnvironment[$name]) { Remove-Item -Path "Env:$name" -ErrorAction SilentlyContinue }
        else { [Environment]::SetEnvironmentVariable($name, $savedEnvironment[$name], 'Process') }
    }
}
