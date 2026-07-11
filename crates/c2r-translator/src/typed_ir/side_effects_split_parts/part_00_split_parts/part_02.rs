
fn emit_inc_dec_value_expr(
    expr: &IrExpr,
    symbols: &mut HashSet<String>,
    context: &EmitContext,
    indent_level: usize,
) -> Result<Option<EmittedExpr>, String> {
    if let Some(emitted) = emit_prefix_inc_dec_value_expr(expr, symbols, context, indent_level)? {
        return Ok(Some(emitted));
    }
    emit_postfix_inc_dec_value_expr(expr, symbols, context, indent_level)
}

fn emit_member_inc_dec_value_target<'a>(
    target: &'a IrExpr,
    result_ty: &IrType,
    symbols: &HashSet<String>,
    context: &EmitContext,
    path: &str,
) -> Result<Option<(String, &'a IrType)>, String> {
    let IrExpr::Member {
        field,
        ty: target_ty,
        is_arrow,
        ..
    } = target
    else {
        return Ok(None);
    };
    if !*is_arrow {
        return Ok(None);
    }
    if target_ty != result_ty {
        return Err(format!(
            "{path} field {field} type {} does not match result type {}",
            type_label(target_ty),
            type_label(result_ty)
        ));
    }
    if !is_integer_type(target_ty) {
        return Err(format!(
            "{path} field {field} has unsupported type {}",
            type_label(target_ty)
        ));
    }
    let Some(target_name) = emit_mutable_record_pointer_member_assignment_target(
        target, symbols, context,
    )
    .map_err(|detail| format!("{path} {detail}"))?
    else {
        return Ok(None);
    };
    Ok(Some((target_name, target_ty)))
}

fn emit_inc_dec_assignment_rhs(
    name: &str,
    target_ty: &IrType,
    op: &IrIncDecOp,
    one: &str,
) -> Option<String> {
    let bin_op = match op {
        IrIncDecOp::Inc => IrBinOp::Add,
        IrIncDecOp::Dec => IrBinOp::Sub,
    };
    if let Some(method) = unsigned_wrapping_method(&bin_op, target_ty) {
        Some(format!("{name}.{method}({one})"))
    } else if let Some((method, message)) = signed_checked_method(&bin_op, target_ty) {
        Some(format!("{name}.{method}({one}).expect(\"{message}\")"))
    } else {
        None
    }
}
