#[test]
fn l3_tsdb_payload_boundary_fixture_replays_visible_payloads() {
    assert_eq!(TSDB_128_BYTE_PAYLOAD.len(), 128);
    let report = temp_path("l3-tsdb-payload-boundary-report.json");
    let out = cli::run([
        "replay".to_string(),
        "--fixture".to_string(),
        "fixtures/l3-tsdb-payload-boundary.json".to_string(),
        "--backend".to_string(),
        "file".to_string(),
        "--report".to_string(),
        report.display().to_string(),
    ])
    .unwrap();

    assert!(out.contains("\"fixture_name\":\"l3-tsdb-payload-boundary\""));
    assert!(out.contains("\"level\":\"L3\""));
    assert!(out.contains("\"target_id\":\"flashdb\""));
    assert!(out.contains("\"slice_id\":\"tsdb-payload-boundary\""));
    assert!(out.contains("\"commit\":\"93d175549da579b8abac07bd175ce4c3f9dde829\""));
    assert!(out.contains("\"id\":\"layout-and-metadata\""));
    assert!(out.contains("\"fields\":\"image_hash,backend,toolchain_status,source,fixture,fixture_hash,report_path\""));
    assert!(out.contains(
        "\"id\":\"ts-pb-001\",\"op\":\"ts.append\",\"status\":\"ok\",\"code\":\"OK\",\"entry_id\":1,\"timestamp\":10,\"value\":\"\""
    ));
    assert!(out.contains(&format!(
        "\"id\":\"ts-pb-002\",\"op\":\"ts.append\",\"status\":\"ok\",\"code\":\"OK\",\"entry_id\":2,\"timestamp\":20,\"value\":\"{}\"",
        TSDB_128_BYTE_PAYLOAD
    )));
    assert!(out.contains(&format!(
        "\"id\":\"ts-pb-003\",\"op\":\"ts.query\",\"status\":\"ok\",\"code\":\"OK\",\"entries\":[{{\"entry_id\":1,\"timestamp\":10,\"status\":\"written\",\"value\":\"\"}},{{\"entry_id\":2,\"timestamp\":20,\"status\":\"written\",\"value\":\"{}\"}}]",
        TSDB_128_BYTE_PAYLOAD
    )));
    assert!(out.contains(&format!(
        "\"id\":\"ts-pb-004\",\"op\":\"ts.query\",\"status\":\"ok\",\"code\":\"OK\",\"entries\":[{{\"entry_id\":2,\"timestamp\":20,\"status\":\"written\",\"value\":\"{}\"}}]",
        TSDB_128_BYTE_PAYLOAD
    )));
    assert!(out.contains(
        "\"id\":\"ts-pb-005\",\"op\":\"ts.query\",\"status\":\"ok\",\"code\":\"OK\",\"entries\":[]"
    ));
    assert!(out.contains(
        "\"id\":\"ts-pb-006\",\"op\":\"ts.count_status\",\"status\":\"ok\",\"code\":\"OK\",\"count\":2"
    ));
    assert!(out.contains(
        "\"id\":\"ts-pb-007\",\"op\":\"ts.count_status\",\"status\":\"ok\",\"code\":\"OK\",\"count\":0"
    ));
    assert!(out.contains("\"id\":\"ts-pb-008\""));
    assert!(out.contains("\"op\":\"ts.reopen\""));
    assert!(out.contains(&format!(
        "\"id\":\"ts-pb-009\",\"op\":\"ts.query\",\"status\":\"ok\",\"code\":\"OK\",\"entries\":[{{\"entry_id\":1,\"timestamp\":10,\"status\":\"written\",\"value\":\"\"}},{{\"entry_id\":2,\"timestamp\":20,\"status\":\"written\",\"value\":\"{}\"}}]",
        TSDB_128_BYTE_PAYLOAD
    )));
    assert!(!out.contains("\"fields\":\"value\""));
    assert!(!out.contains("\"fields\":\"entries\""));
    assert!(report.exists());
    let _ = fs::remove_file(report);
}

