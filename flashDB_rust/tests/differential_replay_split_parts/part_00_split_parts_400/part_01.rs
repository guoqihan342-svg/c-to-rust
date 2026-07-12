#[test]
fn l3_tsdb_deleted_status_reopen_fixture_replays_visible_counts() {
    let report = temp_path("l3-tsdb-deleted-status-reopen-report.json");
    let out = cli::run([
        "replay".to_string(),
        "--fixture".to_string(),
        "fixtures/l3-tsdb-deleted-status-reopen.json".to_string(),
        "--backend".to_string(),
        "file".to_string(),
        "--report".to_string(),
        report.display().to_string(),
    ])
    .unwrap();

    assert!(out.contains("\"fixture_name\":\"l3-tsdb-deleted-status-reopen\""));
    assert!(out.contains("\"level\":\"L3\""));
    assert!(out.contains("\"target_id\":\"flashdb\""));
    assert!(out.contains("\"slice_id\":\"tsdb-deleted-status-reopen\""));
    assert!(out.contains("\"commit\":\"93d175549da579b8abac07bd175ce4c3f9dde829\""));
    assert!(out.contains("\"id\":\"layout-and-metadata\""));
    assert!(out.contains("\"fields\":\"image_hash,backend,toolchain_status,source,fixture,fixture_hash,report_path\""));
    assert!(out.contains("\"id\":\"ts-del-001\""));
    assert!(out.contains("\"op\":\"ts.append\""));
    assert!(out.contains("\"entry_id\":1"));
    assert!(out.contains("\"id\":\"ts-del-002\""));
    assert!(out.contains("\"entry_id\":2"));
    assert!(out.contains("\"id\":\"ts-del-003\""));
    assert!(out.contains("\"op\":\"ts.set_status\""));
    assert!(out.contains("\"entry_id\":1"));
    assert!(out.contains("\"ts_status\":\"deleted\""));
    assert!(out.contains(
        "\"id\":\"ts-del-004\",\"op\":\"ts.count_status\",\"status\":\"ok\",\"code\":\"OK\",\"count\":1"
    ));
    assert!(out.contains(
        "\"id\":\"ts-del-005\",\"op\":\"ts.count_status\",\"status\":\"ok\",\"code\":\"OK\",\"count\":1"
    ));
    assert!(out.contains("\"id\":\"ts-del-006\""));
    assert!(out.contains("\"op\":\"ts.reopen\""));
    assert!(out.contains(
        "\"id\":\"ts-del-007\",\"op\":\"ts.count_status\",\"status\":\"ok\",\"code\":\"OK\",\"count\":1"
    ));
    assert!(!out.contains("\"fields\":\"count\""));
    assert!(!out.contains("\"fields\":\"status\""));
    assert!(report.exists());
    let _ = fs::remove_file(report);
}

#[test]
fn l3_tsdb_user2_status_fixture_replays_visible_counts() {
    let report = temp_path("l3-tsdb-user2-status-report.json");
    let out = cli::run([
        "replay".to_string(),
        "--fixture".to_string(),
        "fixtures/l3-tsdb-user2-status.json".to_string(),
        "--backend".to_string(),
        "file".to_string(),
        "--report".to_string(),
        report.display().to_string(),
    ])
    .unwrap();

    assert!(out.contains("\"fixture_name\":\"l3-tsdb-user2-status\""));
    assert!(out.contains("\"level\":\"L3\""));
    assert!(out.contains("\"target_id\":\"flashdb\""));
    assert!(out.contains("\"slice_id\":\"tsdb-user2-status\""));
    assert!(out.contains("\"commit\":\"93d175549da579b8abac07bd175ce4c3f9dde829\""));
    assert!(out.contains("\"id\":\"layout-and-metadata\""));
    assert!(out.contains("\"fields\":\"image_hash,backend,toolchain_status,source,fixture,fixture_hash,report_path\""));
    assert!(out.contains("\"id\":\"ts-u2-001\""));
    assert!(out.contains("\"op\":\"ts.append\""));
    assert!(out.contains("\"entry_id\":1"));
    assert!(out.contains("\"id\":\"ts-u2-002\""));
    assert!(out.contains("\"entry_id\":2"));

    let set_status_step = step_json_for(&out, "ts-u2-003");
    assert!(set_status_step.contains("\"op\":\"ts.set_status\""));
    assert!(set_status_step.contains("\"status\":\"ok\""));
    assert!(set_status_step.contains("\"code\":\"OK\""));
    assert!(set_status_step.contains("\"entry_id\":2"));
    assert!(set_status_step.contains("\"ts_status\":\"user2\""));
    assert_eq!(set_status_step.matches("\"status\"").count(), 1);
    assert!(!set_status_step.contains("\"status\":\"user2\""));

    assert!(out.contains(
        "\"id\":\"ts-u2-004\",\"op\":\"ts.count_status\",\"status\":\"ok\",\"code\":\"OK\",\"count\":1"
    ));
    assert!(out.contains(
        "\"id\":\"ts-u2-005\",\"op\":\"ts.count_status\",\"status\":\"ok\",\"code\":\"OK\",\"count\":1"
    ));
    assert!(out.contains("\"id\":\"ts-u2-006\""));
    assert!(out.contains("\"op\":\"ts.query\""));
    assert!(out.contains(
        "\"entries\":[{\"entry_id\":1,\"timestamp\":10,\"status\":\"written\",\"value\":\"alpha\"},{\"entry_id\":2,\"timestamp\":20,\"status\":\"user2\",\"value\":\"beta\"}]"
    ));
    assert!(out.contains("\"id\":\"ts-u2-007\""));
    assert!(out.contains("\"op\":\"ts.reopen\""));
    assert!(out.contains(
        "\"id\":\"ts-u2-008\",\"op\":\"ts.count_status\",\"status\":\"ok\",\"code\":\"OK\",\"count\":1"
    ));
    assert!(out.contains("\"id\":\"ts-u2-009\""));
    assert!(!out.contains("\"fields\":\"count\""));
    assert!(!out.contains("\"fields\":\"status\""));
    assert!(report.exists());
    let _ = fs::remove_file(report);
}

