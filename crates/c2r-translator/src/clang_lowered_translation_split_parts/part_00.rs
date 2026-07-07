use std::{
    collections::BTreeMap,
    fs,
    path::{Path, PathBuf},
};

use crate::{
    clang_frontend, typed_ir, BuildProfile, CallExpressionEvidence, CfgBlock, CfgFunction,
    PointerNode, SliceSpec, TranslationError, TranslationPlan, TranslationResult,
    TranslationSource, TypeMapping, TypeUncertainty,
};

/// Collects process environment variables without panicking on non-Unicode
/// entries; `std::env::vars()` panics on the first non-UTF-8 key or value,
/// which on Linux hosts would crash artifact writing instead of failing closed.
pub(crate) fn collect_environment_lossy() -> BTreeMap<String, String> {
    std::env::vars_os()
        .map(|(key, value)| {
            (
                key.to_string_lossy().into_owned(),
                value.to_string_lossy().into_owned(),
            )
        })
        .collect()
}

pub(crate) struct ClangLoweredTranslationAttempt {
    pub report: clang_frontend::ClangLoweringReport,
    pub result: Option<TranslationResult>,
}

pub(crate) fn try_clang_lowered_translation_attempt(
    spec: &SliceSpec,
) -> Option<ClangLoweredTranslationAttempt> {
    let parse_spec = clang_frontend::ClangParseSpec::from_slice_spec(spec).ok()?;
    let environment = collect_environment_lossy();
    let report = lower_parse_spec_report_with_optional_ast_fixture(
        &environment,
        &parse_spec,
        spec.build_profile.clang_ast_fixture.as_deref(),
    );
    let result = translation_result_from_clang_lowering_report(spec, &report);
    Some(ClangLoweredTranslationAttempt { report, result })
}

fn translation_result_from_clang_lowering_report(
    spec: &SliceSpec,
    report: &clang_frontend::ClangLoweringReport,
) -> Option<TranslationResult> {
    let function_ir = report.function_ir.as_ref()?;
    let rust_code = typed_ir::emit_rust_from_ir_with_globals_and_policy(
        function_ir,
        &report.globals,
        emit_policy_from_spec(spec),
    )
    .ok()?
    .rust;

    let mut result = TranslationResult {
        rust_code,
        translation_source: TranslationSource::selected("clang-lowered-typed-ir"),
        plan: TranslationPlan {
            target_id: spec.target_id.clone(),
            slice_id: spec.slice_id.clone(),
            function_name: spec.function_name.clone(),
            translation_rule_ids: vec!["clang-lowered-typed-ir".to_string()],
            call_expressions: Vec::new(),
            unsupported_node_count: 0,
            unsafe_candidate_count: 0,
        },
        ..TranslationResult::default()
    };
    record_clang_lowered_ir_evidence(spec, function_ir, &mut result);
    Some(result)
}

pub(crate) fn lower_parse_spec_report_with_optional_ast_fixture(
    environment: &BTreeMap<String, String>,
    parse_spec: &clang_frontend::ClangParseSpec,
    ast_fixture: Option<&str>,
) -> clang_frontend::ClangLoweringReport {
    let report =
        clang_frontend::lower_function_from_clang_parse_spec_report(environment, parse_spec);
    if report.function_ir.is_some() || !clang_report_allows_fixture_fallback(&report) {
        return report;
    }
    let Some(ast_fixture) = ast_fixture.map(str::trim).filter(|value| !value.is_empty()) else {
        return report;
    };
    lower_parse_spec_from_ast_fixture_report(environment, parse_spec, ast_fixture, report)
}

fn clang_report_allows_fixture_fallback(report: &clang_frontend::ClangLoweringReport) -> bool {
    report.status == "unavailable"
        && report.errors.iter().any(|error| {
            error.kind == "missing_clang_path" || error.kind == "clang_ast_dump_unavailable"
        })
}

