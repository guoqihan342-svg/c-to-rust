use flashdb_rust::cli;
use std::fs;
use std::path::PathBuf;
use std::time::{SystemTime, UNIX_EPOCH};

const TSDB_128_BYTE_PAYLOAD: &str = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";

fn step_json_for<'a>(report: &'a str, step_id: &str) -> &'a str {
    let marker = format!("{{\"id\":\"{step_id}\"");
    let start = report.find(&marker).expect("step id exists in report");
    let end = report[start..].find('}').expect("step object closes");
    &report[start..start + end + 1]
}

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
fn l3_kvdb_lifecycle_fixture_replays_main_path() {
    let report = temp_path("l3-kvdb-lifecycle-report.json");
    let out = cli::run([
        "replay".to_string(),
        "--fixture".to_string(),
        "fixtures/l3-kvdb-lifecycle.json".to_string(),
        "--backend".to_string(),
        "file".to_string(),
        "--report".to_string(),
        report.display().to_string(),
    ])
    .unwrap();

    assert!(out.contains("\"fixture_name\":\"l3-kvdb-lifecycle\""));
    assert!(out.contains("\"level\":\"L3\""));
    assert!(out.contains("\"target_id\":\"flashdb\""));
    assert!(out.contains("\"slice_id\":\"kvdb-lifecycle\""));
    assert!(out.contains("\"commit\":\"93d175549da579b8abac07bd175ce4c3f9dde829\""));
    assert!(out.contains("\"id\":\"layout-and-metadata\""));
    assert!(out.contains("\"fields\":\"image_hash,message,backend,toolchain_status,source,fixture,fixture_hash,report_path\""));
    assert!(out.contains("\"id\":\"kv-l3-001\""));
    assert!(out.contains("\"op\":\"kv.set\""));
    assert!(out.contains("\"id\":\"kv-l3-004\""));
    assert!(out.contains("\"value\":null"));
    assert!(out.contains("\"id\":\"kv-l3-006\""));
    assert!(out.contains("\"op\":\"kv.reopen\""));
    assert!(out.contains("\"id\":\"kv-l3-009\""));
    assert!(out.contains("\"code\":\"INVALID_KEY\""));
    assert!(out.contains("\"id\":\"kv-l3-010\""));
    assert!(out.contains("\"code\":\"KEY_TOO_LONG\""));
    assert!(report.exists());
    let _ = fs::remove_file(report);
}

#[test]
fn l3_kvdb_compact_overwrite_fixture_replays_visible_behavior() {
    let report = temp_path("l3-kvdb-compact-overwrite-report.json");
    let out = cli::run([
        "replay".to_string(),
        "--fixture".to_string(),
        "fixtures/l3-kvdb-compact-overwrite.json".to_string(),
        "--backend".to_string(),
        "file".to_string(),
        "--report".to_string(),
        report.display().to_string(),
    ])
    .unwrap();

    assert!(out.contains("\"fixture_name\":\"l3-kvdb-compact-overwrite\""));
    assert!(out.contains("\"level\":\"L3\""));
    assert!(out.contains("\"target_id\":\"flashdb\""));
    assert!(out.contains("\"slice_id\":\"kvdb-compact-overwrite\""));
    assert!(out.contains("\"commit\":\"93d175549da579b8abac07bd175ce4c3f9dde829\""));
    assert!(out.contains("\"id\":\"layout-and-metadata\""));
    assert!(out.contains("\"fields\":\"image_hash,backend,toolchain_status,source,fixture,fixture_hash,report_path\""));
    assert!(out.contains("\"id\":\"kv-co-001\""));
    assert!(out.contains("\"op\":\"kv.set\""));
    assert!(out.contains("\"id\":\"kv-co-004\""));
    assert!(out.contains("\"value\":\"two\""));
    assert!(out.contains("\"id\":\"kv-co-005\""));
    assert!(out.contains(
        "\"entries\":[{\"key\":\"alpha\",\"value\":\"two\"},{\"key\":\"beta\",\"value\":\"keep\"}]"
    ));
    assert!(out.contains("\"id\":\"kv-co-006\""));
    assert!(out.contains("\"op\":\"kv.compact\""));
    assert!(out.contains(
        "\"id\":\"kv-co-008\",\"op\":\"kv.entries\",\"status\":\"ok\",\"code\":\"OK\",\"entries\":[{\"key\":\"alpha\",\"value\":\"two\"},{\"key\":\"beta\",\"value\":\"keep\"}]"
    ));
    assert!(out.contains("\"id\":\"kv-co-009\""));
    assert!(out.contains("\"op\":\"kv.reopen\""));
    assert!(out.contains("\"id\":\"kv-co-010\""));
    assert!(out.contains("\"value\":\"two\""));
    assert!(out.contains(
        "\"id\":\"kv-co-012\",\"op\":\"kv.entries\",\"status\":\"ok\",\"code\":\"OK\",\"entries\":[{\"key\":\"alpha\",\"value\":\"two\"},{\"key\":\"beta\",\"value\":\"keep\"}]"
    ));
    assert!(out.contains("\"id\":\"kv-co-013\""));
    assert!(out.contains("\"op\":\"kv.delete\""));
    assert!(out.contains("\"id\":\"kv-co-014\""));
    assert!(out.contains("\"value\":null"));
    assert!(report.exists());
    let _ = fs::remove_file(report);
}

