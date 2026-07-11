#!/usr/bin/env bash
set -uo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
project_root="$(cd "$script_dir/.." && pwd)"
cd "$project_root"

evidence_dir="${FLASHDB_VERIFY_EVIDENCE_DIR:-target/verification/ci}"
mkdir -p "$evidence_dir"

status=0

json_escape() {
    local value="$1"
    value="${value//\\/\\\\}"
    value="${value//\"/\\\"}"
    value="${value//$'\n'/\\n}"
    value="${value//$'\r'/\\r}"
    printf '%s' "$value"
}

write_evidence() {
    local path="$1"
    local marker="$2"
    local result="$3"
    local detail="$4"
    local timestamp
    timestamp="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
    mkdir -p "$(dirname "$path")"
    cat >"$path" <<EOF
{
  "marker": "$(json_escape "$marker")",
  "status": "$(json_escape "$result")",
  "detail": "$(json_escape "$detail")",
  "timestamp_utc": "$timestamp"
}
EOF
}

sha256_file() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$1" | awk '{print $1}'
    else
        shasum -a 256 "$1" | awk '{print $1}'
    fi
}

run_step() {
    local name="$1"
    shift
    echo "==> $name"
    "$@"
    local code=$?
    if [ "$code" -ne 0 ]; then
        echo "step failed: $name (exit $code)" >&2
        return "$code"
    fi
}

mark_failed() {
    local path="$1"
    local marker="$2"
    local detail="$3"
    write_evidence "$path" "$marker" "failed" "$detail"
    status=1
}

run_rust_baseline() {
    run_step "cargo fmt" cargo fmt -- --check || return 1
    run_step "cargo check" cargo check || return 1
    run_step "cargo test" cargo test || return 1
    run_step "CLI smoke report" cargo run -- smoke --backend memory --report "$evidence_dir/smoke-memory.json" || return 1
    run_step "unsafe scan" cargo run -- unsafe-scan || return 1
}

run_rust_fixture_replay_diff() {
    local fixture="${FLASHDB_RUST_FIXTURE:-fixtures/ci-smoke.json}"
    local expected="${FLASHDB_RUST_EXPECTED_REPORT:-fixtures/ci-smoke.expected.json}"
    local rust_report="${FLASHDB_RUST_REPLAY_REPORT:-$evidence_dir/rust-fixture-replay.json}"
    local diff_report="${FLASHDB_RUST_DIFF_REPORT:-$evidence_dir/rust-fixture-diff.json}"
    local evidence="$evidence_dir/rust-fixture-replay-diff-evidence.json"

    if [ ! -f "$fixture" ] || [ ! -f "$expected" ]; then
        mark_failed "$evidence" "FAILED_RUST_FIXTURE_INPUT_MISSING" "Expected fixture '$fixture' and expected report '$expected'. Add the mainline fixture assets or override FLASHDB_RUST_FIXTURE and FLASHDB_RUST_EXPECTED_REPORT."
        return 1
    fi

    if ! cargo run -- fixture-replay --fixture "$fixture" --report "$rust_report"; then
        mark_failed "$evidence" "FAILED_RUST_FIXTURE_REPLAY" "Expected mainline Rust CLI support: fixture-replay --fixture <path> --report <path>."
        return 1
    fi

    if ! cargo run -- diff-report --expected "$expected" --actual "$rust_report" --report "$diff_report"; then
        mark_failed "$evidence" "FAILED_RUST_FIXTURE_DIFF" "Expected mainline Rust CLI support: diff-report --expected <path> --actual <path> --report <path>."
        return 1
    fi

    local fixture_hash rust_hash diff_hash
    fixture_hash="$(sha256_file "$fixture")"
    rust_hash="$(sha256_file "$rust_report")"
    diff_hash="$(sha256_file "$diff_report")"
    write_evidence "$evidence" "RUST_FIXTURE_REPLAY_DIFF_PASSED" "passed" "fixture_sha256=$fixture_hash rust_report_sha256=$rust_hash diff_report_sha256=$diff_hash"
}

