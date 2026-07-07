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
