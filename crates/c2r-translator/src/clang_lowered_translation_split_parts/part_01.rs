fn ir_expr_label(expr: &typed_ir::IrExpr) -> String {
    match expr {
        typed_ir::IrExpr::Var { name, .. } => name.clone(),
        typed_ir::IrExpr::LitInt { spelling, .. } => spelling.clone(),
        typed_ir::IrExpr::NullPtr { .. } => "null_ptr".to_string(),
        typed_ir::IrExpr::Binary { op, .. } => format!("{op:?}"),
        typed_ir::IrExpr::Unary { op, .. } => format!("{op:?}"),
        typed_ir::IrExpr::Conditional { .. } => "conditional".to_string(),
        typed_ir::IrExpr::Cast { .. } => "cast".to_string(),
        typed_ir::IrExpr::LValueToRValue { .. } => "lvalue_to_rvalue".to_string(),
        typed_ir::IrExpr::ArrayToPointerDecay { .. } => "array_to_pointer_decay".to_string(),
        typed_ir::IrExpr::FunctionToPointerDecay { .. } => "function_to_pointer_decay".to_string(),
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

/// Derives pointer-boundary evidence from accepted typed IR parameters and uses.
///
/// This is a narrow evidence projection, not alias analysis. Today it recognizes
/// const inputs and byte-cursor reads such as `*p++`; unrecognized pointer
/// behavior must stay outside the emitted route or be rejected earlier.
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
        typed_ir::IrExpr::LValueToRValue { expr, .. } => {
            collect_ir_post_increment_deref_vars_from_expr(expr, vars);
        }
        typed_ir::IrExpr::ArrayToPointerDecay { expr, .. } => {
            collect_ir_post_increment_deref_vars_from_expr(expr, vars);
        }
        typed_ir::IrExpr::FunctionToPointerDecay { expr, .. } => {
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

