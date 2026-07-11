$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot

$EvidenceDir = "target/verification"
New-Item -ItemType Directory -Force -Path $EvidenceDir | Out-Null

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)]
        [scriptblock] $Command
    )

    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code $LASTEXITCODE"
    }
}

function Write-Evidence {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Path,
        [Parameter(Mandatory = $true)]
        [string] $Marker,
        [Parameter(Mandatory = $true)]
        [string] $Status,
        [Parameter(Mandatory = $true)]
        [string] $Detail
    )

    $Parent = Split-Path -Parent $Path
    if ($Parent) {
        New-Item -ItemType Directory -Force -Path $Parent | Out-Null
    }

    [ordered]@{
        marker = $Marker
        status = $Status
        detail = $Detail
        timestamp_utc = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    } | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $Path -Encoding UTF8
}

function Write-LocalCOracleEvidence {
    $EvidencePath = Join-Path $EvidenceDir "local-c-oracle-evidence.json"
    $Gcc = Get-Command gcc -ErrorAction SilentlyContinue
    if (-not $Gcc) {
        Write-Evidence `
            -Path $EvidencePath `
            -Marker "SKIPPED_LOCAL_NO_C_TOOLCHAIN" `
            -Status "skipped" `
            -Detail "Native Windows verification did not run the C oracle producer because gcc was not found. This is not C/Rust equivalence evidence."
        return
    }

    if (-not $env:FLASHDB_C_ORACLE_PRODUCER) {
        Write-Evidence `
            -Path $EvidencePath `
            -Marker "SKIPPED_C_ORACLE_PRODUCER_NOT_CONFIGURED" `
            -Status "skipped" `
            -Detail "gcc is available, but FLASHDB_C_ORACLE_PRODUCER is not configured. This is not C/Rust equivalence evidence."
        return
    }

    Write-Evidence `
        -Path $EvidencePath `
        -Marker "C_ORACLE_PRODUCER_CONFIGURED" `
        -Status "ready" `
        -Detail "FLASHDB_C_ORACLE_PRODUCER is configured. Run the producer through scripts/verify-ci.sh on Linux for the C oracle contract."
}

Invoke-Checked { cargo fmt -- --check }
Invoke-Checked { cargo check }
Invoke-Checked { cargo test }
Invoke-Checked { cargo run -- smoke --backend memory --report target/verification/smoke-memory.json }
Invoke-Checked { cargo run -- replay --fixture fixtures/ci-smoke.json --report target/verification/rust-fixture-replay.json }
Invoke-Checked { cargo run -- diff --rust-report target/verification/rust-fixture-replay.json --oracle-report fixtures/ci-smoke.expected.json --report target/verification/rust-fixture-diff.json }
Invoke-Checked { cargo run -- unsafe-scan }
Write-LocalCOracleEvidence

Write-Output "flashDB_rust baseline verification passed"