fn lower_parse_spec_from_ast_fixture_report(
    environment: &BTreeMap<String, String>,
    parse_spec: &clang_frontend::ClangParseSpec,
    ast_fixture: &str,
    unavailable_report: clang_frontend::ClangLoweringReport,
) -> clang_frontend::ClangLoweringReport {
    let fixture_path = resolve_ast_fixture_path(ast_fixture);
    let logical_source_file = parse_spec.source_root.join(&parse_spec.source_file);
    let mut diagnostics = unavailable_report.diagnostics.clone();
    diagnostics.push(format!(
        "clang AST JSON fixture replay used after clang AST dump was unavailable: {}",
        normalize_path(&fixture_path)
    ));

    let result = match fs::read_to_string(&fixture_path) {
        Ok(raw_json) => match serde_json::from_str::<serde_json::Value>(&raw_json) {
            Ok(ast) => {
                clang_frontend::lower_function_and_globals_from_clang_ast_json_value_with_target_abi(
                    &ast,
                    &parse_spec.function_name,
                    parse_spec.target_abi.as_ref(),
                )
            }
            Err(error) => Err(clang_frontend::ClangFrontendError {
                kind: "invalid_ast_fixture_json".to_string(),
                message: format!(
                    "failed to parse clang AST JSON fixture {}: {error}",
                    normalize_path(&fixture_path)
                ),
            }),
        },
        Err(error) => Err(clang_frontend::ClangFrontendError {
            kind: "missing_ast_fixture".to_string(),
            message: format!(
                "failed to read clang AST JSON fixture {}: {error}",
                normalize_path(&fixture_path)
            ),
        }),
    };

    match result {
        Ok(lowered) => clang_frontend::ClangLoweringReport {
            status: "lowered".to_string(),
            frontend: "clang_ast_json_fixture".to_string(),
            source_file: Some(normalize_path(&logical_source_file)),
            function_name: parse_spec.function_name.clone(),
            clang_path: None,
            arguments: ast_fixture_arguments(parse_spec, &fixture_path),
            environment: clang_frontend::ClangEnvironment::detect_from_env(environment),
            diagnostics,
            errors: Vec::new(),
            function_ir: Some(lowered.function_ir),
            globals: lowered.globals,
        },
        Err(error) => clang_frontend::ClangLoweringReport {
            status: "blocked".to_string(),
            frontend: "clang_ast_json_fixture".to_string(),
            source_file: Some(normalize_path(&logical_source_file)),
            function_name: parse_spec.function_name.clone(),
            clang_path: None,
            arguments: ast_fixture_arguments(parse_spec, &fixture_path),
            environment: clang_frontend::ClangEnvironment::detect_from_env(environment),
            diagnostics: diagnostics
                .into_iter()
                .chain(std::iter::once(error.message.clone()))
                .collect(),
            errors: vec![error],
            function_ir: None,
            globals: Vec::new(),
        },
    }
}

fn resolve_ast_fixture_path(ast_fixture: &str) -> PathBuf {
    let path = PathBuf::from(ast_fixture);
    if path.is_absolute() || path.exists() {
        return path;
    }
    if let Ok(current_dir) = std::env::current_dir() {
        let candidate = current_dir.join(&path);
        if candidate.exists() {
            return candidate;
        }
    }
    if let Ok(manifest_dir) = std::env::var("CARGO_MANIFEST_DIR") {
        let crate_dir = PathBuf::from(&manifest_dir);
        if let Some(repo_root) = crate_dir.parent().and_then(Path::parent) {
            let candidate = repo_root.join(&path);
            if candidate.exists() {
                return candidate;
            }
        }
    }
    path
}

fn ast_fixture_arguments(
    parse_spec: &clang_frontend::ClangParseSpec,
    fixture_path: &Path,
) -> Vec<String> {
    let mut arguments = parse_spec.clang_arguments();
    arguments.push("--ast-json-fixture".to_string());
    arguments.push(normalize_path(fixture_path));
    arguments.push(parse_spec.source_file.to_string_lossy().replace('\\', "/"));
    arguments
}

fn normalize_path(path: &Path) -> String {
    path.to_string_lossy().replace('\\', "/")
}