#[test]
fn l3_tsdb_over_limit_payload_error_fixture_replays_visible_error_and_recovery() {
    assert_eq!(TSDB_129_BYTE_PAYLOAD.len(), 129);
    let report = temp_path("l3-tsdb-over-limit-payload-error-report.json");
    let out = cli::run([
        "replay".to_string(),
        "--fixture".to_string(),
        "fixtures/l3-tsdb-over-limit-payload-error.json".to_string(),
        "--backend".to_string(),
        "file".to_string(),
        "--report".to_string(),
        report.display().to_string(),
    ])
    .unwrap();

    assert!(out.contains("\"fixture_name\":\"l3-tsdb-over-limit-payload-error\""));
    assert!(out.contains("\"level\":\"L3\""));
    assert!(out.contains("\"target_id\":\"flashdb\""));
    assert!(out.contains("\"slice_id\":\"tsdb-over-limit-payload-error\""));
    assert!(out.contains("\"commit\":\"93d175549da579b8abac07bd175ce4c3f9dde829\""));
    assert!(out.contains("\"id\":\"layout-and-metadata\""));
    assert!(out.contains("\"fields\":\"image_hash,message,backend,toolchain_status,source,fixture,fixture_hash,report_path\""));
    assert!(out.contains(
        "\"id\":\"ts-ol-001\",\"op\":\"ts.append\",\"status\":\"ok\",\"code\":\"OK\",\"entry_id\":1,\"timestamp\":10,\"value\":\"control\""
    ));
    assert!(out.contains(
        "\"id\":\"ts-ol-002\",\"op\":\"ts.append\",\"status\":\"error\",\"code\":\"FDB_WRITE_ERR\""
    ));
    assert!(!step_json_for(&out, "ts-ol-002").contains("\"entry_id\""));
    assert!(!step_json_for(&out, "ts-ol-002").contains(TSDB_129_BYTE_PAYLOAD));
    assert!(out.contains(
        "\"id\":\"ts-ol-003\",\"op\":\"ts.append\",\"status\":\"ok\",\"code\":\"OK\",\"entry_id\":2,\"timestamp\":30,\"value\":\"after\""
    ));
    assert!(out.contains(
        "\"id\":\"ts-ol-004\",\"op\":\"ts.query\",\"status\":\"ok\",\"code\":\"OK\",\"entries\":[{\"entry_id\":1,\"timestamp\":10,\"status\":\"written\",\"value\":\"control\"},{\"entry_id\":2,\"timestamp\":30,\"status\":\"written\",\"value\":\"after\"}]"
    ));
    assert!(out.contains(
        "\"id\":\"ts-ol-005\",\"op\":\"ts.query\",\"status\":\"ok\",\"code\":\"OK\",\"entries\":[]"
    ));
    assert!(out.contains(
        "\"id\":\"ts-ol-006\",\"op\":\"ts.count_status\",\"status\":\"ok\",\"code\":\"OK\",\"count\":2"
    ));
    assert!(out.contains(
        "\"id\":\"ts-ol-007\",\"op\":\"ts.count_status\",\"status\":\"ok\",\"code\":\"OK\",\"count\":0"
    ));
    assert!(out.contains("\"id\":\"ts-ol-008\""));
    assert!(out.contains("\"op\":\"ts.reopen\""));
    assert!(out.contains(
        "\"id\":\"ts-ol-009\",\"op\":\"ts.query\",\"status\":\"ok\",\"code\":\"OK\",\"entries\":[{\"entry_id\":1,\"timestamp\":10,\"status\":\"written\",\"value\":\"control\"},{\"entry_id\":2,\"timestamp\":30,\"status\":\"written\",\"value\":\"after\"}]"
    ));
    assert!(out.contains(
        "\"id\":\"ts-ol-010\",\"op\":\"ts.count_status\",\"status\":\"ok\",\"code\":\"OK\",\"count\":2"
    ));
    assert!(!out.contains("\"fields\":\"code\""));
    assert!(!out.contains("\"fields\":\"status\""));
    assert!(!out.contains("\"fields\":\"entries\""));
    assert!(report.exists());
    let _ = fs::remove_file(report);
}

