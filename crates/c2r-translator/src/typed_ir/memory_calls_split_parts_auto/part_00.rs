fn emit_c_memset_statement(
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
    if callee != "memset" {
        return Ok(None);
    }
    let (dest, byte, count) = validate_c_memset_statement_shape(args, ty)?;
    let dest = emit_identifier(dest, "C memset destination")?;
    if !symbols.contains(&dest) {
        return Err(format!(
            "C memset destination {dest} is not a function parameter or local binding"
        ));
    }
    let count =
        emit_expr(count, symbols, context).map_err(|detail| format!("C memset size {detail}"))?;
    Ok(Some(format!(
        "{dest}.get_mut(..({count} as usize)).expect(\"C memset precondition violated\").fill({byte}u8);"
    )))
}

fn emit_c_memcpy_statement(
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
    if callee != "memcpy" {
        return Ok(None);
    }
    let (dest, src, count) = validate_c_memcpy_statement_shape(args, ty)?;
    let dest = emit_identifier(dest, "C memcpy destination")?;
    let src = emit_identifier(src, "C memcpy source")?;
    if !symbols.contains(&dest) {
        return Err(format!(
            "C memcpy destination {dest} is not a function parameter or local binding"
        ));
    }
    if !symbols.contains(&src) {
        return Err(format!(
            "C memcpy source {src} is not a function parameter or local binding"
        ));
    }
    let count =
        emit_expr(count, symbols, context).map_err(|detail| format!("C memcpy size {detail}"))?;
    Ok(Some(format!(
        "{dest}.get_mut(..({count} as usize)).expect(\"C memcpy destination precondition violated\").copy_from_slice({src}.get(..({count} as usize)).expect(\"C memcpy source precondition violated\"));"
    )))
}

fn emit_prefix_inc_dec_statement(
    expr: &IrExpr,
    symbols: &HashSet<String>,
) -> Result<Option<String>, String> {
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
    let IrExpr::Var {
        name,
        ty: target_ty,
        ..
    } = target.as_ref()
    else {
        return Ok(None);
    };
    if !symbols.contains(name) {
        return Err(format!("prefix inc/dec target {name} is not declared"));
    }
    if target_ty != ty {
        return Err(format!(
            "prefix inc/dec target {name} type {} does not match result type {}",
            type_label(target_ty),
            type_label(ty)
        ));
    }
    if !is_integer_type(target_ty) {
        return Err(format!(
            "prefix inc/dec target {name} has unsupported type {}",
            type_label(target_ty)
        ));
    }

    let name = emit_identifier(name, "prefix inc/dec target")?;
    let one = emit_integer_literal(1, target_ty)
        .map_err(|detail| format!("prefix inc/dec step {detail}"))?;
    let rhs = emit_inc_dec_assignment_rhs(&name, target_ty, op, &one).ok_or_else(|| {
        format!(
            "prefix inc/dec target {name} has unsupported type {}",
            type_label(target_ty)
        )
    })?;
    Ok(Some(format!("{name} = {rhs};")))
}

fn emit_discarded_inc_dec_statement(
    expr: &IrExpr,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<Option<String>, String> {
    let IrExpr::IncDec { target, op, ty, .. } = expr else {
        return Ok(None);
    };

    if let Some(line) = emit_discarded_scalar_inc_dec_statement(target, ty, op, symbols)? {
        return Ok(Some(line));
    }
    emit_discarded_record_pointer_member_inc_dec_statement(target, ty, op, symbols, context)
}

fn emit_discarded_scalar_inc_dec_statement(
    target: &IrExpr,
    result_ty: &IrType,
    op: &IrIncDecOp,
    symbols: &HashSet<String>,
) -> Result<Option<String>, String> {
    let IrExpr::Var {
        name,
        ty: target_ty,
        ..
    } = target
    else {
        return Ok(None);
    };
    if !symbols.contains(name) {
        return Err(format!("inc/dec statement target {name} is not declared"));
    }
    if target_ty != result_ty {
        return Err(format!(
            "inc/dec statement target {name} type {} does not match result type {}",
            type_label(target_ty),
            type_label(result_ty)
        ));
    }
    if !is_integer_type(target_ty) {
        return Err(format!(
            "inc/dec statement target {name} has unsupported type {}",
            type_label(target_ty)
        ));
    }
    let name = emit_identifier(name, "inc/dec statement target")?;
    emit_inc_dec_statement_assignment(&name, target_ty, op, "inc/dec statement")
        .map(Some)
}

fn emit_discarded_record_pointer_member_inc_dec_statement(
    target: &IrExpr,
    result_ty: &IrType,
    op: &IrIncDecOp,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<Option<String>, String> {
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
            "inc/dec statement field {field} type {} does not match result type {}",
            type_label(target_ty),
            type_label(result_ty)
        ));
    }
    if !is_integer_type(target_ty) {
        return Err(format!(
            "inc/dec statement field {field} has unsupported type {}",
            type_label(target_ty)
        ));
    }
    let Some(target_name) =
        emit_mutable_record_pointer_member_assignment_target(target, symbols, context)
            .map_err(|detail| format!("inc/dec statement {detail}"))?
    else {
        return Ok(None);
    };
    emit_inc_dec_statement_assignment(&target_name, target_ty, op, "inc/dec statement")
        .map(Some)
}

fn emit_inc_dec_statement_assignment(
    target_name: &str,
    target_ty: &IrType,
    op: &IrIncDecOp,
    path: &str,
) -> Result<String, String> {
    let one = emit_integer_literal(1, target_ty).map_err(|detail| format!("{path} step {detail}"))?;
    let rhs = emit_inc_dec_assignment_rhs(target_name, target_ty, op, &one).ok_or_else(|| {
        format!(
            "{path} target {target_name} has unsupported type {}",
            type_label(target_ty)
        )
    })?;
    Ok(format!("{target_name} = {rhs};"))
}
