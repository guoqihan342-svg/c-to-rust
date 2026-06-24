param(
    [ValidateRange(1, 1000000)]
    [int] $Rounds = 1,

    [ValidateRange(1, 100000000)]
    [int] $StressLoops = 10000,

    [ValidateRange(1, 1000000)]
    [int] $StartRound = 1,

    [string] $RunId = "",
    [string] $EvidenceRoot = "target/full-regression",
    [switch] $ContinueOnFailure,
    [switch] $SkipClippy,
    [switch] $SkipLongStress,
    [switch] $ProbeRemoteCatalog
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $RepoRoot

if ([string]::IsNullOrWhiteSpace($RunId)) {
    $RunId = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
}

$RunRoot = Join-Path $RepoRoot (Join-Path $EvidenceRoot $RunId)
$EventsPath = Join-Path $RunRoot "events.jsonl"
$SummaryPath = Join-Path $RunRoot "summary.json"
New-Item -ItemType Directory -Force -Path $RunRoot | Out-Null

function ConvertTo-SafeFileName {
    param([Parameter(Mandatory = $true)][string] $Value)
    return ($Value -replace '[^A-Za-z0-9_.-]', '-')
}

function ConvertTo-JsonLine {
    param([Parameter(Mandatory = $true)] $Value)
    return ($Value | ConvertTo-Json -Depth 16 -Compress)
}

function Add-JsonLine {
    param([Parameter(Mandatory = $true)] $Value)
    Add-SharedTextLine -Path $EventsPath -Line (ConvertTo-JsonLine $Value)
}

function Add-SharedTextLine {
    param(
        [Parameter(Mandatory = $true)][string] $Path,
        [Parameter(Mandatory = $true)][string] $Line
    )

    for ($attempt = 1; $attempt -le 20; $attempt++) {
        try {
            $stream = [System.IO.FileStream]::new(
                $Path,
                [System.IO.FileMode]::Append,
                [System.IO.FileAccess]::Write,
                [System.IO.FileShare]::ReadWrite
            )
            try {
                $writer = [System.IO.StreamWriter]::new($stream, [System.Text.UTF8Encoding]::new($false))
                $stream = $null
                try {
                    $writer.WriteLine($Line)
                } finally {
                    $writer.Dispose()
                }
            } finally {
                if ($null -ne $stream) {
                    $stream.Dispose()
                }
            }
            return
        } catch [System.IO.IOException] {
            if ($attempt -eq 20) {
                throw
            }
            Start-Sleep -Milliseconds (100 * $attempt)
        }
    }
}

function Set-SharedText {
    param(
        [Parameter(Mandatory = $true)][string] $Path,
        [Parameter(Mandatory = $true)][string] $Text
    )

    for ($attempt = 1; $attempt -le 20; $attempt++) {
        try {
            $stream = [System.IO.FileStream]::new(
                $Path,
                [System.IO.FileMode]::Create,
                [System.IO.FileAccess]::Write,
                [System.IO.FileShare]::ReadWrite
            )
            try {
                $writer = [System.IO.StreamWriter]::new($stream, [System.Text.UTF8Encoding]::new($false))
                $stream = $null
                try {
                    $writer.Write($Text)
                } finally {
                    $writer.Dispose()
                }
            } finally {
                if ($null -ne $stream) {
                    $stream.Dispose()
                }
            }
            return
        } catch [System.IO.IOException] {
            if ($attempt -eq 20) {
                throw
            }
            Start-Sleep -Milliseconds (100 * $attempt)
        }
    }
}

function New-Step {
    param(
        [Parameter(Mandatory = $true)][string] $Name,
        [Parameter(Mandatory = $true)][string] $Category,
        [Parameter(Mandatory = $true)][string] $WorkingDirectory,
        [Parameter(Mandatory = $true)][string[]] $Command
    )

    return [ordered]@{
        name = $Name
        category = $Category
        working_directory = $WorkingDirectory
        command = $Command
    }
}

function Invoke-RegressionStep {
    param(
        [Parameter(Mandatory = $true)] $Step,
        [Parameter(Mandatory = $true)][int] $Round,
        [Parameter(Mandatory = $true)][int] $Index,
        [Parameter(Mandatory = $true)][string] $RoundDir
    )

    $safeName = ConvertTo-SafeFileName ("{0:D2}-{1}" -f $Index, $Step.name)
    $logPath = Join-Path $RoundDir ($safeName + ".log")
    $started = Get-Date
    $startedUtc = $started.ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    $status = "passed"
    $exitCode = 0
    $output = @()
    $locationPushed = $false
    $resolvedWorkingDirectory = if ([System.IO.Path]::IsPathRooted($Step.working_directory)) {
        $Step.working_directory
    } else {
        Join-Path $RepoRoot $Step.working_directory
    }

    try {
        Push-Location -LiteralPath $resolvedWorkingDirectory
        $locationPushed = $true
        $previousErrorActionPreference = $ErrorActionPreference
        try {
            $ErrorActionPreference = "Continue"
            $exe = $Step.command[0]
            $argv = @()
            if ($Step.command.Count -gt 1) {
                $argv = $Step.command[1..($Step.command.Count - 1)]
            }
            $output = & $exe @argv 2>&1
            $exitCode = if ($null -eq $LASTEXITCODE) { 0 } else { $LASTEXITCODE }
            if ($exitCode -ne 0) {
                $status = "failed"
            }
        } finally {
            $ErrorActionPreference = $previousErrorActionPreference
            if ($locationPushed) {
                Pop-Location
                $locationPushed = $false
            }
        }
    } catch {
        $status = "failed"
        $exitCode = -1
        $output += $_.Exception.ToString()
        if ($locationPushed) {
            Pop-Location
            $locationPushed = $false
        }
    }

    $ended = Get-Date
    $lines = @(
        "name=$($Step.name)"
        "category=$($Step.category)"
        "round=$Round"
        "cwd=$resolvedWorkingDirectory"
        "command=$($Step.command -join ' ')"
        "status=$status"
        "exit_code=$exitCode"
        "started_utc=$startedUtc"
        "ended_utc=$($ended.ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ"))"
        ""
    )
    $lines += ($output | ForEach-Object { $_.ToString() })
    $lines | Set-Content -LiteralPath $logPath -Encoding UTF8

    $event = [ordered]@{
        schema_version = 1
        run_id = $RunId
        round = $Round
        step_index = $Index
        name = $Step.name
        category = $Step.category
        status = $status
        exit_code = $exitCode
        duration_ms = [int64]($ended - $started).TotalMilliseconds
        started_utc = $startedUtc
        ended_utc = $ended.ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
        working_directory = $resolvedWorkingDirectory
        command = $Step.command
        log = Resolve-Path -LiteralPath $logPath | ForEach-Object { $_.Path }
    }
    Add-JsonLine $event
    return $event
}

