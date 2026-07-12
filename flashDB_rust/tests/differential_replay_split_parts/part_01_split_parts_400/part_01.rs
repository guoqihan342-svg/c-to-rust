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

#[test]
fn l3_diff_rejects_kvdb_lifecycle_value_regression() {
    let actual = temp_path("l3-actual-report.json");
    let expected = temp_path("l3-expected-report.json");
    let diff_report = temp_path("l3-negative-diff.json");

    cli::run([
        "replay".to_string(),
        "--fixture".to_string(),
        "fixtures/l3-kvdb-lifecycle.json".to_string(),
        "--backend".to_string(),
        "file".to_string(),
        "--report".to_string(),
        actual.display().to_string(),
    ])
    .unwrap();
    fs::copy(&actual, &expected).unwrap();

    let mut mutated = fs::read_to_string(&expected).unwrap();
    mutated = mutated.replace(
        r#""id":"kv-l3-007","op":"kv.get","status":"ok","code":"OK","value":"two""#,
        r#""id":"kv-l3-007","op":"kv.get","status":"ok","code":"OK","value":"changed""#,
    );
    fs::write(&expected, mutated).unwrap();

    let err = cli::run([
        "diff".to_string(),
        "--rust-report".to_string(),
        actual.display().to_string(),
        "--oracle-report".to_string(),
        expected.display().to_string(),
        "--report".to_string(),
        diff_report.display().to_string(),
    ])
    .unwrap_err();
    assert_eq!(err.code(), "CLI");
    let failure = fs::read_to_string(&diff_report).unwrap();
    assert!(failure.contains("\"status\":\"failed\""));
    assert!(failure.contains("steps.kv-l3-007.value"));

    let _ = fs::remove_file(actual);
    let _ = fs::remove_file(expected);
    let _ = fs::remove_file(diff_report);
}

#[test]
fn l3_diff_rejects_kvdb_compact_overwrite_value_regression() {
    let actual = temp_path("l3-kvdb-compact-overwrite-actual-report.json");
    let expected = temp_path("l3-kvdb-compact-overwrite-expected-report.json");
    let diff_report = temp_path("l3-kvdb-compact-overwrite-negative-diff.json");

    cli::run([
        "replay".to_string(),
        "--fixture".to_string(),
        "fixtures/l3-kvdb-compact-overwrite.json".to_string(),
        "--backend".to_string(),
        "file".to_string(),
        "--report".to_string(),
        actual.display().to_string(),
    ])
    .unwrap();
    fs::copy(&actual, &expected).unwrap();

    let mut mutated = fs::read_to_string(&expected).unwrap();
    mutated = mutated.replace(
        r#""id":"kv-co-010","op":"kv.get","status":"ok","code":"OK","value":"two""#,
        r#""id":"kv-co-010","op":"kv.get","status":"ok","code":"OK","value":"changed""#,
    );
    fs::write(&expected, mutated).unwrap();

    let err = cli::run([
        "diff".to_string(),
        "--rust-report".to_string(),
        actual.display().to_string(),
        "--oracle-report".to_string(),
        expected.display().to_string(),
        "--report".to_string(),
        diff_report.display().to_string(),
    ])
    .unwrap_err();
    assert_eq!(err.code(), "CLI");
    let failure = fs::read_to_string(&diff_report).unwrap();
    assert!(failure.contains("\"status\":\"failed\""));
    assert!(failure.contains("steps.kv-co-010.value"));

    let _ = fs::remove_file(actual);
    let _ = fs::remove_file(expected);
    let _ = fs::remove_file(diff_report);
}

#[test]
fn l3_diff_rejects_kvdb_error_boundary_code_regression() {
    let actual = temp_path("l3-kvdb-error-boundary-actual-report.json");
    let expected = temp_path("l3-kvdb-error-boundary-expected-report.json");
    let diff_report = temp_path("l3-kvdb-error-boundary-negative-diff.json");

    cli::run([
        "replay".to_string(),
        "--fixture".to_string(),
        "fixtures/l3-kvdb-error-boundary.json".to_string(),
        "--backend".to_string(),
        "file".to_string(),
        "--report".to_string(),
        actual.display().to_string(),
    ])
    .unwrap();
    fs::copy(&actual, &expected).unwrap();

    let mut mutated = fs::read_to_string(&expected).unwrap();
    mutated = mutated.replace(
        r#""id":"kv-eb-003","op":"kv.set","status":"error","code":"KEY_TOO_LONG""#,
        r#""id":"kv-eb-003","op":"kv.set","status":"error","code":"INVALID_KEY""#,
    );
    fs::write(&expected, mutated).unwrap();

    let err = cli::run([
        "diff".to_string(),
        "--rust-report".to_string(),
        actual.display().to_string(),
        "--oracle-report".to_string(),
        expected.display().to_string(),
        "--report".to_string(),
        diff_report.display().to_string(),
    ])
    .unwrap_err();
    assert_eq!(err.code(), "CLI");
    let failure = fs::read_to_string(&diff_report).unwrap();
    assert!(failure.contains("\"status\":\"failed\""));
    assert!(failure.contains("steps.kv-eb-003.code"));

    let _ = fs::remove_file(actual);
    let _ = fs::remove_file(expected);
    let _ = fs::remove_file(diff_report);
}
