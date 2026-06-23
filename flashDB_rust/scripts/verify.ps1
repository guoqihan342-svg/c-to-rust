$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot

New-Item -ItemType Directory -Force -Path "target/verification" | Out-Null

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

Invoke-Checked { cargo fmt -- --check }
Invoke-Checked { cargo check }
Invoke-Checked { cargo test }
Invoke-Checked { cargo run -- smoke --backend memory --report target/verification/smoke-memory.json }
Invoke-Checked { cargo run -- stress --loops 20 --seed 1 --backend memory --scenario all --report target/verification/stress-smoke.json }
Invoke-Checked { cargo run -- unsafe-scan }

Write-Output "flashDB_rust baseline verification passed"
