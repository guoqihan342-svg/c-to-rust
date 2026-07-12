#[test]
fn l3_diff_rejects_tsdb_over_limit_payload_error_regression() {
    let actual = temp_path("l3-tsdb-over-limit-payload-error-actual-report.json");
    let expected = temp_path("l3-tsdb-over-limit-payload-error-expected-report.json");
    let diff_report = temp_path("l3-tsdb-over-limit-payload-error-negative-diff.json");

    cli::run([
        "replay".to_string(),
        "--fixture".to_string(),
        "fixtures/l3-tsdb-over-limit-payload-error.json".to_string(),
        "--backend".to_string(),
        "file".to_string(),
        "--report".to_string(),
        actual.display().to_string(),
    ])
    .unwrap();
    fs::copy(&actual, &expected).unwrap();

    let mut mutated = fs::read_to_string(&expected).unwrap();
    mutated = mutated.replace(
        r#""id":"ts-ol-002","op":"ts.append","status":"error","code":"FDB_WRITE_ERR""#,
        r#""id":"ts-ol-002","op":"ts.append","status":"ok","code":"OK""#,
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
    assert!(failure.contains("steps.ts-ol-002.code"));

    let _ = fs::remove_file(actual);
    let _ = fs::remove_file(expected);
    let _ = fs::remove_file(diff_report);
}

#[test]
fn l3_diff_rejects_tsdb_non_monotonic_timestamp_regression() {
    let actual = temp_path("l3-tsdb-non-monotonic-timestamp-actual-report.json");
    let expected = temp_path("l3-tsdb-non-monotonic-timestamp-expected-report.json");
    let diff_report = temp_path("l3-tsdb-non-monotonic-timestamp-negative-diff.json");

    cli::run([
        "replay".to_string(),
        "--fixture".to_string(),
        "fixtures/l3-tsdb-non-monotonic-timestamp.json".to_string(),
        "--backend".to_string(),
        "file".to_string(),
        "--report".to_string(),
        actual.display().to_string(),
    ])
    .unwrap();
    fs::copy(&actual, &expected).unwrap();

    let mut mutated = fs::read_to_string(&expected).unwrap();
    mutated = mutated.replace(
        r#""id":"ts-nmt-002","op":"ts.append","status":"error","code":"FDB_WRITE_ERR""#,
        r#""id":"ts-nmt-002","op":"ts.append","status":"ok","code":"OK""#,
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
    assert!(failure.contains("steps.ts-nmt-002.code"));

    let _ = fs::remove_file(actual);
    let _ = fs::remove_file(expected);
    let _ = fs::remove_file(diff_report);
}

#[test]
fn l3_diff_rejects_tsdb_reverse_query_reopen_order_regression() {
    let actual = temp_path("l3-tsdb-reverse-query-reopen-actual-report.json");
    let expected = temp_path("l3-tsdb-reverse-query-reopen-expected-report.json");
    let diff_report = temp_path("l3-tsdb-reverse-query-reopen-negative-diff.json");

    cli::run([
        "replay".to_string(),
        "--fixture".to_string(),
        "fixtures/l3-tsdb-reverse-query-reopen.json".to_string(),
        "--backend".to_string(),
        "file".to_string(),
        "--report".to_string(),
        actual.display().to_string(),
    ])
    .unwrap();
    fs::copy(&actual, &expected).unwrap();

    let mut mutated = fs::read_to_string(&expected).unwrap();
    mutated = mutated.replace(
        r#""id":"ts-rqr-007","op":"ts.query","status":"ok","code":"OK","entries":[{"entry_id":3,"timestamp":30,"status":"written","value":"gamma"},{"entry_id":2,"timestamp":20,"status":"user1","value":"beta"},{"entry_id":1,"timestamp":10,"status":"written","value":"alpha"}]"#,
        r#""id":"ts-rqr-007","op":"ts.query","status":"ok","code":"OK","entries":[{"entry_id":1,"timestamp":10,"status":"written","value":"alpha"},{"entry_id":2,"timestamp":20,"status":"user1","value":"beta"},{"entry_id":3,"timestamp":30,"status":"written","value":"gamma"}]"#,
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
    assert!(failure.contains("steps.ts-rqr-007.entries"));

    let _ = fs::remove_file(actual);
    let _ = fs::remove_file(expected);
    let _ = fs::remove_file(diff_report);
}

#[test]
fn l3_diff_rejects_tsdb_error_boundary_code_regression() {
    let actual = temp_path("l3-tsdb-error-boundary-actual-report.json");
    let expected = temp_path("l3-tsdb-error-boundary-expected-report.json");
    let diff_report = temp_path("l3-tsdb-error-boundary-negative-diff.json");

    cli::run([
        "replay".to_string(),
        "--fixture".to_string(),
        "fixtures/l3-tsdb-error-boundary.json".to_string(),
        "--backend".to_string(),
        "file".to_string(),
        "--report".to_string(),
        actual.display().to_string(),
    ])
    .unwrap();
    fs::copy(&actual, &expected).unwrap();

    let mut mutated = fs::read_to_string(&expected).unwrap();
    mutated = mutated.replace(
        r#""id":"ts-eb-002","op":"ts.set_status","status":"error","code":"INVALID_RANGE""#,
        r#""id":"ts-eb-002","op":"ts.set_status","status":"error","code":"PARSE""#,
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
    assert!(failure.contains("steps.ts-eb-002.code"));

    let _ = fs::remove_file(actual);
    let _ = fs::remove_file(expected);
    let _ = fs::remove_file(diff_report);
}