pub(crate) fn emit_policy_from_spec(spec: &SliceSpec) -> typed_ir::EmitPolicy {
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

/// Mirrors an already-emitted typed IR function into translator evidence.
///
/// Rust code has already been produced by `typed_ir` before this runs. The job
/// here is to describe the semantic route that was accepted: type mappings,
/// call expressions, coarse CFG shape, pointer boundaries, and rule ids.
fn record_clang_lowered_ir_evidence(
    spec: &SliceSpec,
    function: &typed_ir::IrFunction,
    result: &mut TranslationResult,
) {
    record_ir_type_mapping("return", &function.return_type, &spec.build_profile, result);
    for param in &function.params {
        record_ir_type_mapping(&param.name, &param.ty, &spec.build_profile, result);
    }
    record_ir_decl_type_mappings(&function.body, &spec.build_profile, result);
    record_ir_call_expression_evidence(&function.body, result);
    result.cfg.functions.push(CfgFunction {
        name: function.name.clone(),
        blocks: vec![CfgBlock {
            id: "entry".to_string(),
            statements: function.body.iter().map(ir_statement_label).collect(),
            statement_kinds: ir_statement_kind_labels(&function.body),
            lvalue_kinds: Vec::new(),
            terminator: if function
                .body
                .iter()
                .any(|stmt| matches!(stmt, typed_ir::IrStmt::Return { .. }))
            {
                "return".to_string()
            } else {
                "fallthrough".to_string()
            },
            edges: ir_cfg_edges(&function.body),
        }],
        unsupported_control_flow: Vec::new(),
        structured_control_flow: None,
    });
    emit_ir_pointer_graph(function, result);
    push_rule_once(
        &mut result.plan.translation_rule_ids,
        "clang-lowered-typed-ir",
    );
    if ir_has_byte_cursor_read(function, "buf") {
        for rule in [
            "const-void-byte-slice",
            "byte-cursor-post-increment-read",
            "byte-cursor-loop",
            "structured-while",
            "structured-return-expression",
        ] {
            push_rule_once(&mut result.plan.translation_rule_ids, rule);
        }
    }
}

fn record_ir_decl_type_mappings(
    statements: &[typed_ir::IrStmt],
    profile: &BuildProfile,
    result: &mut TranslationResult,
) {
    for statement in statements {
        match statement {
            typed_ir::IrStmt::Decl { name, ty, .. } => {
                record_ir_type_mapping(name, ty, profile, result);
            }
            typed_ir::IrStmt::If {
                then_body,
                else_body,
                ..
            } => {
                record_ir_decl_type_mappings(then_body, profile, result);
                record_ir_decl_type_mappings(else_body, profile, result);
            }
            typed_ir::IrStmt::While { body, .. } => {
                record_ir_decl_type_mappings(body, profile, result);
            }
            typed_ir::IrStmt::DoWhile { body, .. } => {
                record_ir_decl_type_mappings(body, profile, result);
            }
            typed_ir::IrStmt::For {
                init, step, body, ..
            } => {
                record_ir_decl_type_mappings(init, profile, result);
                record_ir_decl_type_mappings(body, profile, result);
                if let Some(step) = step.as_deref() {
                    record_ir_decl_type_mappings(std::slice::from_ref(step), profile, result);
                }
            }
            _ => {}
        }
    }
}

/// Records direct-call evidence across all statement positions in typed IR.
///
/// The traversal keeps statement context labels because the validation reports
/// need to distinguish calls in initializers, assignments, loop conditions, and
/// returns. It recurses through nested control flow without changing the IR.
fn record_ir_call_expression_evidence(
    statements: &[typed_ir::IrStmt],
    result: &mut TranslationResult,
) {
    for statement in statements {
        match statement {
            typed_ir::IrStmt::Decl {
                init: Some(init), ..
            } => {
                record_ir_call_expression_evidence_for_expr(init, "declaration_initializer", result)
            }
            typed_ir::IrStmt::Decl { init: None, .. } => {}
            typed_ir::IrStmt::Assign { value, .. } => {
                record_ir_call_expression_evidence_for_expr(value, "assignment", result);
            }
            typed_ir::IrStmt::If {
                then_body,
                else_body,
                ..
            } => {
                record_ir_call_expression_evidence(then_body, result);
                record_ir_call_expression_evidence(else_body, result);
            }
            typed_ir::IrStmt::While { body, .. } => {
                record_ir_call_expression_evidence(body, result);
            }
            typed_ir::IrStmt::DoWhile {
                body, condition, ..
            } => {
                record_ir_call_expression_evidence(body, result);
                record_ir_call_expression_evidence_for_expr(
                    condition,
                    "do_while_condition",
                    result,
                );
            }
            typed_ir::IrStmt::For {
                init, step, body, ..
            } => {
                record_ir_call_expression_evidence(init, result);
                record_ir_call_expression_evidence(body, result);
                if let Some(step) = step.as_deref() {
                    record_ir_call_expression_evidence(std::slice::from_ref(step), result);
                }
            }
            typed_ir::IrStmt::Return {
                value: Some(value), ..
            } => record_ir_call_expression_evidence_for_expr(value, "return", result),
            typed_ir::IrStmt::Return { value: None, .. } => {}
            typed_ir::IrStmt::Break { .. } | typed_ir::IrStmt::Continue { .. } => {}
            typed_ir::IrStmt::Expr { expr, .. } => {
                record_ir_call_expression_evidence_for_expr(expr, "expression", result);
            }
            typed_ir::IrStmt::Unsupported { .. } => {}
        }
    }
}

fn record_ir_call_expression_evidence_for_expr(
    expr: &typed_ir::IrExpr,
    statement_context: &str,
    result: &mut TranslationResult,
) {
    match expr {
        typed_ir::IrExpr::Call { callee, args, .. } => {
            let arguments = args.iter().map(ir_expr_source_text).collect::<Vec<_>>();
            let call = CallExpressionEvidence {
                callee: callee.clone(),
                source_expression: format!("{callee}({})", arguments.join(", ")),
                arguments,
                statement_context: statement_context.to_string(),
            };
            result.plan.call_expressions.push(call);
            push_rule_once(
                &mut result.plan.translation_rule_ids,
                "bounded-call-expression",
            );
            for arg in args {
                record_ir_call_expression_evidence_for_expr(arg, statement_context, result);
            }
        }
        typed_ir::IrExpr::Binary { lhs, rhs, .. } => {
            record_ir_call_expression_evidence_for_expr(lhs, statement_context, result);
            record_ir_call_expression_evidence_for_expr(rhs, statement_context, result);
        }
        typed_ir::IrExpr::Unary { operand, .. } => {
            record_ir_call_expression_evidence_for_expr(operand, statement_context, result);
        }
        typed_ir::IrExpr::Conditional {
            condition,
            then_expr,
            else_expr,
            ..
        } => {
            record_ir_call_expression_evidence_for_expr(condition, statement_context, result);
            record_ir_call_expression_evidence_for_expr(then_expr, statement_context, result);
            record_ir_call_expression_evidence_for_expr(else_expr, statement_context, result);
        }
        typed_ir::IrExpr::Cast { expr, .. } => {
            record_ir_call_expression_evidence_for_expr(expr, statement_context, result);
        }
        typed_ir::IrExpr::LValueToRValue { expr, .. } => {
            record_ir_call_expression_evidence_for_expr(expr, statement_context, result);
        }
        typed_ir::IrExpr::ArrayToPointerDecay { expr, .. } => {
            record_ir_call_expression_evidence_for_expr(expr, statement_context, result);
        }
        typed_ir::IrExpr::FunctionToPointerDecay { expr, .. } => {
            record_ir_call_expression_evidence_for_expr(expr, statement_context, result);
        }
        typed_ir::IrExpr::Index { base, index, .. } => {
            record_ir_call_expression_evidence_for_expr(base, statement_context, result);
            record_ir_call_expression_evidence_for_expr(index, statement_context, result);
        }
        typed_ir::IrExpr::Member { base, .. } => {
            record_ir_call_expression_evidence_for_expr(base, statement_context, result);
        }
        typed_ir::IrExpr::ArrayLiteral { elements, .. } => {
            for element in elements {
                record_ir_call_expression_evidence_for_expr(element, statement_context, result);
            }
        }
        typed_ir::IrExpr::IncDec { target, .. } => {
            record_ir_call_expression_evidence_for_expr(target, statement_context, result);
        }
        typed_ir::IrExpr::Deref { ptr, .. } => {
            record_ir_call_expression_evidence_for_expr(ptr, statement_context, result);
        }
        typed_ir::IrExpr::AddrOf { operand, .. } => {
            record_ir_call_expression_evidence_for_expr(operand, statement_context, result);
        }
        typed_ir::IrExpr::LitInt { .. }
        | typed_ir::IrExpr::NullPtr { .. }
        | typed_ir::IrExpr::Var { .. }
        | typed_ir::IrExpr::Unsupported { .. } => {}
    }
}

/// Renders typed IR expressions as source-like text for evidence fields only.
///
/// The output is intentionally diagnostic, not a round-trippable C or Rust
/// emitter. Rust generation remains in `typed_ir`; this helper gives reviewers
/// stable labels for call arguments and pointer graph evidence.
fn ir_expr_source_text(expr: &typed_ir::IrExpr) -> String {
    match expr {
        typed_ir::IrExpr::Var { name, .. } => name.clone(),
        typed_ir::IrExpr::LitInt { spelling, .. } => spelling.clone(),
        typed_ir::IrExpr::NullPtr { .. } => "NULL".to_string(),
        typed_ir::IrExpr::Binary { op, lhs, rhs, .. } => format!(
            "({} {} {})",
            ir_expr_source_text(lhs),
            ir_bin_op_source(op),
            ir_expr_source_text(rhs)
        ),
        typed_ir::IrExpr::Unary { op, operand, .. } => {
            format!("({}{})", ir_un_op_source(op), ir_expr_source_text(operand))
        }
        typed_ir::IrExpr::Conditional {
            condition,
            then_expr,
            else_expr,
            ..
        } => format!(
            "({} ? {} : {})",
            ir_expr_source_text(condition),
            ir_expr_source_text(then_expr),
            ir_expr_source_text(else_expr)
        ),
        typed_ir::IrExpr::Cast { target, expr, .. } => {
            format!("({} as {})", ir_expr_source_text(expr), ir_c_type(target))
        }
        typed_ir::IrExpr::LValueToRValue { expr, .. } => ir_expr_source_text(expr),
        typed_ir::IrExpr::ArrayToPointerDecay { expr, .. } => {
            format!("array_to_pointer_decay({})", ir_expr_source_text(expr))
        }
        typed_ir::IrExpr::FunctionToPointerDecay { expr, .. } => {
            format!("function_to_pointer_decay({})", ir_expr_source_text(expr))
        }
        typed_ir::IrExpr::Index { base, index, .. } => {
            format!(
                "{}[{}]",
                ir_expr_source_text(base),
                ir_expr_source_text(index)
            )
        }
        typed_ir::IrExpr::Member {
            base,
            field,
            is_arrow,
            ..
        } => {
            let op = if *is_arrow { "->" } else { "." };
            format!("{}{}{}", ir_member_base_source_text(base), op, field)
        }
        typed_ir::IrExpr::ArrayLiteral { elements, .. } => format!(
            "[{}]",
            elements
                .iter()
                .map(ir_expr_source_text)
                .collect::<Vec<_>>()
                .join(", ")
        ),
        typed_ir::IrExpr::Call { callee, args, .. } => format!(
            "{callee}({})",
            args.iter()
                .map(ir_expr_source_text)
                .collect::<Vec<_>>()
                .join(", ")
        ),
        typed_ir::IrExpr::IncDec {
            target, op, prefix, ..
        } => {
            let marker = ir_inc_dec_op_source(op);
            let target = ir_expr_source_text(target);
            if *prefix {
                format!("{marker}{target}")
            } else {
                format!("{target}{marker}")
            }
        }
        typed_ir::IrExpr::Deref { ptr, .. } => format!("*{}", ir_expr_source_text(ptr)),
        typed_ir::IrExpr::AddrOf { operand, .. } => format!("&{}", ir_expr_source_text(operand)),
        typed_ir::IrExpr::Unsupported { node, .. } => format!("unsupported({node})"),
    }
}

fn ir_member_base_source_text(base: &typed_ir::IrExpr) -> String {
    let source = ir_expr_source_text(base);
    match base {
        typed_ir::IrExpr::Var { .. }
        | typed_ir::IrExpr::Call { .. }
        | typed_ir::IrExpr::Index { .. }
        | typed_ir::IrExpr::Member { .. } => source,
        _ => format!("({source})"),
    }
}

fn ir_bin_op_source(op: &typed_ir::IrBinOp) -> &'static str {
    match op {
        typed_ir::IrBinOp::Add => "+",
        typed_ir::IrBinOp::Sub => "-",
        typed_ir::IrBinOp::Mul => "*",
        typed_ir::IrBinOp::Div => "/",
        typed_ir::IrBinOp::Mod => "%",
        typed_ir::IrBinOp::BitAnd => "&",
        typed_ir::IrBinOp::BitOr => "|",
        typed_ir::IrBinOp::BitXor => "^",
        typed_ir::IrBinOp::Shl => "<<",
        typed_ir::IrBinOp::Shr => ">>",
        typed_ir::IrBinOp::Eq => "==",
        typed_ir::IrBinOp::Neq => "!=",
        typed_ir::IrBinOp::Lt => "<",
        typed_ir::IrBinOp::Le => "<=",
        typed_ir::IrBinOp::Gt => ">",
        typed_ir::IrBinOp::Ge => ">=",
        typed_ir::IrBinOp::LogAnd => "&&",
        typed_ir::IrBinOp::LogOr => "||",
        typed_ir::IrBinOp::Assign => "=",
        typed_ir::IrBinOp::Comma => ",",
    }
}