#[test]
fn l3_tsdb_non_monotonic_timestamp_fixture_replays_visible_error_and_recovery() {
    let report = temp_path("l3-tsdb-non-monotonic-timestamp-report.json");
    let out = cli::run([
        "replay".to_string(),
        "--fixture".to_string(),
        "fixtures/l3-tsdb-non-monotonic-timestamp.json".to_string(),
        "--backend".to_string(),
        "file".to_string(),
        "--report".to_string(),
        report.display().to_string(),
    ])
    .unwrap();

    assert!(out.contains("\"fixture_name\":\"l3-tsdb-non-monotonic-timestamp\""));
    assert!(out.contains("\"level\":\"L3\""));
    assert!(out.contains("\"target_id\":\"flashdb\""));
    assert!(out.contains("\"slice_id\":\"tsdb-non-monotonic-timestamp\""));
    assert!(out.contains("\"commit\":\"93d175549da579b8abac07bd175ce4c3f9dde829\""));
    assert!(out.contains("\"id\":\"layout-and-metadata\""));
    assert!(out.contains("\"fields\":\"image_hash,message,backend,toolchain_status,source,fixture,fixture_hash,report_path\""));
    assert!(out.contains(
        "\"id\":\"ts-nmt-001\",\"op\":\"ts.append\",\"status\":\"ok\",\"code\":\"OK\",\"entry_id\":1,\"timestamp\":10,\"value\":\"control\""
    ));
    assert!(out.contains(
        "\"id\":\"ts-nmt-002\",\"op\":\"ts.append\",\"status\":\"error\",\"code\":\"FDB_WRITE_ERR\""
    ));
    assert!(!step_json_for(&out, "ts-nmt-002").contains("\"entry_id\""));
    assert!(!step_json_for(&out, "ts-nmt-002").contains("duplicate"));
    assert!(out.contains(
        "\"id\":\"ts-nmt-003\",\"op\":\"ts.append\",\"status\":\"error\",\"code\":\"FDB_WRITE_ERR\""
    ));
    assert!(!step_json_for(&out, "ts-nmt-003").contains("\"entry_id\""));
    assert!(!step_json_for(&out, "ts-nmt-003").contains("before"));
    assert!(out.contains(
        "\"id\":\"ts-nmt-004\",\"op\":\"ts.append\",\"status\":\"ok\",\"code\":\"OK\",\"entry_id\":2,\"timestamp\":20,\"value\":\"after\""
    ));
    assert!(out.contains(
        "\"id\":\"ts-nmt-005\",\"op\":\"ts.query\",\"status\":\"ok\",\"code\":\"OK\",\"entries\":[{\"entry_id\":1,\"timestamp\":10,\"status\":\"written\",\"value\":\"control\"},{\"entry_id\":2,\"timestamp\":20,\"status\":\"written\",\"value\":\"after\"}]"
    ));
    assert!(out.contains(
        "\"id\":\"ts-nmt-006\",\"op\":\"ts.query\",\"status\":\"ok\",\"code\":\"OK\",\"entries\":[{\"entry_id\":1,\"timestamp\":10,\"status\":\"written\",\"value\":\"control\"}]"
    ));
    assert!(out.contains(
        "\"id\":\"ts-nmt-007\",\"op\":\"ts.count_status\",\"status\":\"ok\",\"code\":\"OK\",\"count\":2"
    ));
    assert!(out.contains(
        "\"id\":\"ts-nmt-008\",\"op\":\"ts.count_status\",\"status\":\"ok\",\"code\":\"OK\",\"count\":1"
    ));
    assert!(out.contains("\"id\":\"ts-nmt-009\""));
    assert!(out.contains("\"op\":\"ts.reopen\""));
    assert!(out.contains(
        "\"id\":\"ts-nmt-010\",\"op\":\"ts.query\",\"status\":\"ok\",\"code\":\"OK\",\"entries\":[{\"entry_id\":1,\"timestamp\":10,\"status\":\"written\",\"value\":\"control\"},{\"entry_id\":2,\"timestamp\":20,\"status\":\"written\",\"value\":\"after\"}]"
    ));
    assert!(out.contains(
        "\"id\":\"ts-nmt-011\",\"op\":\"ts.count_status\",\"status\":\"ok\",\"code\":\"OK\",\"count\":2"
    ));
    assert!(!out.contains("\"fields\":\"code\""));
    assert!(!out.contains("\"fields\":\"status\""));
    assert!(!out.contains("\"fields\":\"entries\""));
    assert!(report.exists());
    let _ = fs::remove_file(report);
}

