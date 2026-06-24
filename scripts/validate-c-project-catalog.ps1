param(
    [string]$Catalog = "validation/projects.json",
    [string]$Report = "",
    [switch]$ProbeRemote
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($Report)) {
    $Report = if ($ProbeRemote) {
        "validation/evidence/catalog-remote-probe.json"
    } else {
        "validation/evidence/catalog-validation.json"
    }
}

function Fail($Message) {
    throw $Message
}

function Require-String($Object, $Name, $TargetId) {
    $value = $Object.$Name
    if ([string]::IsNullOrWhiteSpace([string]$value)) {
        Fail "target '$TargetId' missing required string field '$Name'"
    }
}

function Require-Array($Object, $Name, $TargetId) {
    $value = $Object.$Name
    if ($null -eq $value -or @($value).Count -eq 0) {
        Fail "target '$TargetId' missing required non-empty array field '$Name'"
    }
}

function Probe-Head($RepoUrl) {
    $output = & git ls-remote --symref $RepoUrl HEAD 2>&1
    $exitCode = $LASTEXITCODE
    $branch = $null
    $sha = $null
    if ($exitCode -eq 0) {
        foreach ($line in $output) {
            if ($line -match '^ref: refs/heads/(.+)\s+HEAD$') {
                $branch = $Matches[1]
            } elseif ($line -match '^([0-9a-f]{40})\s+HEAD$') {
                $sha = $Matches[1]
            }
        }
    }
    [ordered]@{
        ok = ($exitCode -eq 0 -and -not [string]::IsNullOrWhiteSpace($sha))
        default_branch = $branch
        head_sha = $sha
        error = if ($exitCode -eq 0) { $null } else { ($output -join "`n") }
    }
}

if (-not (Test-Path -LiteralPath $Catalog)) {
    Fail "catalog not found: $Catalog"
}

$raw = Get-Content -Raw -LiteralPath $Catalog
$catalogObject = $raw | ConvertFrom-Json
$targets = @($catalogObject.targets)
$minimumTargets = [int]$catalogObject.minimum_targets
if ($minimumTargets -lt 12) {
    Fail "catalog minimum_targets must be at least 12"
}
if ($targets.Count -lt $minimumTargets) {
    Fail "catalog has $($targets.Count) targets, below required $minimumTargets"
}

$ids = New-Object System.Collections.Generic.HashSet[string]
$requiredStrings = @(
    "id",
    "name",
    "repo_url",
    "expected_default_branch",
    "domain",
    "language_profile",
    "migration_slice",
    "oracle_strategy",
    "performance_smoke",
    "risk_notes"
)
$requiredArrays = @("complexity_signals", "build_smoke", "test_smoke")
$targetReports = @()
$failures = @()

foreach ($target in $targets) {
    $id = [string]$target.id
    try {
        foreach ($field in $requiredStrings) {
            Require-String $target $field $id
        }
        foreach ($field in $requiredArrays) {
            Require-Array $target $field $id
        }
        if (-not $ids.Add($id)) {
            Fail "duplicate target id '$id'"
        }
        if ($target.repo_url -notmatch '^https://github\.com/.+/.+\.git$') {
            Fail "target '$id' repo_url must be a GitHub HTTPS .git URL"
        }
        $probe = if ($ProbeRemote) { Probe-Head ([string]$target.repo_url) } else { $null }
        if ($ProbeRemote -and -not $probe.ok) {
            $failures += "target '$id' remote probe failed"
        }
        $targetReports += [ordered]@{
            id = $id
            repo_url = [string]$target.repo_url
            domain = [string]$target.domain
            expected_default_branch = [string]$target.expected_default_branch
            probe = $probe
        }
    } catch {
        $failures += $_.Exception.Message
        $targetReports += [ordered]@{
            id = if ([string]::IsNullOrWhiteSpace($id)) { "<missing>" } else { $id }
            repo_url = [string]$target.repo_url
            domain = [string]$target.domain
            expected_default_branch = [string]$target.expected_default_branch
            probe = $null
            error = $_.Exception.Message
        }
    }
}

$reportObject = [ordered]@{
    command = "validate-c-project-catalog"
    schema_version = 1
    level = "L0"
    probe_remote = [bool]$ProbeRemote
    status = if ($failures.Count -eq 0) { "passed" } else { "failed" }
    target_count = $targets.Count
    minimum_targets = $minimumTargets
    generated_at_utc = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    failures = $failures
    targets = $targetReports
    note = "L0 validates catalog metadata and optional remote reachability only; it is not C-to-Rust migration equivalence evidence."
}

$reportDir = Split-Path -Parent $Report
if (-not [string]::IsNullOrWhiteSpace($reportDir)) {
    New-Item -ItemType Directory -Path $reportDir -Force | Out-Null
}
$json = $reportObject | ConvertTo-Json -Depth 8
Set-Content -LiteralPath $Report -Value $json -Encoding utf8
$json

if ($failures.Count -ne 0) {
    exit 1
}