fn ir_un_op_source(op: &typed_ir::IrUnOp) -> &'static str {
    match op {
        typed_ir::IrUnOp::Neg => "-",
        typed_ir::IrUnOp::Not => "!",
        typed_ir::IrUnOp::BitNot => "~",
    }
}

fn ir_inc_dec_op_source(op: &typed_ir::IrIncDecOp) -> &'static str {
    match op {
        typed_ir::IrIncDecOp::Inc => "++",
        typed_ir::IrIncDecOp::Dec => "--",
    }
}

fn record_ir_type_mapping(
    symbol: &str,
    ty: &typed_ir::IrType,
    _profile: &BuildProfile,
    result: &mut TranslationResult,
) {
    let c_type = ir_c_type(ty);
    let Some(rust_type) = ir_rust_type(ty) else {
        let reason = format!(
            "clang-lowered typed IR type {} is outside the current evidence mapping subset",
            type_label_for_evidence(ty)
        );
        result.type_map.uncertainties.push(TypeUncertainty {
            symbol: symbol.to_string(),
            c_type,
            reason: reason.clone(),
        });
        result.errors.push(TranslationError {
            kind: "type_uncertainty".to_string(),
            message: format!("{symbol}: {reason}"),
            source_span: Some(type_label_for_evidence(ty)),
        });
        return;
    };

    result.type_map.mappings.push(TypeMapping {
        c_type,
        rust_type,
        symbol: symbol.to_string(),
        reason: "clang-lowered typed IR mapping".to_string(),
    });
}

