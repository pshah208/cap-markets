<#
.SYNOPSIS
    End-to-end deployment for the BMO Capital Markets Client Intelligence demo.

.DESCRIPTION
    Runs the full stack in dependency order:

      1. bicep      Azure control plane - AI Search, Foundry account/project/model,
                    Grounding with Bing connection, role assignments.
      2. fabric     workspace, lakehouse, OneLake upload, Delta tables, Direct Lake
                    semantic model (Fabric data plane - no ARM provider).
      3. foundry-iq AI Search index + the 14 policy documents (CP-001..CP-014).
      4. work-iq    Entra app registration, persona job titles, then mail, Teams and
                    files into Microsoft 365 (Graph - no ARM provider).
      5. agent      the Foundry agent and its four function tools.

    Every stage is idempotent and can be run on its own with -Only.

    SYNTHETIC DEMO DATA. BMO Capital Markets is a branding label only. Gibson
    Energy Inc. (TSX:GEI), Keyera Corp. and the other TSX-listed issuers are real,
    publicly listed companies named only so live web grounding returns real public
    news; every internal figure is invented for a demo.

.PARAMETER ResourceGroup
    Resource group for the Bicep deployment. Default rg-cmintel-demo.

.PARAMETER FabricCapacity
    Name of the Fabric capacity hosting the workspace. Default fabcap26.

.PARAMETER Only
    Run a single stage: bicep | fabric | foundry-iq | work-iq | agent.

.PARAMETER SkipWorkIq
    Skip the Microsoft 365 seeding. Use when the tenant content already exists -
    re-seeding is safe but slow, and the Teams message step needs interactive auth.

.PARAMETER WhatIf
    For the bicep stage, run what-if instead of deploying.

.EXAMPLE
    .\deploy.ps1 -WhatIf
    .\deploy.ps1
    .\deploy.ps1 -Only fabric
    .\deploy.ps1 -Only work-iq

.NOTES
    Prerequisites:
      * az login, against subscription ME-M365CPI65678641-shahpar-1
      * pip install -r requirements.txt
      * the Fabric capacity must be ACTIVE - the script checks and tells you how
        to resume it if it is paused
      * Global Administrator in Entra for the work-iq stage (admin consent)
#>

[CmdletBinding(SupportsShouldProcess)]
param(
    [string] $ResourceGroup = "rg-cmintel-demo",
    [string] $Location = "eastus",
    [string] $FabricCapacity = "fabcap26",
    [ValidateSet("bicep", "fabric", "foundry-iq", "work-iq", "agent")]
    [string] $Only,
    [switch] $SkipWorkIq
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$stages = if ($Only) { @($Only) } else { @("bicep", "fabric", "foundry-iq", "work-iq", "agent") }

function Write-Stage([string] $name) {
    Write-Host ""
    Write-Host ("=" * 72) -ForegroundColor Cyan
    Write-Host "  $name" -ForegroundColor Cyan
    Write-Host ("=" * 72) -ForegroundColor Cyan
}

function Assert-LastExit([string] $what) {
    if ($LASTEXITCODE -ne 0) { throw "$what failed with exit code $LASTEXITCODE" }
}

# --------------------------------------------------------------- preflight ---
Write-Stage "Pre-flight"

$acct = az account show -o json | ConvertFrom-Json
if (-not $acct) { throw "Not logged in. Run 'az login' first." }
Write-Host "  subscription : $($acct.name)  ($($acct.id))"
Write-Host "  identity     : $($acct.user.name)"

# The Fabric capacity must be Active or workspace creation fails with an opaque
# error, so check it up front and give the exact command to fix it.
if ($stages -contains "fabric") {
    $cap = az resource list --resource-type Microsoft.Fabric/capacities `
        --query "[?name=='$FabricCapacity'] | [0]" -o json | ConvertFrom-Json
    if (-not $cap) { throw "Fabric capacity '$FabricCapacity' not found in this subscription." }
    $state = (az resource show --ids $cap.id --query "properties.state" -o tsv)
    Write-Host "  capacity     : $FabricCapacity ($($cap.sku.name), $($cap.location)) - $state"
    if ($state -ne "Active") {
        Write-Host ""
        Write-Host "  Capacity is '$state'. Resume it with:" -ForegroundColor Yellow
        Write-Host "    az rest --method post --url `"https://management.azure.com$($cap.id)/resume?api-version=2023-11-01`"" -ForegroundColor Yellow
        throw "Fabric capacity '$FabricCapacity' is not Active."
    }
}

