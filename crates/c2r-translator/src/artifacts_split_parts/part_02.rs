#[cfg(test)]
mod core_translation_artifact_tests {
    use std::{
        env, fs,
        path::PathBuf,
        time::{SystemTime, UNIX_EPOCH},
    };

    use serde_json::Value;

    use super::*;
    use crate::{TranslationError, TranslationPlan};

    fn unique_out_dir(name: &str) -> PathBuf {
        let nanos = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        env::temp_dir().join(format!(
            "c2r-artifacts-{name}-{}-{nanos}",
            std::process::id()
        ))
    }

    #[test]
    fn core_translation_artifacts_write_stable_file_set_and_blocked_repairs() {
        let spec = SliceSpec {
            target_id: "demo-target".to_string(),
            slice_id: "demo-slice".to_string(),
            source_commit: "abcdef0".to_string(),
            fixture_hash: "fixture-sha".to_string(),
            ..SliceSpec::default()
        };
        let result = TranslationResult {
            plan: TranslationPlan {
                target_id: spec.target_id.clone(),
                slice_id: spec.slice_id.clone(),
                function_name: "demo".to_string(),
                ..TranslationPlan::default()
            },
            errors: vec![TranslationError {
                kind: "unsupported_syntax".to_string(),
                message: "switch requires CFG/relooper support before automatic lowering"
                    .to_string(),
                source_span: Some("switch".to_string()),
            }],
            ..TranslationResult::default()
        };
        let out_dir = unique_out_dir("core-translation-artifacts");
        fs::create_dir_all(&out_dir).unwrap();

        let artifacts =
            write_core_translation_artifacts(&spec, &result, &out_dir, "l3-demo-slice", "blocked")
                .unwrap();
        let names = artifacts
            .iter()
            .map(|path| path.file_name().unwrap().to_string_lossy().to_string())
            .collect::<Vec<_>>();

        assert_eq!(
            names,
            vec![
                "l3-demo-slice-auto-translation-plan.json",
                "l3-demo-slice-auto-translation-events.jsonl",
                "l3-demo-slice-type-map.json",
                "l3-demo-slice-cfg.json",
                "l3-demo-slice-pointer-graph.json",
                "l3-demo-slice-ai-candidate-manifest.json",
                "l3-demo-slice-blocked-repairs.json",
                "l3-demo-slice-rust-draft.rs",
            ]
        );
        let blocked: Value = serde_json::from_str(
            &fs::read_to_string(out_dir.join("l3-demo-slice-blocked-repairs.json")).unwrap(),
        )
        .unwrap();

        assert_eq!(blocked["status"], "blocked");
        assert_eq!(blocked["blocked"][0]["kind"], "unsupported_syntax");
        assert_eq!(blocked["blocked"][0]["source_span"], "switch");
    }

    #[test]
    fn write_translation_artifacts_public_orchestration_stays_in_artifacts_module() {
        let spec = SliceSpec {
            target_id: "demo-target".to_string(),
            slice_id: "artifact-orchestration".to_string(),
            source_commit: "abcdef0".to_string(),
            fixture_hash: "fixture-sha".to_string(),
            function_name: "identity".to_string(),
            c_source: "int identity(int value) { return value; }".to_string(),
            ..SliceSpec::default()
        };
        let out_dir = unique_out_dir("artifact-orchestration");

        let manifest = write_translation_artifacts(&spec, &out_dir).unwrap();

        let mut expected_artifact_count = 8;
        if cfg!(feature = "clang-frontend") {
            expected_artifact_count += 1;
        }
        if cfg!(feature = "clang-lowering-report") {
            expected_artifact_count += 1;
        }

        assert_eq!(manifest.status, "blocked");
        assert_eq!(manifest.artifact_paths.len(), expected_artifact_count);
        assert!(out_dir
            .join("l3-artifact-orchestration-rust-draft.rs")
            .exists());
        #[cfg(feature = "clang-frontend")]
        assert!(out_dir
            .join("l3-artifact-orchestration-clang-dry-run.json")
            .exists());
        #[cfg(feature = "clang-lowering-report")]
        assert!(out_dir
            .join("l3-artifact-orchestration-clang-lowering-report.json")
            .exists());
    }

    #[test]
    fn write_translation_artifacts_manifest_paths_are_repo_relative() {
        let spec = SliceSpec {
            target_id: "demo-target".to_string(),
            slice_id: "repo-relative-artifacts".to_string(),
            source_commit: "abcdef0".to_string(),
            fixture_hash: "fixture-sha".to_string(),
            function_name: "identity".to_string(),
            c_source: "int identity(int value) { return value; }".to_string(),
            ..SliceSpec::default()
        };
        let out_dir = std::env::current_dir()
            .unwrap()
            .join("target/c2r-translator-tests/repo-relative-artifacts");

        let manifest = write_translation_artifacts(&spec, &out_dir).unwrap();

        assert!(!manifest
            .artifact_paths
            .iter()
            .any(|path| path.contains(':') || path.starts_with('/')));
        assert!(manifest
            .artifact_paths
            .iter()
            .all(|path| path.starts_with("target/c2r-translator-tests/repo-relative-artifacts/")));
    }
}

#[cfg(all(test, feature = "clang-frontend"))]
mod clang_dry_run_artifact_tests {
    use std::{
        collections::BTreeMap,
        env, fs,
        path::PathBuf,
        time::{SystemTime, UNIX_EPOCH},
    };

    use serde_json::Value;

