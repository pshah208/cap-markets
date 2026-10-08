[CmdletBinding()]
param(
    [AllowEmptyString()][string]$BankName,
    [AllowEmptyString()][string]$BankShortName,
    [AllowEmptyString()][string]$PrimaryColor,
    [AllowEmptyString()][string]$AccentColor,
    [AllowEmptyString()][string]$LogoPath,
    [switch]$Check,
    [switch]$NonInteractive
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-CodePointCount {
    param([string]$Value)
    $count = 0
    for ($index = 0; $index -lt $Value.Length; $index++) {
        if ([char]::IsHighSurrogate($Value[$index]) -and ($index + 1) -lt $Value.Length -and
            [char]::IsLowSurrogate($Value[$index + 1])) {
            $index++
        }
        $count++
    }
    return $count
}

function Invoke-BankValidator {
    param([string]$Mode, [string]$Json)
    $node = Get-Command node -CommandType Application -ErrorAction Stop | Select-Object -First 1
    $webRoot = Join-Path $PSScriptRoot 'app\src\web'
    $validator = Join-Path $webRoot 'scripts\bank-config.mjs'
    if (-not (Test-Path -LiteralPath $validator -PathType Leaf)) {
        throw 'Shared bank validator is missing: app\src\web\scripts\bank-config.mjs.'
    }
    $start = New-Object System.Diagnostics.ProcessStartInfo
    $start.FileName = $node.Source
    # Only the trusted script path and fixed mode enter the native argument string.
    $start.Arguments = '"' + $validator + '" ' + $Mode
    $start.WorkingDirectory = (Get-Location).ProviderPath
    $start.UseShellExecute = $false
    $start.RedirectStandardInput = $true
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    $utf8 = New-Object System.Text.UTF8Encoding($false)
    $start.StandardOutputEncoding = $utf8
    $start.StandardErrorEncoding = $utf8
    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $start
    try {
        [void]$process.Start()
        $stdout = $process.StandardOutput.ReadToEndAsync()
        $stderr = $process.StandardError.ReadToEndAsync()
        if ($Mode -eq '--write') {
            # BaseStream keeps UTF-8 intact on both Windows PowerShell 5 and PowerShell 7.
            $bytes = $utf8.GetBytes($Json)
            $process.StandardInput.BaseStream.Write($bytes, 0, $bytes.Length)
            $process.StandardInput.BaseStream.Flush()
        }
        $process.StandardInput.Close()
        $process.WaitForExit()
        $output = $stdout.GetAwaiter().GetResult()
        $failure = $stderr.GetAwaiter().GetResult()
        if ($process.ExitCode -ne 0) {
            if ([string]::IsNullOrWhiteSpace($failure)) {
                throw ('Bank validator failed with exit code ' + $process.ExitCode + '.')
            }
            throw $failure.Trim()
        }
        if (-not [string]::IsNullOrWhiteSpace($output)) {
            Write-Output $output.Trim()
        }
    }
    finally {
        $process.Dispose()
    }
}

try {
    $creationKeys = @('BankName', 'BankShortName', 'PrimaryColor', 'AccentColor', 'LogoPath')
    if ($PSBoundParameters.ContainsKey('Check')) {
        foreach ($key in $creationKeys) {
            if ($PSBoundParameters.ContainsKey($key)) {
                throw '-Check cannot be combined with bank creation options.'
            }
        }
        if (-not $Check) {
            throw 'Omit -Check to create configuration; -Check:$false is not a creation mode.'
        }
        Invoke-BankValidator -Mode '--check'
        exit 0
    }

    $interactive = $PSBoundParameters.Count -eq 0
    if ($interactive) {
        Write-Output 'Configure your bank locally before running the application. No bank is preselected.'
        do {
            $BankName = (Read-Host 'Bank name (required, 1..120 characters)').Trim()
        } while ([string]::IsNullOrWhiteSpace($BankName))

        $shortDefault = ''
        if ((Get-CodePointCount $BankName) -le 32) {
            $shortDefault = $BankName
        }
        $shortPrompt = 'Short bank name (required, 1..32 characters)'
        if ($shortDefault) {
            $shortPrompt += ' [' + $shortDefault + ']'
        }
        do {
            $BankShortName = (Read-Host $shortPrompt).Trim()
            if (-not $BankShortName -and $shortDefault) {
                $BankShortName = $shortDefault
            }
        } while ([string]::IsNullOrWhiteSpace($BankShortName))
        $PrimaryColor = (Read-Host 'Primary color [#334155]').Trim()
        if (-not $PrimaryColor) { $PrimaryColor = '#334155' }
        $AccentColor = (Read-Host 'Accent color [#64748b]').Trim()
        if (-not $AccentColor) { $AccentColor = '#64748b' }
        $LogoPath = Read-Host 'Optional local PNG logo path (Enter for text initials)'
    }
    else {
        if (-not $PSBoundParameters.ContainsKey('BankName') -or [string]::IsNullOrWhiteSpace($BankName)) {
            throw 'BankName is required for parameterized/noninteractive setup. Supply -BankName.'
        }
        $BankName = $BankName.Trim()
        if (-not $PSBoundParameters.ContainsKey('BankShortName')) {
            if ((Get-CodePointCount $BankName) -gt 32) {
                throw 'BankName exceeds 32 characters; supply an explicit -BankShortName.'
            }
            $BankShortName = $BankName
        }
        if (-not $PSBoundParameters.ContainsKey('PrimaryColor')) { $PrimaryColor = '#334155' }
        if (-not $PSBoundParameters.ContainsKey('AccentColor')) { $AccentColor = '#64748b' }
        if ($PSBoundParameters.ContainsKey('LogoPath') -and [string]::IsNullOrWhiteSpace($LogoPath)) {
            throw 'LogoPath must be a nonempty local PNG path when supplied; omit it for text initials.'
        }
    }

    $config = [ordered]@{
        schemaVersion = 1
        bankName = $BankName
        bankShortName = $BankShortName.Trim()
        primaryColor = $PrimaryColor
        accentColor = $AccentColor
    }
    $inputData = [ordered]@{ config = $config }
    if (-not [string]::IsNullOrEmpty($LogoPath)) {
        $config.logo = 'logo.png'
        $inputData.logoPath = $LogoPath
    }
    $json = ConvertTo-Json -InputObject $inputData -Depth 4 -Compress
    Invoke-BankValidator -Mode '--write' -Json $json
}
catch {
    [Console]::Error.WriteLine('Bank setup failed: ' + $_.Exception.Message)
    [Console]::Error.WriteLine('Run setup-bank.ps1 interactively, or supply -BankName and optional -BankShortName. Use -Check for local validation.')
    exit 1
}