fn ir_rust_type(ty: &typed_ir::IrType) -> Option<String> {
    match &ty.kind {
        typed_ir::IrTypeKind::Void => Some("()".to_string()),
        typed_ir::IrTypeKind::Integer { signed, width } => {
            if is_size_t_ir_type(ty) {
                return Some("usize".to_string());
            }
            match (*signed, *width) {
                (true, 8) => Some("i8".to_string()),
                (true, 16) => Some("i16".to_string()),
                (true, 32) => Some("i32".to_string()),
                (true, 64) => Some("i64".to_string()),
                (false, 8) => Some("u8".to_string()),
                (false, 16) => Some("u16".to_string()),
                (false, 32) => Some("u32".to_string()),
                (false, 64) => Some("u64".to_string()),
                _ => None,
            }
        }
        typed_ir::IrTypeKind::Pointer { pointee } => match &pointee.kind {
            typed_ir::IrTypeKind::Void => Some(if ty.is_const || pointee.is_const {
                "*const core::ffi::c_void".to_string()
            } else {
                "*mut core::ffi::c_void".to_string()
            }),
            typed_ir::IrTypeKind::Record { name, .. } => Some(if ty.is_const || pointee.is_const {
                format!("&{}", record_type_name_for_evidence(name))
            } else {
                format!("&mut {}", record_type_name_for_evidence(name))
            }),
            _ => ir_rust_type(pointee).map(|inner| {
                if ty.is_const || pointee.is_const {
                    format!("*const {inner}")
                } else {
                    format!("*mut {inner}")
                }
            }),
        },
        typed_ir::IrTypeKind::Array { element, len } => {
            ir_rust_type(element).map(|inner| match len {
                Some(len) => format!("[{inner}; {len}]"),
                None => format!("*const {inner}"),
            })
        }
        typed_ir::IrTypeKind::Record { name, .. } => Some(record_type_name_for_evidence(name)),
        typed_ir::IrTypeKind::Function | typed_ir::IrTypeKind::Unsupported { .. } => None,
    }
}

