use std::fs;
use std::process::Command;
use std::time::{SystemTime, UNIX_EPOCH};

fn temp_report(name: &str) -> std::path::PathBuf {
    std::env::temp_dir().join(format!(
        "flashdb_rust_{name}_{}_{}.json",
        std::process::id(),
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos()
    ))
}

fn temp_dir(name: &str) -> std::path::PathBuf {
    std::env::temp_dir().join(format!(
        "flashdb_rust_{name}_{}_{}",
        std::process::id(),
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos()
    ))
}

#[test]
fn cli_smoke_writes_json_report() {
    let report = temp_report("smoke");
    let output = Command::new(env!("CARGO_BIN_EXE_flashdb-rust"))
        .args([
            "smoke",
            "--backend",
            "memory",
            "--report",
            report.to_str().unwrap(),
        ])
        .output()
        .unwrap();

    assert!(
        output.status.success(),
        "stderr={}",
        String::from_utf8_lossy(&output.stderr)
    );
    let text = fs::read_to_string(&report).unwrap();
    assert!(text.contains("\"command\":\"smoke\""));
    assert!(text.contains("\"production\":1"));
    let _ = fs::remove_file(report);
}

#[test]
fn cli_stress_small_loop_reports_all_scenarios() {
    let output = Command::new(env!("CARGO_BIN_EXE_flashdb-rust"))
        .args(["stress", "--loops", "5", "--seed", "42"])
        .output()
        .unwrap();

    assert!(
        output.status.success(),
        "stderr={}",
        String::from_utf8_lossy(&output.stderr)
    );
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("\"loops\":5"));
    assert!(stdout.contains("\"production\":5"));
    assert!(stdout.contains("\"abnormal\":5"));
    assert!(stdout.contains("\"reliability\":5"));
}

#[test]
fn cli_version_manifest_writes_version_governance_report() {
    let report = temp_report("version-manifest");
    let output = Command::new(env!("CARGO_BIN_EXE_flashdb-rust"))
        .args(["version-manifest", "--report", report.to_str().unwrap()])
        .output()
        .unwrap();

    assert!(
        output.status.success(),
        "stderr={}",
        String::from_utf8_lossy(&output.stderr)
    );
    let text = fs::read_to_string(&report).unwrap();
    assert!(text.contains("\"command\":\"version-manifest\""));
    assert!(text.contains("\"schema_version\":1"));
    assert!(text.contains("\"package_name\":\"flashdb_rust\""));
    assert!(text.contains("\"package_version\":\"0.1.0\""));
    assert!(text.contains("\"flashdb_source_commit\":\"93d175549da579b8abac07bd175ce4c3f9dde829\""));
    assert!(text.contains("\"agent_contract_version\":\"0.1.0\""));
    assert!(text.contains("\"context_schema_version\":\"0.1.0\""));
    assert!(text.contains("\"patch_plan_schema_version\":\"0.1.0\""));
    assert!(text.contains("\"fixture_schema_version\":1"));
    assert!(text.contains("\"evidence_schema_version\":1"));
    assert!(text.contains("\"cargo_lock_sha256\""));
    assert!(text.contains("\"cache_key_inputs\""));
    assert!(text.contains("\"command_arguments\":[\"version-manifest\"]"));
    assert!(text.contains("\"fixture_sha256\":null"));
    assert!(text.contains("\"ai_metadata\":{\"used\":false,\"provider\":\"not_configured\"}"));
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert_eq!(stdout.trim(), text.trim());
    let _ = fs::remove_file(report);
}

