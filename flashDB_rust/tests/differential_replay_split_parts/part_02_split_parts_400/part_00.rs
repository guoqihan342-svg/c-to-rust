#[test]
fn l3_diff_rejects_kvdb_delete_missing_key_code_regression() {
    let actual = temp_path("l3-kvdb-delete-missing-key-actual-report.json");
    let expected = temp_path("l3-kvdb-delete-missing-key-expected-report.json");
    let diff_report = temp_path("l3-kvdb-delete-missing-key-negative-diff.json");

    cli::run([
        "replay".to_string(),
        "--fixture".to_string(),
        "fixtures/l3-kvdb-delete-missing-key.json".to_string(),
        "--backend".to_string(),
        "file".to_string(),
        "--report".to_string(),
        actual.display().to_string(),
    ])
    .unwrap();
    fs::copy(&actual, &expected).unwrap();

    let mut mutated = fs::read_to_string(&expected).unwrap();
    mutated = mutated.replace(
        r#""id":"kv-dmk-001","op":"kv.delete","status":"error","code":"FDB_KV_NAME_ERR""#,
        r#""id":"kv-dmk-001","op":"kv.delete","status":"ok","code":"OK""#,
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
    assert!(
        failure.contains("steps.kv-dmk-001.status") || failure.contains("steps.kv-dmk-001.code")
    );

    let _ = fs::remove_file(actual);
    let _ = fs::remove_file(expected);
    let _ = fs::remove_file(diff_report);
}

#[test]
fn l3_diff_rejects_tsdb_count_regression() {
    let actual = temp_path("l3-tsdb-actual-report.json");
    let expected = temp_path("l3-tsdb-expected-report.json");
    let diff_report = temp_path("l3-tsdb-negative-diff.json");

    cli::run([
        "replay".to_string(),
        "--fixture".to_string(),
        "fixtures/l3-tsdb-append-query-status.json".to_string(),
        "--backend".to_string(),
        "file".to_string(),
        "--report".to_string(),
        actual.display().to_string(),
    ])
    .unwrap();
    fs::copy(&actual, &expected).unwrap();

    let mut mutated = fs::read_to_string(&expected).unwrap();
    mutated = mutated.replace(
        r#""id":"ts-l3-006","op":"ts.count_status","status":"ok","code":"OK","count":1"#,
        r#""id":"ts-l3-006","op":"ts.count_status","status":"ok","code":"OK","count":2"#,
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
    assert!(failure.contains("steps.ts-l3-006.count"));

    let _ = fs::remove_file(actual);
    let _ = fs::remove_file(expected);
    let _ = fs::remove_file(diff_report);
}

#[test]
fn l3_diff_rejects_tsdb_deleted_status_reopen_count_regression() {
    let actual = temp_path("l3-tsdb-deleted-status-reopen-actual-report.json");
    let expected = temp_path("l3-tsdb-deleted-status-reopen-expected-report.json");
    let diff_report = temp_path("l3-tsdb-deleted-status-reopen-negative-diff.json");

    cli::run([
        "replay".to_string(),
        "--fixture".to_string(),
        "fixtures/l3-tsdb-deleted-status-reopen.json".to_string(),
        "--backend".to_string(),
        "file".to_string(),
        "--report".to_string(),
        actual.display().to_string(),
    ])
    .unwrap();
    fs::copy(&actual, &expected).unwrap();

    let mut mutated = fs::read_to_string(&expected).unwrap();
    mutated = mutated.replace(
        r#""id":"ts-del-007","op":"ts.count_status","status":"ok","code":"OK","count":1"#,
        r#""id":"ts-del-007","op":"ts.count_status","status":"ok","code":"OK","count":2"#,
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
    assert!(failure.contains("steps.ts-del-007.count"));

    let _ = fs::remove_file(actual);
    let _ = fs::remove_file(expected);
    let _ = fs::remove_file(diff_report);
}

#[test]
fn l3_diff_rejects_tsdb_user2_status_regression() {
    let actual = temp_path("l3-tsdb-user2-status-actual-report.json");
    let expected = temp_path("l3-tsdb-user2-status-expected-report.json");
    let diff_report = temp_path("l3-tsdb-user2-status-negative-diff.json");

    cli::run([
        "replay".to_string(),
        "--fixture".to_string(),
        "fixtures/l3-tsdb-user2-status.json".to_string(),
        "--backend".to_string(),
        "file".to_string(),
        "--report".to_string(),
        actual.display().to_string(),
    ])
    .unwrap();
    fs::copy(&actual, &expected).unwrap();

    let mut mutated = fs::read_to_string(&expected).unwrap();
    mutated = mutated.replace(
        r#""id":"ts-u2-003","op":"ts.set_status","status":"ok","code":"OK","entry_id":2,"ts_status":"user2""#,
        r#""id":"ts-u2-003","op":"ts.set_status","status":"ok","code":"OK","entry_id":2,"ts_status":"user1""#,
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
    assert!(failure.contains("steps.ts-u2-003.ts_status"));

    let _ = fs::remove_file(actual);
    let _ = fs::remove_file(expected);
    let _ = fs::remove_file(diff_report);
}

#[test]
fn l3_diff_rejects_tsdb_status_transition_query_regression() {
    let actual = temp_path("l3-tsdb-status-transition-actual-report.json");
    let expected = temp_path("l3-tsdb-status-transition-expected-report.json");
    let diff_report = temp_path("l3-tsdb-status-transition-negative-diff.json");

    cli::run([
        "replay".to_string(),
        "--fixture".to_string(),
        "fixtures/l3-tsdb-status-transition.json".to_string(),
        "--backend".to_string(),
        "file".to_string(),
        "--report".to_string(),
        actual.display().to_string(),
    ])
    .unwrap();
    fs::copy(&actual, &expected).unwrap();

    let mut mutated = fs::read_to_string(&expected).unwrap();
    mutated = mutated.replace(
        r#""id":"ts-tr-013","op":"ts.query","status":"ok","code":"OK","entries":[{"entry_id":1,"timestamp":10,"status":"deleted","value":"alpha"}"#,
        r#""id":"ts-tr-013","op":"ts.query","status":"ok","code":"OK","entries":[{"entry_id":1,"timestamp":10,"status":"user2","value":"alpha"}"#,
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
    assert!(failure.contains("steps.ts-tr-013.entries"));

    let _ = fs::remove_file(actual);
    let _ = fs::remove_file(expected);
    let _ = fs::remove_file(diff_report);
}

#[test]
fn l3_diff_rejects_tsdb_payload_boundary_value_regression() {
    let actual = temp_path("l3-tsdb-payload-boundary-actual-report.json");
    let expected = temp_path("l3-tsdb-payload-boundary-expected-report.json");
    let diff_report = temp_path("l3-tsdb-payload-boundary-negative-diff.json");

    cli::run([
        "replay".to_string(),
        "--fixture".to_string(),
        "fixtures/l3-tsdb-payload-boundary.json".to_string(),
        "--backend".to_string(),
        "file".to_string(),
        "--report".to_string(),
        actual.display().to_string(),
    ])
    .unwrap();
    fs::copy(&actual, &expected).unwrap();

    let mutated_payload = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdee";
    assert_eq!(mutated_payload.len(), 128);
    let mut mutated = fs::read_to_string(&expected).unwrap();
    mutated = mutated.replace(
        &format!(
            r#""id":"ts-pb-009","op":"ts.query","status":"ok","code":"OK","entries":[{{"entry_id":1,"timestamp":10,"status":"written","value":""}},{{"entry_id":2,"timestamp":20,"status":"written","value":"{}"}}]"#,
            TSDB_128_BYTE_PAYLOAD
        ),
        &format!(
            r#""id":"ts-pb-009","op":"ts.query","status":"ok","code":"OK","entries":[{{"entry_id":1,"timestamp":10,"status":"written","value":""}},{{"entry_id":2,"timestamp":20,"status":"written","value":"{}"}}]"#,
            mutated_payload
        ),
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
    assert!(failure.contains("steps.ts-pb-009.entries"));

    let _ = fs::remove_file(actual);
    let _ = fs::remove_file(expected);
    let _ = fs::remove_file(diff_report);
}
