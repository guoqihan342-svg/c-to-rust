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
