<#
.SYNOPSIS
    Build, push and deploy the BMO Capital Markets Client Intelligence web app.

.DESCRIPTION
    Order matters here:

      1. Bicep      registry, observability, Container Apps env, both apps
                    (first pass uses placeholder images)
      2. Build+push web and BFF images to the new ACR
      3. Update both container apps to the real images
      4. Print the SPA redirect URI to register

    The Entra app registrations are NOT created here - run
    infra/provision_app_registrations.py first and pass the values in.

.EXAMPLE
    # one-time
    python infra\provision_app_registrations.py --spa-redirect http://localhost:5173

    .\deploy.ps1 -ResourceGroup rg-cmintel-demo `
                 -AadClientId <bff-client-id> `
                 -AadClientSecret <secret> `
                 -AadApiScope api://<bff-client-id>/access_as_user `
                 -FoundryProjectEndpoint https://cmintel-foundry.services.ai.azure.com/api/projects/proj-client-intelligence

    .\deploy.ps1 -ResourceGroup rg-cmintel-demo -Only images   # rebuild + redeploy code only
#>

[CmdletBinding()]
param(
    [string]$ResourceGroup = 'rg-cmintel-demo',
    [string]$NamePrefix = 'cmci',
    [string]$Location = 'eastus',

    [string]$AadClientId,
    [string]$AadClientSecret,
    [string]$AadApiScope,
    [string]$AadTenantId,

    [string]$FoundryProjectEndpoint = 'https://cmintel-foundry.services.ai.azure.com/api/projects/proj-client-intelligence',
    [string]$FoundryAccountName = 'cmintel-foundry',
    [string]$FoundryAgentName = 'Agent-cap-market',

    [ValidateSet('infra', 'images', 'all')]
    [string]$Only = 'all',
    [switch]$WhatIf
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Push-Location $root

function Stage($n, $t) {
    Write-Host ''
    Write-Host ('=' * 72) -ForegroundColor Cyan
    Write-Host " $n. $t" -ForegroundColor Cyan
    Write-Host ('=' * 72) -ForegroundColor Cyan
}

# `az acr build` streams the remote build log through colorama, which throws
# UnicodeEncodeError on a cp1252 console the moment the log contains a check
# mark. That kills the CLI with a non-zero exit code *after* the image has been
# built and pushed. Forcing UTF-8 on the console prevents the crash outright.
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$env:PYTHONIOENCODING = 'utf-8'

# Belt and braces: if the CLI still dies, trusting $LASTEXITCODE would abort on a
# healthy build, so confirm the outcome by asking the registry whether the tag
# arrived. Tag listing is eventually consistent and can lag the push by a few
# seconds, so retry before concluding the build failed.
function Assert-ImagePushed($registry, $repository, $tag) {
    $exit = $LASTEXITCODE
    foreach ($attempt in 1..6) {
        $tags = az acr repository show-tags -n $registry --repository $repository -o tsv 2>$null
        if ($tags -contains $tag) {
            if ($exit -ne 0) {
                Write-Host "   (CLI exited $exit but ${repository}:$tag was pushed - continuing)" `
                    -ForegroundColor DarkGray
            }
            return
        }
        Start-Sleep -Seconds (3 * $attempt)
    }
    throw "$repository image build failed - tag $tag is not in the registry after retries."
}

try {
    $acct = az account show --query "{sub:name,user:user.name}" -o json | ConvertFrom-Json
    if (-not $acct) { throw 'Not logged in. Run: az login' }
    Write-Host "subscription : $($acct.sub)"
    Write-Host "identity     : $($acct.user)"
    Write-Host "resource grp : $ResourceGroup"

    if (-not $AadTenantId) { $AadTenantId = az account show --query tenantId -o tsv }

    # ------------------------------------------------------------- infra ---
    if ($Only -in @('infra', 'all')) {
        Stage 1 'Azure infrastructure (Bicep)'
        if (-not ($AadClientId -and $AadClientSecret -and $AadApiScope)) {
            throw @'
Missing Entra parameters. Create the app registrations first:

    python infra\provision_app_registrations.py --spa-redirect http://localhost:5173

then pass -AadClientId, -AadClientSecret and -AadApiScope.
'@
        }

        $verb = $WhatIf ? 'what-if' : 'create'
        az deployment group $verb `
            -g $ResourceGroup `
            -n cmci-app `
            --template-file infra/main.bicep `
            --parameters `
                namePrefix=$NamePrefix `
                location=$Location `
                aadTenantId=$AadTenantId `
                aadClientId=$AadClientId `
                aadClientSecret=$AadClientSecret `
                aadApiScope=$AadApiScope `
                foundryProjectEndpoint=$FoundryProjectEndpoint `
                foundryAccountName=$FoundryAccountName `
                foundryAgentName=$FoundryAgentName `
            -o table
        if ($LASTEXITCODE -ne 0) { throw 'Bicep deployment failed.' }
        if ($WhatIf) { Write-Host "`nwhat-if only." -ForegroundColor Yellow; return }
    }

    $out = az deployment group show -g $ResourceGroup -n cmci-app `
        --query properties.outputs -o json | ConvertFrom-Json
    if (-not $out) { throw "Deployment 'cmci-app' not found. Run with -Only infra first." }

    $acr = $out.acrName.value
    $server = $out.acrLoginServer.value
    $webUrl = $out.webUrl.value
    Write-Host "`nregistry : $server"
    Write-Host "web url  : $webUrl"

    # ------------------------------------------------------------ images ---
    if ($Only -in @('images', 'all')) {
        Stage 2 'Build and push images'
        $tag = Get-Date -Format 'yyyyMMddHHmmss'

        # The web bundle is built, not configured at runtime, so these values are
        # baked in permanently. Blank ones produce an app that loads and then
        # fails at sign-in, so recover them from the deployed BFF rather than
        # letting -Only images ship an unauthenticated bundle.
        if (-not $AadTenantId) {
            $AadTenantId = az containerapp show -g $ResourceGroup -n "ca-$NamePrefix-bff" `
                --query "properties.template.containers[0].env[?name=='AAD_TENANT_ID'].value | [0]" -o tsv
        }
        if (-not $AadApiScope) {
            $AadApiScope = az containerapp show -g $ResourceGroup -n "ca-$NamePrefix-bff" `
                --query "properties.template.containers[0].env[?name=='AAD_API_SCOPE'].value | [0]" -o tsv
        }
        $spaClientId = (az ad app list --display-name cm-client-intelligence-spa `
            --query "[0].appId" -o tsv)
        foreach ($pair in @{ 'tenant id' = $AadTenantId; 'api scope' = $AadApiScope
                             'SPA client id' = $spaClientId }.GetEnumerator()) {
            if (-not $pair.Value) { throw "Could not resolve $($pair.Key) for the web build." }
        }

        Write-Host '-> BFF' -ForegroundColor Yellow
        az acr build --registry $acr --image "cmci/bff:$tag" --image "cmci/bff:latest" `
            --file src/bff/Dockerfile src/bff -o none
        Assert-ImagePushed $acr 'cmci/bff' $tag

        Write-Host '-> web (Entra values are baked into the bundle)' -ForegroundColor Yellow
        az acr build --registry $acr --image "cmci/web:$tag" --image "cmci/web:latest" `
            --file src/web/Dockerfile src/web `
            --build-arg VITE_AAD_TENANT_ID=$AadTenantId `
            --build-arg VITE_AAD_CLIENT_ID=$spaClientId `
            --build-arg VITE_API_SCOPE=$AadApiScope -o none
        Assert-ImagePushed $acr 'cmci/web' $tag

        Stage 3 'Point the apps at the new images'
        az containerapp update -g $ResourceGroup -n "ca-$NamePrefix-bff" `
            --image "$server/cmci/bff:$tag" -o none
        az containerapp update -g $ResourceGroup -n "ca-$NamePrefix-web" `
            --image "$server/cmci/web:$tag" -o none
        Write-Host "deployed tag $tag"
    }

    Stage 4 'Register the redirect URI'
    Write-Host @"
The SPA app registration needs the deployed URL as a redirect URI:

    python infra\provision_app_registrations.py --add-redirect $webUrl

Then open:  $webUrl
"@ -ForegroundColor Yellow

    Write-Host ''
    Write-Host 'DONE' -ForegroundColor Green
}
finally {
    Pop-Location
}
