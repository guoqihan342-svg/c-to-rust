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

#[test]
fn diff_ignores_metadata_but_rejects_behavior_difference() {
    let rust_report = temp_path("schema-rust.json");
    let oracle_report = temp_path("schema-oracle.json");
    let diff_report = temp_path("schema-diff.json");

    fs::write(
        &rust_report,
        r#"{"command":"replay","backend":"memory","toolchain_status":"NOT_APPLICABLE_RUST_REPLAY","accepted_differences":[{"id":"metadata","fields":"backend,toolchain_status,message,image_hash"}],"steps":[{"id":"kv-1","op":"kv.get","status":"ok","code":"OK","value":"one","image_hash":"rust"}]}"#,
    )
    .unwrap();
    fs::write(
        &oracle_report,
        r#"{"command":"replay","backend":"c-flashdb","toolchain_status":"C_ORACLE_GENERATED","source":{"commit":"93d1755"},"steps":[{"id":"kv-1","op":"kv.get","status":"ok","code":"OK","value":"one","image_hash":"c"}]}"#,
    )
    .unwrap();

    let pass = cli::run([
        "diff".to_string(),
        "--rust-report".to_string(),
        rust_report.display().to_string(),
        "--oracle-report".to_string(),
        oracle_report.display().to_string(),
        "--report".to_string(),
        diff_report.display().to_string(),
    ])
    .unwrap();
    assert!(pass.contains("\"status\":\"passed\""));

    fs::write(
        &oracle_report,
        r#"{"command":"replay","backend":"c-flashdb","steps":[{"id":"kv-1","op":"kv.get","status":"ok","code":"OK","value":"two"}]}"#,
    )
    .unwrap();
    let err = cli::run([
        "diff-report".to_string(),
        "--actual".to_string(),
        rust_report.display().to_string(),
        "--expected".to_string(),
        oracle_report.display().to_string(),
        "--report".to_string(),
        diff_report.display().to_string(),
    ])
    .unwrap_err();
    assert_eq!(err.code(), "CLI");
    let failure = fs::read_to_string(&diff_report).unwrap();
    assert!(failure.contains("steps.kv-1.value"));

    let _ = fs::remove_file(rust_report);
    let _ = fs::remove_file(oracle_report);
    let _ = fs::remove_file(diff_report);
}

#[test]
fn diff_does_not_allow_accepted_differences_to_hide_behavior_fields() {
    let rust_report = temp_path("accepted-rust.json");
    let oracle_report = temp_path("accepted-oracle.json");
    let diff_report = temp_path("accepted-diff.json");

    fs::write(
        &rust_report,
        r#"{"command":"replay","accepted_differences":[{"id":"bad","fields":"value,image_hash"}],"steps":[{"id":"kv-1","op":"kv.get","status":"ok","code":"OK","value":"one","image_hash":"rust"}]}"#,
    )
    .unwrap();
    fs::write(
        &oracle_report,
        r#"{"command":"replay","accepted_differences":[{"id":"bad","fields":"value,image_hash"}],"steps":[{"id":"kv-1","op":"kv.get","status":"ok","code":"OK","value":"two","image_hash":"c"}]}"#,
    )
    .unwrap();

    let err = cli::run([
        "diff".to_string(),
        "--rust-report".to_string(),
        rust_report.display().to_string(),
        "--oracle-report".to_string(),
        oracle_report.display().to_string(),
        "--report".to_string(),
        diff_report.display().to_string(),
    ])
    .unwrap_err();
    assert_eq!(err.code(), "CLI");
    let failure = fs::read_to_string(&diff_report).unwrap();
    assert!(failure.contains("\"status\":\"failed\""));
    assert!(failure.contains("steps.kv-1.value"));

    let _ = fs::remove_file(rust_report);
    let _ = fs::remove_file(oracle_report);
    let _ = fs::remove_file(diff_report);
}

fn temp_path(name: &str) -> PathBuf {
    let sequence = NEXT_TEMP_PATH_ID.fetch_add(1, Ordering::Relaxed);
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "flashdb_rust_{}_{}_{}_{}",
        std::process::id(),
        sequence,
        nanos,
        name
    ))
}
