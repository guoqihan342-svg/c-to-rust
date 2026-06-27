use std::collections::BTreeMap;

use crate::{
    clang_frontend, record_type_mapping, typed_ir, BuildProfile, CallExpressionEvidence, CfgBlock,
    CfgFunction, PointerNode, SliceSpec, TranslationPlan, TranslationResult,
};

pub(crate) fn try_translate_slice_with_clang_lowered_ir(
    spec: &SliceSpec,
) -> Option<TranslationResult> {
    let parse_spec = clang_frontend::ClangParseSpec::from_slice_spec(spec).ok()?;
    let environment = std::env::vars().collect::<BTreeMap<_, _>>();
    let report =
        clang_frontend::lower_function_from_clang_parse_spec_report(&environment, &parse_spec);
    let function_ir = report.function_ir.as_ref()?;
    let rust_code = typed_ir::emit_rust_from_ir_with_globals(function_ir, &report.globals)
        .ok()?
        .rust;

    let mut result = TranslationResult {
        rust_code,
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
    profile: &BuildProfile,
    result: &mut TranslationResult,
) {
    let c_type = ir_c_type(ty);
    record_type_mapping(symbol, &c_type, profile, result);
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

fn ir_expr_label(expr: &typed_ir::IrExpr) -> String {
    match expr {
        typed_ir::IrExpr::Var { name, .. } => name.clone(),
        typed_ir::IrExpr::LitInt { spelling, .. } => spelling.clone(),
        typed_ir::IrExpr::NullPtr { .. } => "null_ptr".to_string(),
        typed_ir::IrExpr::Binary { op, .. } => format!("{op:?}"),
        typed_ir::IrExpr::Unary { op, .. } => format!("{op:?}"),
        typed_ir::IrExpr::Conditional { .. } => "conditional".to_string(),
        typed_ir::IrExpr::Cast { .. } => "cast".to_string(),
        typed_ir::IrExpr::Index { .. } => "index".to_string(),
        typed_ir::IrExpr::Member { field, .. } => format!("member {field}"),
        typed_ir::IrExpr::ArrayLiteral { .. } => "array_literal".to_string(),
        typed_ir::IrExpr::Call { callee, .. } => format!("call {callee}"),
        typed_ir::IrExpr::IncDec { op, prefix, .. } => format!("{op:?} prefix={prefix}"),
        typed_ir::IrExpr::Deref { .. } => "deref".to_string(),
        typed_ir::IrExpr::AddrOf { .. } => "addr_of".to_string(),
        typed_ir::IrExpr::Unsupported { node, .. } => format!("unsupported {node}"),
    }
}

fn ir_statement_kind_labels(statements: &[typed_ir::IrStmt]) -> Vec<String> {
    let mut labels = Vec::new();
    for statement in statements {
        push_unique(
            &mut labels,
            match statement {
                typed_ir::IrStmt::Decl { .. } => "primitive_declaration",
                typed_ir::IrStmt::Assign { .. } => "assignment",
                typed_ir::IrStmt::If { .. } => "if",
                typed_ir::IrStmt::While { .. } => "while",
                typed_ir::IrStmt::DoWhile { .. } => "do_while",
                typed_ir::IrStmt::For { .. } => "for",
                typed_ir::IrStmt::Return { .. } => "return",
                typed_ir::IrStmt::Break { .. } => "break",
                typed_ir::IrStmt::Continue { .. } => "continue",
                typed_ir::IrStmt::Expr { .. } => "expression",
                typed_ir::IrStmt::Unsupported { .. } => "unsupported",
            },
        );
    }
    labels
}

fn ir_cfg_edges(statements: &[typed_ir::IrStmt]) -> Vec<String> {
    statements
        .iter()
        .enumerate()
        .filter_map(|(index, statement)| match statement {
            typed_ir::IrStmt::If { .. } => Some(format!("entry->if-{index}")),
            typed_ir::IrStmt::While { .. } => Some(format!("entry->while-{index}")),
            typed_ir::IrStmt::DoWhile { .. } => Some(format!("entry->do-while-{index}")),
            typed_ir::IrStmt::For { .. } => Some(format!("entry->for-{index}")),
            typed_ir::IrStmt::Return { .. } => Some(format!("entry->return-{index}")),
            _ => None,
        })
        .collect()
}

fn emit_ir_pointer_graph(function: &typed_ir::IrFunction, result: &mut TranslationResult) {
    for param in &function.params {
        if !matches!(param.ty.kind, typed_ir::IrTypeKind::Pointer { .. }) {
            continue;
        }
        let c_type = ir_c_type(&param.ty);
        let is_const_input = c_type.starts_with("const ") || ir_pointer_is_const(&param.ty);
        let mut boundary_decisions = Vec::new();
        let mut read_effects = Vec::new();
        if ir_has_byte_cursor_read(function, &param.name) {
            boundary_decisions.push("byte_cursor_post_increment_read".to_string());
            read_effects.push("*p++".to_string());
        }
        result.pointer_graph.nodes.push(PointerNode {
            id: param.name.clone(),
            c_type,
            role: if is_const_input {
                "borrowed_input".to_string()
            } else {
                "out_param".to_string()
            },
            rust_boundary: if param.name == "buf" || is_const_input {
                "&[u8]".to_string()
            } else {
                "owned safe report".to_string()
            },
            read_effects,
            write_effects: Vec::new(),
            boundary_decisions,
        });
    }
}

fn ir_has_byte_cursor_read(function: &typed_ir::IrFunction, param_name: &str) -> bool {
    let mut cursor_sources = Vec::new();
    collect_ir_pointer_cursor_sources(&function.body, &mut cursor_sources);
    let mut post_increment_reads = Vec::new();
    collect_ir_post_increment_deref_vars_from_stmts(&function.body, &mut post_increment_reads);

    cursor_sources.iter().any(|(cursor, source)| {
        source == param_name && post_increment_reads.iter().any(|item| item == cursor)
    })
}

fn collect_ir_pointer_cursor_sources(
    statements: &[typed_ir::IrStmt],
    cursor_sources: &mut Vec<(String, String)>,
) {
    for statement in statements {
        match statement {
            typed_ir::IrStmt::Assign { target, value, .. } => {
                if let (Some(cursor), Some(source)) =
                    (ir_simple_var_name(target), ir_cast_source_var_name(value))
                {
                    cursor_sources.push((cursor.to_string(), source.to_string()));
                }
            }
            typed_ir::IrStmt::If {
                then_body,
                else_body,
                ..
            } => {
                collect_ir_pointer_cursor_sources(then_body, cursor_sources);
                collect_ir_pointer_cursor_sources(else_body, cursor_sources);
            }
            typed_ir::IrStmt::While { body, .. } => {
                collect_ir_pointer_cursor_sources(body, cursor_sources);
            }
            typed_ir::IrStmt::DoWhile { body, .. } => {
                collect_ir_pointer_cursor_sources(body, cursor_sources);
            }
            typed_ir::IrStmt::For {
                init, step, body, ..
            } => {
                collect_ir_pointer_cursor_sources(init, cursor_sources);
                collect_ir_pointer_cursor_sources(body, cursor_sources);
                if let Some(step) = step.as_deref() {
                    collect_ir_pointer_cursor_sources(std::slice::from_ref(step), cursor_sources);
                }
            }
            _ => {}
        }
    }
}

fn ir_cast_source_var_name(expr: &typed_ir::IrExpr) -> Option<&str> {
    match expr {
        typed_ir::IrExpr::Cast {
            expr,
            implicit: false,
            ..
        } => ir_simple_var_name(expr),
        _ => None,
    }
}

fn collect_ir_post_increment_deref_vars_from_stmts(
    statements: &[typed_ir::IrStmt],
    vars: &mut Vec<String>,
) {
    for statement in statements {
        match statement {
            typed_ir::IrStmt::Decl { init, .. } => {
                if let Some(init) = init {
                    collect_ir_post_increment_deref_vars_from_expr(init, vars);
                }
            }
            typed_ir::IrStmt::Assign { target, value, .. } => {
                collect_ir_post_increment_deref_vars_from_expr(target, vars);
                collect_ir_post_increment_deref_vars_from_expr(value, vars);
            }
            typed_ir::IrStmt::If {
                condition,
                then_body,
                else_body,
                ..
            } => {
                collect_ir_post_increment_deref_vars_from_expr(condition, vars);
                collect_ir_post_increment_deref_vars_from_stmts(then_body, vars);
                collect_ir_post_increment_deref_vars_from_stmts(else_body, vars);
            }
            typed_ir::IrStmt::While {
                condition, body, ..
            } => {
                collect_ir_post_increment_deref_vars_from_expr(condition, vars);
                collect_ir_post_increment_deref_vars_from_stmts(body, vars);
            }
            typed_ir::IrStmt::DoWhile {
                body, condition, ..
            } => {
                collect_ir_post_increment_deref_vars_from_stmts(body, vars);
                collect_ir_post_increment_deref_vars_from_expr(condition, vars);
            }
            typed_ir::IrStmt::For {
                init,
                condition,
                step,
                body,
                ..
            } => {
                collect_ir_post_increment_deref_vars_from_stmts(init, vars);
                if let Some(condition) = condition {
                    collect_ir_post_increment_deref_vars_from_expr(condition, vars);
                }
                collect_ir_post_increment_deref_vars_from_stmts(body, vars);
                if let Some(step) = step.as_deref() {
                    collect_ir_post_increment_deref_vars_from_stmts(
                        std::slice::from_ref(step),
                        vars,
                    );
                }
            }
            typed_ir::IrStmt::Return { value, .. } => {
                if let Some(value) = value {
                    collect_ir_post_increment_deref_vars_from_expr(value, vars);
                }
            }
            typed_ir::IrStmt::Break { .. } | typed_ir::IrStmt::Continue { .. } => {}
            typed_ir::IrStmt::Expr { expr, .. } => {
                collect_ir_post_increment_deref_vars_from_expr(expr, vars);
            }
            typed_ir::IrStmt::Unsupported { .. } => {}
        }
    }
}

fn collect_ir_post_increment_deref_vars_from_expr(expr: &typed_ir::IrExpr, vars: &mut Vec<String>) {
    match expr {
        typed_ir::IrExpr::Deref { ptr, .. } => {
            if let Some(name) = ir_post_increment_var_name(ptr) {
                push_unique(vars, name);
            }
            collect_ir_post_increment_deref_vars_from_expr(ptr, vars);
        }
        typed_ir::IrExpr::Binary { lhs, rhs, .. } => {
            collect_ir_post_increment_deref_vars_from_expr(lhs, vars);
            collect_ir_post_increment_deref_vars_from_expr(rhs, vars);
        }
        typed_ir::IrExpr::Unary { operand, .. } => {
            collect_ir_post_increment_deref_vars_from_expr(operand, vars);
        }
        typed_ir::IrExpr::Conditional {
            condition,
            then_expr,
            else_expr,
            ..
        } => {
            collect_ir_post_increment_deref_vars_from_expr(condition, vars);
            collect_ir_post_increment_deref_vars_from_expr(then_expr, vars);
            collect_ir_post_increment_deref_vars_from_expr(else_expr, vars);
        }
        typed_ir::IrExpr::Cast { expr, .. } => {
            collect_ir_post_increment_deref_vars_from_expr(expr, vars);
        }
        typed_ir::IrExpr::Index { base, index, .. } => {
            collect_ir_post_increment_deref_vars_from_expr(base, vars);
            collect_ir_post_increment_deref_vars_from_expr(index, vars);
        }
        typed_ir::IrExpr::Member { base, .. } => {
            collect_ir_post_increment_deref_vars_from_expr(base, vars);
        }
        typed_ir::IrExpr::ArrayLiteral { elements, .. } => {
            for element in elements {
                collect_ir_post_increment_deref_vars_from_expr(element, vars);
            }
        }
        typed_ir::IrExpr::Call { args, .. } => {
            for arg in args {
                collect_ir_post_increment_deref_vars_from_expr(arg, vars);
            }
        }
        typed_ir::IrExpr::IncDec { target, .. } => {
            collect_ir_post_increment_deref_vars_from_expr(target, vars);
        }
        typed_ir::IrExpr::AddrOf { operand, .. } => {
            collect_ir_post_increment_deref_vars_from_expr(operand, vars);
        }
        typed_ir::IrExpr::LitInt { .. }
        | typed_ir::IrExpr::NullPtr { .. }
        | typed_ir::IrExpr::Var { .. }
        | typed_ir::IrExpr::Unsupported { .. } => {}
    }
}

fn ir_post_increment_var_name(expr: &typed_ir::IrExpr) -> Option<&str> {
    match expr {
        typed_ir::IrExpr::IncDec {
            target,
            op: typed_ir::IrIncDecOp::Inc,
            prefix: false,
            ..
        } => ir_simple_var_name(target),
        typed_ir::IrExpr::Cast { expr, .. } => ir_post_increment_var_name(expr),
        _ => None,
    }
}

fn ir_simple_var_name(expr: &typed_ir::IrExpr) -> Option<&str> {
    match expr {
        typed_ir::IrExpr::Var { name, .. } => Some(name),
        _ => None,
    }
}

fn ir_pointer_is_const(ty: &typed_ir::IrType) -> bool {
    match &ty.kind {
        typed_ir::IrTypeKind::Pointer { pointee } => ty.is_const || pointee.is_const,
        _ => false,
    }
}

fn push_unique(values: &mut Vec<String>, value: &str) {
    if !values.iter().any(|item| item == value) {
        values.push(value.to_string());
    }
}

fn push_rule_once(rules: &mut Vec<String>, rule: &str) {
    if !rules.iter().any(|existing| existing == rule) {
        rules.push(rule.to_string());
    }
}

#[cfg(all(test, feature = "clang-lowering-report"))]
mod clang_lowered_ir_evidence_tests {
    use super::*;
    use crate::typed_ir::{
        IrBinOp, IrExpr, IrFunction, IrIncDecOp, IrParam, IrStmt, IrType, IrTypeKind, SourceSpan,
    };

    fn test_profile() -> BuildProfile {
        BuildProfile {
            include_paths: Vec::new(),
            defines: Vec::new(),
            target_triple: None,
            abi: None,
            compiler_command_source: "unit-test".to_string(),
            clang_available: true,
        }
    }

    fn unsigned_ty(spelled: &str, canonical: &str, width: u16) -> IrType {
        IrType {
            spelled: spelled.to_string(),
            canonical: canonical.to_string(),
            kind: IrTypeKind::Integer {
                signed: false,
                width,
            },
            is_const: false,
            width_bits: Some(width),
            source_span: None,
        }
    }

    fn signed_ty(spelled: &str, canonical: &str, width: u16) -> IrType {
        IrType {
            spelled: spelled.to_string(),
            canonical: canonical.to_string(),
            kind: IrTypeKind::Integer {
                signed: true,
                width,
            },
            is_const: false,
            width_bits: Some(width),
            source_span: None,
        }
    }

    fn void_ty(is_const: bool) -> IrType {
        IrType {
            spelled: "void".to_string(),
            canonical: "void".to_string(),
            kind: IrTypeKind::Void,
            is_const,
            width_bits: None,
            source_span: None,
        }
    }

    fn pointer_ty(spelled: &str, canonical: &str, pointee: IrType, is_const: bool) -> IrType {
        IrType {
            spelled: spelled.to_string(),
            canonical: canonical.to_string(),
            kind: IrTypeKind::Pointer {
                pointee: Box::new(pointee),
            },
            is_const,
            width_bits: Some(64),
            source_span: None,
        }
    }

    fn record_ty(name: &str) -> IrType {
        IrType {
            spelled: name.to_string(),
            canonical: name.to_string(),
            kind: IrTypeKind::Record {
                name: name.to_string(),
                fields: None,
            },
            is_const: false,
            width_bits: None,
            source_span: None,
        }
    }

    fn param(name: &str, ty: IrType) -> IrParam {
        IrParam {
            name: name.to_string(),
            ty,
            source_span: None,
        }
    }

    fn var(name: &str, ty: IrType) -> IrExpr {
        IrExpr::Var {
            name: name.to_string(),
            ty,
            source_span: None,
        }
    }

    fn call(callee: &str, args: Vec<IrExpr>, ty: IrType) -> IrExpr {
        IrExpr::Call {
            callee: callee.to_string(),
            args,
            ty,
            source_span: None,
        }
    }

    #[test]
    fn clang_lowered_ir_records_direct_call_expression_evidence() {
        let i32_ty = signed_ty("int", "int", 32);
        let function = IrFunction {
            name: "call_expression".to_string(),
            return_type: i32_ty.clone(),
            params: vec![param("value", i32_ty.clone())],
            body: vec![
                IrStmt::Decl {
                    name: "first".to_string(),
                    ty: i32_ty.clone(),
                    init: Some(call(
                        "helper",
                        vec![var("value", i32_ty.clone())],
                        i32_ty.clone(),
                    )),
                    source_span: None,
                },
                IrStmt::Assign {
                    target: var("value", i32_ty.clone()),
                    value: call("helper", vec![var("first", i32_ty.clone())], i32_ty.clone()),
                    source_span: None,
                },
                IrStmt::Return {
                    value: Some(call("helper", vec![var("value", i32_ty.clone())], i32_ty)),
                    source_span: None,
                },
            ],
            source_span: None,
        };
        let spec = SliceSpec {
            target_id: "demo".to_string(),
            slice_id: "call-expression".to_string(),
            source_commit: "1234567".to_string(),
            function_name: "call_expression".to_string(),
            build_profile: test_profile(),
            ..SliceSpec::default()
        };
        let mut result = TranslationResult::default();

        record_clang_lowered_ir_evidence(&spec, &function, &mut result);

        assert_eq!(result.plan.call_expressions.len(), 3);
        assert!(result
            .plan
            .translation_rule_ids
            .contains(&"bounded-call-expression".to_string()));
        assert_eq!(result.plan.call_expressions[0].callee, "helper");
        assert_eq!(result.plan.call_expressions[0].arguments, vec!["value"]);
        assert_eq!(
            result.plan.call_expressions[0].source_expression,
            "helper(value)"
        );
        assert_eq!(
            result.plan.call_expressions[0].statement_context,
            "declaration_initializer"
        );
        assert_eq!(
            result.plan.call_expressions[1].source_expression,
            "helper(first)"
        );
        assert_eq!(
            result.plan.call_expressions[1].statement_context,
            "assignment"
        );
        assert_eq!(result.plan.call_expressions[2].statement_context, "return");
    }

    #[test]
    fn clang_lowered_ir_parenthesizes_complex_member_source_text() {
        let i32_ty = signed_ty("int", "int", 32);
        let ptr_ty = pointer_ty(
            "struct point *",
            "struct point *",
            record_ty("point"),
            false,
        );
        let member = IrExpr::Member {
            base: Box::new(IrExpr::Deref {
                ptr: Box::new(var("p", ptr_ty)),
                ty: record_ty("point"),
                source_span: None,
            }),
            field: "x".to_string(),
            ty: i32_ty,
            is_arrow: false,
            source_span: None,
        };

        assert_eq!(ir_expr_source_text(&member), "(*p).x");
    }

    #[test]
    fn clang_lowered_ir_records_call_inside_member_base() {
        let i32_ty = signed_ty("int", "int", 32);
        let point_ty = record_ty("point");
        let function = IrFunction {
            name: "member_call".to_string(),
            return_type: i32_ty.clone(),
            params: vec![param("value", i32_ty.clone())],
            body: vec![IrStmt::Return {
                value: Some(call(
                    "helper",
                    vec![IrExpr::Member {
                        base: Box::new(call("obj_factory", Vec::new(), point_ty)),
                        field: "x".to_string(),
                        ty: i32_ty.clone(),
                        is_arrow: false,
                        source_span: None,
                    }],
                    i32_ty,
                )),
                source_span: None,
            }],
            source_span: None,
        };
        let spec = SliceSpec {
            target_id: "demo".to_string(),
            slice_id: "member-call".to_string(),
            source_commit: "1234567".to_string(),
            function_name: "member_call".to_string(),
            build_profile: test_profile(),
            ..SliceSpec::default()
        };
        let mut result = TranslationResult::default();

        record_clang_lowered_ir_evidence(&spec, &function, &mut result);

        assert_eq!(result.plan.call_expressions.len(), 2);
        assert_eq!(result.plan.call_expressions[0].callee, "helper");
        assert_eq!(
            result.plan.call_expressions[0].source_expression,
            "helper(obj_factory().x)"
        );
        assert_eq!(result.plan.call_expressions[1].callee, "obj_factory");
        assert_eq!(
            result.plan.call_expressions[1].source_expression,
            "obj_factory()"
        );
    }

    #[test]
    fn clang_lowered_ir_preserves_repeated_direct_call_sites_in_same_context() {
        let i32_ty = signed_ty("int", "int", 32);
        let function = IrFunction {
            name: "repeat_call".to_string(),
            return_type: i32_ty.clone(),
            params: vec![param("value", i32_ty.clone())],
            body: vec![
                IrStmt::Assign {
                    target: var("value", i32_ty.clone()),
                    value: call("helper", vec![var("value", i32_ty.clone())], i32_ty.clone()),
                    source_span: None,
                },
                IrStmt::Assign {
                    target: var("value", i32_ty.clone()),
                    value: call("helper", vec![var("value", i32_ty.clone())], i32_ty.clone()),
                    source_span: None,
                },
                IrStmt::Return {
                    value: Some(var("value", i32_ty)),
                    source_span: None,
                },
            ],
            source_span: None,
        };
        let spec = SliceSpec {
            target_id: "demo".to_string(),
            slice_id: "repeat-call".to_string(),
            source_commit: "1234567".to_string(),
            function_name: "repeat_call".to_string(),
            build_profile: test_profile(),
            ..SliceSpec::default()
        };
        let mut result = TranslationResult::default();

        record_clang_lowered_ir_evidence(&spec, &function, &mut result);

        assert_eq!(result.plan.call_expressions.len(), 2);
        assert!(result
            .plan
            .call_expressions
            .iter()
            .all(|call| call.source_expression == "helper(value)"));
        assert!(result
            .plan
            .call_expressions
            .iter()
            .all(|call| call.statement_context == "assignment"));
    }

    #[test]
    fn clang_lowered_ir_does_not_record_condition_call_as_success_evidence() {
        let i32_ty = signed_ty("int", "int", 32);
        let function = IrFunction {
            name: "condition_call".to_string(),
            return_type: i32_ty.clone(),
            params: vec![param("value", i32_ty.clone())],
            body: vec![
                IrStmt::If {
                    condition: call("helper", vec![var("value", i32_ty.clone())], i32_ty.clone()),
                    then_body: vec![IrStmt::Return {
                        value: Some(var("value", i32_ty.clone())),
                        source_span: None,
                    }],
                    else_body: Vec::new(),
                    source_span: None,
                },
                IrStmt::Return {
                    value: Some(var("value", i32_ty)),
                    source_span: None,
                },
            ],
            source_span: None,
        };
        let spec = SliceSpec {
            target_id: "demo".to_string(),
            slice_id: "condition-call".to_string(),
            source_commit: "1234567".to_string(),
            function_name: "condition_call".to_string(),
            build_profile: test_profile(),
            ..SliceSpec::default()
        };
        let mut result = TranslationResult::default();

        record_clang_lowered_ir_evidence(&spec, &function, &mut result);

        assert!(result.plan.call_expressions.is_empty());
        assert!(!result
            .plan
            .translation_rule_ids
            .contains(&"bounded-call-expression".to_string()));
    }

    #[test]
    fn clang_lowered_ir_records_for_statement_evidence_recursively() {
        let i32_ty = signed_ty("int", "int", 32);
        let function = IrFunction {
            name: "for_evidence".to_string(),
            return_type: i32_ty.clone(),
            params: vec![param("limit", i32_ty.clone())],
            body: vec![
                IrStmt::Decl {
                    name: "total".to_string(),
                    ty: i32_ty.clone(),
                    init: Some(var("limit", i32_ty.clone())),
                    source_span: None,
                },
                IrStmt::For {
                    init: vec![IrStmt::Decl {
                        name: "i".to_string(),
                        ty: i32_ty.clone(),
                        init: Some(var("limit", i32_ty.clone())),
                        source_span: None,
                    }],
                    condition: Some(IrExpr::Binary {
                        op: IrBinOp::Lt,
                        lhs: Box::new(var("i", i32_ty.clone())),
                        rhs: Box::new(var("limit", i32_ty.clone())),
                        ty: i32_ty.clone(),
                        source_span: None,
                    }),
                    step: Some(Box::new(IrStmt::Assign {
                        target: var("i", i32_ty.clone()),
                        value: call(
                            "step_helper",
                            vec![var("i", i32_ty.clone())],
                            i32_ty.clone(),
                        ),
                        source_span: None,
                    })),
                    body: vec![IrStmt::Decl {
                        name: "next".to_string(),
                        ty: i32_ty.clone(),
                        init: Some(call(
                            "body_helper",
                            vec![var("total", i32_ty.clone())],
                            i32_ty.clone(),
                        )),
                        source_span: None,
                    }],
                    source_span: None,
                },
                IrStmt::Return {
                    value: Some(var("total", i32_ty.clone())),
                    source_span: None,
                },
            ],
            source_span: None,
        };
        let spec = SliceSpec {
            target_id: "demo".to_string(),
            slice_id: "for-evidence".to_string(),
            source_commit: "1234567".to_string(),
            function_name: "for_evidence".to_string(),
            build_profile: test_profile(),
            ..SliceSpec::default()
        };
        let mut result = TranslationResult::default();

        record_clang_lowered_ir_evidence(&spec, &function, &mut result);

        let block = &result.cfg.functions[0].blocks[0];
        assert!(block.statement_kinds.contains(&"for".to_string()));
        assert!(block.edges.contains(&"entry->for-1".to_string()));
        assert!(result
            .type_map
            .mappings
            .iter()
            .any(|mapping| mapping.symbol == "i"));
        assert!(result
            .type_map
            .mappings
            .iter()
            .any(|mapping| mapping.symbol == "next"));
        assert_eq!(result.plan.call_expressions.len(), 2);
        assert_eq!(
            result.plan.call_expressions[0].source_expression,
            "body_helper(total)"
        );
        assert_eq!(
            result.plan.call_expressions[0].statement_context,
            "declaration_initializer"
        );
        assert_eq!(
            result.plan.call_expressions[1].source_expression,
            "step_helper(i)"
        );
        assert_eq!(
            result.plan.call_expressions[1].statement_context,
            "assignment"
        );
    }

    #[test]
    fn clang_lowered_pointer_graph_does_not_infer_byte_cursor_from_buf_name_only() {
        let u32_ty = unsigned_ty("uint32_t", "unsigned int", 32);
        let usize_ty = unsigned_ty("size_t", "unsigned long", 64);
        let const_void_ptr = pointer_ty("const void *", "const void *", void_ty(true), true);
        let function = IrFunction {
            name: "fdb_calc_crc32".to_string(),
            return_type: u32_ty.clone(),
            params: vec![
                param("crc", u32_ty.clone()),
                param("buf", const_void_ptr),
                param("size", usize_ty),
            ],
            body: vec![IrStmt::Return {
                value: Some(IrExpr::Var {
                    name: "crc".to_string(),
                    ty: u32_ty,
                    source_span: None::<SourceSpan>,
                }),
                source_span: None,
            }],
            source_span: None,
        };
        let spec = SliceSpec {
            target_id: "flashdb".to_string(),
            slice_id: "real-fdb-calc-crc32".to_string(),
            source_commit: "93d1755".to_string(),
            function_name: "fdb_calc_crc32".to_string(),
            build_profile: test_profile(),
            ..SliceSpec::default()
        };
        let mut result = TranslationResult::default();

        record_clang_lowered_ir_evidence(&spec, &function, &mut result);

        let buf = result
            .pointer_graph
            .nodes
            .iter()
            .find(|node| node.id == "buf")
            .expect("buf pointer node");
        assert!(buf.read_effects.is_empty(), "{:?}", buf.read_effects);
        assert!(
            !buf.boundary_decisions
                .contains(&"byte_cursor_post_increment_read".to_string()),
            "{:?}",
            buf.boundary_decisions
        );
    }

    #[test]
    fn clang_lowered_pointer_graph_records_post_increment_deref_inside_member_base() {
        let u32_ty = unsigned_ty("uint32_t", "unsigned int", 32);
        let u8_ty = unsigned_ty("uint8_t", "unsigned char", 8);
        let const_u8_ptr = pointer_ty(
            "const uint8_t *",
            "const unsigned char *",
            u8_ty.clone(),
            true,
        );
        let const_void_ptr = pointer_ty("const void *", "const void *", void_ty(true), true);
        let function = IrFunction {
            name: "member_cursor".to_string(),
            return_type: u32_ty.clone(),
            params: vec![param("buf", const_void_ptr.clone())],
            body: vec![
                IrStmt::Assign {
                    target: var("cursor", const_u8_ptr.clone()),
                    value: IrExpr::Cast {
                        target: const_u8_ptr.clone(),
                        expr: Box::new(var("buf", const_void_ptr)),
                        implicit: false,
                        source_span: None,
                    },
                    source_span: None,
                },
                IrStmt::Return {
                    value: Some(IrExpr::Member {
                        base: Box::new(IrExpr::Deref {
                            ptr: Box::new(IrExpr::IncDec {
                                target: Box::new(var("cursor", const_u8_ptr.clone())),
                                op: IrIncDecOp::Inc,
                                prefix: false,
                                ty: const_u8_ptr,
                                source_span: None,
                            }),
                            ty: record_ty("byte_record"),
                            source_span: None,
                        }),
                        field: "value".to_string(),
                        ty: u32_ty,
                        is_arrow: false,
                        source_span: None,
                    }),
                    source_span: None,
                },
            ],
            source_span: None,
        };
        let spec = SliceSpec {
            target_id: "demo".to_string(),
            slice_id: "member-cursor".to_string(),
            source_commit: "1234567".to_string(),
            function_name: "member_cursor".to_string(),
            build_profile: test_profile(),
            ..SliceSpec::default()
        };
        let mut result = TranslationResult::default();

        record_clang_lowered_ir_evidence(&spec, &function, &mut result);

        let buf = result
            .pointer_graph
            .nodes
            .iter()
            .find(|node| node.id == "buf")
            .expect("buf pointer node");
        assert_eq!(buf.read_effects, vec!["*p++"]);
        assert!(
            buf.boundary_decisions
                .contains(&"byte_cursor_post_increment_read".to_string()),
            "{:?}",
            buf.boundary_decisions
        );
    }
}
