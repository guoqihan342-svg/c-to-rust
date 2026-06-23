use flashdb_rust::cli;
use std::fs;
use std::path::PathBuf;
use std::time::{SystemTime, UNIX_EPOCH};

#[test]
fn replay_fixture_writes_per_step_report_with_error_codes() {
    let report = temp_path("replay-report.json");
    let out = cli::run([
        "replay".to_string(),
        "--fixture".to_string(),
        "fixtures/ci-smoke.json".to_string(),
        "--report".to_string(),
        report.display().to_string(),
    ])
    .unwrap();

    assert!(out.contains("\"command\":\"replay\""));
    assert!(out.contains("\"id\":\"kv-010\""));
    assert!(out.contains("\"code\":\"INVALID_KEY\""));
    assert!(out.contains("\"code\":\"KEY_TOO_LONG\""));
    assert!(report.exists());
    let _ = fs::remove_file(report);
}

#[test]
fn diff_passes_for_matching_reports_and_fails_with_first_mismatch() {
    let actual = temp_path("actual-report.json");
    let expected = temp_path("expected-report.json");
    let pass_report = temp_path("diff-pass.json");
    let fail_report = temp_path("diff-fail.json");

    cli::run([
        "fixture-replay".to_string(),
        "--fixture".to_string(),
        "fixtures/ci-smoke.json".to_string(),
        "--report".to_string(),
        actual.display().to_string(),
    ])
    .unwrap();
    fs::copy(&actual, &expected).unwrap();

    let pass = cli::run([
        "diff-report".to_string(),
        "--actual".to_string(),
        actual.display().to_string(),
        "--expected".to_string(),
        expected.display().to_string(),
        "--report".to_string(),
        pass_report.display().to_string(),
    ])
    .unwrap();
    assert!(pass.contains("\"status\":\"passed\""));

    let mut mutated = fs::read_to_string(&expected).unwrap();
    mutated = mutated.replacen("\"value\":\"one\"", "\"value\":\"changed\"", 1);
    fs::write(&expected, mutated).unwrap();

    let err = cli::run([
        "diff".to_string(),
        "--rust-report".to_string(),
        actual.display().to_string(),
        "--oracle-report".to_string(),
        expected.display().to_string(),
        "--report".to_string(),
        fail_report.display().to_string(),
    ])
    .unwrap_err();
    assert_eq!(err.code(), "CLI");
    let failure = fs::read_to_string(&fail_report).unwrap();
    assert!(failure.contains("\"status\":\"failed\""));
    assert!(failure.contains("\"first_mismatch\""));

    let _ = fs::remove_file(actual);
    let _ = fs::remove_file(expected);
    let _ = fs::remove_file(pass_report);
    let _ = fs::remove_file(fail_report);
}

fn temp_path(name: &str) -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!("flashdb_rust_{nanos}_{name}"))
}
