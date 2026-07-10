#[cfg(test)]
mod real_fdb_is_str_report_tests {
    use super::*;
    use std::time::{SystemTime, UNIX_EPOCH};

    #[test]
    fn emits_real_fdb_is_str_report_bundle() {
        let unique = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("system time after Unix epoch")
            .as_nanos();
        let repo_root = std::env::temp_dir().join(format!(
            "c-to-rust-l2-real-fdb-is-str-{}-{unique}",
            std::process::id()
        ));
        let slice_spec_dir = repo_root.join("validation").join("slice-specs");
        let oracle_status_dir = repo_root
            .join("validation")
            .join("evidence")
            .join("flashdb")
            .join("auto-translation")
            .join("real-fdb-is-str");
        let module_dir = repo_root
            .join("validation")
            .join("l2_slices")
            .join("src");
        fs::create_dir_all(&slice_spec_dir).expect("create temporary slice-spec directory");
        fs::create_dir_all(&oracle_status_dir)
            .expect("create temporary oracle-status directory");
        fs::create_dir_all(&module_dir).expect("create temporary module directory");
        write_json(
            &slice_spec_dir.join("flashdb-real-fdb-is-str.json"),
            &json!({
                "source": {"source_file_hashes": [{"path": "src/fdb_kvdb.c", "sha256": "test-source"}]},
                "c_boundary": {"signatures": [{"source_span": {"sha256": "test-span"}}]},
                "fixture_contract": {"hash": "test-fixture"}
            }),
        )
        .expect("write temporary slice spec");
        write_json(
            &oracle_status_dir.join("l3-real-fdb-is-str-c-oracle-status.json"),
            &json!({
                "harness_draft_ref": "temporary-harness.c",
                "compile_execution": {
                    "status": "passed",
                    "semantic_pass": true,
                    "toolchain_adapter": "test-compiler",
                    "toolchain_status_after_attempt": "C_ORACLE_GENERATED"
                }
            }),
        )
        .expect("write temporary oracle status");
        fs::write(
            module_dir.join("fdb_is_str.rs"),
            include_str!("../../../../fdb_is_str.rs"),
        )
        .expect("write temporary first-party module");

        let fixtures_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("fixtures");
        emit_real_fdb_is_str(&fixtures_dir, &repo_root)
            .expect("emit real-fdb-is-str report bundle");

        let evidence_dir = repo_root
            .join("validation")
            .join("evidence")
            .join("flashdb");
        let c_oracle: Value = read_json(&evidence_dir.join("l3-real-fdb-is-str-c-oracle.json"))
            .expect("read C oracle report");
        let rust_report: Value =
            read_json(&evidence_dir.join("l3-real-fdb-is-str-rust-report.json"))
                .expect("read Rust report");
        let diff: Value = read_json(&evidence_dir.join("l3-real-fdb-is-str-diff.json"))
            .expect("read diff report");
        let negative_diff: Value =
            read_json(&evidence_dir.join("l3-real-fdb-is-str-negative-diff.json"))
                .expect("read negative diff report");
        let unsafe_ledger: Value =
            read_json(&evidence_dir.join("l3-real-fdb-is-str-unsafe-ledger.json"))
                .expect("read unsafe ledger");

        assert_eq!(c_oracle["status"], "passed");
        assert_eq!(c_oracle["semantic_pass"], true);
        assert_eq!(c_oracle["case_count"], 8);
        assert_eq!(rust_report["status"], "passed");
        assert_eq!(rust_report["case_count"], 8);
        assert_eq!(diff["status"], "passed");
        assert!(diff["first_mismatch"].is_null());
        assert_eq!(negative_diff["status"], "expected_failed");
        assert_eq!(negative_diff["mutation_detected"], true);
        assert_eq!(negative_diff["case_id"], "upper-exclusive-boundary");
        assert_eq!(unsafe_ledger["status"], "passed");
        assert_eq!(unsafe_ledger["first_party_non_test_unsafe_count"], 0);

        fs::remove_dir_all(&repo_root).expect("remove temporary report tree");
    }
}