#[test]
fn l3_tsdb_reverse_query_reopen_fixture_replays_reverse_order() {
    let report = temp_path("l3-tsdb-reverse-query-reopen-report.json");
    let out = cli::run([
        "replay".to_string(),
        "--fixture".to_string(),
        "fixtures/l3-tsdb-reverse-query-reopen.json".to_string(),
        "--backend".to_string(),
        "file".to_string(),
        "--report".to_string(),
        report.display().to_string(),
    ])
    .unwrap();

    assert!(out.contains("\"fixture_name\":\"l3-tsdb-reverse-query-reopen\""));
    assert!(out.contains("\"level\":\"L3\""));
    assert!(out.contains("\"target_id\":\"flashdb\""));
    assert!(out.contains("\"slice_id\":\"tsdb-reverse-query-reopen\""));
    assert!(out.contains("\"commit\":\"93d175549da579b8abac07bd175ce4c3f9dde829\""));
    assert!(out.contains("\"id\":\"layout-and-metadata\""));
    assert!(out.contains("\"fields\":\"image_hash,backend,toolchain_status,source,fixture,fixture_hash,report_path\""));
    assert!(out.contains("\"id\":\"ts-rqr-001\""));
    assert!(out.contains("\"op\":\"ts.append\""));
    assert!(out.contains("\"entry_id\":1"));
    assert!(out.contains("\"id\":\"ts-rqr-002\""));
    assert!(out.contains("\"entry_id\":2"));
    assert!(out.contains("\"id\":\"ts-rqr-003\""));
    assert!(out.contains("\"entry_id\":3"));
    assert!(out.contains(
        "\"id\":\"ts-rqr-004\",\"op\":\"ts.set_status\",\"status\":\"ok\",\"code\":\"OK\",\"entry_id\":2,\"ts_status\":\"user1\""
    ));
    assert!(out.contains(
        "\"id\":\"ts-rqr-005\",\"op\":\"ts.query\",\"status\":\"ok\",\"code\":\"OK\",\"entries\":[{\"entry_id\":3,\"timestamp\":30,\"status\":\"written\",\"value\":\"gamma\"},{\"entry_id\":2,\"timestamp\":20,\"status\":\"user1\",\"value\":\"beta\"},{\"entry_id\":1,\"timestamp\":10,\"status\":\"written\",\"value\":\"alpha\"}]"
    ));
    let reopen_step = step_json_for(&out, "ts-rqr-006");
    assert!(reopen_step.contains("\"op\":\"ts.reopen\""));
    assert!(reopen_step.contains("\"status\":\"ok\""));
    assert!(reopen_step.contains("\"code\":\"OK\""));
    assert!(reopen_step.contains("\"image_hash\""));
    assert!(out.contains(
        "\"id\":\"ts-rqr-007\",\"op\":\"ts.query\",\"status\":\"ok\",\"code\":\"OK\",\"entries\":[{\"entry_id\":3,\"timestamp\":30,\"status\":\"written\",\"value\":\"gamma\"},{\"entry_id\":2,\"timestamp\":20,\"status\":\"user1\",\"value\":\"beta\"},{\"entry_id\":1,\"timestamp\":10,\"status\":\"written\",\"value\":\"alpha\"}]"
    ));
    assert!(!out.contains("\"fields\":\"entries\""));
    assert!(!out.contains("\"fields\":\"timestamp\""));
    assert!(report.exists());
    let _ = fs::remove_file(report);
}

#[test]
fn l3_tsdb_error_boundary_fixture_replays_visible_errors() {
    let report = temp_path("l3-tsdb-error-boundary-report.json");
    let out = cli::run([
        "replay".to_string(),
        "--fixture".to_string(),
        "fixtures/l3-tsdb-error-boundary.json".to_string(),
        "--backend".to_string(),
        "file".to_string(),
        "--report".to_string(),
        report.display().to_string(),
    ])
    .unwrap();

    assert!(out.contains("\"fixture_name\":\"l3-tsdb-error-boundary\""));
    assert!(out.contains("\"level\":\"L3\""));
    assert!(out.contains("\"target_id\":\"flashdb\""));
    assert!(out.contains("\"slice_id\":\"tsdb-error-boundary\""));
    assert!(out.contains("\"commit\":\"93d175549da579b8abac07bd175ce4c3f9dde829\""));
    assert!(out.contains("\"id\":\"layout-and-metadata\""));
    assert!(out.contains("\"fields\":\"image_hash,message,backend,toolchain_status,source,fixture,fixture_hash,report_path\""));
    assert!(out.contains("\"id\":\"ts-eb-001\""));
    assert!(out.contains("\"op\":\"ts.append\""));
    assert!(out.contains("\"entry_id\":1"));
    assert!(out.contains(
        "\"id\":\"ts-eb-002\",\"op\":\"ts.set_status\",\"status\":\"error\",\"code\":\"INVALID_RANGE\""
    ));
    assert!(out.contains(
        "\"id\":\"ts-eb-003\",\"op\":\"ts.set_status\",\"status\":\"error\",\"code\":\"PARSE\""
    ));
    assert!(out.contains(
        "\"id\":\"ts-eb-004\",\"op\":\"ts.count_status\",\"status\":\"error\",\"code\":\"PARSE\""
    ));
    assert!(out.contains(
        "\"id\":\"ts-eb-005\",\"op\":\"ts.append\",\"status\":\"error\",\"code\":\"PARSE\""
    ));
    assert!(out.contains(
        "\"id\":\"ts-eb-006\",\"op\":\"ts.query\",\"status\":\"error\",\"code\":\"PARSE\""
    ));
    assert!(out.contains(
        "\"id\":\"ts-eb-007\",\"op\":\"ts.append\",\"status\":\"ok\",\"code\":\"OK\",\"entry_id\":2,\"timestamp\":30,\"value\":\"\""
    ));
    assert!(out.contains(
        "\"id\":\"ts-eb-008\",\"op\":\"ts.query\",\"status\":\"ok\",\"code\":\"OK\",\"entries\":[{\"entry_id\":1,\"timestamp\":10,\"status\":\"written\",\"value\":\"ok\"},{\"entry_id\":2,\"timestamp\":30,\"status\":\"written\",\"value\":\"\"}]"
    ));
    assert!(!out.contains("\"fields\":\"code\""));
    assert!(!out.contains("\"fields\":\"status\""));
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