fn is_size_t_ir_type(ty: &typed_ir::IrType) -> bool {
    let spelled = ty.spelled.trim();
    let canonical = ty.canonical.trim();
    spelled == "size_t" || canonical == "size_t"
}

fn record_type_name_for_evidence(name: &str) -> String {
    let raw = name.trim().strip_prefix("struct ").unwrap_or(name.trim());
    let mut out = String::new();
    let mut uppercase_next = true;
    for ch in raw.chars() {
        if ch == '_' || ch == '-' || ch == ' ' {
            uppercase_next = true;
        } else if uppercase_next {
            out.extend(ch.to_uppercase());
            uppercase_next = false;
        } else {
            out.push(ch);
        }
    }
    if out.is_empty() {
        "Record".to_string()
    } else {
        out
    }
}

fn type_label_for_evidence(ty: &typed_ir::IrType) -> String {
    if !ty.spelled.trim().is_empty() {
        ty.spelled.clone()
    } else if !ty.canonical.trim().is_empty() {
        ty.canonical.clone()
    } else {
        format!("{:?}", ty.kind)
    }
}

fn ir_c_type(ty: &typed_ir::IrType) -> String {
    if !ty.spelled.trim().is_empty() {
        return ty.spelled.clone();
    }
    if !ty.canonical.trim().is_empty() {
        return ty.canonical.clone();
    }
    match &ty.kind {
        typed_ir::IrTypeKind::Void => "void".to_string(),
        typed_ir::IrTypeKind::Integer {
            signed: false,
            width: 8,
        } => "uint8_t".to_string(),
        typed_ir::IrTypeKind::Integer {
            signed: false,
            width: 32,
        } => "uint32_t".to_string(),
        typed_ir::IrTypeKind::Integer {
            signed: false,
            width: 64,
        } => "size_t".to_string(),
        typed_ir::IrTypeKind::Integer {
            signed: true,
            width: 32,
        } => "int".to_string(),
        typed_ir::IrTypeKind::Pointer { pointee } => {
            let pointee_type = ir_c_type(pointee);
            if ty.is_const && !pointee_type.starts_with("const ") {
                format!("const {pointee_type} *")
            } else {
                format!("{pointee_type} *")
            }
        }
        typed_ir::IrTypeKind::Array { element, .. } => format!("{}[]", ir_c_type(element)),
        typed_ir::IrTypeKind::Record { name, .. } => format!("struct {name}"),
        typed_ir::IrTypeKind::Function => "function".to_string(),
        typed_ir::IrTypeKind::Unsupported { reason } => format!("unsupported:{reason}"),
        _ => ty.canonical.clone(),
    }
}

fn ir_statement_label(statement: &typed_ir::IrStmt) -> String {
    match statement {
        typed_ir::IrStmt::Decl { name, .. } => format!("decl {name}"),
        typed_ir::IrStmt::Assign { target, .. } => format!("assign {}", ir_expr_label(target)),
        typed_ir::IrStmt::If { .. } => "if".to_string(),
        typed_ir::IrStmt::While { .. } => "while".to_string(),
        typed_ir::IrStmt::DoWhile { .. } => "do_while".to_string(),
        typed_ir::IrStmt::For { .. } => "for".to_string(),
        typed_ir::IrStmt::Return { .. } => "return".to_string(),
        typed_ir::IrStmt::Break { .. } => "break".to_string(),
        typed_ir::IrStmt::Continue { .. } => "continue".to_string(),
        typed_ir::IrStmt::Expr { expr, .. } => format!("expr {}", ir_expr_label(expr)),
        typed_ir::IrStmt::Unsupported { node, .. } => format!("unsupported {node}"),
    }
}

