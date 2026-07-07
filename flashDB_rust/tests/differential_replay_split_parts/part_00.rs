use flashdb_rust::cli;
use std::fs;
use std::path::PathBuf;
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{SystemTime, UNIX_EPOCH};

const TSDB_128_BYTE_PAYLOAD: &str = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";
const TSDB_129_BYTE_PAYLOAD: &str = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdefx";
static NEXT_TEMP_PATH_ID: AtomicU64 = AtomicU64::new(0);

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
fn l3_kvdb_delete_missing_key_fixture_replays_visible_error_and_recovery() {
    let report = temp_path("l3-kvdb-delete-missing-key-report.json");
    let out = cli::run([
        "replay".to_string(),
        "--fixture".to_string(),
        "fixtures/l3-kvdb-delete-missing-key.json".to_string(),
        "--backend".to_string(),
        "file".to_string(),
        "--report".to_string(),
        report.display().to_string(),
    ])
    .unwrap();

    assert!(out.contains("\"fixture_name\":\"l3-kvdb-delete-missing-key\""));
    assert!(out.contains("\"level\":\"L3\""));
    assert!(out.contains("\"target_id\":\"flashdb\""));
    assert!(out.contains("\"slice_id\":\"kvdb-delete-missing-key\""));
    assert!(out.contains("\"commit\":\"93d175549da579b8abac07bd175ce4c3f9dde829\""));
    assert!(out.contains("\"id\":\"layout-and-metadata\""));
    assert!(out.contains("\"fields\":\"image_hash,message,backend,toolchain_status,source,fixture,fixture_hash,report_path\""));

    let first_missing_delete = step_json_for(&out, "kv-dmk-001");
    assert!(first_missing_delete.contains("\"op\":\"kv.delete\""));
    assert!(first_missing_delete.contains("\"status\":\"error\""));
    assert!(first_missing_delete.contains("\"code\":\"FDB_KV_NAME_ERR\""));

    assert!(out.contains(
        "\"id\":\"kv-dmk-002\",\"op\":\"kv.get\",\"status\":\"ok\",\"code\":\"OK\",\"value\":null"
    ));
    assert!(out.contains(
        "\"id\":\"kv-dmk-003\",\"op\":\"kv.entries\",\"status\":\"ok\",\"code\":\"OK\",\"entries\":[]"
    ));
    assert!(out.contains(
        "\"id\":\"kv-dmk-005\",\"op\":\"kv.get\",\"status\":\"ok\",\"code\":\"OK\",\"value\":\"one\""
    ));
    assert!(out.contains(
        "\"id\":\"kv-dmk-006\",\"op\":\"kv.entries\",\"status\":\"ok\",\"code\":\"OK\",\"entries\":[{\"key\":\"alpha\",\"value\":\"one\"}]"
    ));
    assert!(out.contains(
        "\"id\":\"kv-dmk-007\",\"op\":\"kv.delete\",\"status\":\"ok\",\"code\":\"OK\",\"key\":\"alpha\""
    ));

    let second_missing_delete = step_json_for(&out, "kv-dmk-008");
    assert!(second_missing_delete.contains("\"op\":\"kv.delete\""));
    assert!(second_missing_delete.contains("\"status\":\"error\""));
    assert!(second_missing_delete.contains("\"code\":\"FDB_KV_NAME_ERR\""));

    assert!(out.contains(
        "\"id\":\"kv-dmk-009\",\"op\":\"kv.get\",\"status\":\"ok\",\"code\":\"OK\",\"value\":null"
    ));
    assert!(out.contains("\"id\":\"kv-dmk-010\""));
    assert!(out.contains("\"op\":\"kv.reopen\""));
    assert!(out.contains(
        "\"id\":\"kv-dmk-011\",\"op\":\"kv.get\",\"status\":\"ok\",\"code\":\"OK\",\"value\":null"
    ));
    assert!(out.contains(
        "\"id\":\"kv-dmk-012\",\"op\":\"kv.get\",\"status\":\"ok\",\"code\":\"OK\",\"value\":null"
    ));
    assert!(out.contains(
        "\"id\":\"kv-dmk-013\",\"op\":\"kv.entries\",\"status\":\"ok\",\"code\":\"OK\",\"entries\":[]"
    ));
    assert!(!out.contains("\"fields\":\"code\""));
    assert!(!out.contains("\"fields\":\"status\""));
    assert!(!out.contains("\"fields\":\"value\""));
    assert!(!out.contains("\"fields\":\"entries\""));
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
