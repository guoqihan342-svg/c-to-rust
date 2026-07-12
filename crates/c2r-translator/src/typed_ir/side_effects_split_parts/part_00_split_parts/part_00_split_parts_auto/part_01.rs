
fn emit_direct_inc_dec_comparison_value_expr(
    op: &IrBinOp,
    lhs: &IrExpr,
    rhs: &IrExpr,
    result_ty: &IrType,
    symbols: &mut HashSet<String>,
    context: &EmitContext,
    indent_level: usize,
    path: &str,
) -> Result<Option<EmittedExpr>, String> {
    let Some(emitted) = emit_direct_inc_dec_comparison_condition_expr(
        op,
        lhs,
        rhs,
        result_ty,
        symbols,
        context,
        indent_level,
        path,
    )?
    else {
        return Ok(None);
    };
    let one = emit_integer_literal(1, result_ty)
        .map_err(|detail| format!("{path} comparison true literal {detail}"))?;
    let zero = emit_integer_literal(0, result_ty)
        .map_err(|detail| format!("{path} comparison false literal {detail}"))?;

    Ok(Some(EmittedExpr {
        prelude: emitted.prelude,
        expr: format!("(if {} {{ {one} }} else {{ {zero} }})", emitted.expr),
    }))
}

fn emit_direct_inc_dec_comparison_condition_expr(
    op: &IrBinOp,
    lhs: &IrExpr,
    rhs: &IrExpr,
    result_ty: &IrType,
    symbols: &mut HashSet<String>,
    context: &EmitContext,
    indent_level: usize,
    path: &str,
) -> Result<Option<EmittedExpr>, String> {
    let Ok(op) = emit_comparison_op(op) else {
        return Ok(None);
    };
    let lhs_is_direct_inc_dec = matches!(lhs, IrExpr::IncDec { .. });
    let rhs_is_direct_inc_dec = matches!(rhs, IrExpr::IncDec { .. });
    let (inc_dec, other, inc_dec_is_lhs) = match (
        lhs_is_direct_inc_dec,
        rhs_is_direct_inc_dec,
    ) {
        (false, false) => return Ok(None),
        (true, true) => {
            return Err(format!(
                "{path} comparison cannot lower two direct increment/decrement operands"
            ));
        }
        (true, false) => (lhs, rhs, true),
        (false, true) => (rhs, lhs, false),
    };
    if scalar_inc_dec_assigned_var_name(inc_dec).is_none() {
        return Ok(None);
    }
    if let Some(callee) = find_call_callee(other) {
        return Err(format!(
            "{path} comparison operand call expression {callee} is unsupported"
        ));
    }
    if let Some(kind) = find_direct_inc_dec_comparison_memory_operand(other) {
        return Err(format!(
            "{path} comparison operand {kind} expression is unsupported"
        ));
    }
    if expr_has_inc_dec(other) {
        return Err(format!(
            "{path} comparison cannot lower more than one increment/decrement side effect"
        ));
    }
    validate_binary_side_effect_operand_order(lhs, rhs, path)?;
    validate_comparison_condition_types(lhs, rhs, result_ty, op)
        .map_err(|detail| format!("{path} {detail}"))?;

    let other = emit_expr(other, symbols, context).map_err(|detail| {
        format!(
            "{path} comparison {} {detail}",
            if inc_dec_is_lhs { "rhs" } else { "lhs" }
        )
    })?;
    let mut prelude_symbols = symbols.clone();
    let emitted_inc_dec = emit_expr_with_prelude(
        inc_dec,
        &mut prelude_symbols,
        context,
        indent_level,
        &format!(
            "{path} comparison {}",
            if inc_dec_is_lhs { "lhs" } else { "rhs" }
        ),
    )?;
    let (lhs, rhs) = if inc_dec_is_lhs {
        (emitted_inc_dec.expr, other)
    } else {
        (other, emitted_inc_dec.expr)
    };
    *symbols = prelude_symbols;

    Ok(Some(EmittedExpr {
        prelude: emitted_inc_dec.prelude,
        expr: format!("({lhs} {op} {rhs})"),
    }))
}

fn find_direct_inc_dec_comparison_memory_operand(expr: &IrExpr) -> Option<&'static str> {
    match expr {
        IrExpr::Deref { .. } => Some("deref"),
        IrExpr::Member { .. } => Some("member"),
        IrExpr::Binary { lhs, rhs, .. } => find_direct_inc_dec_comparison_memory_operand(lhs)
            .or_else(|| find_direct_inc_dec_comparison_memory_operand(rhs)),
        IrExpr::Unary { operand, .. }
        | IrExpr::Cast { expr: operand, .. }
        | IrExpr::LValueToRValue { expr: operand, .. }
        | IrExpr::ArrayToPointerDecay { expr: operand, .. }
        | IrExpr::FunctionToPointerDecay { expr: operand, .. }
        | IrExpr::AddrOf { operand, .. }
        | IrExpr::MutableVoidPointerAddress { operand, .. }
        | IrExpr::IncDec {
            target: operand, ..
        } => find_direct_inc_dec_comparison_memory_operand(operand),
        IrExpr::Conditional {
            condition,
            then_expr,
            else_expr,
            ..
        } => find_direct_inc_dec_comparison_memory_operand(condition)
            .or_else(|| find_direct_inc_dec_comparison_memory_operand(then_expr))
            .or_else(|| find_direct_inc_dec_comparison_memory_operand(else_expr)),
        IrExpr::Index { .. } => Some("index"),
        IrExpr::ArrayLiteral { elements, .. } => elements
            .iter()
            .find_map(find_direct_inc_dec_comparison_memory_operand),
        IrExpr::Call { args, .. } => args
            .iter()
            .find_map(find_direct_inc_dec_comparison_memory_operand),
        IrExpr::LitInt { .. }
        | IrExpr::NullPtr { .. }
        | IrExpr::Var { .. }
        | IrExpr::Unsupported { .. } => None,
    }
}
