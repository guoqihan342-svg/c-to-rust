//! Low-level artifact file I/O and translation event serialization.
//!
//! This module deliberately does not decide manifest status, route provenance,
//! or semantic acceptance. `artifacts.rs` owns orchestration; this module only
//! preserves the bytes written for reusable leaf artifacts.

use std::{
    error::Error,
    fs,
    path::{Path, PathBuf},
};

use serde_json::json;

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
    if let Some(fallback_from) = &result.translation_source.fallback_from {
        lines.push(serde_json::to_string(&json!({
            "schema_version": 1,
            "target_id": spec.target_id,
            "slice_id": spec.slice_id,
            "event": "translation_fallback",
            "selected": result.translation_source.selected,
            "fallback_from": fallback_from,
            "fallback_reason": result.translation_source.fallback_reason,
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

#[cfg(test)]
mod tests {
    use std::{
        env, fs,
        path::PathBuf,
        time::{SystemTime, UNIX_EPOCH},
    };

    use serde_json::Value;

    use super::*;
    use crate::{TranslationError, TranslationPlan, TranslationSource};

    fn unique_out_dir(name: &str) -> PathBuf {
        let nanos = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        env::temp_dir().join(format!(
            "c2r-artifact-io-{name}-{}-{nanos}",
            std::process::id()
        ))
    }

    fn parse_jsonl(jsonl: &str) -> Vec<Value> {
        jsonl
            .lines()
            .map(|line| serde_json::from_str(line).unwrap())
            .collect()
    }

    #[test]
    fn write_text_file_preserves_text_and_requires_existing_directory() {
        let out_dir = unique_out_dir("text");
        let missing_dir = out_dir.join("missing");

        assert!(write_text_file(&missing_dir, "event.jsonl", "alpha\n").is_err());

        fs::create_dir_all(&out_dir).unwrap();
        let path = write_text_file(&out_dir, "event.jsonl", "alpha\n").unwrap();

        assert_eq!(path, out_dir.join("event.jsonl"));
        assert_eq!(fs::read_to_string(path).unwrap(), "alpha\n");
    }

    #[test]
    fn write_json_file_writes_pretty_json_with_trailing_newline() {
        let out_dir = unique_out_dir("json");
        fs::create_dir_all(&out_dir).unwrap();

        let path = write_json_file(
            &out_dir,
            "manifest.json",
            &serde_json::json!({
                "schema_version": 1,
                "status": "recorded",
            }),
        )
        .unwrap();

        let text = fs::read_to_string(path).unwrap();
        assert!(text.contains("\n  \"schema_version\": 1,"));
        assert!(text.ends_with('\n'));
        let value: Value = serde_json::from_str(&text).unwrap();
        assert_eq!(value["status"], "recorded");
    }

    #[test]
    fn translation_events_jsonl_preserves_blocked_event_contract() {
        let spec = SliceSpec {
            target_id: "demo".to_string(),
            slice_id: "unsupported".to_string(),
            source_commit: "1234567".to_string(),
            fixture_hash: "fixture-sha".to_string(),
            ..SliceSpec::default()
        };
        let mut result = TranslationResult::default();
        result.errors.push(TranslationError {
            kind: "unsupported_syntax".to_string(),
            message: "switch is not supported".to_string(),
            source_span: Some("switch (value)".to_string()),
        });

        let jsonl = translation_events_jsonl(&spec, &result).unwrap();
        let events = parse_jsonl(&jsonl);

        assert!(jsonl.ends_with('\n'));
        assert_eq!(events.len(), 2);
        assert_eq!(events[0]["event"], "translation_started");
        assert_eq!(events[0]["target_id"], "demo");
        assert_eq!(events[0]["slice_id"], "unsupported");
        assert_eq!(events[0]["source_commit"], "1234567");
        assert_eq!(events[0]["fixture_hash"], "fixture-sha");
        assert_eq!(events[1]["event"], "translation_blocked");
        assert_eq!(events[1]["kind"], "unsupported_syntax");
        assert_eq!(events[1]["source_span"], "switch (value)");
        assert!(!jsonl.contains("translation_generated"));
    }

    #[test]
    fn translation_events_jsonl_preserves_fallback_then_generated_order() {
        let spec = SliceSpec {
            target_id: "demo".to_string(),
            slice_id: "fallback".to_string(),
            source_commit: "1234567".to_string(),
            fixture_hash: "fixture-sha".to_string(),
            ..SliceSpec::default()
        };
        let result = TranslationResult {
            plan: TranslationPlan {
                translation_rule_ids: vec!["scalar-return".to_string()],
                ..TranslationPlan::default()
            },
            translation_source: TranslationSource::fallback(
                "legacy-string-translator",
                "clang-lowered-typed-ir",
                "clang_lowered_typed_ir_unavailable",
            ),
            ..TranslationResult::default()
        };

        let jsonl = translation_events_jsonl(&spec, &result).unwrap();
        let events = parse_jsonl(&jsonl);

        assert_eq!(events.len(), 3);
        assert_eq!(events[0]["event"], "translation_started");
        assert_eq!(events[1]["event"], "translation_fallback");
        assert_eq!(events[1]["selected"], "legacy-string-translator");
        assert_eq!(events[1]["fallback_from"], "clang-lowered-typed-ir");
        assert_eq!(
            events[1]["fallback_reason"],
            "clang_lowered_typed_ir_unavailable"
        );
        assert_eq!(events[2]["event"], "translation_generated");
        assert_eq!(events[2]["translation_rule_ids"][0], "scalar-return");
    }
}
