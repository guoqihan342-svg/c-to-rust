#[cfg(feature = "clang-lowering-report")]
fn collect_unary_runtime_preconditions(
    op: &typed_ir::IrUnOp,
    ty: &typed_ir::IrType,
    source_span: &Option<typed_ir::SourceSpan>,
    preconditions: &mut Vec<serde_json::Value>,
) {
    if !is_signed_integer_type(ty) {
        return;
    }
    if matches!(op, typed_ir::IrUnOp::Neg) {
        preconditions.push(unary_runtime_precondition(
            "signed_negation_no_overflow",
            "C signed negation must not evaluate -MIN (C11 6.5) unless the slice contract models that UB boundary",
            op,
            ty,
            source_span,
        ));
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
    runtime_precondition_for_node(
        code,
        detail,
        format!("IrExpr::Binary.{op:?}"),
        ty,
        source_span,
    )
}

#[cfg(feature = "clang-lowering-report")]
fn unary_runtime_precondition(
    code: &str,
    detail: &str,
    op: &typed_ir::IrUnOp,
    ty: &typed_ir::IrType,
    source_span: &Option<typed_ir::SourceSpan>,
) -> serde_json::Value {
    runtime_precondition_for_node(
        code,
        detail,
        format!("IrExpr::Unary.{op:?}"),
        ty,
        source_span,
    )
}

#[cfg(feature = "clang-lowering-report")]
fn runtime_precondition_for_node(
    code: &str,
    detail: &str,
    ir_node: String,
    ty: &typed_ir::IrType,
    source_span: &Option<typed_ir::SourceSpan>,
) -> serde_json::Value {
    json!({
        "code": code,
        "detail": detail,
        "ir_node": ir_node,
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
            EmitPolicy, IrBinOp, IrExpr, IrFunction, IrParam, IrStmt, IrType, IrTypeKind, IrUnOp,
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
    fn sanitize_host_path_text_replaces_absolute_paths_with_stable_placeholders() {
        assert_eq!(
            sanitize_host_path_text("C:\\Program Files\\LLVM\\bin\\clang.exe").as_deref(),
            Some("<host>/clang.exe")
        );
        assert_eq!(
            sanitize_host_path_text("-IC:/src/FlashDB/inc").as_deref(),
            Some("-I<host>/inc")
        );
        assert_eq!(
            sanitize_host_path_text("/usr/bin/clang").as_deref(),
            Some("<host>/clang")
        );
        assert_eq!(
            sanitize_host_path_text("-I/usr/include").as_deref(),
            Some("-I<host>/include")
        );
        assert_eq!(sanitize_host_path_text("src/fdb_utils.c"), None);
        assert_eq!(sanitize_host_path_text("-Xclang"), None);
        assert_eq!(
            sanitize_host_path_text("https://json-schema.org/draft-07/schema#"),
            None
        );
    }

    #[test]
    fn typed_ir_candidate_evidence_records_signed_left_shift_and_negation_preconditions() {
        let i32_ty = int_type("int", true, 32);
        let function = IrFunction {
            name: "signed_shift_negation".to_string(),
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
                    IrBinOp::Add,
                    binary(
                        IrBinOp::Shl,
                        var("value", &i32_ty),
                        var("count", &i32_ty),
                        &i32_ty,
                    ),
                    IrExpr::Unary {
                        op: IrUnOp::Neg,
                        operand: Box::new(var("value", &i32_ty)),
                        ty: i32_ty.clone(),
                        source_span: None,
                    },
                    &i32_ty,
                )),
                source_span: None,
            }],
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
        assert!(codes.contains(&"shift_count_in_range"));
        assert!(codes.contains(&"signed_left_shift_no_overflow"));
        assert!(codes.contains(&"signed_negation_no_overflow"));
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

        let path =
            write_clang_lowering_report_artifact(&spec, &out_dir, "l3-add-one", None).unwrap();
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
