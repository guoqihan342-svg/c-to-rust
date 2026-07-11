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
    profile: &BuildProfile,
    result: &mut TranslationResult,
) {
    record_ir_type_mapping_with_rust_type_override(symbol, ty, profile, None, result);
}

fn record_ir_type_mapping_with_rust_type_override(
    symbol: &str,
    ty: &typed_ir::IrType,
    _profile: &BuildProfile,
    rust_type_override: Option<String>,
    result: &mut TranslationResult,
) {
    let c_type = ir_c_type(ty);
    let Some(rust_type) = rust_type_override.or_else(|| ir_rust_type(ty)) else {
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
    if let Ok(Some(function_pointer)) = typed_ir::emit_function_pointer_param_type(ty) {
        return Some(function_pointer);
    }
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
        | typed_ir::IrExpr::AddrOf { operand, .. } => ir_expr_mentions_var(operand, expected),
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
