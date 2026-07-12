
fn emit_call_expr_with_prelude(
    callee: &str,
    args: &[IrExpr],
    ty: &IrType,
    symbols: &mut HashSet<String>,
    context: &EmitContext,
    indent_level: usize,
    path: &str,
) -> Result<EmittedExpr, String> {
    if let Some(emitted) =
        emit_side_effect_call_expr(callee, args, ty, symbols, context, indent_level, path)?
    {
        return Ok(emitted);
    }
    Ok(EmittedExpr {
        prelude: String::new(),
        expr: emit_call_expr(callee, args, ty, symbols, context)
            .map_err(|detail| format!("{path} {detail}"))?,
    })
}

fn emit_side_effect_call_callee(callee: &str, ty: &IrType, path: &str) -> Result<String, String> {
    let callee =
        emit_identifier(callee, "call callee").map_err(|detail| format!("{path} {detail}"))?;
    if matches!(
        callee.as_str(),
        "assert" | "abs" | "strlen" | "strnlen" | "memcmp"
    ) {
        return Err(format!(
            "{path} call callee {callee} cannot use increment/decrement value arguments"
        ));
    }
    if reserved_c_macro_or_stdlib_callee(&callee) {
        return Err(format!(
            "{path} call callee \"{callee}\" is reserved C macro/stdlib/extern surface and requires explicit lowering or extern binding"
        ));
    }
    if matches!(ty.kind, IrTypeKind::Pointer { .. }) {
        return Err(format!(
            "{path} call result has pointer value return {} requires explicit ownership/lifetime/ABI lowering",
            type_label(ty)
        ));
    }
    if !is_void_type(ty) {
        emit_scalar_type(ty).map_err(|detail| format!("{path} call result has {detail}"))?;
    }

    Ok(callee)
}

fn emit_side_effect_call_expr(
    callee: &str,
    args: &[IrExpr],
    ty: &IrType,
    symbols: &mut HashSet<String>,
    context: &EmitContext,
    indent_level: usize,
    path: &str,
) -> Result<Option<EmittedExpr>, String> {
    let side_effect_args = side_effect_call_args(args)?;
    if side_effect_args.is_empty() {
        return Ok(None);
    }
    validate_bounded_call_args(args, context).map_err(|detail| format!("{path} {detail}"))?;

    let callee = emit_side_effect_call_callee(callee, ty, path)?;
    let mut prelude = String::new();
    let mut emitted_args = Vec::with_capacity(args.len());
    for (index, arg) in args.iter().enumerate() {
        if side_effect_args
            .iter()
            .any(|(side_effect_index, _)| *side_effect_index == index)
        {
            let emitted = emit_expr_with_prelude(
                arg,
                symbols,
                context,
                indent_level,
                &format!("{path} call arg[{index}]"),
            )?;
            prelude.push_str(&emitted.prelude);
            emitted_args.push(emitted.expr);
        } else {
            emitted_args.push(
                emit_call_arg_expr(arg, symbols, context)
                    .map_err(|detail| format!("{path} call arg[{index}] {detail}"))?,
            );
        }
    }
    Ok(Some(EmittedExpr {
        prelude,
        expr: format!("{callee}({})", emitted_args.join(", ")),
    }))
}

fn validate_binary_side_effect_operand_order(
    lhs: &IrExpr,
    rhs: &IrExpr,
    path: &str,
) -> Result<(), String> {
    if let Some(assigned_var) = side_effect_expr_assigned_var_name(lhs)? {
        if expr_mentions_var(rhs, assigned_var) {
            return Err(format!(
                "{path} binary rhs reads variable {assigned_var} modified by lhs side-effect expression"
            ));
        }
    }
    if let Some(assigned_var) = side_effect_expr_assigned_var_name(rhs)? {
        if expr_mentions_var(lhs, assigned_var) {
            return Err(format!(
                "{path} binary lhs reads variable {assigned_var} modified by rhs side-effect expression"
            ));
        }
    }
    Ok(())
}

