fn emit_sum_i32_buffer_static_l3_evidence(
    evidence_dir: &Path,
    case_count: usize,
    status: &str,
    unsafe_status: &str,
) -> Result<(), Box<dyn Error>> {
    let manifest_status = if status == "passed" {
        "passed"
    } else {
        "failed"
    };
    let repo_commit = "workspace".to_owned();
    let source_commit = "demo-sum-i32-buffer-20260625";
    let fixture_path = "validation/l2_slices/fixtures/sum-i32-buffer-c-oracle.json";

    emit_sum_i32_buffer_static_l3_core_evidence(
        evidence_dir,
        case_count,
        status,
        unsafe_status,
        &repo_commit,
        source_commit,
        fixture_path,
    )?;
    emit_sum_i32_buffer_static_l3_summary_evidence(
        evidence_dir,
        case_count,
        status,
        unsafe_status,
        manifest_status,
        &repo_commit,
        source_commit,
        fixture_path,
    )
}
