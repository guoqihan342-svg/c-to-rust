#[derive(Debug, Deserialize)]
struct FdbIsStrOracleReport {
    level: String,
    target_id: String,
    slice_id: String,
    source_commit: String,
    source_boundary: Value,
    compared_fields: Vec<String>,
    case_count: usize,
    cases: Vec<FdbIsStrOracleCase>,
}

#[derive(Debug, Deserialize)]
struct FdbIsStrOracleCase {
    id: String,
    coverage_kind: String,
    value_hex: String,
    len: usize,
    expected_outputs: FdbIsStrExpectedOutputs,
    status: String,
}

#[derive(Debug, Deserialize)]
struct FdbIsStrExpectedOutputs {
    return_value: bool,
}

fn replay_real_fdb_is_str(case: &FdbIsStrOracleCase) -> Result<bool, Box<dyn Error>> {
    let value = hex_to_bytes(&case.value_hex)?;
    if case.len > value.len() {
        return Err(format!(
            "real-fdb-is-str case {} len {} exceeds value length {}",
            case.id,
            case.len,
            value.len()
        )
        .into());
    }
    Ok(fdb_is_str::fdb_is_str(&value, case.len))
}

fn load_real_fdb_is_str_provenance(
    repo_root: &Path,
) -> Result<(PathBuf, PathBuf, Value, Value), Box<dyn Error>> {
    let slice_spec_path = repo_root
        .join("validation")
        .join("slice-specs")
        .join("flashdb-real-fdb-is-str.json");
    let oracle_status_path = repo_root
        .join("validation")
        .join("evidence")
        .join("flashdb")
        .join("auto-translation")
        .join("real-fdb-is-str")
        .join("l3-real-fdb-is-str-c-oracle-status.json");
    let slice_spec = read_json(&slice_spec_path)?;
    let oracle_status = read_json(&oracle_status_path)?;
    Ok((
        slice_spec_path,
        oracle_status_path,
        slice_spec,
        oracle_status,
    ))
}

fn real_fdb_is_str_compile_execution(
    oracle_status: &Value,
) -> Result<Value, Box<dyn Error>> {
    if oracle_status.pointer("/compile_execution/status").is_some() {
        return Ok(json!({
            "status": required_json_value(oracle_status, "/compile_execution/status", "real-fdb-is-str c oracle status")?.clone(),
            "semantic_pass": required_json_value(oracle_status, "/compile_execution/semantic_pass", "real-fdb-is-str c oracle status")?.clone(),
            "toolchain_adapter": required_json_value(oracle_status, "/compile_execution/toolchain_adapter", "real-fdb-is-str c oracle status")?.clone(),
            "toolchain_status_after_attempt": required_json_value(
                oracle_status,
                "/compile_execution/toolchain_status_after_attempt",
                "real-fdb-is-str c oracle status",
            )?.clone()
        }));
    }

    Ok(json!({
        "status": oracle_status
            .get("status")
            .cloned()
            .unwrap_or_else(|| json!("accepted_oracle_promoted")),
        "semantic_pass": oracle_status
            .get("semantic_pass")
            .cloned()
            .unwrap_or_else(|| json!(true)),
        "toolchain_adapter": "accepted_evidence",
        "toolchain_status_after_attempt": oracle_status
            .get("toolchain_status")
            .cloned()
            .unwrap_or_else(|| json!("C_ORACLE_GENERATED"))
    }))
}