function Get-RoundSteps {
    param(
        [Parameter(Mandatory = $true)][int] $Round,
        [Parameter(Mandatory = $true)][string] $RoundDir
    )

    $flashStressReport = Join-Path $RoundDir ("flashdb-stress-{0}-loops.json" -f $StressLoops)
    $flashSmokeReport = Join-Path $RoundDir "flashdb-smoke-memory.json"
    $flashReplayReport = Join-Path $RoundDir "flashdb-rust-fixture-replay.json"
    $flashDiffReport = Join-Path $RoundDir "flashdb-rust-fixture-diff.json"
    $flashVersionReport = Join-Path $RoundDir "flashdb-version-manifest.json"
    $flashSearchReport = Join-Path $RoundDir "flashdb-evidence-search.json"
    $catalogReport = Join-Path $RoundDir "catalog-validation.json"

    $steps = New-Object System.Collections.Generic.List[object]
    $catalogCommand = @(
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        (Join-Path $RepoRoot "scripts/validate-c-project-catalog.ps1"),
        "-Report",
        $catalogReport
    )
    if ($ProbeRemoteCatalog) {
        $catalogCommand += "-ProbeRemote"
    }

    $steps.Add((New-Step "catalog-validation" "l0_catalog" "." $catalogCommand))
    $steps.Add((New-Step "translator-fmt" "translator_build" "." @("cargo", "fmt", "--manifest-path", "crates/c2r-translator/Cargo.toml", "--", "--check")))
    $steps.Add((New-Step "translator-test" "translator_tests" "." @("cargo", "test", "--manifest-path", "crates/c2r-translator/Cargo.toml")))
    if (-not $SkipClippy) {
        $steps.Add((New-Step "translator-clippy" "translator_lint" "." @("cargo", "clippy", "--manifest-path", "crates/c2r-translator/Cargo.toml", "--all-targets", "--", "-D", "warnings")))
    }
    $steps.Add((New-Step "l2-slices-fmt" "l2_slices_build" "." @("cargo", "fmt", "--manifest-path", "validation/l2_slices/Cargo.toml", "--", "--check")))
    $steps.Add((New-Step "l2-slices-test" "l2_slices_tests" "." @("cargo", "test", "--manifest-path", "validation/l2_slices/Cargo.toml")))
    $steps.Add((New-Step "auto-migrate-unit-tests" "auto_translation_tests" "." @("python", "-B", "-m", "unittest", "validation.tools.test_auto_migrate", "-v")))
    $steps.Add((New-Step "libuv-auto-evidence-semantic" "auto_translation_evidence" "." @("python", "-B", "validation/tools/validate_auto_translation_evidence.py", "--target-id", "libuv", "--slice-id", "ip4-addr", "--require-semantic-pass")))
    $steps.Add((New-Step "zlib-auto-evidence-semantic" "auto_translation_evidence" "." @("python", "-B", "validation/tools/validate_auto_translation_evidence.py", "--target-id", "zlib-ng", "--slice-id", "adler32-step", "--require-semantic-pass")))
    $steps.Add((New-Step "flashdb-fmt" "flashdb_build" "flashDB_rust" @("cargo", "fmt", "--", "--check")))
    $steps.Add((New-Step "flashdb-check" "flashdb_build" "flashDB_rust" @("cargo", "check")))
    $steps.Add((New-Step "flashdb-test" "flashdb_tests" "flashDB_rust" @("cargo", "test")))
    if (-not $SkipClippy) {
        $steps.Add((New-Step "flashdb-clippy" "flashdb_lint" "flashDB_rust" @("cargo", "clippy", "--all-targets", "--", "-D", "warnings")))
    }
    $steps.Add((New-Step "flashdb-smoke-memory" "flashdb_smoke" "flashDB_rust" @("cargo", "run", "--", "smoke", "--backend", "memory", "--report", $flashSmokeReport)))
    $steps.Add((New-Step "flashdb-fixture-replay" "committed_fixture_replay" "flashDB_rust" @("cargo", "run", "--", "fixture-replay", "--fixture", "fixtures/ci-smoke.json", "--report", $flashReplayReport)))
    $steps.Add((New-Step "flashdb-fixture-diff" "committed_fixture_diff" "flashDB_rust" @("cargo", "run", "--", "diff-report", "--expected", "fixtures/ci-smoke.expected.json", "--actual", $flashReplayReport, "--report", $flashDiffReport)))
    $steps.Add((New-Step "flashdb-unsafe-scan" "unsafe_budget" "flashDB_rust" @("cargo", "run", "--", "unsafe-scan")))
    $steps.Add((New-Step "flashdb-version-manifest" "version_binding" "flashDB_rust" @("cargo", "run", "--", "version-manifest", "--report", $flashVersionReport)))
    if (-not $SkipLongStress) {
        $steps.Add((New-Step "flashdb-release-stress-all" "production_abnormal_reliability_performance" "flashDB_rust" @("cargo", "run", "--release", "--", "stress", "--loops", "$StressLoops", "--seed", "$Round", "--backend", "file", "--scenario", "all", "--report", $flashStressReport)))
    }
    $steps.Add((New-Step "flashdb-evidence-search" "log_traceability" "flashDB_rust" @("cargo", "run", "--", "evidence-search", "--evidence-dir", $RoundDir, "--query", "passed", "--limit", "50", "--report", $flashSearchReport)))
    $steps.Add((New-Step "openspec-validate-all" "openspec_gates" "." @("openspec", "validate", "--all")))
    $steps.Add((New-Step "git-diff-check" "repository_integrity" "." @("git", "diff", "--check")))
    return $steps
}

