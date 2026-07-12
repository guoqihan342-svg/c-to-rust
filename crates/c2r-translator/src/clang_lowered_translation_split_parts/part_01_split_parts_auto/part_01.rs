
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
        typed_ir::IrStmt::RecordMemset { destination, .. } => {
            format!("record_memset {}", ir_expr_label(destination))
        }
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
        typed_ir::IrExpr::MutableVoidPointerAddress { .. } => {
            "mutable_void_pointer_address".to_string()
        }
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
                typed_ir::IrStmt::RecordMemset { .. } => "record_memset",
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
        let has_byte_cursor_read = ir_has_byte_cursor_read(function, &param.name);
        let is_unused_readonly_8_bit_pointer =
            ir_param_is_unused_readonly_8_bit_pointer(function, param);
        if has_byte_cursor_read {
            boundary_decisions.push("byte_cursor_post_increment_read".to_string());
            read_effects.push("*p++".to_string());
        }
        if is_unused_readonly_8_bit_pointer {
            boundary_decisions.push("unused_readonly_8_bit_pointer_raw_candidate".to_string());
        }
        result.pointer_graph.nodes.push(PointerNode {
            id: param.name.clone(),
            c_type,
            role: if is_const_input {
                "borrowed_input".to_string()
            } else {
                "out_param".to_string()
            },
            rust_boundary: if has_byte_cursor_read {
                "&[u8]".to_string()
            } else if is_unused_readonly_8_bit_pointer {
                "*const core::ffi::c_void".to_string()
            } else if param.name == "buf" || is_const_input {
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

fn ir_param_type_map_rust_override(
    function: &typed_ir::IrFunction,
    param: &typed_ir::IrParam,
) -> Option<String> {
    if ir_has_byte_cursor_read(function, &param.name) {
        Some("&[u8]".to_string())
    } else if ir_param_is_unused_readonly_8_bit_pointer(function, param) {
        Some("*const core::ffi::c_void".to_string())
    } else {
        None
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

fn ir_param_is_unused_readonly_8_bit_pointer(
    function: &typed_ir::IrFunction,
    param: &typed_ir::IrParam,
) -> bool {
    ir_is_readonly_8_bit_pointer_type(&param.ty) && !ir_body_mentions_var(&function.body, &param.name)
}

fn ir_is_readonly_8_bit_pointer_type(ty: &typed_ir::IrType) -> bool {
    let typed_ir::IrTypeKind::Pointer { pointee } = &ty.kind else {
        return false;
    };
    pointee.is_const
        && matches!(
            pointee.kind,
            typed_ir::IrTypeKind::Integer {
                signed: _,
                width: 8
            }
        )
}

fn ir_body_mentions_var(statements: &[typed_ir::IrStmt], expected: &str) -> bool {
    statements
        .iter()
        .any(|statement| ir_stmt_mentions_var(statement, expected))
}

fn ir_stmt_mentions_var(statement: &typed_ir::IrStmt, expected: &str) -> bool {
    match statement {
        typed_ir::IrStmt::Decl { init, .. } => init
            .as_ref()
            .is_some_and(|init| ir_expr_mentions_var(init, expected)),
        typed_ir::IrStmt::Assign { target, value, .. } => {
            ir_expr_mentions_var(target, expected) || ir_expr_mentions_var(value, expected)
        }
        typed_ir::IrStmt::If {
            condition,
            then_body,
            else_body,
            ..
        } => {
            ir_expr_mentions_var(condition, expected)
                || ir_body_mentions_var(then_body, expected)
                || ir_body_mentions_var(else_body, expected)
        }
        typed_ir::IrStmt::While {
            condition, body, ..
        } => ir_expr_mentions_var(condition, expected) || ir_body_mentions_var(body, expected),
        typed_ir::IrStmt::DoWhile {
            body, condition, ..
        } => ir_body_mentions_var(body, expected) || ir_expr_mentions_var(condition, expected),
        typed_ir::IrStmt::For {
            init,
            condition,
            step,
            body,
            ..
        } => {
            ir_body_mentions_var(init, expected)
                || condition
                    .as_ref()
                    .is_some_and(|condition| ir_expr_mentions_var(condition, expected))
                || step
                    .as_deref()
                    .is_some_and(|step| ir_stmt_mentions_var(step, expected))
                || ir_body_mentions_var(body, expected)
        }
        typed_ir::IrStmt::Return { value, .. } => value
            .as_ref()
            .is_some_and(|value| ir_expr_mentions_var(value, expected)),
        typed_ir::IrStmt::Expr { expr, .. } => ir_expr_mentions_var(expr, expected),
        typed_ir::IrStmt::RecordMemset { destination, .. } => {
            ir_expr_mentions_var(destination, expected)
        }
        typed_ir::IrStmt::Break { .. }
        | typed_ir::IrStmt::Continue { .. }
        | typed_ir::IrStmt::Unsupported { .. } => false,
    }
}

fn ir_expr_mentions_var(expr: &typed_ir::IrExpr, expected: &str) -> bool {
    match expr {
        typed_ir::IrExpr::Var { name, .. } => name == expected,
        typed_ir::IrExpr::Binary { lhs, rhs, .. } => {
            ir_expr_mentions_var(lhs, expected) || ir_expr_mentions_var(rhs, expected)
        }
        typed_ir::IrExpr::Unary { operand, .. }
        | typed_ir::IrExpr::Cast { expr: operand, .. }
        | typed_ir::IrExpr::LValueToRValue { expr: operand, .. }
        | typed_ir::IrExpr::ArrayToPointerDecay { expr: operand, .. }
        | typed_ir::IrExpr::FunctionToPointerDecay { expr: operand, .. }
        | typed_ir::IrExpr::Member { base: operand, .. }
        | typed_ir::IrExpr::IncDec { target: operand, .. }
        | typed_ir::IrExpr::Deref { ptr: operand, .. }
        | typed_ir::IrExpr::AddrOf { operand, .. }
        | typed_ir::IrExpr::MutableVoidPointerAddress { operand, .. } => {
            ir_expr_mentions_var(operand, expected)
        }
        typed_ir::IrExpr::Conditional {
            condition,
            then_expr,
            else_expr,
            ..
        } => {
            ir_expr_mentions_var(condition, expected)
                || ir_expr_mentions_var(then_expr, expected)
                || ir_expr_mentions_var(else_expr, expected)
        }
        typed_ir::IrExpr::Index { base, index, .. } => {
            ir_expr_mentions_var(base, expected) || ir_expr_mentions_var(index, expected)
        }
        typed_ir::IrExpr::ArrayLiteral { elements, .. } => elements
            .iter()
            .any(|element| ir_expr_mentions_var(element, expected)),
        typed_ir::IrExpr::Call { args, .. } => args
            .iter()
            .any(|arg| ir_expr_mentions_var(arg, expected)),
        typed_ir::IrExpr::LitInt { .. }
        | typed_ir::IrExpr::NullPtr { .. }
        | typed_ir::IrExpr::Unsupported { .. } => false,
    }
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