run_c_oracle_producer() {
    local fixture="${FLASHDB_C_RUST_FIXTURE:-fixtures/c-rust-smoke.json}"
    local oracle_report="${FLASHDB_C_ORACLE_REPORT:-$evidence_dir/c-oracle-report.json}"
    local rust_report="${FLASHDB_C_RUST_REPLAY_REPORT:-$evidence_dir/c-rust-replay.json}"
    local diff_report="${FLASHDB_C_RUST_DIFF_REPORT:-$evidence_dir/c-rust-diff.json}"
    local evidence="$evidence_dir/c-oracle-producer-evidence.json"

    if ! command -v gcc >/dev/null 2>&1; then
        if [ "${GITHUB_ACTIONS:-}" = "true" ] || [ -n "${FLASHDB_C_ORACLE_PRODUCER:-}" ]; then
            mark_failed "$evidence" "FAILED_C_ORACLE_NO_GCC" "gcc was not found; C oracle producer and C/Rust diff cannot run."
            return 1
        fi
        write_evidence "$evidence" "SKIPPED_C_ORACLE_NO_GCC" "skipped" "gcc was not found; C oracle producer was not run."
        return 0
    fi

    if [ -z "${FLASHDB_C_ORACLE_PRODUCER:-}" ]; then
        if [ "${GITHUB_ACTIONS:-}" = "true" ]; then
            mark_failed "$evidence" "FAILED_C_ORACLE_PRODUCER_NOT_CONFIGURED" "GitHub Actions has gcc, but FLASHDB_C_ORACLE_PRODUCER is not configured."
            return 1
        fi
        write_evidence "$evidence" "SKIPPED_C_ORACLE_PRODUCER_NOT_CONFIGURED" "skipped" "gcc is available, but FLASHDB_C_ORACLE_PRODUCER is not configured. No C/Rust equivalence is claimed."
        return 0
    fi

    if [ ! -f "$fixture" ]; then
        mark_failed "$evidence" "FAILED_C_ORACLE_FIXTURE_MISSING" "Expected fixture '$fixture' for C oracle producer."
        return 1
    fi

    if ! "$FLASHDB_C_ORACLE_PRODUCER" --fixture "$fixture" --report "$oracle_report" --evidence "$evidence"; then
        mark_failed "$evidence" "FAILED_C_ORACLE_PRODUCER" "Configured C oracle producer failed."
        return 1
    fi

    local oracle_hash
    oracle_hash="$(sha256_file "$oracle_report")"
    write_evidence "$evidence" "C_ORACLE_PRODUCER_PASSED" "passed" "oracle_report_sha256=$oracle_hash"

    if ! cargo run -- fixture-replay --fixture "$fixture" --report "$rust_report"; then
        mark_failed "$evidence" "FAILED_C_RUST_REPLAY" "Rust replay failed for C/Rust fixture '$fixture'."
        return 1
    fi
    if ! cargo run -- diff-report --expected "$oracle_report" --actual "$rust_report" --report "$diff_report"; then
        mark_failed "$evidence" "FAILED_C_RUST_DIFF" "Rust replay report did not match generated C oracle report."
        return 1
    fi

    local rust_hash diff_hash
    rust_hash="$(sha256_file "$rust_report")"
    diff_hash="$(sha256_file "$diff_report")"
    write_evidence "$evidence" "C_RUST_DIFF_PASSED" "passed" "oracle_report_sha256=$oracle_hash rust_report_sha256=$rust_hash diff_report_sha256=$diff_hash"
}

run_rust_baseline || status=1
run_rust_fixture_replay_diff || status=1
run_c_oracle_producer || status=1

if [ "$status" -ne 0 ]; then
    echo "CI verification failed; see $evidence_dir for evidence files." >&2
    exit "$status"
fi

echo "CI verification passed; evidence is in $evidence_dir"
