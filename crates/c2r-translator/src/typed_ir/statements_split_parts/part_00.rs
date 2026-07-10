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
            if let Some(decl_ty) = emit_function_pointer_param_type(ty)
                .map_err(|detail| format!("decl {name} has {detail}"))?
            {
                let Some(init) = init else {
                    symbols.insert(name.clone());
                    return Ok(format!("{indent}let mut {decl_name}: {decl_ty};\n"));
                };
                let IrExpr::FunctionToPointerDecay { target, expr, .. } = init else {
                    return Err(format!(
                        "decl {name} function pointer initializer must be a direct function-to-pointer decay"
                    ));
                };
                if target != ty {
                    return Err(format!(
                        "decl {name} function pointer initializer target {} does not match declared type {}",
                        type_label(target),
                        type_label(ty)
                    ));
                }
                let init = emit_function_pointer_decay_call_arg(target, expr)
                    .map_err(|detail| format!("decl {name} initializer {detail}"))?;
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
            if let Some(emitted) = emit_record_pointer_field_assignment_value(
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
            if let Some(line) =
                emit_function_pointer_decay_assignment(target, value, &target_name, target_ty)?
            {
                return Ok(format!("{indent}{line}\n"));
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
                if let Some(line) =
                    emit_function_pointer_decay_return(value, return_type, indent_level)?
                {
                    return Ok(line);
                }
                if let Some(line) = emit_record_pointer_field_raw_pointer_return(
                    value,
                    return_type,
                    indent_level,
                    symbols,
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
            if let Some(line) = emit_discarded_inc_dec_statement(expr, symbols, context)
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
            let emitted_condition = match condition {
                IrExpr::Binary {
                    op, lhs, rhs, ty, ..
                } => emit_direct_inc_dec_comparison_condition_expr(
                    op,
                    lhs,
                    rhs,
                    ty,
                    symbols,
                    context,
                    indent_level,
                    "if condition",
                )?,
                _ => None,
            };
            let (condition_prelude, condition) = match emitted_condition {
                Some(emitted) => (emitted.prelude, emitted.expr),
                None => (
                    String::new(),
                    emit_condition_expr(condition, symbols, context)
                        .map_err(|detail| format!("if condition {detail}"))?,
                ),
            };
            let mut block = String::new();
            block.push_str(&condition_prelude);
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
            let emitted_condition = match condition {
                IrExpr::Binary {
                    op, lhs, rhs, ty, ..
                } => {
                    let mut condition_symbols = symbols.clone();
                    emit_direct_inc_dec_comparison_condition_expr(
                        op,
                        lhs,
                        rhs,
                        ty,
                        &mut condition_symbols,
                        context,
                        indent_level + 1,
                        "while condition",
                    )?
                }
                _ => None,
            };
            if let Some(emitted_condition) = emitted_condition {
                let inner_indent = "    ".repeat(indent_level + 1);
                let break_indent = "    ".repeat(indent_level + 2);
                let mut loop_symbols = symbols.clone();
                let mut block = format!("{indent}loop {{\n");
                block.push_str(&emitted_condition.prelude);
                block.push_str(&format!(
                    "{inner_indent}if !{} {{\n{break_indent}break;\n{inner_indent}}}\n",
                    emitted_condition.expr
                ));
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
        } => {
            if let Some(block) = emit_for_with_direct_inc_dec_comparison_condition(
                init,
                condition.as_ref(),
                step.as_deref(),
                body,
                return_type,
                indent_level,
                symbols,
                context,
            )? {
                return Ok(block);
            }
            emit_for_stmt(
                init,
                condition.as_ref(),
                step.as_deref(),
                body,
                return_type,
                indent_level,
                symbols,
                context,
            )
        }
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
    let emitted_condition = match condition {
        IrExpr::Binary {
            op, lhs, rhs, ty, ..
        } => {
            let mut condition_symbols = symbols.clone();
            emit_direct_inc_dec_comparison_condition_expr(
                op,
                lhs,
                rhs,
                ty,
                &mut condition_symbols,
                context,
                indent_level,
                &format!("do while {path}"),
            )?
        }
        _ => None,
    };
    if let Some(emitted_condition) = emitted_condition {
        let indent = "    ".repeat(indent_level);
        let inner_indent = "    ".repeat(indent_level + 1);
        return Ok(format!(
            "{}{indent}if !{} {{\n{inner_indent}break;\n{indent}}}\n",
            emitted_condition.prelude, emitted_condition.expr
        ));
    }
    let condition = emit_condition_expr(condition, symbols, context)
        .map_err(|detail| format!("do while {path} {detail}"))?;
    let indent = "    ".repeat(indent_level);
    let inner_indent = "    ".repeat(indent_level + 1);
    Ok(format!(
        "{indent}if !({condition}) {{\n{inner_indent}break;\n{indent}}}\n"
    ))
}

fn emit_for_with_direct_inc_dec_comparison_condition(
    init: &[IrStmt],
    condition: Option<&IrExpr>,
    step: Option<&IrStmt>,
    body: &[IrStmt],
    return_type: &IrType,
    indent_level: usize,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<Option<String>, String> {
    let Some(IrExpr::Binary {
        op, lhs, rhs, ty, ..
    }) = condition
    else {
        return Ok(None);
    };

    let indent = "    ".repeat(indent_level);
    let inner_indent = "    ".repeat(indent_level + 1);
    let loop_indent = "    ".repeat(indent_level + 2);
    let break_indent = "    ".repeat(indent_level + 3);
    let mut loop_symbols = symbols.clone();
    let mut init_block = String::new();
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
        init_block.push_str(&line);
    }

    let mut condition_symbols = loop_symbols.clone();
    let Some(emitted_condition) = emit_direct_inc_dec_comparison_condition_expr(
        op,
        lhs,
        rhs,
        ty,
        &mut condition_symbols,
        context,
        indent_level + 2,
        "for condition",
    )?
    else {
        return Ok(None);
    };

    let mut block = format!("{indent}{{\n{init_block}{inner_indent}loop {{\n");
    block.push_str(&emitted_condition.prelude);
    block.push_str(&format!(
        "{loop_indent}if !{} {{\n{break_indent}break;\n{loop_indent}}}\n",
        emitted_condition.expr
    ));

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

    block.push_str(&format!("{inner_indent}}}\n{indent}}}\n"));
    Ok(Some(block))
}