#[test]
fn cli_unsafe_scan_writes_machine_readable_report() {
    let report = temp_report("unsafe-scan");
    let output = Command::new(env!("CARGO_BIN_EXE_flashdb-rust"))
        .args(["unsafe-scan", "--report", report.to_str().unwrap()])
        .output()
        .unwrap();

    assert!(
        output.status.success(),
        "stderr={}",
        String::from_utf8_lossy(&output.stderr)
    );
    let text = fs::read_to_string(&report).unwrap();
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert_eq!(stdout.trim(), text.trim());
    assert!(text.contains("\"command\":\"unsafe-scan\""));
    assert!(text.contains("\"schema_version\":1"));
    assert!(text.contains("\"first_party_non_test_unsafe_count\":0"));
    assert!(text.contains("\"unsafe_ratio\":0"));
    assert!(text.contains("\"categories\":{"));
    assert!(text.contains("\"findings\":[]"));
    let _ = fs::remove_file(report);
}

#[test]
fn cli_evidence_search_reports_matches() {
    let dir = temp_dir("evidence-search");
    fs::create_dir_all(&dir).unwrap();
    fs::write(
        dir.join("final-verification.json"),
        "{\"status\":\"passed\"}\n",
    )
    .unwrap();
    let report = temp_report("evidence-search-report");

    let output = Command::new(env!("CARGO_BIN_EXE_flashdb-rust"))
        .args([
            "evidence-search",
            "--evidence-dir",
            dir.to_str().unwrap(),
            "--query",
            "passed",
            "--report",
            report.to_str().unwrap(),
        ])
        .output()
        .unwrap();

    assert!(
        output.status.success(),
        "stderr={}",
        String::from_utf8_lossy(&output.stderr)
    );
    let text = fs::read_to_string(&report).unwrap();
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert_eq!(stdout.trim(), text.trim());
    assert!(text.contains("\"command\":\"evidence-search\""));
    assert!(text.contains("\"match_count\":1"));
    assert!(text.contains("\"path\":\"final-verification.json\""));
    assert!(text.contains("\"line\":1"));
    assert!(text.contains("\"snippet\":\"{\\\"status\\\":\\\"passed\\\"}\""));

    let _ = fs::remove_file(report);
    let _ = fs::remove_dir_all(dir);
}

#[test]
fn cli_evidence_search_excludes_report_inside_evidence_dir() {
    let dir = temp_dir("evidence-search-report-exclusion");
    fs::create_dir_all(&dir).unwrap();
    fs::write(dir.join("source.json"), "{\"status\":\"passed\"}\n").unwrap();
    let report = dir.join("evidence-search-report.json");
    fs::write(&report, "{\"old_query\":\"passed\"}\n").unwrap();

    let output = Command::new(env!("CARGO_BIN_EXE_flashdb-rust"))
        .args([
            "evidence-search",
            "--evidence-dir",
            dir.to_str().unwrap(),
            "--query",
            "passed",
            "--report",
            report.to_str().unwrap(),
        ])
        .output()
        .unwrap();

    assert!(
        output.status.success(),
        "stderr={}",
        String::from_utf8_lossy(&output.stderr)
    );
    let text = fs::read_to_string(&report).unwrap();
    assert!(text.contains("\"match_count\":1"));
    assert!(text.contains("\"path\":\"source.json\""));
    assert!(!text.contains("\"path\":\"evidence-search-report.json\""));

    let _ = fs::remove_dir_all(dir);
}

#[test]
fn cli_evidence_search_tolerates_non_utf8_evidence_file() {
    let dir = temp_dir("evidence-search-non-utf8");
    fs::create_dir_all(&dir).unwrap();
    fs::write(dir.join("a-bad.log"), [0xff, b'\n']).unwrap();
    fs::write(dir.join("z-good.json"), "{\"status\":\"passed\"}\n").unwrap();

    let output = Command::new(env!("CARGO_BIN_EXE_flashdb-rust"))
        .args([
            "evidence-search",
            "--evidence-dir",
            dir.to_str().unwrap(),
            "--query",
            "passed",
        ])
        .output()
        .unwrap();

    assert!(
        output.status.success(),
        "stderr={}",
        String::from_utf8_lossy(&output.stderr)
    );
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("\"match_count\":1"));
    assert!(stdout.contains("\"path\":\"z-good.json\""));

    let _ = fs::remove_dir_all(dir);
}
