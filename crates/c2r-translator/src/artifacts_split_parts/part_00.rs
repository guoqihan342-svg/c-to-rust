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
use crate::{translate_slice, ArtifactManifest, SliceSpec, TranslationError, TranslationResult};

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
    Ok(vec![
        write_json_file(
            out_dir,
            &format!("{prefix}-auto-translation-plan.json"),
            &json!({
                "schema_version": 1,
                "target_id": spec.target_id,
                "slice_id": spec.slice_id,
                "source_commit": spec.source_commit,
                "fixture_hash": spec.fixture_hash,
                "status": status,
                "translation_source": &result.translation_source,
                "plan": &result.plan,
                "errors": &result.errors,
            }),
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
        clang_lowered_attempt
            .as_ref()
            .and_then(|attempt| attempt.result.clone()),
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

#[cfg(feature = "clang-lowering-report")]
fn translate_slice_with_optional_clang_lowered_ir(
    spec: &SliceSpec,
    clang_lowered_result: Option<TranslationResult>,
) -> TranslationResult {
    if let Some(result) = clang_lowered_result {
        return result;
    }
    let mut result = translate_slice(spec);
    result.translation_source = TranslationSource::fallback(
        "legacy-string-translator",
        "clang-lowered-typed-ir",
        "clang_lowered_typed_ir_unavailable",
    );
    result.errors.push(TranslationError {
        kind: "legacy_fallback_retired".to_string(),
        message: "legacy string translator fallback is retained only as diagnostic compatibility evidence when clang-lowered typed IR is unavailable; it no longer produces a generated candidate".to_string(),
        source_span: None,
    });
    result
}

#[cfg(feature = "clang-frontend")]
pub(crate) fn write_clang_dry_run_artifact(
    spec: &SliceSpec,
    out_dir: &Path,
    prefix: &str,
) -> Result<PathBuf, Box<dyn Error>> {
    let value = match clang_frontend::ClangParseSpec::from_slice_spec(spec) {
        Ok(parse_spec) => {
            let dry_run = parse_spec.dry_run();
            json!({
                "schema_version": 1,
                "artifact_kind": "clang-dry-run",
                "target_id": spec.target_id,
                "slice_id": spec.slice_id,
                "source_commit": spec.source_commit,
                "frontend": "clang",
                "active_frontend": dry_run.active_frontend.clone(),
                "claim_boundary": dry_run.claim_boundary.clone(),
                "status": "diagnostic_only",
                "dry_run": dry_run,
                "metadata": {
                    "source_file_hashes": parse_spec.source_file_hashes,
                    "function_source_span": parse_spec.function_source_span,
                },
                "errors": [],
            })
        }
        Err(error) => json!({
            "schema_version": 1,
            "artifact_kind": "clang-dry-run",
            "target_id": spec.target_id,
            "slice_id": spec.slice_id,
            "source_commit": spec.source_commit,
            "frontend": "clang",
            "active_frontend": clang_frontend::clang_ast_dump_active_frontend(),
            "claim_boundary": clang_frontend::diagnostic_claim_boundary(),
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

#[cfg(feature = "clang-lowering-report")]
pub(crate) fn write_clang_lowering_report_artifact(
    spec: &SliceSpec,
    out_dir: &Path,
    prefix: &str,
    reused_report: Option<&clang_frontend::ClangLoweringReport>,
) -> Result<PathBuf, Box<dyn Error>> {
    let mut value = match clang_frontend::ClangParseSpec::from_slice_spec(spec) {
        Ok(parse_spec) => {
            let source_file = parse_spec.source_root.join(&parse_spec.source_file);
            let owned_report;
            let report = if let Some(report) = reused_report {
                report
            } else {
                let environment = crate::clang_lowered_translation::collect_environment_lossy();
                owned_report =
                    crate::clang_lowered_translation::lower_parse_spec_report_with_optional_ast_fixture(
                    &environment,
                    &parse_spec,
                    spec.build_profile.clang_ast_fixture.as_deref(),
                );
                &owned_report
            };
            let emit_policy = emit_policy_from_spec(spec);
            let typed_ir_candidate = typed_ir_candidate_evidence(
                report.function_ir.as_ref(),
                &report.globals,
                emit_policy,
            );
            json!({
                "schema_version": 1,
                "artifact_kind": "clang-lowering-report",
                "target_id": spec.target_id,
                "slice_id": spec.slice_id,
                "source_commit": spec.source_commit,
                "fixture_hash": spec.fixture_hash,
                "frontend": "clang",
                "status": report.status,
                "source_file": source_file.to_string_lossy().replace('\\', "/"),
                "function_name": parse_spec.function_name,
                "claim_boundary": {
                    "role": "diagnostic_only",
                    "affects_manifest_status": false,
                    "affects_semantic_pass": false,
                    "authoritative_evidence": false,
                },
                "diagnostics": report.diagnostics,
                "errors": report.errors,
                "typed_ir_candidate": typed_ir_candidate,
                "lowering_report": report,
                "metadata": {
                    "source_root": parse_spec.source_root,
                    "logical_source_file": parse_spec.source_file,
                    "compile_commands": parse_spec.compile_commands,
                    "clang_ast_fixture": spec.build_profile.clang_ast_fixture,
                    "source_file_hashes": parse_spec.source_file_hashes,
                    "function_source_span": parse_spec.function_source_span,
                },
            })
        }
        Err(error) => json!({
            "schema_version": 1,
            "artifact_kind": "clang-lowering-report",
            "target_id": spec.target_id,
            "slice_id": spec.slice_id,
            "source_commit": spec.source_commit,
            "fixture_hash": spec.fixture_hash,
            "frontend": "clang",
            "status": "blocked",
            "source_file": spec.source_file,
            "function_name": spec.function_name,
            "claim_boundary": {
                "role": "diagnostic_only",
                "affects_manifest_status": false,
                "affects_semantic_pass": false,
                "authoritative_evidence": false,
            },
            "diagnostics": [
                error.message,
            ],
            "typed_ir_candidate": {
                "status": "not_available",
                "candidate_route": null,
                "readonly_globals": [],
                "runtime_preconditions": [],
                "rust_draft_generated": false,
                "semantic_pass": false,
                "reason": "clang_parse_spec_error",
            },
            "lowering_report": null,
            "metadata": {
                "source_root": spec.source_root,
                "logical_source_file": spec.source_file,
                "compile_commands": spec.compile_commands,
                "clang_ast_fixture": spec.build_profile.clang_ast_fixture,
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
    sanitize_host_paths_json(&mut value);
    write_json_file(
        out_dir,
        &format!("{prefix}-clang-lowering-report.json"),
        &value,
    )
}

/// Public evidence must only contain repo-relative POSIX paths, but the
/// serialized lowering report captures host details (`clang_path`, synthesized
/// clang arguments, the resolved source root, diagnostics). Every string in
/// the artifact JSON is therefore rewritten before writing: repo-internal
/// paths become repo-relative and any remaining absolute host path collapses
/// to a stable `<host>/<file-name>` placeholder. Only the serialized artifact
/// is sanitized; the in-memory report keeps the real paths it lowered with.
#[cfg(feature = "clang-lowering-report")]
fn sanitize_host_paths_json(value: &mut serde_json::Value) {
    match value {
        serde_json::Value::String(text) => {
            if let Some(sanitized) = sanitize_host_path_text(text) {
                *text = sanitized;
            }
        }
        serde_json::Value::Array(items) => {
            for item in items {
                sanitize_host_paths_json(item);
            }
        }
        serde_json::Value::Object(entries) => {
            for item in entries.values_mut() {
                sanitize_host_paths_json(item);
            }
        }
        _ => {}
    }
}

#[cfg(feature = "clang-lowering-report")]
fn sanitize_host_path_text(text: &str) -> Option<String> {
    let start = absolute_host_path_start(text)?;
    let (prefix, path_text) = text.split_at(start);
    let replacement = repo_relative_path(Path::new(path_text)).unwrap_or_else(|| {
        match path_text
            .rsplit(['/', '\\'])
            .find(|component| !component.is_empty())
        {
            Some(file_name) => format!("<host>/{file_name}"),
            None => "<host>".to_string(),
        }
    });
    Some(format!("{prefix}{replacement}"))
}

/// Returns the byte offset where an absolute host path begins, or `None` for
/// strings that only contain relative (repo-portable) paths. Detected shapes:
/// a leading POSIX root (`/usr/...`), a POSIX root embedded in a clang
/// include/define flag (`-I/usr/include`), and a Windows drive-letter root
/// (`C:/` or `C:\`) at any position. `X://` is skipped so URL schemes survive.
#[cfg(feature = "clang-lowering-report")]
fn absolute_host_path_start(text: &str) -> Option<usize> {
    let bytes = text.as_bytes();
    if bytes.first() == Some(&b'/') {
        return Some(0);
    }
    if (text.starts_with("-I/") || text.starts_with("-D/")) && bytes.len() > 2 {
        return Some(2);
    }
    (0..bytes.len().saturating_sub(2)).find(|&index| {
        bytes[index].is_ascii_alphabetic()
            && bytes[index + 1] == b':'
            && (bytes[index + 2] == b'/' || bytes[index + 2] == b'\\')
            && !(bytes[index + 2] == b'/' && bytes.get(index + 3) == Some(&b'/'))
    })
}