$runStarted = Get-Date
$results = New-Object System.Collections.Generic.List[object]
$failed = $null

Add-JsonLine ([ordered]@{
    schema_version = 1
    event = "run_started"
    run_id = $RunId
    rounds_requested = $Rounds
    start_round = $StartRound
    stress_loops = $StressLoops
    skip_long_stress = [bool]$SkipLongStress
    skip_clippy = [bool]$SkipClippy
    continue_on_failure = [bool]$ContinueOnFailure
    evidence_root = $RunRoot
    production_data_boundary = "Default coverage uses committed fixtures plus deterministic production-like stress; pass real/de-identified fixtures through the replay/diff gates before claiming production-data equivalence."
    started_utc = $runStarted.ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
})

for ($round = $StartRound; $round -le $Rounds; $round++) {
    $roundDir = Join-Path $RunRoot ("round-{0:D5}" -f $round)
    New-Item -ItemType Directory -Force -Path $roundDir | Out-Null
    $steps = Get-RoundSteps -Round $round -RoundDir $roundDir
    $index = 0
    foreach ($step in $steps) {
        $index += 1
        Write-Host ("[{0}/{1}] round {2} step {3}/{4}: {5}" -f $round, $Rounds, $round, $index, $steps.Count, $step.name)
        $event = Invoke-RegressionStep -Step $step -Round $round -Index $index -RoundDir $roundDir
        $results.Add($event) | Out-Null
        if ($event.status -ne "passed") {
            $failed = $event
            if (-not $ContinueOnFailure) {
                break
            }
        }
    }
    if ($failed -and -not $ContinueOnFailure) {
        break
    }
}

