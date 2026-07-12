fn validate_expr_matches_type(
    expr: &IrExpr,
    expected_ty: &IrType,
    context: &str,
) -> Result<(), String> {
    let actual_ty = expr_type(expr).ok_or_else(|| format!("{context} type is unsupported"))?;
    validate_record_value_type_matches(actual_ty, expected_ty, context)?;
    let expected = emit_value_type(expected_ty)
        .map_err(|detail| format!("{context} expected type has {detail}"))?;
    let actual = emit_value_type(actual_ty).map_err(|detail| format!("{context} has {detail}"))?;
    if actual != expected {
        Err(format!(
            "{context} type {actual} does not match expected type {expected}"
        ))
    } else {
        Ok(())
    }
}

fn validate_record_value_type_matches(
    actual_ty: &IrType,
    expected_ty: &IrType,
    context: &str,
) -> Result<(), String> {
    let (
        IrTypeKind::Record {
            name: actual_name,
            fields: actual_fields,
        },
        IrTypeKind::Record {
            name: expected_name,
            fields: expected_fields,
        },
    ) = (&actual_ty.kind, &expected_ty.kind)
    else {
        return Ok(());
    };
    if actual_name != expected_name {
        return Err(format!(
            "{context} record type {actual_name} does not match expected record type {expected_name}"
        ));
    }
    let Some(expected_fields) = expected_fields else {
        return Ok(());
    };
    match actual_fields {
        Some(actual_fields) if actual_fields == expected_fields => Ok(()),
        Some(_) => Err(format!(
            "{context} record field inventory does not match expected record type {expected_name}"
        )),
        None => Err(format!(
            "{context} record type {actual_name} lacks field inventory required by expected record type {expected_name}"
        )),
    }
}

fn validate_signed_unary_minus_operand(expr: &IrExpr, result_ty: &IrType) -> Result<(), String> {
    let IrTypeKind::Integer {
        signed: true,
        width: result_width,
    } = result_ty.kind
    else {
        return Err(format!(
            "unary minus result type {} is not a signed integer",
            type_label(result_ty)
        ));
    };
    let operand_ty =
        expr_type(expr).ok_or_else(|| "unary minus operand type is unsupported".to_string())?;
    let IrTypeKind::Integer {
        signed: true,
        width: operand_width,
    } = operand_ty.kind
    else {
        return Err(format!(
            "unary minus operand type {} is not a signed integer",
            type_label(operand_ty)
        ));
    };
    let result_ty =
        emit_scalar_type(result_ty).map_err(|detail| format!("unary minus result has {detail}"))?;
    let operand_ty = emit_scalar_type(operand_ty)
        .map_err(|detail| format!("unary minus operand has {detail}"))?;
    if operand_width == result_width && operand_ty == result_ty {
        Ok(())
    } else {
        Err(format!(
            "unary minus operand type {operand_ty} does not match result type {result_ty}"
        ))
    }
}

