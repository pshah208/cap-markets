$ErrorActionPreference = 'Stop'
$source = Split-Path -Parent $PSScriptRoot
$fixture = Join-Path ([IO.Path]::GetTempPath()) ("cmci-deploy-test-" + [guid]::NewGuid().ToString('N'))
$subscription = '11111111-1111-4111-8111-111111111111'
$tenant = '22222222-2222-4222-8222-222222222222'
$client = '33333333-3333-4333-8333-333333333333'
$scope = "/subscriptions/$subscription/resourceGroups/rg-example-dev"
$deploymentTestState = @{
    Calls = [Collections.Generic.List[string]]::new()
    GroupExists = $true
}

function az {
    $command = $args -join ' '
    $deploymentTestState.Calls.Add($command)
    $global:LASTEXITCODE = 0
    if ($command -match '\b(create|update|build|set|delete)\b') {
        throw "Unexpected mutation: $command"
    }
    if ($command -like 'account show *') {
        return (@{
            id = $subscription; tenantId = $tenant; state = 'Enabled'; isDefault = $true
            user = @{ name = 'demo@example.com'; type = 'user' }
        } | ConvertTo-Json -Depth 5)
    }
    if ($command -like 'policy assignment list *' -or $command -like 'role assignment list *') { return '[]' }
    if ($command -like 'policy state summarize *') { return '{"results":{}}' }
    if ($command -like 'group exists *') { return $deploymentTestState.GroupExists.ToString().ToLowerInvariant() }
    if ($command -like 'ad signed-in-user show *') { return (@{ id = $client } | ConvertTo-Json) }
    if ($command -like 'rest --method get *') {
        return '{"value":[{"actions":["*"],"notActions":[],"dataActions":[],"notDataActions":[]}]}'
    }
    if ($command -like 'group show *') {
        return (@{ id = $scope; name = 'rg-example-dev'; location = 'eastus2' } | ConvertTo-Json)
    }
    if ($command -like 'deployment group what-if *') {
        return '{"status":"Succeeded","changes":[]}'
    }
    throw "Unmocked Azure command: $command"
}

function python { throw 'Python must never run during a deployment preview.' }

function Assert-FailureBeforeAzure([scriptblock]$Action) {
    $deploymentTestState.Calls.Clear()
    $failed = $false
    try { & $Action *> $null }
    catch { $failed = $true }
    if (-not $failed) { throw 'Expected deployment to reject the input.' }
    if ($deploymentTestState.Calls.Count -ne 0) { throw 'Azure ran before local input validation succeeded.' }
}

try {
    $null = New-Item -ItemType Directory -Path (Join-Path $fixture 'app') -Force
    Copy-Item (Join-Path $source 'deploy.ps1') $fixture
    Copy-Item (Join-Path $source 'app\deploy.ps1') (Join-Path $fixture 'app')
    foreach ($directory in @('infra', 'app\infra')) {
        foreach ($template in Get-ChildItem (Join-Path $source $directory) -Filter '*.bicep' -Recurse) {
            $relative = [IO.Path]::GetRelativePath($source, $template.FullName)
            $destination = Join-Path $fixture $relative
            $null = New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force
            Copy-Item -LiteralPath $template.FullName -Destination $destination
        }
    }
    $bankCheck = Join-Path $fixture 'setup-bank.ps1'
    Set-Content -LiteralPath $bankCheck -Value "param([switch]`$Check); throw 'Bank setup required.'"
    Assert-FailureBeforeAzure { & (Join-Path $fixture 'deploy.ps1') -WhatIf }
    Assert-FailureBeforeAzure { & (Join-Path $fixture 'app\deploy.ps1') -WhatIf }

    Set-Content -LiteralPath $bankCheck -Value 'param([switch]$Check); if (-not $Check) { throw "Expected -Check." }'
    Assert-FailureBeforeAzure { & (Join-Path $fixture 'deploy.ps1') -WhatIf }
    Assert-FailureBeforeAzure { & (Join-Path $fixture 'app\deploy.ps1') -WhatIf }

    $parameters = Get-Content (Join-Path $source 'infra\main.parameters.example.json') -Raw | ConvertFrom-Json
    $parameters.parameters.location.value = 'eastus2'
    $parameters.parameters.foundryAccountName.value = 'example-foundry'
    $parameters.parameters.foundryProjectName.value = 'example-project'
    $parameters | ConvertTo-Json -Depth 20 | Set-Content (Join-Path $fixture 'infra\main.parameters.local.json')
    $core = @{
        ResourceGroup = 'rg-example-dev'; SubscriptionId = $subscription
        TenantId = $tenant; Location = 'eastus2'; Only = 'bicep'; WhatIf = $true
    }
    foreach ($exists in @($false, $true)) {
        $deploymentTestState.GroupExists = $exists
        $deploymentTestState.Calls.Clear()
        & (Join-Path $fixture 'deploy.ps1') @core *> $null
        $previews = @($deploymentTestState.Calls | Where-Object { $_ -like 'deployment group what-if *' })
        if ($previews.Count -ne [int]$exists) { throw 'Core ARM preview did not match group-existence behavior.' }
    }

    $app = @{
        ResourceGroup = 'rg-example-dev'; SubscriptionId = $subscription
        AadTenantId = $tenant; Location = 'eastus2'; AadClientId = $client
        AadApiScope = "api://$client/access_as_user"; SpaClientId = $client
        FoundryAccountName = 'example-foundry'; FoundryProjectName = 'example-project'
        FoundryProjectEndpoint = 'https://example-foundry.services.ai.azure.com/api/projects/example-project'
        FoundryAgentName = 'example-agent'; FabricWorkspaceId = $client
        FabricLakehouseId = $client; FabricSemanticModelId = $client; WhatIf = $true
    }
    foreach ($secret in @('', 'not-a-real-secret')) {
        $deploymentTestState.Calls.Clear()
        & (Join-Path $fixture 'app\deploy.ps1') @app -AadClientSecret $secret *> $null
        $previews = @($deploymentTestState.Calls | Where-Object { $_ -like 'deployment group what-if *' })
        if ($previews.Count -ne [int][bool]$secret) { throw 'App secret-free/full ARM preview behavior was incorrect.' }
    }
    Write-Host 'Deployment regressions passed: bank gate, explicit inputs, absent/existing group, secret-free/full WhatIf.'
}
finally {
    if (Test-Path -LiteralPath $fixture) { Remove-Item -LiteralPath $fixture -Recurse -Force }
}