fn side_effect_call_args(args: &[IrExpr]) -> Result<Vec<(usize, &str)>, String> {
    let mut found = Vec::new();
    for (index, arg) in args.iter().enumerate() {
        let Some(assigned_var) = side_effect_expr_assigned_var_name(arg)? else {
            continue;
        };
        if found
            .iter()
            .any(|(_, existing_var)| *existing_var == assigned_var)
        {
            return Err(format!(
                "call arguments cannot modify variable {assigned_var} more than once"
            ));
        }
        found.push((index, assigned_var));
    }
    Ok(found)
}

fn side_effect_expr_assigned_var_name(expr: &IrExpr) -> Result<Option<&str>, String> {
    if let Some(name) = scalar_inc_dec_assigned_var_name(expr) {
        return Ok(Some(name.as_str()));
    }
    if let Some(name) = member_inc_dec_assigned_base_var_name(expr) {
        return Ok(Some(name.as_str()));
    }
    let IrExpr::Call { args, .. } = expr else {
        return Ok(None);
    };
    let found = side_effect_call_args(args)?;
    match found.as_slice() {
        [] => Ok(None),
        [(_, name)] => Ok(Some(*name)),
        _ => Err(
            "nested call argument cannot use increment/decrement value semantics for more than one variable"
                .to_string(),
        ),
    }
}

fn member_inc_dec_assigned_base_var_name(expr: &IrExpr) -> Option<&String> {
    let IrExpr::IncDec { target, ty, .. } = expr else {
        return None;
    };
    let IrExpr::Member {
        base,
        ty: target_ty,
        is_arrow: true,
        ..
    } = target.as_ref()
    else {
        return None;
    };
    let IrExpr::Var { name, .. } = base.as_ref() else {
        return None;
    };
    (target_ty == ty && is_integer_type(target_ty)).then_some(name)
}

fn expr_mentions_var(expr: &IrExpr, expected: &str) -> bool {
    match expr {
        IrExpr::Var { name, .. } => name == expected,
        IrExpr::Binary { lhs, rhs, .. } => {
            expr_mentions_var(lhs, expected) || expr_mentions_var(rhs, expected)
        }
        IrExpr::Unary { operand, .. }
        | IrExpr::Cast { expr: operand, .. }
        | IrExpr::LValueToRValue { expr: operand, .. }
        | IrExpr::ArrayToPointerDecay { expr: operand, .. }
        | IrExpr::FunctionToPointerDecay { expr: operand, .. }
        | IrExpr::AddrOf { operand, .. }
        | IrExpr::MutableVoidPointerAddress { operand, .. } => {
            expr_mentions_var(operand, expected)
        }
        IrExpr::Conditional {
            condition,
            then_expr,
            else_expr,
            ..
        } => {
            expr_mentions_var(condition, expected)
                || expr_mentions_var(then_expr, expected)
                || expr_mentions_var(else_expr, expected)
        }
        IrExpr::Index { base, index, .. } => {
            expr_mentions_var(base, expected) || expr_mentions_var(index, expected)
        }
        IrExpr::Member { base, .. } => expr_mentions_var(base, expected),
        IrExpr::ArrayLiteral { elements, .. } => {
            elements.iter().any(|element| expr_mentions_var(element, expected))
        }
        IrExpr::Call { args, .. } => args.iter().any(|arg| expr_mentions_var(arg, expected)),
        IrExpr::IncDec { target, .. } => expr_mentions_var(target, expected),
        IrExpr::Deref { ptr, .. } => expr_mentions_var(ptr, expected),
        IrExpr::LitInt { .. }
        | IrExpr::NullPtr { .. }
        | IrExpr::Unsupported { .. } => false,
    }
}

fn emit_single_inc_dec_call_statement_expr(
    expr: &IrExpr,
    symbols: &mut HashSet<String>,
    context: &EmitContext,
    indent_level: usize,
    path: &str,
) -> Result<Option<EmittedExpr>, String> {
    let IrExpr::Call {
        callee, args, ty, ..
    } = expr
    else {
        return Ok(None);
    };
    if side_effect_call_args(args)?.is_empty() {
        return Ok(None);
    }
    emit_call_expr_with_prelude(callee, args, ty, symbols, context, indent_level, path).map(Some)
}

