fn validate_bounded_nested_call_arg(
    callee: &str,
    args: &[IrExpr],
    ty: &IrType,
    context: Option<&EmitContext>,
) -> Result<(), String> {
    emit_identifier(callee, "nested call callee")?;
    if callee == "strlen" {
        validate_c_strlen_call_shape(args, ty)?;
        return Ok(());
    }
    if callee == "strnlen" {
        validate_c_strnlen_call_shape(args, ty)?;
        return Ok(());
    }
    if callee == "memcmp" {
        validate_c_memcmp_call_shape(args, ty)?;
        return Ok(());
    }
    if mutable_record_pointer_pointee_type(ty).is_some() {
        return validate_record_pointer_return_nested_call_arg(callee, args, ty, context);
    }
    if pointer_return_nested_call_arg_type_allowed(ty) {
        return validate_pointer_return_nested_call_arg(callee, args, ty, context);
    }
    emit_scalar_type(ty).map_err(|detail| format!("nested call result has {detail}"))?;
    validate_bounded_nested_call_plain_args(args, context)
}

fn pointer_return_nested_call_arg_type_allowed(ty: &IrType) -> bool {
    is_readonly_8_bit_pointer_type(ty) || emit_opaque_void_pointer_type(ty).is_some()
}

fn validate_pointer_return_nested_call_arg(
    callee: &str,
    args: &[IrExpr],
    ty: &IrType,
    context: Option<&EmitContext>,
) -> Result<(), String> {
    emit_identifier(callee, "pointer return nested call callee")?;
    if !pointer_return_nested_call_arg_type_allowed(ty) {
        return Err(format!(
            "pointer return nested call result {} is unsupported",
            type_label(ty)
        ));
    }
    validate_bounded_nested_call_plain_args(args, context)
}

fn validate_bounded_nested_call_plain_args(
    args: &[IrExpr],
    context: Option<&EmitContext>,
) -> Result<(), String> {
    let side_effect_args = validate_bounded_side_effect_call_args(args)?;
    if !side_effect_args.is_empty() {
        for (index, arg) in args.iter().enumerate() {
            if side_effect_args
                .iter()
                .any(|(side_effect_index, _)| *side_effect_index == index)
            {
                continue;
            }
            validate_bounded_call_arg_with_context(arg, false, context)
                .map_err(|detail| format!("nested call arg[{index}] {detail}"))?;
        }
        return Ok(());
    }
    for (index, arg) in args.iter().enumerate() {
        validate_bounded_call_arg_with_context(arg, false, context)
            .map_err(|detail| format!("nested call arg[{index}] {detail}"))?;
    }
    Ok(())
}

fn validate_record_pointer_return_nested_call_arg(
    callee: &str,
    args: &[IrExpr],
    ty: &IrType,
    context: Option<&EmitContext>,
) -> Result<(), String> {
    emit_identifier(callee, "record pointer return nested call callee")?;
    let return_pointee = mutable_record_pointer_pointee_type(ty).ok_or_else(|| {
        format!(
            "record pointer return nested call result {} must be a mutable record pointer",
            type_label(ty)
        )
    })?;
    let Some(first_arg) = args.first() else {
        return Err(
            "record pointer return nested call requires an address-of local record first argument"
                .to_string(),
        );
    };
    let IrExpr::AddrOf {
        operand,
        ty: first_arg_ty,
        ..
    } = first_arg
    else {
        return Err(
            "record pointer return nested call first argument must be address-of local record"
                .to_string(),
        );
    };
    let first_pointee = mutable_record_pointer_pointee_type(first_arg_ty).ok_or_else(|| {
        format!(
            "record pointer return nested call first argument target {} must be a mutable record pointer",
            type_label(first_arg_ty)
        )
    })?;
    validate_record_value_type_matches(
        first_pointee,
        return_pointee,
        "record pointer return nested call first argument",
    )?;
    validate_local_record_address_call_arg(operand, first_arg_ty)
        .map_err(|detail| format!("record pointer return nested call first argument {detail}"))?;
    for (index, arg) in args.iter().enumerate().skip(1) {
        if validate_record_pointer_return_call_inner_arg(arg).is_ok() {
            continue;
        }
        validate_bounded_call_arg_with_context(arg, false, context)
            .map_err(|detail| format!("record pointer return nested call arg[{index}] {detail}"))?;
    }
    Ok(())
}

fn validate_record_pointer_return_call_inner_arg(arg: &IrExpr) -> Result<(), String> {
    match arg {
        IrExpr::Var { ty, .. } if is_readonly_8_bit_pointer_type(ty) => Ok(()),
        IrExpr::Call {
            callee, args, ty, ..
        } if callee == "strlen" => validate_c_strlen_call_shape(args, ty).map(|_| ()),
        _ => Err("not a record pointer return call inner special case".to_string()),
    }
}

fn find_call_callee(expr: &IrExpr) -> Option<&str> {
    match expr {
        IrExpr::Call { callee, .. } => Some(callee),
        IrExpr::Binary { lhs, rhs, .. } => find_call_callee(lhs).or_else(|| find_call_callee(rhs)),
        IrExpr::Unary { operand, .. } => find_call_callee(operand),
        IrExpr::Conditional {
            condition,
            then_expr,
            else_expr,
            ..
        } => find_call_callee(condition)
            .or_else(|| find_call_callee(then_expr))
            .or_else(|| find_call_callee(else_expr)),
        IrExpr::Cast { expr, .. }
        | IrExpr::LValueToRValue { expr, .. }
        | IrExpr::ArrayToPointerDecay { expr, .. }
        | IrExpr::FunctionToPointerDecay { expr, .. } => find_call_callee(expr),
        IrExpr::Index { base, index, .. } => {
            find_call_callee(base).or_else(|| find_call_callee(index))
        }
        IrExpr::Member { base, .. } => find_call_callee(base),
        IrExpr::ArrayLiteral { elements, .. } => elements.iter().find_map(find_call_callee),
        IrExpr::IncDec { target, .. } => find_call_callee(target),
        IrExpr::Deref { ptr, .. } => find_call_callee(ptr),
        IrExpr::AddrOf { operand, .. }
        | IrExpr::MutableVoidPointerAddress { operand, .. } => find_call_callee(operand),
        IrExpr::LitInt { .. }
        | IrExpr::NullPtr { .. }
        | IrExpr::Var { .. }
        | IrExpr::Unsupported { .. } => None,
    }
}
