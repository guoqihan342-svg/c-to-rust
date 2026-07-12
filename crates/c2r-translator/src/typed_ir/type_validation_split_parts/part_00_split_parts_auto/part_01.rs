
fn emit_comparison_value_expr(
    op: &IrBinOp,
    lhs: &IrExpr,
    rhs: &IrExpr,
    result_ty: &IrType,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<Option<String>, String> {
    let Some(condition) =
        emit_comparison_condition_from_parts(op, lhs, rhs, result_ty, symbols, context)?
    else {
        return Ok(None);
    };
    let one = emit_integer_literal(1, result_ty)
        .map_err(|detail| format!("comparison true literal {detail}"))?;
    let zero = emit_integer_literal(0, result_ty)
        .map_err(|detail| format!("comparison false literal {detail}"))?;
    Ok(Some(format!(
        "(if {condition} {{ {one} }} else {{ {zero} }})"
    )))
}

fn emit_conditional_value_expr(
    condition: &IrExpr,
    then_expr: &IrExpr,
    else_expr: &IrExpr,
    result_ty: &IrType,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<String, String> {
    emit_scalar_type(result_ty)
        .map_err(|detail| format!("conditional result type has {detail}"))?;
    if !is_integer_type(result_ty) {
        return Err(format!(
            "conditional result type {} is unsupported",
            type_label(result_ty)
        ));
    }
    validate_conditional_arm_expr(then_expr, result_ty, "then")?;
    validate_conditional_arm_expr(else_expr, result_ty, "else")?;
    let condition = emit_condition_expr(condition, symbols, context)
        .map_err(|detail| format!("conditional condition {detail}"))?;
    let then_expr = emit_expr(then_expr, symbols, context)
        .map_err(|detail| format!("conditional then expression {detail}"))?;
    let else_expr = emit_expr(else_expr, symbols, context)
        .map_err(|detail| format!("conditional else expression {detail}"))?;
    Ok(format!(
        "(if {condition} {{ {then_expr} }} else {{ {else_expr} }})"
    ))
}

fn validate_conditional_arm_expr(
    expr: &IrExpr,
    expected_ty: &IrType,
    side: &str,
) -> Result<(), String> {
    if let Some(callee) = find_call_callee(expr) {
        return Err(format!(
            "conditional {side} expression call expression {callee} is unsupported"
        ));
    }
    if expr_has_inc_dec(expr) {
        return Err(format!(
            "conditional {side} expression cannot use increment/decrement value semantics"
        ));
    }
    if count_post_increment_byte_reads(expr) > 0 {
        return Err(format!(
            "conditional {side} expression cannot use post-increment byte reads"
        ));
    }
    if expr_has_assign_or_comma(expr) {
        return Err(format!(
            "conditional {side} expression cannot use assignment or comma operators"
        ));
    }
    validate_expr_matches_type(expr, expected_ty, &format!("conditional {side} expression"))
}

fn expr_has_inc_dec(expr: &IrExpr) -> bool {
    match expr {
        IrExpr::IncDec { .. } => true,
        IrExpr::Binary { lhs, rhs, .. } => expr_has_inc_dec(lhs) || expr_has_inc_dec(rhs),
        IrExpr::Unary { operand, .. }
        | IrExpr::Cast { expr: operand, .. }
        | IrExpr::LValueToRValue { expr: operand, .. }
        | IrExpr::ArrayToPointerDecay { expr: operand, .. }
        | IrExpr::FunctionToPointerDecay { expr: operand, .. }
        | IrExpr::AddrOf { operand, .. }
        | IrExpr::MutableVoidPointerAddress { operand, .. } => expr_has_inc_dec(operand),
        IrExpr::Conditional {
            condition,
            then_expr,
            else_expr,
            ..
        } => {
            expr_has_inc_dec(condition)
                || expr_has_inc_dec(then_expr)
                || expr_has_inc_dec(else_expr)
        }
        IrExpr::Index { base, index, .. } => expr_has_inc_dec(base) || expr_has_inc_dec(index),
        IrExpr::Member { base, .. } => expr_has_inc_dec(base),
        IrExpr::ArrayLiteral { elements, .. } => elements.iter().any(expr_has_inc_dec),
        IrExpr::Call { args, .. } => args.iter().any(expr_has_inc_dec),
        IrExpr::Deref { ptr, .. } => expr_has_inc_dec(ptr),
        IrExpr::LitInt { .. }
        | IrExpr::NullPtr { .. }
        | IrExpr::Var { .. }
        | IrExpr::Unsupported { .. } => false,
    }
}

fn expr_has_assign_or_comma(expr: &IrExpr) -> bool {
    match expr {
        IrExpr::Binary {
            op: IrBinOp::Assign | IrBinOp::Comma,
            ..
        } => true,
        IrExpr::Binary { lhs, rhs, .. } => {
            expr_has_assign_or_comma(lhs) || expr_has_assign_or_comma(rhs)
        }
        IrExpr::Unary { operand, .. }
        | IrExpr::Cast { expr: operand, .. }
        | IrExpr::LValueToRValue { expr: operand, .. }
        | IrExpr::ArrayToPointerDecay { expr: operand, .. }
        | IrExpr::FunctionToPointerDecay { expr: operand, .. }
        | IrExpr::AddrOf { operand, .. }
        | IrExpr::MutableVoidPointerAddress { operand, .. } => {
            expr_has_assign_or_comma(operand)
        }
        IrExpr::Conditional {
            condition,
            then_expr,
            else_expr,
            ..
        } => {
            expr_has_assign_or_comma(condition)
                || expr_has_assign_or_comma(then_expr)
                || expr_has_assign_or_comma(else_expr)
        }
        IrExpr::Index { base, index, .. } => {
            expr_has_assign_or_comma(base) || expr_has_assign_or_comma(index)
        }
        IrExpr::Member { base, .. } => expr_has_assign_or_comma(base),
        IrExpr::ArrayLiteral { elements, .. } => elements.iter().any(expr_has_assign_or_comma),
        IrExpr::Call { args, .. } => args.iter().any(expr_has_assign_or_comma),
        IrExpr::IncDec { target, .. } => expr_has_assign_or_comma(target),
        IrExpr::Deref { ptr, .. } => expr_has_assign_or_comma(ptr),
        IrExpr::LitInt { .. }
        | IrExpr::NullPtr { .. }
        | IrExpr::Var { .. }
        | IrExpr::Unsupported { .. } => false,
    }
}

fn emit_logical_not_condition_expr(
    operand: &IrExpr,
    result_ty: &IrType,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<String, String> {
    if !is_c_int_type(result_ty) {
        return Err(format!(
            "logical not result type must be C int, got {}",
            type_label(result_ty)
        ));
    }
    if let Some(condition) = emit_direct_call_truthiness_condition_expr(
        operand,
        symbols,
        context,
        DirectCallConditionPolarity::Negated,
    )? {
        return Ok(condition);
    }
    if let Some(callee) = find_call_callee(operand) {
        return Err(format!(
            "logical not operand call expression {callee} is unsupported"
        ));
    }
    if let Some(condition) = emit_negated_comparison_condition_expr(operand, symbols, context)? {
        return Ok(condition);
    }
    let ty =
        expr_type(operand).ok_or_else(|| "logical not operand type is unsupported".to_string())?;
    let zero =
        zero_literal_for_type(ty).map_err(|detail| format!("logical not operand zero {detail}"))?;
    let operand = emit_expr(operand, symbols, context)
        .map_err(|detail| format!("logical not operand {detail}"))?;
    Ok(format!("{operand} == {zero}"))
}

fn emit_logical_not_value_expr(
    operand: &IrExpr,
    result_ty: &IrType,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<String, String> {
    let condition = emit_logical_not_condition_expr(operand, result_ty, symbols, context)?;
    let one = emit_integer_literal(1, result_ty)
        .map_err(|detail| format!("logical not true literal {detail}"))?;
    let zero = emit_integer_literal(0, result_ty)
        .map_err(|detail| format!("logical not false literal {detail}"))?;
    Ok(format!("(if {condition} {{ {one} }} else {{ {zero} }})"))
}

fn emit_negated_comparison_condition_expr(
    expr: &IrExpr,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<Option<String>, String> {
    if let IrExpr::Binary {
        op, lhs, rhs, ty, ..
    } = expr
    {
        if let Ok(negated_op) = emit_negated_comparison_op(op) {
            if let Some(condition) =
                emit_null_pointer_comparison_condition(negated_op, lhs, rhs, ty, symbols, context)?
            {
                return Ok(Some(condition));
            }
            validate_comparison_condition_types(lhs, rhs, ty, negated_op)?;
            let lhs = emit_expr(lhs, symbols, context)
                .map_err(|detail| format!("logical not operand comparison lhs {detail}"))?;
            let rhs = emit_expr(rhs, symbols, context)
                .map_err(|detail| format!("logical not operand comparison rhs {detail}"))?;
            return Ok(Some(format!("({lhs} {negated_op} {rhs})")));
        }
    }
    Ok(None)
}

fn emit_null_pointer_comparison_condition(
    op: &str,
    lhs: &IrExpr,
    rhs: &IrExpr,
    result_ty: &IrType,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<Option<String>, String> {
    let Some((name, pointer_ty)) = null_pointer_comparison_var(lhs, rhs) else {
        return Ok(None);
    };
    if !context.is_nullable_pointer_param(name) {
        return Ok(None);
    }
    if !is_c_int_type(result_ty) {
        return Err(format!(
            "comparison result type must be C int, got {}",
            type_label(result_ty)
        ));
    }
    if !symbols.contains(name) {
        return Err(format!("nullable pointer param {name} is not declared"));
    }
    validate_nullable_pointer_type(name, pointer_ty)?;
    let name = emit_identifier(name, "nullable pointer param")?;
    match op {
        "==" => Ok(Some(format!("{name}.is_none()"))),
        "!=" => Ok(Some(format!("{name}.is_some()"))),
        _ => Ok(None),
    }
}