fn emit_prefix_inc_dec_value_expr(
    expr: &IrExpr,
    symbols: &HashSet<String>,
    context: &EmitContext,
    indent_level: usize,
) -> Result<Option<EmittedExpr>, String> {
    let IrExpr::IncDec {
        target,
        op,
        prefix: true,
        ty,
        ..
    } = expr
    else {
        return Ok(None);
    };
    let indent = "    ".repeat(indent_level);

    if let Some(line) = emit_prefix_inc_dec_statement(expr, symbols)? {
        let IrExpr::Var { name, .. } = target.as_ref() else {
            return Ok(None);
        };
        let name = emit_identifier(name, "prefix inc/dec value target")?;
        return Ok(Some(EmittedExpr {
            prelude: format!("{indent}{line}\n"),
            expr: name,
        }));
    }

    let Some((target_name, target_ty)) =
        emit_member_inc_dec_value_target(target, ty, symbols, context, "prefix inc/dec target")?
    else {
        return Ok(None);
    };
    let one = emit_integer_literal(1, target_ty)
        .map_err(|detail| format!("prefix inc/dec step {detail}"))?;
    let rhs = emit_inc_dec_assignment_rhs(&target_name, target_ty, op, &one).ok_or_else(|| {
        format!(
            "prefix inc/dec target {target_name} has unsupported type {}",
            type_label(target_ty)
        )
    })?;
    Ok(Some(EmittedExpr {
        prelude: format!("{indent}{target_name} = {rhs};\n"),
        expr: target_name,
    }))
}

fn emit_postfix_inc_dec_value_expr(
    expr: &IrExpr,
    symbols: &mut HashSet<String>,
    context: &EmitContext,
    indent_level: usize,
) -> Result<Option<EmittedExpr>, String> {
    let IrExpr::IncDec {
        target,
        op,
        prefix: false,
        ty,
        ..
    } = expr
    else {
        return Ok(None);
    };
    let (name, target_ty) = if let IrExpr::Var {
        name,
        ty: target_ty,
        ..
    } = target.as_ref()
    {
        if !symbols.contains(name) {
            return Err(format!("postfix inc/dec target {name} is not declared"));
        }
        if target_ty != ty {
            return Err(format!(
                "postfix inc/dec target {name} type {} does not match result type {}",
                type_label(target_ty),
                type_label(ty)
            ));
        }
        if !is_integer_type(target_ty) {
            return Err(format!(
                "postfix inc/dec target {name} has unsupported type {}",
                type_label(target_ty)
            ));
        }
        (emit_identifier(name, "postfix inc/dec target")?, target_ty)
    } else if let Some((target_name, target_ty)) =
        emit_member_inc_dec_value_target(target, ty, symbols, context, "postfix inc/dec target")?
    {
        (target_name, target_ty)
    } else {
        return Ok(None);
    };
    let one = emit_integer_literal(1, target_ty)
        .map_err(|detail| format!("postfix inc/dec step {detail}"))?;
    let rhs = emit_inc_dec_assignment_rhs(&name, target_ty, op, &one).ok_or_else(|| {
        format!(
            "postfix inc/dec target {name} has unsupported type {}",
            type_label(target_ty)
        )
    })?;
    let temp_prefix = match op {
        IrIncDecOp::Inc => "post_inc_value",
        IrIncDecOp::Dec => "post_dec_value",
    };
    let temp = first_available_named_temp(temp_prefix, symbols);
    symbols.insert(temp.clone());
    let temp = emit_identifier(&temp, "postfix inc/dec value snapshot")?;
    let snapshot_ty = emit_scalar_type(target_ty)
        .map_err(|detail| format!("postfix inc/dec snapshot has {detail}"))?;
    let indent = "    ".repeat(indent_level);

    Ok(Some(EmittedExpr {
        prelude: format!("{indent}let {temp}: {snapshot_ty} = {name};\n{indent}{name} = {rhs};\n"),
        expr: temp,
    }))
}
