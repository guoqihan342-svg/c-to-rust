fn emit_bounded_for_stmt(
    stmt: &IrStmt,
    return_type: &IrType,
    indent_level: usize,
    symbols: &mut HashSet<String>,
    context: &EmitContext,
) -> Result<String, String> {
    let IrStmt::For {
        init,
        condition,
        step,
        body,
        ..
    } = stmt
    else {
        unreachable!("emit_bounded_for_stmt requires an IrStmt::For");
    };
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
