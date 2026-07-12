use std::{
    error::Error,
    fs,
    path::{Path, PathBuf},
};

use serde_json::json;

use crate::artifact_io::{translation_events_jsonl, write_json_file, write_text_file};
#[cfg(feature = "clang-frontend")]
use crate::clang_frontend;
#[cfg(feature = "clang-lowering-report")]
use crate::typed_ir;
#[cfg(feature = "clang-lowering-report")]
use crate::TranslationSource;
use crate::{
    translate_slice, ArtifactManifest, SliceSpec, TranslationError, TranslationPlan,
    TranslationResult,
};

pub(crate) fn write_core_translation_artifacts(
    spec: &SliceSpec,
    result: &TranslationResult,
    out_dir: &Path,
    prefix: &str,
    status: &str,
) -> Result<Vec<PathBuf>, Box<dyn Error>> {
    // Pointer analysis only runs after translation clears the parse,
    // control-flow, and syntax gates, so an empty node set is evidence of
    // "no pointer surface" only when translation finished without blocking
    // errors; a blocked translation must not claim any pointer conclusion.
    let pointer_graph_status = if !result.pointer_graph.nodes.is_empty() {
        "recorded"
    } else if result.errors.is_empty() {
        "not_applicable"
    } else {
        "not_evaluated"
    };
    let mut translation_plan = json!({
        "schema_version": 1,
        "target_id": spec.target_id,
        "slice_id": spec.slice_id,
        "source_commit": spec.source_commit,
        "fixture_hash": spec.fixture_hash,
        "status": status,
        "translation_source": &result.translation_source,
        "plan": &result.plan,
        "errors": &result.errors,
    });
    bind_translation_carrier(&mut translation_plan, spec);

    Ok(vec![
        write_json_file(
            out_dir,
            &format!("{prefix}-auto-translation-plan.json"),
            &translation_plan,
        )?,
        write_text_file(
            out_dir,
            &format!("{prefix}-auto-translation-events.jsonl"),
            &translation_events_jsonl(spec, result)?,
        )?,
        write_json_file(
            out_dir,
            &format!("{prefix}-type-map.json"),
            &json!({
                "schema_version": 1,
                "target_id": spec.target_id,
                "slice_id": spec.slice_id,
                "source_commit": spec.source_commit,
                "status": if result.type_map.uncertainties.is_empty() { "recorded" } else { "uncertain" },
                "type_map": &result.type_map,
            }),
        )?,
        write_json_file(
            out_dir,
            &format!("{prefix}-cfg.json"),
            &json!({
                "schema_version": 1,
                "target_id": spec.target_id,
                "slice_id": spec.slice_id,
                "source_commit": spec.source_commit,
                "status": "recorded",
                "cfg": &result.cfg,
            }),
        )?,
        write_json_file(
            out_dir,
            &format!("{prefix}-pointer-graph.json"),
            &json!({
                "schema_version": 1,
                "target_id": spec.target_id,
                "slice_id": spec.slice_id,
                "source_commit": spec.source_commit,
                "status": pointer_graph_status,
                "pointer_graph": &result.pointer_graph,
                "not_applicable_reason": if pointer_graph_status == "not_applicable" { Some("slice has no pointer surface") } else { None },
                "not_evaluated_reason": if pointer_graph_status == "not_evaluated" { Some("pointer analysis did not run (translation blocked)") } else { None },
            }),
        )?,
        write_json_file(
            out_dir,
            &format!("{prefix}-ai-candidate-manifest.json"),
            &json!({
                "schema_version": 1,
                "target_id": spec.target_id,
                "slice_id": spec.slice_id,
                "status": "not_used",
                "ai_required": false,
                "candidates": [],
                "boundary": "Local rule-based translator path; AI output is not evidence.",
            }),
        )?,
        write_json_file(
            out_dir,
            &format!("{prefix}-blocked-repairs.json"),
            &json!({
                "schema_version": 1,
                "target_id": spec.target_id,
                "slice_id": spec.slice_id,
                "status": if result.errors.is_empty() { "none" } else { "blocked" },
                "blocked": result.errors.iter().map(|error| {
                    json!({
                        "kind": error.kind,
                        "reason": error.message,
                        "source_span": error.source_span,
                    })
                }).collect::<Vec<_>>(),
            }),
        )?,
        write_text_file(
            out_dir,
            &format!("{prefix}-rust-draft.rs"),
            &result.rust_code,
        )?,
    ])
}