    use super::*;
    use crate::{BuildProfile, SourceSpanRef};

    fn unique_out_dir(name: &str) -> PathBuf {
        let nanos = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        env::temp_dir().join(format!(
            "c2r-artifacts-{name}-{}-{nanos}",
            std::process::id()
        ))
    }

    fn profile() -> BuildProfile {
        BuildProfile {
            include_paths: Vec::new(),
            defines: Vec::new(),
            target: None,
            clang_ast_fixture: None,
            target_triple: None,
            abi: None,
            compiler_command_source: "unit-test".to_string(),
            clang_available: true,
        }
    }

    #[test]
    fn clang_dry_run_artifact_records_parse_spec_errors() {
        let spec = SliceSpec {
            target_id: "demo".to_string(),
            slice_id: "add-one".to_string(),
            source_commit: "1234567".to_string(),
            function_name: "add_one".to_string(),
            c_source: "int add_one(int value) { return value + 1; }".to_string(),
            fixture_hash: "fixture-sha".to_string(),
            build_profile: profile(),
            ..SliceSpec::default()
        };
        let out_dir = unique_out_dir("clang-dry-run-error");
        fs::create_dir_all(&out_dir).unwrap();

        let path = write_clang_dry_run_artifact(&spec, &out_dir, "l3-add-one").unwrap();
        let value: Value = serde_json::from_str(&fs::read_to_string(path).unwrap()).unwrap();

        assert_eq!(value["schema_version"], 1);
        assert_eq!(value["target_id"], "demo");
        assert_eq!(value["slice_id"], "add-one");
        assert_eq!(value["frontend"], "clang");
        assert_eq!(value["status"], "blocked");
        assert_eq!(value["dry_run"], Value::Null);
        assert_eq!(value["errors"][0]["kind"], "missing_source_root");
    }

    #[test]
    fn clang_dry_run_artifact_allows_inline_slice_source_without_function_span() {
        let spec = SliceSpec {
            target_id: "demo".to_string(),
            slice_id: "inline-add-one".to_string(),
            source_commit: "1234567".to_string(),
            function_name: "add_one".to_string(),
            c_source: "int add_one(int value) { return value + 1; }".to_string(),
            fixture_hash: "fixture-sha".to_string(),
            source_root: Some("<pinned-demo-root>".to_string()),
            source_file: Some("src/add_one.c".to_string()),
            source_file_hashes: BTreeMap::from([(
                "src/add_one.c".to_string(),
                "source-sha".to_string(),
            )]),
            build_profile: profile(),
            ..SliceSpec::default()
        };
        let out_dir = unique_out_dir("clang-dry-run-inline-source");
        fs::create_dir_all(&out_dir).unwrap();

        let path = write_clang_dry_run_artifact(&spec, &out_dir, "l3-inline-add-one").unwrap();
        let value: Value = serde_json::from_str(&fs::read_to_string(path).unwrap()).unwrap();

        assert_eq!(value["artifact_kind"], "clang-dry-run");
        assert_eq!(value["status"], "diagnostic_only");
        assert_eq!(value["errors"], Value::Array(Vec::new()));
        assert_eq!(value["metadata"]["function_source_span"], Value::Null);
        assert_eq!(value["dry_run"]["function_name"], "add_one");
    }

    #[test]
    fn clang_dry_run_artifact_marks_libclang_as_diagnostic_only() {
        let spec = SliceSpec {
            target_id: "demo".to_string(),
            slice_id: "add-one".to_string(),
            source_commit: "1234567".to_string(),
            function_name: "add_one".to_string(),
            c_source: "int add_one(int value) { return value + 1; }".to_string(),
            fixture_hash: "fixture-sha".to_string(),
            source_root: Some("C:/src/demo".to_string()),
            source_file: Some("src/add_one.c".to_string()),
            source_files: Vec::new(),
            source_file_hashes: BTreeMap::from([(
                "src/add_one.c".to_string(),
                "source-sha".to_string(),
            )]),
            function_source_span: Some(SourceSpanRef {
                file: "src/add_one.c".to_string(),
                line_start: 1,
                line_end: 1,
                byte_start: 0,
                byte_end: 42,
                sha256: "function-span-sha".to_string(),
            }),
            build_profile: profile(),
            ..SliceSpec::default()
        };
        let out_dir = unique_out_dir("clang-dry-run-diagnostic-only");
        fs::create_dir_all(&out_dir).unwrap();

        let path = write_clang_dry_run_artifact(&spec, &out_dir, "l3-add-one").unwrap();
        let value: Value = serde_json::from_str(&fs::read_to_string(path).unwrap()).unwrap();

        assert_eq!(value["artifact_kind"], "clang-dry-run");
        assert_eq!(value["status"], "diagnostic_only");
        assert_eq!(value["claim_boundary"]["role"], "diagnostic_only");
        assert_eq!(value["claim_boundary"]["affects_manifest_status"], false);
        assert_eq!(value["claim_boundary"]["affects_semantic_pass"], false);
        assert_eq!(value["active_frontend"]["kind"], "clang_ast_dump_json");
        assert_eq!(
            value["active_frontend"]["command"],
            "clang -Xclang -ast-dump=json -fsyntax-only"
        );
        assert_eq!(value["active_frontend"]["required_env"][0], "CLANG_PATH");
        assert_eq!(value["active_frontend"]["uses_libclang"], false);
        assert_eq!(value["dry_run"]["status"], "diagnostic_only");
    }
}
