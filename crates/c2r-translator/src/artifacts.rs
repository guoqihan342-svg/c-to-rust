#[cfg(feature = "clang-lowering-report")]
use std::collections::BTreeMap;
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
    legacy_translation::translate_slice, ArtifactManifest, SliceSpec, TranslationError,
    TranslationResult,
};

pub(crate) fn write_core_translation_artifacts(
    spec: &SliceSpec,
    result: &TranslationResult,
    out_dir: &Path,
    prefix: &str,
    status: &str,
) -> Result<Vec<PathBuf>, Box<dyn Error>> {
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
                "status": if result.pointer_graph.nodes.is_empty() { "not_applicable" } else { "recorded" },
                "pointer_graph": &result.pointer_graph,
                "not_applicable_reason": if result.pointer_graph.nodes.is_empty() { Some("slice has no pointer surface") } else { None },
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
    let result = translate_slice_with_optional_clang_lowered_ir(spec);
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
            spec, out_dir, &prefix,
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
        if let Ok(current_dir) = std::env::current_dir() {
            if let Ok(relative) = path.strip_prefix(&current_dir) {
                return path_to_manifest_string(relative);
            }
        }
        if let Some(manifest_dir) = option_env!("CARGO_MANIFEST_DIR") {
            let crate_dir = Path::new(manifest_dir);
            if let Some(repo_root) = crate_dir.parent().and_then(Path::parent) {
                if let Ok(relative) = path.strip_prefix(repo_root) {
                    return path_to_manifest_string(relative);
                }
            }
        }
    }
    path_to_manifest_string(path)
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
fn translate_slice_with_optional_clang_lowered_ir(spec: &SliceSpec) -> TranslationResult {
    if let Some(result) =
        crate::clang_lowered_translation::try_translate_slice_with_clang_lowered_ir(spec)
    {
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
) -> Result<PathBuf, Box<dyn Error>> {
    let value = match clang_frontend::ClangParseSpec::from_slice_spec(spec) {
        Ok(parse_spec) => {
            let source_file = parse_spec.source_root.join(&parse_spec.source_file);
            let environment = std::env::vars().collect::<BTreeMap<_, _>>();
            let report =
                crate::clang_lowered_translation::lower_parse_spec_report_with_optional_ast_fixture(
                    &environment,
                    &parse_spec,
                    spec.build_profile.clang_ast_fixture.as_deref(),
                );
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
    write_json_file(
        out_dir,
        &format!("{prefix}-clang-lowering-report.json"),
        &value,
    )
}

#[cfg(feature = "clang-lowering-report")]
fn typed_ir_candidate_evidence(
    function_ir: Option<&typed_ir::IrFunction>,
    globals: &[typed_ir::IrGlobal],
    emit_policy: typed_ir::EmitPolicy,
) -> serde_json::Value {
    let readonly_globals = globals
        .iter()
        .map(readonly_global_summary)
        .collect::<Vec<_>>();
    let Some(function_ir) = function_ir else {
        return json!({
            "status": "not_available",
            "candidate_route": null,
            "readonly_globals": readonly_globals,
            "runtime_preconditions": [],
            "rust_draft_generated": false,
            "semantic_pass": false,
            "reason": "function_ir_missing",
        });
    };

    match typed_ir::emit_rust_from_ir_with_globals_and_policy(function_ir, globals, emit_policy) {
        Ok(emitted) => json!({
            "status": "generated",
            "candidate_route": emitted.route,
            "readonly_globals": readonly_globals,
            "runtime_preconditions": runtime_precondition_summary(function_ir),
            "rust_draft_generated": true,
            "semantic_pass": false,
        }),
        Err(error) => json!({
            "status": "unsupported",
            "candidate_route": error.route,
            "readonly_globals": readonly_globals,
            "runtime_preconditions": [],
            "rust_draft_generated": false,
            "semantic_pass": false,
            "unsupported_reason": error.reason,
        }),
    }
}

#[cfg(feature = "clang-lowering-report")]
fn emit_policy_from_spec(spec: &SliceSpec) -> typed_ir::EmitPolicy {
    let signed_right_shift = if spec
        .c_boundary
        .scalar_arithmetic_contract
        .signed_right_shift
        == "explicit_implementation_defined_contract"
    {
        typed_ir::SignedRightShiftPolicy::ImplementationDefinedArithmetic
    } else {
        typed_ir::SignedRightShiftPolicy::FailClosed
    };
    typed_ir::EmitPolicy {
        signed_right_shift,
        ..Default::default()
    }
}

#[cfg(feature = "clang-lowering-report")]
fn runtime_precondition_summary(function_ir: &typed_ir::IrFunction) -> Vec<serde_json::Value> {
    let mut preconditions = Vec::new();
    collect_stmt_runtime_preconditions(&function_ir.body, &mut preconditions);
    preconditions
}

#[cfg(feature = "clang-lowering-report")]
fn collect_stmt_runtime_preconditions(
    stmts: &[typed_ir::IrStmt],
    preconditions: &mut Vec<serde_json::Value>,
) {
    for stmt in stmts {
        match stmt {
            typed_ir::IrStmt::Decl { init, .. } => {
                if let Some(init) = init {
                    collect_expr_runtime_preconditions(init, preconditions);
                }
            }
            typed_ir::IrStmt::Assign { target, value, .. } => {
                collect_expr_runtime_preconditions(target, preconditions);
                collect_expr_runtime_preconditions(value, preconditions);
            }
            typed_ir::IrStmt::If {
                condition,
                then_body,
                else_body,
                ..
            } => {
                collect_expr_runtime_preconditions(condition, preconditions);
                collect_stmt_runtime_preconditions(then_body, preconditions);
                collect_stmt_runtime_preconditions(else_body, preconditions);
            }
            typed_ir::IrStmt::While {
                condition, body, ..
            } => {
                collect_expr_runtime_preconditions(condition, preconditions);
                collect_stmt_runtime_preconditions(body, preconditions);
            }
            typed_ir::IrStmt::DoWhile {
                body, condition, ..
            } => {
                collect_stmt_runtime_preconditions(body, preconditions);
                collect_expr_runtime_preconditions(condition, preconditions);
            }
            typed_ir::IrStmt::For {
                init,
                condition,
                step,
                body,
                ..
            } => {
                collect_stmt_runtime_preconditions(init, preconditions);
                if let Some(condition) = condition {
                    collect_expr_runtime_preconditions(condition, preconditions);
                }
                if let Some(step) = step {
                    collect_stmt_runtime_preconditions(std::slice::from_ref(step), preconditions);
                }
                collect_stmt_runtime_preconditions(body, preconditions);
            }
            typed_ir::IrStmt::Return { value, .. } => {
                if let Some(value) = value {
                    collect_expr_runtime_preconditions(value, preconditions);
                }
            }
            typed_ir::IrStmt::Expr { expr, .. } => {
                collect_expr_runtime_preconditions(expr, preconditions);
            }
            typed_ir::IrStmt::Break { .. }
            | typed_ir::IrStmt::Continue { .. }
            | typed_ir::IrStmt::Unsupported { .. } => {}
        }
    }
}

#[cfg(feature = "clang-lowering-report")]
fn collect_expr_runtime_preconditions(
    expr: &typed_ir::IrExpr,
    preconditions: &mut Vec<serde_json::Value>,
) {
    match expr {
        typed_ir::IrExpr::Binary {
            op,
            lhs,
            rhs,
            ty,
            source_span,
        } => {
            collect_expr_runtime_preconditions(lhs, preconditions);
            collect_expr_runtime_preconditions(rhs, preconditions);
            collect_binary_runtime_preconditions(op, ty, source_span, preconditions);
        }
        typed_ir::IrExpr::Unary { operand, .. } => {
            collect_expr_runtime_preconditions(operand, preconditions);
        }
        typed_ir::IrExpr::Conditional {
            condition,
            then_expr,
            else_expr,
            ..
        } => {
            collect_expr_runtime_preconditions(condition, preconditions);
            collect_expr_runtime_preconditions(then_expr, preconditions);
            collect_expr_runtime_preconditions(else_expr, preconditions);
        }
        typed_ir::IrExpr::Cast { expr, .. } => {
            collect_expr_runtime_preconditions(expr, preconditions);
        }
        typed_ir::IrExpr::Index { base, index, .. } => {
            collect_expr_runtime_preconditions(base, preconditions);
            collect_expr_runtime_preconditions(index, preconditions);
        }
        typed_ir::IrExpr::ArrayLiteral { elements, .. } => {
            for element in elements {
                collect_expr_runtime_preconditions(element, preconditions);
            }
        }
        typed_ir::IrExpr::Call { args, .. } => {
            for arg in args {
                collect_expr_runtime_preconditions(arg, preconditions);
            }
        }
        typed_ir::IrExpr::Member { base, .. } => {
            collect_expr_runtime_preconditions(base, preconditions);
        }
        typed_ir::IrExpr::IncDec { target, .. } => {
            collect_expr_runtime_preconditions(target, preconditions);
        }
        typed_ir::IrExpr::Deref { ptr, .. } => {
            collect_expr_runtime_preconditions(ptr, preconditions);
        }
        typed_ir::IrExpr::AddrOf { operand, .. } => {
            collect_expr_runtime_preconditions(operand, preconditions);
        }
        typed_ir::IrExpr::LitInt { .. }
        | typed_ir::IrExpr::NullPtr { .. }
        | typed_ir::IrExpr::Var { .. }
        | typed_ir::IrExpr::Unsupported { .. } => {}
    }
}

#[cfg(feature = "clang-lowering-report")]
fn collect_binary_runtime_preconditions(
    op: &typed_ir::IrBinOp,
    ty: &typed_ir::IrType,
    source_span: &Option<typed_ir::SourceSpan>,
    preconditions: &mut Vec<serde_json::Value>,
) {
    if !is_integer_type(ty) {
        return;
    }
    let signed = is_signed_integer_type(ty);
    match op {
        typed_ir::IrBinOp::Add if signed => preconditions.push(runtime_precondition(
            "signed_add_no_overflow",
            "C signed addition must not overflow unless the slice contract declares a wrapping profile",
            op,
            ty,
            source_span,
        )),
        typed_ir::IrBinOp::Sub if signed => preconditions.push(runtime_precondition(
            "signed_sub_no_overflow",
            "C signed subtraction must not overflow unless the slice contract declares a wrapping profile",
            op,
            ty,
            source_span,
        )),
        typed_ir::IrBinOp::Mul if signed => preconditions.push(runtime_precondition(
            "signed_mul_no_overflow",
            "C signed multiplication must not overflow unless the slice contract declares a wrapping profile",
            op,
            ty,
            source_span,
        )),
        typed_ir::IrBinOp::Div => {
            preconditions.push(runtime_precondition(
                "division_divisor_nonzero",
                "C division requires a non-zero divisor",
                op,
                ty,
                source_span,
            ));
            if signed {
                preconditions.push(runtime_precondition(
                    "signed_division_no_overflow",
                    "C signed division must not evaluate MIN / -1 unless the slice contract models that UB boundary",
                    op,
                    ty,
                    source_span,
                ));
            }
        }
        typed_ir::IrBinOp::Mod => {
            preconditions.push(runtime_precondition(
                "modulo_divisor_nonzero",
                "C modulo requires a non-zero divisor",
                op,
                ty,
                source_span,
            ));
            if signed {
                preconditions.push(runtime_precondition(
                    "signed_modulo_no_overflow",
                    "C signed modulo must not evaluate MIN % -1 unless the slice contract models that UB boundary",
                    op,
                    ty,
                    source_span,
                ));
            }
        }
        typed_ir::IrBinOp::Shl | typed_ir::IrBinOp::Shr => {
            preconditions.push(runtime_precondition(
                "shift_count_in_range",
                "C shift count must be nonnegative and smaller than the shifted integer width",
                op,
                ty,
                source_span,
            ));
            if matches!(op, typed_ir::IrBinOp::Shr) && signed {
                preconditions.push(runtime_precondition(
                    "signed_right_shift_implementation_defined",
                    "C signed right shift is implementation-defined and requires an explicit slice/platform contract",
                    op,
                    ty,
                    source_span,
                ));
            }
        }
        _ => {}
    }
}

#[cfg(feature = "clang-lowering-report")]
fn runtime_precondition(
    code: &str,
    detail: &str,
    op: &typed_ir::IrBinOp,
    ty: &typed_ir::IrType,
    source_span: &Option<typed_ir::SourceSpan>,
) -> serde_json::Value {
    json!({
        "code": code,
        "detail": detail,
        "ir_node": format!("IrExpr::Binary.{op:?}"),
        "type": type_summary(ty),
        "source_span": source_span,
    })
}

#[cfg(feature = "clang-lowering-report")]
fn type_summary(ty: &typed_ir::IrType) -> serde_json::Value {
    match &ty.kind {
        typed_ir::IrTypeKind::Integer { signed, width } => json!({
            "spelled": ty.spelled,
            "canonical": ty.canonical,
            "kind": "integer",
            "signed": signed,
            "width": width,
        }),
        _ => json!({
            "spelled": ty.spelled,
            "canonical": ty.canonical,
            "kind": "unsupported",
        }),
    }
}

#[cfg(feature = "clang-lowering-report")]
fn is_integer_type(ty: &typed_ir::IrType) -> bool {
    matches!(ty.kind, typed_ir::IrTypeKind::Integer { .. })
}

#[cfg(feature = "clang-lowering-report")]
fn is_signed_integer_type(ty: &typed_ir::IrType) -> bool {
    matches!(ty.kind, typed_ir::IrTypeKind::Integer { signed: true, .. })
}

#[cfg(feature = "clang-lowering-report")]
fn readonly_global_summary(global: &typed_ir::IrGlobal) -> serde_json::Value {
    let array_len = match &global.ty.kind {
        typed_ir::IrTypeKind::Array { len, .. } => *len,
        _ => None,
    };
    let (init_kind, value_count) = match &global.init {
        typed_ir::IrGlobalInit::Zeroed => ("zeroed", array_len.unwrap_or(0)),
        typed_ir::IrGlobalInit::IntegerArray(values) => ("integer_array", values.len()),
    };
    json!({
        "name": global.name,
        "spelled_type": global.ty.spelled,
        "canonical_type": global.ty.canonical,
        "array_len": array_len,
        "init_kind": init_kind,
        "value_count": value_count,
    })
}

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

#[cfg(all(test, feature = "clang-lowering-report"))]
mod clang_lowering_report_artifact_tests {
    use std::{
        env, fs,
        path::PathBuf,
        time::{SystemTime, UNIX_EPOCH},
    };

    use serde_json::Value;

    use super::*;
    use crate::{
        typed_ir::{
            EmitPolicy, IrBinOp, IrExpr, IrFunction, IrParam, IrStmt, IrType, IrTypeKind,
            SignedRightShiftPolicy,
        },
        BuildProfile,
    };

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

    fn int_type(name: &str, signed: bool, width: u16) -> IrType {
        IrType {
            spelled: name.to_string(),
            canonical: name.to_string(),
            kind: IrTypeKind::Integer { signed, width },
            is_const: false,
            width_bits: Some(width),
            source_span: None,
        }
    }

    fn var(name: &str, ty: &IrType) -> IrExpr {
        IrExpr::Var {
            name: name.to_string(),
            ty: ty.clone(),
            source_span: None,
        }
    }

    fn lit(value: u64, spelling: &str, ty: &IrType) -> IrExpr {
        IrExpr::LitInt {
            value,
            spelling: spelling.to_string(),
            ty: ty.clone(),
            source_span: None,
        }
    }

    fn binary(op: IrBinOp, lhs: IrExpr, rhs: IrExpr, ty: &IrType) -> IrExpr {
        IrExpr::Binary {
            op,
            lhs: Box::new(lhs),
            rhs: Box::new(rhs),
            ty: ty.clone(),
            source_span: None,
        }
    }

    #[test]
    fn typed_ir_candidate_evidence_records_runtime_preconditions() {
        let i32_ty = int_type("int", true, 32);
        let u32_ty = int_type("uint32_t", false, 32);
        let function = IrFunction {
            name: "preconditioned".to_string(),
            return_type: u32_ty.clone(),
            params: vec![
                IrParam {
                    name: "value".to_string(),
                    ty: i32_ty.clone(),
                    source_span: None,
                },
                IrParam {
                    name: "divisor".to_string(),
                    ty: i32_ty.clone(),
                    source_span: None,
                },
                IrParam {
                    name: "bits".to_string(),
                    ty: u32_ty.clone(),
                    source_span: None,
                },
                IrParam {
                    name: "count".to_string(),
                    ty: i32_ty.clone(),
                    source_span: None,
                },
            ],
            body: vec![
                IrStmt::Decl {
                    name: "sum".to_string(),
                    ty: i32_ty.clone(),
                    init: Some(binary(
                        IrBinOp::Add,
                        var("value", &i32_ty),
                        lit(1, "1", &i32_ty),
                        &i32_ty,
                    )),
                    source_span: None,
                },
                IrStmt::Decl {
                    name: "quotient".to_string(),
                    ty: i32_ty.clone(),
                    init: Some(binary(
                        IrBinOp::Div,
                        var("sum", &i32_ty),
                        var("divisor", &i32_ty),
                        &i32_ty,
                    )),
                    source_span: None,
                },
                IrStmt::Decl {
                    name: "remainder".to_string(),
                    ty: i32_ty.clone(),
                    init: Some(binary(
                        IrBinOp::Mod,
                        var("quotient", &i32_ty),
                        var("divisor", &i32_ty),
                        &i32_ty,
                    )),
                    source_span: None,
                },
                IrStmt::Return {
                    value: Some(binary(
                        IrBinOp::Shl,
                        var("bits", &u32_ty),
                        var("count", &i32_ty),
                        &u32_ty,
                    )),
                    source_span: None,
                },
            ],
            source_span: None,
        };

        let evidence = typed_ir_candidate_evidence(Some(&function), &[], EmitPolicy::default());
        let codes = evidence["runtime_preconditions"]
            .as_array()
            .expect("runtime precondition evidence")
            .iter()
            .map(|item| item["code"].as_str().unwrap())
            .collect::<Vec<_>>();

        assert_eq!(evidence["status"], "generated");
        assert!(codes.contains(&"signed_add_no_overflow"));
        assert!(codes.contains(&"division_divisor_nonzero"));
        assert!(codes.contains(&"signed_division_no_overflow"));
        assert!(codes.contains(&"modulo_divisor_nonzero"));
        assert!(codes.contains(&"signed_modulo_no_overflow"));
        assert!(codes.contains(&"shift_count_in_range"));
    }

    #[test]
    fn typed_ir_candidate_evidence_records_signed_right_shift_contract_precondition() {
        let i32_ty = int_type("int", true, 32);
        let function = IrFunction {
            name: "signed_rshift_contract".to_string(),
            return_type: i32_ty.clone(),
            params: vec![
                IrParam {
                    name: "value".to_string(),
                    ty: i32_ty.clone(),
                    source_span: None,
                },
                IrParam {
                    name: "count".to_string(),
                    ty: i32_ty.clone(),
                    source_span: None,
                },
            ],
            body: vec![IrStmt::Return {
                value: Some(binary(
                    IrBinOp::Shr,
                    var("value", &i32_ty),
                    var("count", &i32_ty),
                    &i32_ty,
                )),
                source_span: None,
            }],
            source_span: None,
        };
        let policy = EmitPolicy {
            signed_right_shift: SignedRightShiftPolicy::ImplementationDefinedArithmetic,
            ..Default::default()
        };

        let evidence = typed_ir_candidate_evidence(Some(&function), &[], policy);
        let codes = evidence["runtime_preconditions"]
            .as_array()
            .expect("runtime precondition evidence")
            .iter()
            .map(|item| item["code"].as_str().unwrap())
            .collect::<Vec<_>>();

        assert_eq!(evidence["status"], "generated");
        assert!(codes.contains(&"shift_count_in_range"));
        assert!(codes.contains(&"signed_right_shift_implementation_defined"));
    }

    #[test]
    fn clang_lowering_report_artifact_records_parse_spec_errors() {
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
        let out_dir = unique_out_dir("clang-lowering-report-error");
        fs::create_dir_all(&out_dir).unwrap();

        let path = write_clang_lowering_report_artifact(&spec, &out_dir, "l3-add-one").unwrap();
        let value: Value = serde_json::from_str(&fs::read_to_string(path).unwrap()).unwrap();

        assert_eq!(value["schema_version"], 1);
        assert_eq!(value["artifact_kind"], "clang-lowering-report");
        assert_eq!(value["frontend"], "clang");
        assert_eq!(value["status"], "blocked");
        assert_eq!(value["claim_boundary"]["role"], "diagnostic_only");
        assert_eq!(value["claim_boundary"]["affects_manifest_status"], false);
        assert_eq!(value["claim_boundary"]["affects_semantic_pass"], false);
        assert_eq!(value["typed_ir_candidate"]["status"], "not_available");
        assert_eq!(
            value["typed_ir_candidate"]["runtime_preconditions"]
                .as_array()
                .unwrap()
                .len(),
            0
        );
        assert_eq!(
            value["typed_ir_candidate"]["reason"],
            "clang_parse_spec_error"
        );
        assert_eq!(value["lowering_report"], Value::Null);
        assert_eq!(value["errors"][0]["kind"], "missing_source_root");
    }

    #[test]
    fn clang_lowering_fallback_to_legacy_is_diagnostic_not_generated() {
        let spec = SliceSpec {
            target_id: "demo".to_string(),
            slice_id: "fallback-identity".to_string(),
            source_commit: "1234567".to_string(),
            function_name: "identity".to_string(),
            c_source: "int identity(int value) { return value; }".to_string(),
            fixture_hash: "fixture-sha".to_string(),
            build_profile: profile(),
            ..SliceSpec::default()
        };
        let out_dir = unique_out_dir("clang-lowering-fallback");

        let manifest = write_translation_artifacts(&spec, &out_dir).unwrap();

        assert_eq!(manifest.status, "blocked");
        let plan: Value = serde_json::from_str(
            &fs::read_to_string(out_dir.join("l3-fallback-identity-auto-translation-plan.json"))
                .unwrap(),
        )
        .unwrap();
        assert_eq!(plan["status"], "blocked");
        assert_eq!(
            plan["translation_source"]["selected"],
            "legacy-string-translator"
        );
        assert_eq!(
            plan["translation_source"]["fallback_from"],
            "clang-lowered-typed-ir"
        );
        assert_eq!(
            plan["translation_source"]["fallback_reason"],
            "clang_lowered_typed_ir_unavailable"
        );
        assert_eq!(plan["errors"][0]["kind"], "legacy_fallback_retired");

        let events =
            fs::read_to_string(out_dir.join("l3-fallback-identity-auto-translation-events.jsonl"))
                .unwrap();
        assert!(events.contains("\"event\":\"translation_fallback\""));
        assert!(events.contains("\"selected\":\"legacy-string-translator\""));
        assert!(events.contains("\"fallback_from\":\"clang-lowered-typed-ir\""));
        assert!(!events.contains("\"event\":\"translation_generated\""));
    }
}