fn emit_condition_expr(
    expr: &IrExpr,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<String, String> {
    if matches!(expr, IrExpr::Conditional { .. }) {
        return Err("conditional expression is unsupported in condition positions".to_string());
    }
    if let IrExpr::Unary {
        op: IrUnOp::Not,
        operand,
        ty,
        ..
    } = expr
    {
        return emit_logical_not_condition_expr(operand, ty, symbols, context);
    }
    if let Some(condition) = emit_direct_call_truthiness_condition_expr(
        expr,
        symbols,
        context,
        DirectCallConditionPolarity::Positive,
    )? {
        return Ok(condition);
    }
    if let Some(callee) = find_call_callee(expr) {
        return Err(format!("call expression {callee} is unsupported"));
    }
    if let IrExpr::Binary {
        op, lhs, rhs, ty, ..
    } = expr
    {
        if let Some(condition) =
            emit_short_circuit_condition_expr(op, lhs, rhs, ty, symbols, context)?
        {
            return Ok(condition);
        }
    }
    if let Some(condition) = emit_comparison_condition_expr(expr, symbols, context)? {
        return Ok(condition);
    }
    if let Some(condition) = emit_nullable_pointer_truthiness_condition(expr, symbols, context)? {
        return Ok(condition);
    }
    let ty = expr_type(expr).ok_or_else(|| "type is unsupported".to_string())?;
    let zero = zero_literal_for_type(ty)?;
    let expr = emit_expr(expr, symbols, context)?;
    Ok(format!("{expr} != {zero}"))
}

#[derive(Clone, Copy)]
enum DirectCallConditionPolarity {
    Positive,
    Negated,
}

fn emit_direct_call_truthiness_condition_expr(
    expr: &IrExpr,
    symbols: &HashSet<String>,
    context: &EmitContext,
    polarity: DirectCallConditionPolarity,
) -> Result<Option<String>, String> {
    let IrExpr::Call {
        callee, args, ty, ..
    } = expr
    else {
        return Ok(None);
    };
    if !is_c_bool_type(ty) {
        return Ok(None);
    }
    let zero =
        zero_literal_for_type(ty).map_err(|detail| format!("condition call zero {detail}"))?;
    let call = emit_call_expr(callee, args, ty, symbols, context)
        .map_err(|detail| format!("condition call {detail}"))?;
    let op = match polarity {
        DirectCallConditionPolarity::Positive => "!=",
        DirectCallConditionPolarity::Negated => "==",
    };
    Ok(Some(format!("{call} {op} {zero}")))
}

fn emit_nullable_pointer_truthiness_condition(
    expr: &IrExpr,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<Option<String>, String> {
    let Some((name, ty)) = nullable_pointer_truthiness_var_parts(expr) else {
        return Ok(None);
    };
    if !context.is_nullable_pointer_param(name) {
        return Ok(None);
    }
    if !symbols.contains(name) {
        return Err(format!("nullable pointer param {name} is not declared"));
    }
    validate_nullable_pointer_type(name, ty)?;
    let name = emit_identifier(name, "nullable pointer condition")?;
    Ok(Some(format!("{name}.is_some()")))
}

fn emit_comparison_condition_expr(
    expr: &IrExpr,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<Option<String>, String> {
    if let IrExpr::Binary {
        op, lhs, rhs, ty, ..
    } = expr
    {
        return emit_comparison_condition_from_parts(op, lhs, rhs, ty, symbols, context);
    }
    Ok(None)
}

fn emit_comparison_condition_from_parts(
    op: &IrBinOp,
    lhs: &IrExpr,
    rhs: &IrExpr,
    result_ty: &IrType,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<Option<String>, String> {
    let Ok(op) = emit_comparison_op(op) else {
        return Ok(None);
    };
    if let Some(callee) = find_call_callee(lhs).or_else(|| find_call_callee(rhs)) {
        return Err(format!(
            "comparison operand call expression {callee} is unsupported"
        ));
    }
    if let Some(condition) =
        emit_null_pointer_comparison_condition(op, lhs, rhs, result_ty, symbols, context)?
    {
        return Ok(Some(condition));
    }
    validate_comparison_condition_types(lhs, rhs, result_ty, op)?;
    let lhs =
        emit_expr(lhs, symbols, context).map_err(|detail| format!("comparison lhs {detail}"))?;
    let rhs =
        emit_expr(rhs, symbols, context).map_err(|detail| format!("comparison rhs {detail}"))?;
    Ok(Some(format!("({lhs} {op} {rhs})")))
}

fn emit_short_circuit_condition_expr(
    op: &IrBinOp,
    lhs: &IrExpr,
    rhs: &IrExpr,
    result_ty: &IrType,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<Option<String>, String> {
    let op = match op {
        IrBinOp::LogAnd => "&&",
        IrBinOp::LogOr => "||",
        _ => return Ok(None),
    };
    if !is_c_int_type(result_ty) {
        return Err(format!(
            "short-circuit result type must be C int, got {}",
            type_label(result_ty)
        ));
    }
    let lhs =
        emit_condition_expr(lhs, symbols, context).map_err(|detail| format!("lhs {detail}"))?;
    let rhs =
        emit_condition_expr(rhs, symbols, context).map_err(|detail| format!("rhs {detail}"))?;
    Ok(Some(format!("({lhs} {op} {rhs})")))
}

fn emit_short_circuit_value_expr(
    op: &IrBinOp,
    lhs: &IrExpr,
    rhs: &IrExpr,
    result_ty: &IrType,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<Option<String>, String> {
    let Some(condition) =
        emit_short_circuit_condition_expr(op, lhs, rhs, result_ty, symbols, context)?
    else {
        return Ok(None);
    };
    let one = emit_integer_literal(1, result_ty)
        .map_err(|detail| format!("short-circuit true literal {detail}"))?;
    let zero = emit_integer_literal(0, result_ty)
        .map_err(|detail| format!("short-circuit false literal {detail}"))?;
    Ok(Some(format!(
        "(if {condition} {{ {one} }} else {{ {zero} }})"
    )))
}