#[test]
fn l3_tsdb_status_transition_fixture_replays_latest_status() {
    let report = temp_path("l3-tsdb-status-transition-report.json");
    let out = cli::run([
        "replay".to_string(),
        "--fixture".to_string(),
        "fixtures/l3-tsdb-status-transition.json".to_string(),
        "--backend".to_string(),
        "file".to_string(),
        "--report".to_string(),
        report.display().to_string(),
    ])
    .unwrap();

    assert!(out.contains("\"fixture_name\":\"l3-tsdb-status-transition\""));
    assert!(out.contains("\"level\":\"L3\""));
    assert!(out.contains("\"target_id\":\"flashdb\""));
    assert!(out.contains("\"slice_id\":\"tsdb-status-transition\""));
    assert!(out.contains("\"commit\":\"93d175549da579b8abac07bd175ce4c3f9dde829\""));
    assert!(out.contains("\"id\":\"layout-and-metadata\""));
    assert!(out.contains("\"fields\":\"image_hash,backend,toolchain_status,source,fixture,fixture_hash,report_path\""));
    assert!(out.contains("\"id\":\"ts-tr-001\""));
    assert!(out.contains("\"op\":\"ts.append\""));
    assert!(out.contains("\"entry_id\":1"));
    assert!(out.contains("\"id\":\"ts-tr-002\""));
    assert!(out.contains("\"entry_id\":2"));

    let user1_step = step_json_for(&out, "ts-tr-003");
    assert!(user1_step.contains("\"op\":\"ts.set_status\""));
    assert!(user1_step.contains("\"status\":\"ok\""));
    assert!(user1_step.contains("\"code\":\"OK\""));
    assert!(user1_step.contains("\"entry_id\":1"));
    assert!(user1_step.contains("\"ts_status\":\"user1\""));

    let user2_step = step_json_for(&out, "ts-tr-005");
    assert!(user2_step.contains("\"op\":\"ts.set_status\""));
    assert!(user2_step.contains("\"entry_id\":1"));
    assert!(user2_step.contains("\"ts_status\":\"user2\""));

    let deleted_step = step_json_for(&out, "ts-tr-008");
    assert!(deleted_step.contains("\"op\":\"ts.set_status\""));
    assert!(deleted_step.contains("\"entry_id\":1"));
    assert!(deleted_step.contains("\"ts_status\":\"deleted\""));

    assert!(out.contains(
        "\"id\":\"ts-tr-004\",\"op\":\"ts.count_status\",\"status\":\"ok\",\"code\":\"OK\",\"count\":1"
    ));
    assert!(out.contains(
        "\"id\":\"ts-tr-006\",\"op\":\"ts.count_status\",\"status\":\"ok\",\"code\":\"OK\",\"count\":0"
    ));
    assert!(out.contains(
        "\"id\":\"ts-tr-007\",\"op\":\"ts.count_status\",\"status\":\"ok\",\"code\":\"OK\",\"count\":1"
    ));
    assert!(out.contains(
        "\"id\":\"ts-tr-009\",\"op\":\"ts.count_status\",\"status\":\"ok\",\"code\":\"OK\",\"count\":1"
    ));
    assert!(out.contains(
        "\"id\":\"ts-tr-010\",\"op\":\"ts.count_status\",\"status\":\"ok\",\"code\":\"OK\",\"count\":0"
    ));
    assert!(out.contains(
        "\"id\":\"ts-tr-011\",\"op\":\"ts.count_status\",\"status\":\"ok\",\"code\":\"OK\",\"count\":0"
    ));
    assert!(out.contains(
        "\"id\":\"ts-tr-012\",\"op\":\"ts.count_status\",\"status\":\"ok\",\"code\":\"OK\",\"count\":1"
    ));
    assert!(out.contains(
        "\"id\":\"ts-tr-013\",\"op\":\"ts.query\",\"status\":\"ok\",\"code\":\"OK\",\"entries\":[{\"entry_id\":1,\"timestamp\":10,\"status\":\"deleted\",\"value\":\"alpha\"},{\"entry_id\":2,\"timestamp\":20,\"status\":\"written\",\"value\":\"beta\"}]"
    ));
    assert!(out.contains("\"id\":\"ts-tr-014\""));
    assert!(out.contains("\"op\":\"ts.reopen\""));
    assert!(out.contains(
        "\"id\":\"ts-tr-015\",\"op\":\"ts.count_status\",\"status\":\"ok\",\"code\":\"OK\",\"count\":1"
    ));
    assert!(out.contains(
        "\"id\":\"ts-tr-016\",\"op\":\"ts.count_status\",\"status\":\"ok\",\"code\":\"OK\",\"count\":1"
    ));
    assert!(out.contains(
        "\"id\":\"ts-tr-017\",\"op\":\"ts.query\",\"status\":\"ok\",\"code\":\"OK\",\"entries\":[{\"entry_id\":1,\"timestamp\":10,\"status\":\"deleted\",\"value\":\"alpha\"},{\"entry_id\":2,\"timestamp\":20,\"status\":\"written\",\"value\":\"beta\"}]"
    ));
    assert!(!out.contains("\"fields\":\"count\""));
    assert!(!out.contains("\"fields\":\"status\""));
    assert!(report.exists());
    let _ = fs::remove_file(report);
}