#[test]
fn l3_kvdb_error_boundary_fixture_replays_visible_errors() {
    let report = temp_path("l3-kvdb-error-boundary-report.json");
    let out = cli::run([
        "replay".to_string(),
        "--fixture".to_string(),
        "fixtures/l3-kvdb-error-boundary.json".to_string(),
        "--backend".to_string(),
        "file".to_string(),
        "--report".to_string(),
        report.display().to_string(),
    ])
    .unwrap();

    assert!(out.contains("\"fixture_name\":\"l3-kvdb-error-boundary\""));
    assert!(out.contains("\"level\":\"L3\""));
    assert!(out.contains("\"target_id\":\"flashdb\""));
    assert!(out.contains("\"slice_id\":\"kvdb-error-boundary\""));
    assert!(out.contains("\"commit\":\"93d175549da579b8abac07bd175ce4c3f9dde829\""));
    assert!(out.contains("\"id\":\"layout-and-metadata\""));
    assert!(out.contains("\"fields\":\"image_hash,message,backend,toolchain_status,source,fixture,fixture_hash,report_path\""));
    assert!(out.contains("\"id\":\"kv-eb-001\""));
    assert!(out.contains("\"op\":\"kv.get\""));
    assert!(out.contains("\"value\":null"));
    assert!(out.contains("\"id\":\"kv-eb-002\""));
    assert!(out.contains("\"op\":\"kv.set\""));
    assert!(out.contains("\"status\":\"error\""));
    assert!(out.contains("\"code\":\"INVALID_KEY\""));
    assert!(out.contains("\"id\":\"kv-eb-003\""));
    assert!(out.contains("\"code\":\"KEY_TOO_LONG\""));
    assert!(out.contains("\"id\":\"kv-eb-004\""));
    assert!(out.contains("\"status\":\"ok\""));
    assert!(out.contains("\"id\":\"kv-eb-005\""));
    assert!(out.contains("\"value\":\"value\""));
    assert!(!out.contains("\"fields\":\"code\""));
    assert!(!out.contains("\"fields\":\"status\""));
    assert!(report.exists());
    let _ = fs::remove_file(report);
}

#[test]
fn l3_tsdb_set_status_report_schema_uses_ts_status_for_business_status() {
    let report = temp_path("l3-tsdb-set-status-report-schema-report.json");
    let out = cli::run([
        "replay".to_string(),
        "--fixture".to_string(),
        "fixtures/l3-tsdb-set-status-report-schema.json".to_string(),
        "--backend".to_string(),
        "file".to_string(),
        "--report".to_string(),
        report.display().to_string(),
    ])
    .unwrap();

    assert!(out.contains("\"fixture_name\":\"l3-tsdb-set-status-report-schema\""));
    assert!(out.contains("\"slice_id\":\"tsdb-set-status-report-schema\""));
    let set_status_step = step_json_for(&out, "ts-schema-002");
    assert!(set_status_step.contains("\"op\":\"ts.set_status\""));
    assert!(set_status_step.contains("\"status\":\"ok\""));
    assert!(set_status_step.contains("\"code\":\"OK\""));
    assert!(set_status_step.contains("\"entry_id\":1"));
    assert!(set_status_step.contains("\"ts_status\":\"user1\""));
    assert_eq!(set_status_step.matches("\"status\"").count(), 1);
    assert!(!set_status_step.contains("\"status\":\"user1\""));
    assert!(report.exists());
    let _ = fs::remove_file(report);
}

#[test]
fn l3_tsdb_append_query_status_fixture_replays_main_path() {
    let report = temp_path("l3-tsdb-append-query-status-report.json");
    let out = cli::run([
        "replay".to_string(),
        "--fixture".to_string(),
        "fixtures/l3-tsdb-append-query-status.json".to_string(),
        "--backend".to_string(),
        "file".to_string(),
        "--report".to_string(),
        report.display().to_string(),
    ])
    .unwrap();

    assert!(out.contains("\"fixture_name\":\"l3-tsdb-append-query-status\""));
    assert!(out.contains("\"level\":\"L3\""));
    assert!(out.contains("\"target_id\":\"flashdb\""));
    assert!(out.contains("\"slice_id\":\"tsdb-append-query-status\""));
    assert!(out.contains("\"commit\":\"93d175549da579b8abac07bd175ce4c3f9dde829\""));
    assert!(out.contains("\"id\":\"ts-l3-001\""));
    assert!(out.contains("\"op\":\"ts.append\""));
    assert!(out.contains("\"entry_id\":1"));
    assert!(out.contains("\"id\":\"ts-l3-004\""));
    assert!(out.contains("\"op\":\"ts.query\""));
    assert!(out.contains("\"timestamp\":30"));
    assert!(out.contains("\"id\":\"ts-l3-005\""));
    assert!(out.contains("\"op\":\"ts.set_status\""));
    assert!(out.contains("\"ts_status\":\"user1\""));
    assert!(out.contains("\"id\":\"ts-l3-006\""));
    assert!(out.contains("\"op\":\"ts.count_status\""));
    assert!(out.contains("\"count\":1"));
    assert!(out.contains("\"id\":\"ts-l3-008\""));
    assert!(out.contains("\"op\":\"ts.reopen\""));
    assert!(out.contains("\"id\":\"ts-l3-009\""));
    assert!(out.contains("\"value\":\"beta\""));
    assert!(report.exists());
    let _ = fs::remove_file(report);
}

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
    assert!(out.contains("\"id\":\"ts-rqr-006\""));
    assert!(out.contains("\"op\":\"ts.reopen\""));
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
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!("flashdb_rust_{nanos}_{name}"))
}