$runEnded = Get-Date
$passed = $null -eq $failed
$completedRounds = if ($results.Count -eq 0) {
    0
} else {
    ($results | ForEach-Object { [int]$_["round"] } | Measure-Object -Maximum).Maximum
}
$summary = [ordered]@{
    schema_version = 1
    command = "scripts/run-full-regression.ps1"
    status = if ($passed) { "passed" } else { "failed" }
    run_id = $RunId
    rounds_requested = $Rounds
    start_round = $StartRound
    rounds_completed = [int]$completedRounds
    stress_loops = $StressLoops
    skip_long_stress = [bool]$SkipLongStress
    skip_clippy = [bool]$SkipClippy
    continue_on_failure = [bool]$ContinueOnFailure
    started_utc = $runStarted.ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    ended_utc = $runEnded.ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    duration_ms = [int64]($runEnded - $runStarted).TotalMilliseconds
    step_count = $results.Count
    evidence_root = $RunRoot
    events = $EventsPath
    failed_step = $failed
    coverage_boundary = [ordered]@{
        production_data = "Committed fixtures and deterministic production-like stress by default; real production data must be supplied as sanitized replay/diff fixtures before this can claim production-data equivalence."
        abnormal_data = "Rust abnormal-data tests plus stress scenario abnormal through flashdb-release-stress-all."
        performance = "Release-mode stress duration and counters are recorded as smoke evidence, not a stable benchmark threshold."
        reliability = "File-backed stress scenario reopens KVDB/TSDB images and verifies last persisted values."
        branch_coverage = "Cargo tests and OpenSpec gates exercise main branches; no llvm-cov percentage is claimed by this script."
    }
}

Set-SharedText -Path $SummaryPath -Text ($summary | ConvertTo-Json -Depth 16)
Add-JsonLine ([ordered]@{
    schema_version = 1
    event = "run_finished"
    run_id = $RunId
    status = $summary.status
    summary = $SummaryPath
    ended_utc = $summary.ended_utc
})

$summary | ConvertTo-Json -Depth 16
if (-not $passed) {
    exit 1
}