fn bind_translation_carrier(value: &mut serde_json::Value, spec: &SliceSpec) {
    let Some(translation_carrier) = &spec.translation_carrier else {
        return;
    };
    let Some(object) = value.as_object_mut() else {
        return;
    };
    object.insert(
        "translation_carrier".to_string(),
        translation_carrier.clone(),
    );
}

pub fn write_translation_artifacts(
    spec: &SliceSpec,
    out_dir: &Path,
) -> Result<ArtifactManifest, Box<dyn Error>> {
    fs::create_dir_all(out_dir)?;
    #[cfg(feature = "clang-lowering-report")]
    let clang_lowered_attempt =
        crate::clang_lowered_translation::try_clang_lowered_translation_attempt(spec);
    #[cfg(feature = "clang-lowering-report")]
    let result = translate_slice_with_optional_clang_lowered_ir(
        spec,
        clang_lowered_attempt.as_ref(),
    );
    #[cfg(not(feature = "clang-lowering-report"))]
    let result = translate_slice_with_retired_legacy_direct_path(spec);
    let prefix = format!("l3-{}", spec.slice_id);
    let status = if result.errors.is_empty() {
        "generated"
    } else {
        "blocked"
    };

    let artifacts = write_core_translation_artifacts(spec, &result, out_dir, &prefix, status)?;
    #[cfg(feature = "clang-frontend")]
    let artifacts = {
        let mut artifacts = artifacts;
        artifacts.push(write_clang_dry_run_artifact(spec, out_dir, &prefix)?);
        artifacts
    };
    #[cfg(feature = "clang-lowering-report")]
    let artifacts = {
        let mut artifacts = artifacts;
        artifacts.push(write_clang_lowering_report_artifact(
            spec,
            out_dir,
            &prefix,
            clang_lowered_attempt
                .as_ref()
                .map(|attempt| &attempt.report),
        )?);
        artifacts
    };

    Ok(ArtifactManifest {
        target_id: spec.target_id.clone(),
        slice_id: spec.slice_id.clone(),
        status: status.to_string(),
        artifact_paths: artifacts
            .into_iter()
            .map(|path| portable_artifact_path(&path))
            .collect(),
    })
}

fn portable_artifact_path(path: &Path) -> String {
    if path.is_absolute() {
        if let Some(relative) = repo_relative_path(path) {
            return relative;
        }
    }
    path_to_manifest_string(path)
}

fn repo_relative_path(path: &Path) -> Option<String> {
    if let Ok(current_dir) = std::env::current_dir() {
        if let Ok(relative) = path.strip_prefix(&current_dir) {
            return Some(path_to_manifest_string(relative));
        }
    }
    if let Some(manifest_dir) = option_env!("CARGO_MANIFEST_DIR") {
        let crate_dir = Path::new(manifest_dir);
        if let Some(repo_root) = crate_dir.parent().and_then(Path::parent) {
            if let Ok(relative) = path.strip_prefix(repo_root) {
                return Some(path_to_manifest_string(relative));
            }
        }
    }
    None
}

fn path_to_manifest_string(path: &Path) -> String {
    path.to_string_lossy().replace('\\', "/")
}

#[cfg(not(feature = "clang-lowering-report"))]
fn translate_slice_with_retired_legacy_direct_path(spec: &SliceSpec) -> TranslationResult {
    let mut result = translate_slice(spec);
    result.errors.push(TranslationError {
        kind: "legacy_direct_retired".to_string(),
        message: "legacy string translator direct artifact generation is retained only as diagnostic compatibility evidence; it no longer produces a generated candidate".to_string(),
        source_span: None,
    });
    result
}
