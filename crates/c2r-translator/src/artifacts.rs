use std::{
    error::Error,
    fs,
    path::{Path, PathBuf},
};

use serde_json::json;

#[cfg(feature = "clang-frontend")]
use crate::clang_frontend;
use crate::{SliceSpec, TranslationResult};

pub(crate) fn write_json_file(
    out_dir: &Path,
    file_name: &str,
    value: &serde_json::Value,
) -> Result<PathBuf, Box<dyn Error>> {
    write_text_file(
        out_dir,
        file_name,
        &(serde_json::to_string_pretty(value)? + "\n"),
    )
}

pub(crate) fn write_text_file(
    out_dir: &Path,
    file_name: &str,
    text: &str,
) -> Result<PathBuf, Box<dyn Error>> {
    let path = out_dir.join(file_name);
    fs::write(&path, text)?;
    Ok(path)
}

pub(crate) fn translation_events_jsonl(
    spec: &SliceSpec,
    result: &TranslationResult,
) -> Result<String, Box<dyn Error>> {
    let mut lines = Vec::new();
    lines.push(serde_json::to_string(&json!({
        "schema_version": 1,
        "target_id": spec.target_id,
        "slice_id": spec.slice_id,
        "event": "translation_started",
        "source_commit": spec.source_commit,
        "fixture_hash": spec.fixture_hash,
    }))?);
    for error in &result.errors {
        lines.push(serde_json::to_string(&json!({
            "schema_version": 1,
            "target_id": spec.target_id,
            "slice_id": spec.slice_id,
            "event": "translation_blocked",
            "kind": error.kind,
            "message": error.message,
            "source_span": error.source_span,
        }))?);
    }
    if result.errors.is_empty() {
        lines.push(serde_json::to_string(&json!({
            "schema_version": 1,
            "target_id": spec.target_id,
            "slice_id": spec.slice_id,
            "event": "translation_generated",
            "translation_rule_ids": result.plan.translation_rule_ids,
        }))?);
    }
    Ok(lines.join("\n") + "\n")
}

#[cfg(feature = "clang-frontend")]
pub(crate) fn write_clang_dry_run_artifact(
    spec: &SliceSpec,
    out_dir: &Path,
    prefix: &str,
) -> Result<PathBuf, Box<dyn Error>> {
    let value = match clang_frontend::ClangParseSpec::from_slice_spec(spec) {
        Ok(parse_spec) => json!({
            "schema_version": 1,
            "target_id": spec.target_id,
            "slice_id": spec.slice_id,
            "source_commit": spec.source_commit,
            "frontend": "clang",
            "status": "ready_without_libclang",
            "dry_run": parse_spec.dry_run(),
            "metadata": {
                "source_file_hashes": parse_spec.source_file_hashes,
                "function_source_span": parse_spec.function_source_span,
            },
            "errors": [],
        }),
        Err(error) => json!({
            "schema_version": 1,
            "target_id": spec.target_id,
            "slice_id": spec.slice_id,
            "source_commit": spec.source_commit,
            "frontend": "clang",
            "status": "blocked",
            "dry_run": null,
            "metadata": {
                "source_file_hashes": spec.source_file_hashes,
                "function_source_span": spec.function_source_span,
            },
            "errors": [
                {
                    "kind": error.kind,
                    "message": error.message,
                }
            ],
        }),
    };
    write_json_file(out_dir, &format!("{prefix}-clang-dry-run.json"), &value)
}

#[cfg(all(test, feature = "clang-frontend"))]
mod clang_dry_run_artifact_tests {
    use std::{
        env, fs,
        path::PathBuf,
        time::{SystemTime, UNIX_EPOCH},
    };

    use serde_json::Value;

    use super::*;
    use crate::BuildProfile;

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
}