# ------------------------------------------------------------------- bicep ---
if ($stages -contains "bicep") {
    Write-Stage "1/5  Bicep - Azure control plane"

    az group create -n $ResourceGroup -l $Location `
        --tags solution=capital-markets-client-intelligence dataClassification=synthetic-demo-data managedBy=bicep `
        -o none
    Assert-LastExit "az group create"

    $infra = Join-Path $root "infra"
    $args = @(
        "deployment", "group",
        $(if ($WhatIfPreference) { "what-if" } else { "create" }),
        "-g", $ResourceGroup,
        "--template-file", (Join-Path $infra "main.bicep"),
        "--parameters", (Join-Path $infra "main.parameters.json"),
        "-n", "cmintel-infra"
    )
    az @args
    Assert-LastExit "bicep deployment"

    if (-not $WhatIfPreference) {
        $out = az deployment group show -g $ResourceGroup -n cmintel-infra `
            --query properties.outputs -o json | ConvertFrom-Json
        $env:SEARCH_ENDPOINT            = $out.searchEndpoint.value
        $env:SEARCH_INDEX               = $out.searchIndexName.value
        $env:FOUNDRY_PROJECT_ENDPOINT   = $out.foundryProjectEndpoint.value
        $env:FOUNDRY_MODEL              = $out.modelDeploymentName.value
        $env:BING_GROUNDING_CONNECTION  = $out.bingConnectionName.value
        Write-Host ""
        Write-Host "  SEARCH_ENDPOINT           = $env:SEARCH_ENDPOINT"
        Write-Host "  FOUNDRY_PROJECT_ENDPOINT  = $env:FOUNDRY_PROJECT_ENDPOINT"
        Write-Host "  FOUNDRY_MODEL             = $env:FOUNDRY_MODEL"
        Write-Host "  BING_GROUNDING_CONNECTION = $env:BING_GROUNDING_CONNECTION"
        Write-Host ""
        Write-Host "  NOTE: Azure AI Search calls back into the model deployment for" -ForegroundColor DarkGray
        Write-Host "  knowledge retrieval, so the Search managed identity needs" -ForegroundColor DarkGray
        Write-Host "  'Cognitive Services OpenAI User' on the Foundry account. The Bicep" -ForegroundColor DarkGray
        Write-Host "  grants it; RBAC can take a minute or two to propagate." -ForegroundColor DarkGray
    }
}

# ------------------------------------------------------------------ fabric ---
if ($stages -contains "fabric") {
    Write-Stage "2/5  Fabric IQ - workspace, lakehouse, Delta tables, semantic model"

    Push-Location (Join-Path $root "data\fabric-iq")
    try {
        # Regenerate and self-reconcile before uploading anything. If the CSVs no
        # longer agree with scenario_facts, stop here rather than load bad data.
        python generate_fabric_data.py --check
        Assert-LastExit "generate_fabric_data.py --check"

        python deploy_fabric.py --capacity $FabricCapacity
        Assert-LastExit "deploy_fabric.py"
    }
    finally { Pop-Location }
}

# -------------------------------------------------------------- foundry-iq ---
if ($stages -contains "foundry-iq") {
    Write-Stage "3/5  Foundry IQ - AI Search index and the 14 policy documents"

    if (-not $env:SEARCH_ENDPOINT) {
        $out = az deployment group show -g $ResourceGroup -n cmintel-infra `
            --query properties.outputs -o json 2>$null | ConvertFrom-Json
        if ($out) {
            $env:SEARCH_ENDPOINT = $out.searchEndpoint.value
            $env:SEARCH_INDEX    = $out.searchIndexName.value
        }
    }
    if (-not $env:SEARCH_ENDPOINT) { throw "SEARCH_ENDPOINT is not set. Run the bicep stage first." }

    Push-Location (Join-Path $root "data\foundry-iq")
    try {
        python check_corpus.py
        Assert-LastExit "check_corpus.py"

        python index_cm_policies.py
        Assert-LastExit "index_cm_policies.py"
    }
    finally { Pop-Location }
}

# ----------------------------------------------------------------- work-iq ---
if ($stages -contains "work-iq") {
    if ($SkipWorkIq) {
        Write-Stage "4/5  Work IQ - SKIPPED (-SkipWorkIq)"
    }
    else {
        Write-Stage "4/5  Work IQ - Microsoft 365 mail, Teams and files"

        Push-Location (Join-Path $root "data\work-iq")
        try {
            python seed_work_iq.py --auth cli --check-users
            Assert-LastExit "check-users"

            python seed_work_iq.py --auth cli --map-users
            Assert-LastExit "map-users"

            if (-not ($env:WORKIQ_CLIENT_ID -and $env:WORKIQ_CLIENT_SECRET)) {
                Write-Host ""
                Write-Host "  WORKIQ_* not set - provisioning the seeder app registration." -ForegroundColor Yellow
                python provision_seeder_app.py
                Assert-LastExit "provision_seeder_app.py"
                Write-Host ""
                Write-Host "  Set the three WORKIQ_* variables printed above, then re-run:" -ForegroundColor Yellow
                Write-Host "    .\deploy.ps1 -Only work-iq" -ForegroundColor Yellow
                return
            }

            python seed_work_iq.py --only mail
            Assert-LastExit "seed mail"

            python seed_work_iq.py --only teams
            Assert-LastExit "seed teams"

            python seed_work_iq.py --only files
            Assert-LastExit "seed files"

            Write-Host ""
            Write-Host "  Teams CHANNEL MESSAGES still need delegated auth." -ForegroundColor Yellow
            Write-Host "  ChannelMessage.Send does not exist as an application permission," -ForegroundColor Yellow
            Write-Host "  so app-only posting returns 401. Run this and sign in when prompted:" -ForegroundColor Yellow
            Write-Host "    python seed_work_iq.py --only teams --messages-only --auth device" -ForegroundColor Yellow
        }
        finally { Pop-Location }
    }
}

# ------------------------------------------------------------------- agent ---
if ($stages -contains "agent") {
    Write-Stage "5/5  Agent - Foundry agent and its four function tools"

    $agent = Join-Path $root "agent\create_agent.py"
    if (-not (Test-Path $agent)) {
        Write-Host "  agent/create_agent.py not present yet - skipping." -ForegroundColor DarkGray
    }
    else {
        Push-Location (Join-Path $root "agent")
        try {
            python create_agent.py --create
            Assert-LastExit "create_agent.py"
        }
        finally { Pop-Location }
    }
}

Write-Stage "Done"
Write-Host "  Sign in to the Foundry portal as the DEMO DRIVER, not as admin:" -ForegroundColor Green
Write-Host "    SydneyM@M365CPI65678641.OnMicrosoft.com  (Sydney Mattos)" -ForegroundColor Green
Write-Host ""
Write-Host "  Work IQ only grounds on content the signed-in user can access. Cora owns" -ForegroundColor DarkGray
Write-Host "  the relationship, is cc'd on every seeded email and owns the Teams team." -ForegroundColor DarkGray
