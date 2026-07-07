#[derive(Clone, Copy, Debug)]
enum LoopContext<'a> {
    None,
    While,
    DoWhile { condition: &'a IrExpr },
    For { step: &'a IrStmt },
}

/// Emits one statement while enforcing symbol, type, and loop-context rules.
///
/// This is the statement-level semantic boundary for the generic emitter.
/// Every arm either proves the local lowering rule it needs or returns a
/// specific error; the caller prefixes those errors with the statement index so
/// evidence can point back to the rejected IR node.
fn emit_stmt(
    stmt: &IrStmt,
    return_type: &IrType,
    indent_level: usize,
    symbols: &mut HashSet<String>,
    context: &EmitContext,
    loop_context: LoopContext<'_>,
) -> Result<String, String> {
    let indent = "    ".repeat(indent_level);
    match stmt {
        IrStmt::Decl { name, ty, init, .. } => {
            let decl_name = emit_identifier(name, "decl")?;
            if symbols.contains(name) {
                return Err(format!("decl {name} duplicates an existing symbol"));
            }
            if init.is_none() && context.byte_cursor_source(name).is_some() && is_u8_pointer(ty) {
                symbols.insert(name.clone());
                return Ok(format!("{indent}let mut {decl_name}: usize = 0;\n"));
            }
            if matches!(ty.kind, IrTypeKind::Array { .. }) {
                let decl_ty = emit_fixed_array_type(ty)
                    .map_err(|detail| format!("decl {name} has {detail}"))?;
                let Some(IrExpr::ArrayLiteral {
                    elements,
                    ty: literal_ty,
                    ..
                }) = init
                else {
                    return Err(format!(
                        "decl {name} array initializer must be an array literal"
                    ));
                };
                if literal_ty != ty {
                    return Err(format!(
                        "decl {name} array literal type {} does not match declared type {}",
                        type_label(literal_ty),
                        type_label(ty)
                    ));
                }
                let init = emit_array_literal(
                    elements,
                    ty,
                    symbols,
                    context,
                    &format!("decl {name} initializer"),
                )?;
                symbols.insert(name.clone());
                let mut_prefix = if context.is_assigned_var(name) {
                    "mut "
                } else {
                    ""
                };
                return Ok(format!(
                    "{indent}let {mut_prefix}{decl_name}: {decl_ty} = {init};\n"
                ));
            }
            if matches!(ty.kind, IrTypeKind::Record { .. }) {
                let decl_ty =
                    emit_value_type(ty).map_err(|detail| format!("decl {name} has {detail}"))?;
                let (init, zero_initialized) = if let Some(init) = init {
                    validate_expr_matches_type(init, ty, &format!("decl {name} initializer"))?;
                    let init = emit_expr(init, symbols, context)
                        .map_err(|detail| format!("decl {name} initializer {detail}"))?;
                    (init, false)
                } else if context.is_zero_initialized_record_local(name) {
                    (emit_record_zero_initializer(ty)?, true)
                } else {
                    return Err(format!("decl {name} record initializer is required"));
                };
                symbols.insert(name.clone());
                let mut_prefix = if zero_initialized || context.is_assigned_var(name) {
                    "mut "
                } else {
                    ""
                };
                return Ok(format!(
                    "{indent}let {mut_prefix}{decl_name}: {decl_ty} = {init};\n"
                ));
            }
            let decl_ty =
                emit_scalar_type(ty).map_err(|detail| format!("decl {name} has {detail}"))?;
            if let Some(init) = init {
                validate_expr_matches_type(init, ty, &format!("decl {name} initializer"))?;
                let emitted = emit_expr_with_prelude(
                    init,
                    symbols,
                    context,
                    indent_level,
                    &format!("decl {name} initializer"),
                )?;
                symbols.insert(name.clone());
                Ok(format!(
                    "{}{indent}let mut {decl_name}: {decl_ty} = {};\n",
                    emitted.prelude, emitted.expr
                ))
            } else {
                symbols.insert(name.clone());
                Ok(format!("{indent}let mut {decl_name}: {decl_ty};\n"))
            }
        }
        IrStmt::Assign { target, value, .. } => {
            if is_byte_cursor_cast_assignment(target, value, symbols, context)? {
                return Ok(String::new());
            }
            let (target_name, target_ty) = emit_assignment_target(target, symbols, context)?;
            if count_post_increment_byte_reads(value) > 1 {
                return Err(
                    "assign value multiple post-increment byte reads are unsupported".to_string(),
                );
            }
            if let Some(compound_value) =
                emit_mutable_record_pointer_member_compound_assignment_value(
                    target,
                    value,
                    &target_name,
                    symbols,
                    context,
                )?
            {
                return Ok(format!("{indent}{target_name} = {compound_value};\n"));
            }
            if let Some(emitted) = emit_opaque_record_pointer_field_assignment_value(
                target,
                value,
                target_ty,
                symbols,
                context,
                "assign value",
            )? {
                return Ok(format!(
                    "{}{indent}{target_name} = {};\n",
                    emitted.prelude, emitted.expr
                ));
            }
            validate_expr_matches_type(value, target_ty, "assign value")?;
            let emitted =
                emit_expr_with_prelude(value, symbols, context, indent_level, "assign value")?;
            Ok(format!(
                "{}{indent}{target_name} = {};\n",
                emitted.prelude, emitted.expr
            ))
        }
        IrStmt::Return { value, .. } => match value {
            Some(value) => {
                if is_void_type(return_type) {
                    return Err("return value in void function".to_string());
                }
                if let Some(line) = emit_post_increment_deref_return(
                    value,
                    return_type,
                    indent_level,
                    symbols,
                    context,
                )? {
                    return Ok(line);
                }
                if let Some(line) = emit_mutable_record_pointer_identity_return(
                    value,
                    return_type,
                    indent_level,
                    symbols,
                    context,
                )? {
                    return Ok(line);
                }
                if count_post_increment_byte_reads(value) > 1 {
                    return Err("multiple post-increment byte reads are unsupported".to_string());
                }
                validate_expr_matches_type(value, return_type, "return expr")?;
                let emitted =
                    emit_expr_with_prelude(value, symbols, context, indent_level, "return expr")?;
                Ok(format!(
                    "{}{indent}return {};\n",
                    emitted.prelude, emitted.expr
                ))
            }
            None if is_void_type(return_type) => Ok(format!("{indent}return;\n")),
            None => Err("return without value in non-void function".to_string()),
        },
        IrStmt::Break { .. } => {
            if matches!(loop_context, LoopContext::None) {
                return Err("break outside loop".to_string());
            }
            Ok(format!("{indent}break;\n"))
        }
        IrStmt::Continue { .. } => match loop_context {
            LoopContext::None => Err("continue outside loop".to_string()),
            LoopContext::While => Ok(format!("{indent}continue;\n")),
            LoopContext::DoWhile { condition } => {
                let condition_break = emit_do_while_condition_break(
                    condition,
                    indent_level,
                    symbols,
                    context,
                    "continue condition",
                )?;
                Ok(format!("{condition_break}{indent}continue;\n"))
            }
            LoopContext::For { step } => {
                validate_for_step_stmt(step)?;
                let mut step_symbols = symbols.clone();
                let step_line = emit_stmt(
                    step,
                    return_type,
                    indent_level,
                    &mut step_symbols,
                    context,
                    LoopContext::None,
                )
                .map_err(|detail| format!("continue step {detail}"))?;
                Ok(format!("{step_line}{indent}continue;\n"))
            }
        },
        IrStmt::Expr { expr, .. } => {
            if let Some(line) = emit_c_memset_statement(expr, symbols, context)
                .map_err(|detail| format!("expr {detail}"))?
            {
                return Ok(format!("{indent}{line}\n"));
            }
            if let Some(line) = emit_c_memcpy_statement(expr, symbols, context)
                .map_err(|detail| format!("expr {detail}"))?
            {
                return Ok(format!("{indent}{line}\n"));
            }
            if let Some(line) = emit_prefix_inc_dec_statement(expr, symbols)
                .map_err(|detail| format!("expr {detail}"))?
            {
                return Ok(format!("{indent}{line}\n"));
            }
            if let Some(line) = emit_discarded_pointer_return_call_statement(expr, symbols, context)
                .map_err(|detail| format!("expr {detail}"))?
            {
                return Ok(format!("{indent}{line}\n"));
            }
            if let Some(emitted) = emit_single_inc_dec_call_statement_expr(
                expr,
                symbols,
                context,
                indent_level,
                "expr",
            )? {
                return Ok(format!("{}{indent}{};\n", emitted.prelude, emitted.expr));
            }
            let expr =
                emit_expr(expr, symbols, context).map_err(|detail| format!("expr {detail}"))?;
            Ok(format!("{indent}{expr};\n"))
        }
        IrStmt::If {
            condition,
            then_body,
            else_body,
            ..
        } => {
            let condition = emit_condition_expr(condition, symbols, context)
                .map_err(|detail| format!("if condition {detail}"))?;
            let mut block = String::new();
            block.push_str(&format!("{indent}if {condition} {{\n"));
            let mut then_symbols = symbols.clone();
            for (index, stmt) in then_body.iter().enumerate() {
                let line = emit_stmt(
                    stmt,
                    return_type,
                    indent_level + 1,
                    &mut then_symbols,
                    context,
                    loop_context,
                )
                .map_err(|detail| format!("if then[{index}].{detail}"))?;
                block.push_str(&line);
            }
            if else_body.is_empty() {
                block.push_str(&format!("{indent}}}\n"));
            } else {
                block.push_str(&format!("{indent}}} else {{\n"));
                let mut else_symbols = symbols.clone();
                for (index, stmt) in else_body.iter().enumerate() {
                    let line = emit_stmt(
                        stmt,
                        return_type,
                        indent_level + 1,
                        &mut else_symbols,
                        context,
                        loop_context,
                    )
                    .map_err(|detail| format!("if else[{index}].{detail}"))?;
                    block.push_str(&line);
                }
                block.push_str(&format!("{indent}}}\n"));
            }
            Ok(block)
        }
        IrStmt::While {
            condition, body, ..
        } => {
            if let Some(block) = emit_prefix_decrement_while_loop(
                condition,
                body,
                return_type,
                indent_level,
                symbols,
                context,
            )? {
                return Ok(block);
            }
            if let Some(block) = emit_postfix_decrement_while_loop(
                condition,
                body,
                return_type,
                indent_level,
                symbols,
                context,
            )? {
                return Ok(block);
            }
            let condition = emit_condition_expr(condition, symbols, context)
                .map_err(|detail| format!("while condition {detail}"))?;
            let mut loop_symbols = symbols.clone();
            let mut block = String::new();
            block.push_str(&format!("{indent}while {condition} {{\n"));
            for (index, stmt) in body.iter().enumerate() {
                let line = emit_stmt(
                    stmt,
                    return_type,
                    indent_level + 1,
                    &mut loop_symbols,
                    context,
                    LoopContext::While,
                )
                .map_err(|detail| format!("while body[{index}].{detail}"))?;
                block.push_str(&line);
            }
            block.push_str(&format!("{indent}}}\n"));
            Ok(block)
        }
        IrStmt::DoWhile {
            body, condition, ..
        } => emit_do_while_stmt(body, condition, return_type, indent_level, symbols, context),
        IrStmt::For {
            init,
            condition,
            step,
            body,
            ..
        } => emit_for_stmt(
            init,
            condition.as_ref(),
            step.as_deref(),
            body,
            return_type,
            indent_level,
            symbols,
            context,
        ),
        IrStmt::Unsupported { node, reason, .. } => {
            Err(format!("unsupported statement {node}: {reason}"))
        }
    }
}

fn emit_discarded_pointer_return_call_statement(
    expr: &IrExpr,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<Option<String>, String> {
    let IrExpr::Call {
        callee, args, ty, ..
    } = expr
    else {
        return Ok(None);
    };
    if !matches!(ty.kind, IrTypeKind::Pointer { .. }) {
        return Ok(None);
    }
    let callee = emit_identifier(callee, "discarded pointer-return call callee")?;
    if reserved_c_macro_or_stdlib_callee(&callee) {
        return Err(format!(
            "discarded pointer-return call callee \"{callee}\" is reserved C macro/stdlib/extern surface and requires explicit lowering or extern binding"
        ));
    }
    validate_bounded_call_args(args, context)?;
    let args = args
        .iter()
        .enumerate()
        .map(|(index, arg)| {
            emit_call_arg_expr(arg, symbols, context)
                .map_err(|detail| format!("call arg[{index}] {detail}"))
        })
        .collect::<Result<Vec<_>, _>>()?
        .join(", ");
    Ok(Some(format!("let _ = {callee}({args});")))
}

fn emit_do_while_stmt(
    body: &[IrStmt],
    condition: &IrExpr,
    return_type: &IrType,
    indent_level: usize,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<String, String> {
    let indent = "    ".repeat(indent_level);
    let mut loop_symbols = symbols.clone();
    let mut block = String::new();
    block.push_str(&format!("{indent}loop {{\n"));
    for (index, stmt) in body.iter().enumerate() {
        let line = emit_stmt(
            stmt,
            return_type,
            indent_level + 1,
            &mut loop_symbols,
            context,
            LoopContext::DoWhile { condition },
        )
        .map_err(|detail| format!("do while body[{index}].{detail}"))?;
        block.push_str(&line);
    }
    block.push_str(&emit_do_while_condition_break(
        condition,
        indent_level + 1,
        symbols,
        context,
        "condition",
    )?);
    block.push_str(&format!("{indent}}}\n"));
    Ok(block)
}

fn emit_do_while_condition_break(
    condition: &IrExpr,
    indent_level: usize,
    symbols: &HashSet<String>,
    context: &EmitContext,
    path: &str,
) -> Result<String, String> {
    let condition = emit_condition_expr(condition, symbols, context)
        .map_err(|detail| format!("do while {path} {detail}"))?;
    let indent = "    ".repeat(indent_level);
    let inner_indent = "    ".repeat(indent_level + 1);
    Ok(format!(
        "{indent}if !({condition}) {{\n{inner_indent}break;\n{indent}}}\n"
    ))
}

fn emit_for_stmt(
    init: &[IrStmt],
    condition: Option<&IrExpr>,
    step: Option<&IrStmt>,
    body: &[IrStmt],
    return_type: &IrType,
    indent_level: usize,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<String, String> {
    let indent = "    ".repeat(indent_level);
    let inner_indent = "    ".repeat(indent_level + 1);
    let mut loop_symbols = symbols.clone();
    let mut block = String::new();
    block.push_str(&format!("{indent}{{\n"));

    for (index, init) in init.iter().enumerate() {
        validate_for_init_stmt(init)?;
        let line = emit_stmt(
            init,
            return_type,
            indent_level + 1,
            &mut loop_symbols,
            context,
            LoopContext::None,
        )
        .map_err(|detail| format!("for init[{index}] {detail}"))?;
        block.push_str(&line);
    }

    let condition = match condition {
        Some(condition) => emit_condition_expr(condition, &loop_symbols, context)
            .map_err(|detail| format!("for condition {detail}"))?,
        None => "true".to_string(),
    };
    block.push_str(&format!("{inner_indent}while {condition} {{\n"));

    let mut body_symbols = loop_symbols.clone();
    let body_loop_context = step
        .map(|step| LoopContext::For { step })
        .unwrap_or(LoopContext::While);
    for (index, stmt) in body.iter().enumerate() {
        let line = emit_stmt(
            stmt,
            return_type,
            indent_level + 2,
            &mut body_symbols,
            context,
            body_loop_context,
        )
        .map_err(|detail| format!("for body[{index}].{detail}"))?;
        block.push_str(&line);
    }

    if let Some(step) = step {
        validate_for_step_stmt(step)?;
        let line = emit_stmt(
            step,
            return_type,
            indent_level + 2,
            &mut loop_symbols,
            context,
            LoopContext::None,
        )
        .map_err(|detail| format!("for step {detail}"))?;
        block.push_str(&line);
    }

    block.push_str(&format!("{inner_indent}}}\n"));
    block.push_str(&format!("{indent}}}\n"));
    Ok(block)
}

fn validate_for_init_stmt(stmt: &IrStmt) -> Result<(), String> {
    match stmt {
        IrStmt::Decl { .. } | IrStmt::Assign { .. } => Ok(()),
        _ => Err("for init must be a Decl or Assign statement".to_string()),
    }
}

fn validate_for_step_stmt(stmt: &IrStmt) -> Result<(), String> {
    match stmt {
        IrStmt::Assign { .. } => Ok(()),
        _ => Err("for step must be an Assign statement".to_string()),
    }
}

fn emit_assignment_target<'a>(
    target: &'a IrExpr,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<(String, &'a IrType), String> {
    match target {
        IrExpr::Var { name, ty, .. } => {
            if !symbols.contains(name) {
                return Err(format!("assign target {name} is not declared"));
            }
            let name = emit_identifier(name, "assign target")?;
            Ok((name, ty))
        }
        IrExpr::Index {
            base, index, ty, ..
        } => {
            let target = emit_index_assignment_target(base, index, ty, symbols, context)?;
            Ok((target, ty))
        }
        IrExpr::Deref { ptr, ty, .. } => {
            let target = emit_mutable_pointer_deref_assignment_target(ptr, ty, symbols, context)?;
            Ok((target, ty))
        }
        IrExpr::Member {
            base,
            field,
            ty,
            is_arrow,
            ..
        } => {
            if *is_arrow {
                let target = emit_mutable_record_pointer_member_assignment_target(
                    base, field, ty, symbols, context,
                )?;
                return Ok((target, ty));
            }
            let target = emit_member_expr(base, field, ty, *is_arrow, symbols, context)?;
            Ok((target, ty))
        }
        _ => Err(
            "assign target must be Var, local fixed array Index, pointer Deref, or by-value record Member"
                .to_string(),
        ),
    }
}

fn emit_mutable_record_pointer_identity_return(
    value: &IrExpr,
    return_type: &IrType,
    indent_level: usize,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<Option<String>, String> {
    if mutable_record_pointer_pointee_type(return_type).is_none() {
        return Ok(None);
    }
    let IrExpr::Var { name, ty, .. } = value else {
        return Err(
            "mutable record pointer return must return the owned record pointer parameter"
                .to_string(),
        );
    };
    if ty != return_type {
        return Err(format!(
            "mutable record pointer return type {} does not match function return type {}",
            type_label(ty),
            type_label(return_type)
        ));
    }
    if !symbols.contains(name) {
        return Err(format!(
            "mutable record pointer return value {name} is not declared"
        ));
    }
    if !context.is_mutable_record_pointer_write_param(name) {
        return Err(format!(
            "mutable record pointer return {name} requires mutable record pointer ownership evidence"
        ));
    }
    let indent = "    ".repeat(indent_level);
    let name = emit_identifier(name, "mutable record pointer return value")?;
    Ok(Some(format!("{indent}return {name};\n")))
}

fn emit_mutable_record_pointer_member_assignment_target(
    base: &IrExpr,
    field: &str,
    ty: &IrType,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<String, String> {
    let IrExpr::Var {
        name: base_name,
        ty: base_ty,
        ..
    } = base
    else {
        return Err("arrow member assignment base must be a record pointer variable".to_string());
    };
    if !symbols.contains(base_name) {
        return Err(format!(
            "arrow member assignment base {base_name} is not declared"
        ));
    }
    if !context.is_mutable_record_pointer_write_param(base_name) {
        return Err(format!(
            "arrow member assignment base {base_name} requires mutable record pointer ownership evidence"
        ));
    }
    mutable_record_pointer_pointee_type(base_ty).ok_or_else(|| {
        format!(
            "arrow member assignment base {base_name} has unsupported type {}",
            type_label(base_ty)
        )
    })?;
    emit_mutable_record_pointer_field_type(ty)
        .map_err(|detail| format!("mutable record pointer arrow field {field} has {detail}"))?;
    let base_name = emit_identifier(base_name, "arrow member assignment base")?;
    let field = emit_identifier(field, "arrow member assignment field")?;
    Ok(format!("{base_name}.{field}"))
}

fn emit_mutable_record_pointer_member_compound_assignment_value(
    target: &IrExpr,
    value: &IrExpr,
    emitted_target: &str,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<Option<String>, String> {
    let IrExpr::Binary {
        op, lhs, rhs, ty, ..
    } = value
    else {
        return Ok(None);
    };
    if !same_direct_mutable_record_pointer_member(lhs, target, context)? {
        return Ok(None);
    }
    if let Some(reason) = mutable_record_pointer_field_compound_rhs_rejection_reason(rhs) {
        return Err(reason);
    }
    let op_token = emit_binary_op(op)?;
    validate_binary_operand_types(op_token, lhs, rhs, ty)?;
    validate_binary_runtime_contract(op, lhs, rhs, ty, &context.policy)?;
    let rhs = emit_expr(rhs, symbols, context).map_err(|detail| {
        format!("mutable record pointer field compound assignment RHS {detail}")
    })?;
    Ok(Some(emit_binary_result_expr(
        op,
        op_token,
        emitted_target,
        &rhs,
        ty,
    )))
}

fn emit_opaque_record_pointer_field_assignment_value(
    target: &IrExpr,
    value: &IrExpr,
    target_ty: &IrType,
    symbols: &HashSet<String>,
    context: &EmitContext,
    path: &str,
) -> Result<Option<EmittedExpr>, String> {
    let Some(target_pointer_ty) = emit_opaque_void_pointer_type(target_ty) else {
        return Ok(None);
    };
    let Some((base_name, _, _, _)) =
        direct_mutable_record_pointer_opaque_member_parts(target, context)?
    else {
        return Err(format!(
            "{path} opaque pointer field target requires direct mutable record pointer ownership evidence"
        ));
    };
    if !context.is_mutable_record_pointer_write_param(base_name) {
        return Err(format!(
            "{path} opaque pointer field target {base_name} requires mutable record pointer ownership evidence"
        ));
    }
    let expr = match value {
        IrExpr::Var { .. } => emit_opaque_record_pointer_field_value_var(
            value,
            &target_pointer_ty,
            symbols,
            context,
            path,
        )?,
        IrExpr::Cast {
            target: cast_target,
            expr,
            ..
        } => {
            let cast_target_ty = emit_opaque_void_pointer_type(cast_target).ok_or_else(|| {
                format!(
                    "{path} opaque pointer cast target {} is unsupported",
                    type_label(cast_target)
                )
            })?;
            if cast_target_ty != target_pointer_ty {
                return Err(format!(
                    "{path} opaque pointer cast target {cast_target_ty} does not match field type {target_pointer_ty}"
                ));
            }
            let source_ty = expr_type(expr)
                .ok_or_else(|| format!("{path} opaque pointer cast source type is unsupported"))?;
            let source_pointer_ty = emit_opaque_void_pointer_type(source_ty).ok_or_else(|| {
                format!(
                    "{path} opaque pointer cast source {} is unsupported",
                    type_label(source_ty)
                )
            })?;
            let expr = emit_opaque_record_pointer_field_value_var(
                expr,
                &source_pointer_ty,
                symbols,
                context,
                &format!("{path} opaque pointer cast source"),
            )?;
            format!("({expr} as {target_pointer_ty})")
        }
        _ => {
            return Err(format!(
                "{path} opaque pointer field write requires an opaque pointer param value or opaque pointer cast"
            ))
        }
    };
    Ok(Some(EmittedExpr {
        prelude: String::new(),
        expr,
    }))
}

fn emit_opaque_record_pointer_field_value_var(
    expr: &IrExpr,
    expected_pointer_ty: &str,
    symbols: &HashSet<String>,
    context: &EmitContext,
    path: &str,
) -> Result<String, String> {
    let IrExpr::Var { name, ty, .. } = expr else {
        let source_ty = expr_type(expr).ok_or_else(|| format!("{path} type is unsupported"))?;
        return Err(format!("{path} {} is unsupported", type_label(source_ty)));
    };
    if !symbols.contains(name) {
        return Err(format!("{path} {name} is not declared"));
    }
    if !context.is_opaque_record_pointer_field_value_param(name) {
        return Err(format!(
            "{path} {name} requires opaque record pointer field value evidence"
        ));
    }
    let source_pointer_ty = emit_opaque_void_pointer_type(ty)
        .ok_or_else(|| format!("{path} {} is unsupported", type_label(ty)))?;
    if source_pointer_ty != expected_pointer_ty {
        return Err(format!(
            "{path} type {source_pointer_ty} does not match expected type {expected_pointer_ty}"
        ));
    }
    emit_identifier(name, "opaque pointer field value")
}

fn direct_mutable_record_pointer_opaque_member_parts<'a>(
    expr: &'a IrExpr,
    context: &EmitContext,
) -> Result<Option<(&'a str, &'a IrType, &'a str, &'a IrType)>, String> {
    let Some((base, base_ty, field, ty)) =
        direct_mutable_record_pointer_member_parts_any_field(expr, context)?
    else {
        return Ok(None);
    };
    emit_opaque_void_pointer_type(ty).ok_or_else(|| {
        format!(
            "mutable record pointer opaque field {base}.{field} has unsupported type {}",
            type_label(ty)
        )
    })?;
    Ok(Some((base, base_ty, field, ty)))
}

fn same_direct_mutable_record_pointer_member(
    lhs: &IrExpr,
    target: &IrExpr,
    context: &EmitContext,
) -> Result<bool, String> {
    let Some((target_base, target_base_ty, target_field, target_ty)) =
        direct_mutable_record_pointer_member_parts(target, context)?
    else {
        return Ok(false);
    };
    let Some((lhs_base, lhs_base_ty, lhs_field, lhs_ty)) =
        direct_mutable_record_pointer_member_parts(lhs, context)?
    else {
        return Ok(false);
    };
    Ok(target_base == lhs_base
        && target_base_ty == lhs_base_ty
        && target_field == lhs_field
        && target_ty == lhs_ty)
}

fn direct_mutable_record_pointer_member_parts<'a>(
    expr: &'a IrExpr,
    context: &EmitContext,
) -> Result<Option<(&'a str, &'a IrType, &'a str, &'a IrType)>, String> {
    let Some((base, base_ty, field, ty)) =
        direct_mutable_record_pointer_member_parts_any_field(expr, context)?
    else {
        return Ok(None);
    };
    emit_scalar_type(ty).map_err(|detail| {
        format!("mutable record pointer field compound assignment field {field} has {detail}")
    })?;
    Ok(Some((base, base_ty, field, ty)))
}

fn direct_mutable_record_pointer_member_parts_any_field<'a>(
    expr: &'a IrExpr,
    context: &EmitContext,
) -> Result<Option<(&'a str, &'a IrType, &'a str, &'a IrType)>, String> {
    let IrExpr::Member {
        base,
        field,
        ty,
        is_arrow: true,
        ..
    } = expr
    else {
        return Ok(None);
    };
    let IrExpr::Var {
        name, ty: base_ty, ..
    } = base.as_ref()
    else {
        return Ok(None);
    };
    if !context.is_mutable_record_pointer_write_param(name) {
        return Ok(None);
    }
    mutable_record_pointer_pointee_type(base_ty).ok_or_else(|| {
        format!(
            "mutable record pointer field compound assignment base {name} has unsupported type {}",
            type_label(base_ty)
        )
    })?;
    Ok(Some((name.as_str(), base_ty, field.as_str(), ty)))
}

fn mutable_record_pointer_field_compound_rhs_rejection_reason(value: &IrExpr) -> Option<String> {
    match value {
        IrExpr::Var { ty, .. } | IrExpr::LitInt { ty, .. } => {
            if is_integer_type(ty) {
                None
            } else {
                Some(format!(
                    "mutable record pointer field compound assignment RHS must be a simple integer variable, literal, or integral cast; got {}",
                    type_label(ty)
                ))
            }
        }
        IrExpr::Cast { target, expr, .. } => {
            if !is_integer_type(target) {
                return Some(format!(
                    "mutable record pointer field compound assignment RHS cast target must be an integer; got {}",
                    type_label(target)
                ));
            }
            mutable_record_pointer_field_compound_rhs_rejection_reason(expr)
        }
        IrExpr::Unsupported { node, reason, .. } => Some(format!(
            "mutable record pointer field compound assignment RHS uses unsupported expression {node}: {reason}"
        )),
        _ => Some(
            "mutable record pointer field compound assignment RHS must be a simple integer variable, literal, or integral cast"
                .to_string(),
        ),
    }
}

fn emit_index_assignment_target(
    base: &IrExpr,
    index: &IrExpr,
    ty: &IrType,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<String, String> {
    let IrExpr::Var {
        name: base_name,
        ty: base_ty,
        ..
    } = base
    else {
        return Err("assign index base must be Var".to_string());
    };
    if context.readonly_global(base_name).is_some() {
        return Err(format!(
            "assign index base {base_name} is a readonly global"
        ));
    }
    if !symbols.contains(base_name) {
        return Err(format!("assign index base {base_name} is not declared"));
    }
    if base_ty.is_const {
        return Err(format!(
            "assign index base {base_name} has const type {}",
            type_label(base_ty)
        ));
    }
    let element_ty = fixed_integer_array_element_type(base_ty)
        .or_else(|| mutable_pointer_slice_element_type(base_ty))
        .ok_or_else(|| {
            format!(
                "assign index base {base_name} has unsupported type {}",
                type_label(base_ty)
            )
        })?;
    let element_ty = emit_scalar_type(element_ty)
        .map_err(|detail| format!("assign index element has {detail}"))?;
    let result_ty =
        emit_scalar_type(ty).map_err(|detail| format!("assign index result has {detail}"))?;
    if result_ty != element_ty {
        return Err(format!(
            "assign index result type {result_ty} does not match element type {element_ty}"
        ));
    }
    let index_ty =
        expr_type(index).ok_or_else(|| "assign index operand type is unsupported".to_string())?;
    if !is_integer_type(index_ty) {
        return Err(format!(
            "assign index operand type {} is unsupported",
            type_label(index_ty)
        ));
    }
    let base = emit_identifier(base_name, "assign index base")?;
    let index = emit_expr(index, symbols, context)
        .map_err(|detail| format!("assign index operand {detail}"))?;
    Ok(format!("{base}[{index} as usize]"))
}

fn emit_mutable_pointer_deref_assignment_target(
    ptr: &IrExpr,
    ty: &IrType,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<String, String> {
    if let Some(target) =
        emit_mutable_pointer_add_deref_assignment_target(ptr, ty, symbols, context)?
    {
        return Ok(target);
    }
    let IrExpr::Var {
        name: ptr_name,
        ty: ptr_ty,
        ..
    } = ptr
    else {
        return Err("deref assignment pointer must be Var".to_string());
    };
    if !symbols.contains(ptr_name) {
        return Err(format!(
            "deref assignment pointer {ptr_name} is not declared"
        ));
    }
    if context.is_nullable_pointer_param(ptr_name) {
        return Err(format!(
            "nullable pointer param {ptr_name} cannot be dereference-assigned in the bounded emitter"
        ));
    }
    let element_ty = mutable_pointer_slice_element_type(ptr_ty).ok_or_else(|| {
        format!(
            "deref assignment pointer {ptr_name} has unsupported type {}",
            type_label(ptr_ty)
        )
    })?;
    let element_ty = emit_scalar_type(element_ty)
        .map_err(|detail| format!("deref assignment element has {detail}"))?;
    let deref_ty =
        emit_scalar_type(ty).map_err(|detail| format!("deref assignment result has {detail}"))?;
    if deref_ty != element_ty {
        return Err(format!(
            "deref assignment result type {deref_ty} does not match pointer element type {element_ty}"
        ));
    }
    let ptr_name = emit_identifier(ptr_name, "deref assignment pointer")?;
    Ok(format!("{ptr_name}[0usize]"))
}

fn emit_mutable_pointer_add_deref_assignment_target(
    ptr: &IrExpr,
    ty: &IrType,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<Option<String>, String> {
    let IrExpr::Binary {
        op: IrBinOp::Add,
        lhs,
        rhs,
        ty: add_ty,
        ..
    } = ptr
    else {
        return Ok(None);
    };
    let Some((base, index)) = mutable_pointer_add_operands(lhs, rhs) else {
        return Ok(None);
    };
    let IrExpr::Var {
        name: base_name,
        ty: base_ty,
        ..
    } = base
    else {
        return Err("deref pointer add assignment base must be Var".to_string());
    };
    if add_ty != base_ty {
        return Err(format!(
            "deref pointer add assignment result type {} does not match base type {}",
            type_label(add_ty),
            type_label(base_ty)
        ));
    }
    if !symbols.contains(base_name) {
        return Err(format!(
            "deref pointer add assignment base {base_name} is not declared"
        ));
    }
    if context.is_nullable_pointer_param(base_name) {
        return Err(format!(
            "nullable pointer param {base_name} cannot be offset-dereference-assigned in the bounded emitter"
        ));
    }
    let element_ty = mutable_pointer_slice_element_type(base_ty).ok_or_else(|| {
        format!(
            "deref pointer add assignment base {base_name} has unsupported type {}",
            type_label(base_ty)
        )
    })?;
    let element_ty = emit_scalar_type(element_ty)
        .map_err(|detail| format!("deref assignment element has {detail}"))?;
    let deref_ty =
        emit_scalar_type(ty).map_err(|detail| format!("deref assignment result has {detail}"))?;
    if deref_ty != element_ty {
        return Err(format!(
            "deref assignment result type {deref_ty} does not match pointer element type {element_ty}"
        ));
    }
    let index_ty = expr_type(index)
        .ok_or_else(|| "deref pointer add index type is unsupported".to_string())?;
    if !is_integer_type(index_ty) {
        return Err(format!(
            "deref pointer add index type {} is unsupported",
            type_label(index_ty)
        ));
    }
    validate_readonly_pointer_add_index_expr(index)?;
    let base = emit_identifier(base_name, "deref pointer add assignment base")?;
    let index = emit_expr(index, symbols, context)
        .map_err(|detail| format!("deref pointer add index {detail}"))?;
    Ok(Some(format!("{base}[{index} as usize]")))
}

fn emit_postfix_decrement_while_loop(
    condition: &IrExpr,
    body: &[IrStmt],
    return_type: &IrType,
    indent_level: usize,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<Option<String>, String> {
    let IrExpr::IncDec {
        target,
        op: IrIncDecOp::Dec,
        prefix: false,
        ty,
        ..
    } = condition
    else {
        return Ok(None);
    };
    let IrExpr::Var {
        name,
        ty: target_ty,
        ..
    } = target.as_ref()
    else {
        return Ok(None);
    };
    if !symbols.contains(name) {
        return Err(format!(
            "while condition decrement target {name} is not declared"
        ));
    }
    if !is_usize(target_ty) || !is_usize(ty) {
        return Ok(None);
    }

    let name = emit_identifier(name, "while condition decrement target")?;
    let counter_ty = emit_scalar_type(target_ty)
        .map_err(|detail| format!("while condition decrement target has {detail}"))?;
    let zero = zero_literal_for_type(target_ty)
        .map_err(|detail| format!("while condition decrement zero {detail}"))?;
    let one = emit_integer_literal(1, target_ty)
        .map_err(|detail| format!("while condition decrement step {detail}"))?;
    let snapshot = emit_identifier(
        &first_available_temp_name(&format!("{name}_before_dec"), symbols),
        "while condition decrement snapshot",
    )?;

    let indent = "    ".repeat(indent_level);
    let inner_indent = "    ".repeat(indent_level + 1);
    let break_indent = "    ".repeat(indent_level + 2);
    let mut block = String::new();
    block.push_str(&format!("{indent}loop {{\n"));
    block.push_str(&format!(
        "{inner_indent}let {snapshot}: {counter_ty} = {name};\n"
    ));
    block.push_str(&format!(
        "{inner_indent}{name} = {name}.wrapping_sub({one});\n"
    ));
    block.push_str(&format!("{inner_indent}if {snapshot} == {zero} {{\n"));
    block.push_str(&format!("{break_indent}break;\n"));
    block.push_str(&format!("{inner_indent}}}\n"));

    let mut loop_symbols = symbols.clone();
    for (index, stmt) in body.iter().enumerate() {
        let line = emit_stmt(
            stmt,
            return_type,
            indent_level + 1,
            &mut loop_symbols,
            context,
            LoopContext::While,
        )
        .map_err(|detail| format!("while body[{index}].{detail}"))?;
        block.push_str(&line);
    }
    block.push_str(&format!("{indent}}}\n"));
    Ok(Some(block))
}

fn emit_prefix_decrement_while_loop(
    condition: &IrExpr,
    body: &[IrStmt],
    return_type: &IrType,
    indent_level: usize,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<Option<String>, String> {
    let IrExpr::IncDec {
        target,
        op: IrIncDecOp::Dec,
        prefix: true,
        ty,
        ..
    } = condition
    else {
        return Ok(None);
    };
    let IrExpr::Var {
        name,
        ty: target_ty,
        ..
    } = target.as_ref()
    else {
        return Ok(None);
    };
    if !symbols.contains(name) {
        return Err(format!(
            "while condition prefix decrement target {name} is not declared"
        ));
    }
    if !is_usize(target_ty) || !is_usize(ty) {
        return Ok(None);
    }

    let name = emit_identifier(name, "while condition prefix decrement target")?;
    let _counter_ty = emit_scalar_type(target_ty)
        .map_err(|detail| format!("while condition prefix decrement target has {detail}"))?;
    let zero = zero_literal_for_type(target_ty)
        .map_err(|detail| format!("while condition prefix decrement zero {detail}"))?;
    let one = emit_integer_literal(1, target_ty)
        .map_err(|detail| format!("while condition prefix decrement step {detail}"))?;

    let indent = "    ".repeat(indent_level);
    let inner_indent = "    ".repeat(indent_level + 1);
    let break_indent = "    ".repeat(indent_level + 2);
    let mut block = String::new();
    block.push_str(&format!("{indent}loop {{\n"));
    block.push_str(&format!(
        "{inner_indent}{name} = {name}.wrapping_sub({one});\n"
    ));
    block.push_str(&format!("{inner_indent}if {name} == {zero} {{\n"));
    block.push_str(&format!("{break_indent}break;\n"));
    block.push_str(&format!("{inner_indent}}}\n"));

    let mut loop_symbols = symbols.clone();
    for (index, stmt) in body.iter().enumerate() {
        let line = emit_stmt(
            stmt,
            return_type,
            indent_level + 1,
            &mut loop_symbols,
            context,
            LoopContext::While,
        )
        .map_err(|detail| format!("while body[{index}].{detail}"))?;
        block.push_str(&line);
    }
    block.push_str(&format!("{indent}}}\n"));
    Ok(Some(block))
}
