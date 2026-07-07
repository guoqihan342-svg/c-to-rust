fn reserved_c_macro_or_stdlib_callee(callee: &str) -> bool {
    matches!(
        callee,
        // Keep modeled macro names here as a fail-closed backstop; modeled
        // forms must be intercepted before this reserved-surface guard.
        "assert"
            | "abs"
            | "labs"
            | "llabs"
            | "fabs"
            | "fabsf"
            | "fabsl"
            | "static_assert"
            | "_Static_assert"
            | "sizeof"
            | "offsetof"
            | "malloc"
            | "calloc"
            | "realloc"
            | "free"
            | "memcpy"
            | "memmove"
            | "memset"
            | "strlen"
            | "strnlen"
            | "strnlen_s"
            | "printf"
            | "fprintf"
            | "sprintf"
            | "snprintf"
            | "puts"
            | "putchar"
            | "getchar"
            | "exit"
            | "abort"
    )
}

fn validate_bounded_call_args(args: &[IrExpr], context: &EmitContext) -> Result<(), String> {
    let nested_call_count = args
        .iter()
        .filter(|arg| matches!(arg, IrExpr::Call { .. }))
        .count();
    if nested_call_count > 1 {
        return Err(
            "multiple nested call arguments are outside the bounded call subset".to_string(),
        );
    }
    let side_effect_arg = single_side_effect_call_arg(args)?;
    for (index, arg) in args.iter().enumerate() {
        if let Some((side_effect_index, assigned_var)) = side_effect_arg {
            if index == side_effect_index {
                continue;
            }
            if expr_mentions_var(arg, assigned_var) {
                return Err(format!(
                    "side-effect call argument cannot be combined with sibling argument reading modified variable {assigned_var}"
                ));
            }
            validate_bounded_call_arg_with_context(arg, false, Some(context))
        } else {
            validate_bounded_call_arg_with_context(arg, true, Some(context))
        }
            .map_err(|detail| format!("call arg[{index}] {detail}"))?;
    }
    Ok(())
}

fn validate_bounded_call_arg(
    expr: &IrExpr,
    allow_immediate_nested_call: bool,
) -> Result<(), String> {
    validate_bounded_call_arg_with_context(expr, allow_immediate_nested_call, None)
}

fn validate_bounded_call_arg_with_context(
    expr: &IrExpr,
    allow_immediate_nested_call: bool,
    context: Option<&EmitContext>,
) -> Result<(), String> {
    match expr {
        IrExpr::LitInt { ty, .. } => {
            if matches!(ty.kind, IrTypeKind::Pointer { .. }) {
                if emit_opaque_void_pointer_type(ty).is_some() {
                    return Ok(());
                }
                return Err(format!(
                    "pointer value argument {} requires explicit ownership/lifetime/ABI lowering",
                    type_label(ty)
                ));
            }
            emit_scalar_type(ty)?;
            Ok(())
        }
        IrExpr::Var { name, ty, .. } => {
            if matches!(ty.kind, IrTypeKind::Pointer { .. }) {
                if emit_opaque_void_pointer_type(ty).is_some() {
                    return Ok(());
                }
                if let Some(context) = context {
                    if validate_raw_direct_call_pointer_arg(name, ty, context).is_ok() {
                        return Ok(());
                    }
                }
                return Err(format!(
                    "pointer value argument {} requires explicit ownership/lifetime/ABI lowering",
                    type_label(ty)
                ));
            }
            emit_scalar_type(ty)?;
            Ok(())
        }
        IrExpr::NullPtr { .. } => {
            Err("null pointer call arguments are outside the bounded call subset".to_string())
        }
        IrExpr::Binary { lhs, rhs, .. } => {
            validate_bounded_call_arg_with_context(lhs, false, context)?;
            validate_bounded_call_arg_with_context(rhs, false, context)
        }
        IrExpr::Unary { operand, .. }
        | IrExpr::Cast { expr: operand, .. }
        | IrExpr::LValueToRValue { expr: operand, .. } => {
            validate_bounded_call_arg_with_context(operand, false, context)
        }
        IrExpr::ArrayToPointerDecay { target, expr, .. } => {
            validate_array_decay_direct_call_arg(target, expr).map(|_| ())
        }
        IrExpr::FunctionToPointerDecay { target, expr, .. } => {
            validate_function_pointer_decay_call_arg(target, expr).map(|_| ())
        }
        IrExpr::Conditional { .. } => {
            Err("conditional call arguments are outside the bounded call subset".to_string())
        }
        IrExpr::Index { base, index, .. } => {
            validate_bounded_call_arg_with_context(base, false, context)?;
            validate_bounded_call_arg_with_context(index, false, context)
        }
        IrExpr::Member { .. } => {
            Err("member access call arguments are outside the bounded call subset".to_string())
        }
        IrExpr::ArrayLiteral { .. } => {
            Err("array literal arguments are outside the bounded call subset".to_string())
        }
        IrExpr::Call {
            callee, args, ty, ..
        } if allow_immediate_nested_call => {
            validate_bounded_nested_call_arg(callee, args, ty, context)
        }
        IrExpr::Call { .. } => {
            Err("nested call expressions are outside the bounded call subset".to_string())
        }
        IrExpr::IncDec { .. } => {
            Err("call arguments cannot use increment/decrement value semantics".to_string())
        }
        IrExpr::Deref { .. } => {
            Err("call arguments cannot use dereference value semantics".to_string())
        }
        IrExpr::AddrOf { operand, ty, .. } => {
            validate_local_record_address_call_arg(operand, ty).map(|_| ())
        }
        IrExpr::Unsupported { node, reason, .. } => {
            Err(format!("unsupported argument expression {node}: {reason}"))
        }
    }
}

fn validate_raw_direct_call_pointer_arg(
    name: &str,
    ty: &IrType,
    context: &EmitContext,
) -> Result<(), String> {
    if !should_emit_raw_direct_call_pointer_param(name, ty, context) {
        return Err(format!(
            "raw direct call pointer argument {name} lacks direct call provenance"
        ));
    }
    emit_raw_direct_call_pointer_param_type(ty).ok_or_else(|| {
        format!(
            "raw direct call pointer argument {name} has unsupported type {}",
            type_label(ty)
        )
    })?;
    Ok(())
}

fn validate_array_decay_direct_call_arg<'a>(
    target: &IrType,
    expr: &'a IrExpr,
) -> Result<&'a str, String> {
    let target_element = readonly_pointer_slice_element_type(target).ok_or_else(|| {
        format!(
            "array-to-pointer decay call argument target {} must be a readonly integer pointer",
            type_label(target)
        )
    })?;
    let IrExpr::Var {
        name,
        ty: array_ty,
        ..
    } = expr
    else {
        return Err(
            "array-to-pointer decay call argument must be a direct fixed array variable"
                .to_string(),
        );
    };
    let array_element = fixed_integer_array_element_type(array_ty).ok_or_else(|| {
        format!(
            "array-to-pointer decay call argument {name} has unsupported array type {}",
            type_label(array_ty)
        )
    })?;
    let target_element = emit_scalar_type(target_element).map_err(|detail| {
        format!("array-to-pointer decay call argument target element has {detail}")
    })?;
    let array_element = emit_scalar_type(array_element).map_err(|detail| {
        format!("array-to-pointer decay call argument array element has {detail}")
    })?;
    if target_element != array_element {
        return Err(format!(
            "array-to-pointer decay call argument element type {array_element} does not match target element type {target_element}"
        ));
    }
    Ok(name)
}

fn validate_local_record_address_call_arg<'a>(
    operand: &'a IrExpr,
    ty: &IrType,
) -> Result<&'a str, String> {
    let pointee = mutable_record_pointer_pointee_type(ty).ok_or_else(|| {
        format!(
            "address-of call argument target {} must be a mutable record pointer",
            type_label(ty)
        )
    })?;
    let IrExpr::Var {
        name,
        ty: operand_ty,
        ..
    } = operand
    else {
        return Err(
            "address-of call argument operand must be a direct record variable".to_string(),
        );
    };
    let IrTypeKind::Record { fields, .. } = &operand_ty.kind else {
        return Err(format!(
            "address-of call argument {name} has unsupported operand type {}",
            type_label(operand_ty)
        ));
    };
    if !matches!(fields, Some(fields) if !fields.is_empty()) {
        return Err(format!(
            "address-of call argument {name} requires complete record field inventory"
        ));
    }
    validate_record_value_type_matches(operand_ty, pointee, "address-of call argument")?;
    Ok(name)
}

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
    emit_scalar_type(ty).map_err(|detail| format!("nested call result has {detail}"))?;
    if let Some((side_effect_index, assigned_var)) = single_side_effect_call_arg(args)? {
        for (index, arg) in args.iter().enumerate() {
            if index == side_effect_index {
                continue;
            }
            if expr_mentions_var(arg, assigned_var) {
                return Err(format!(
                    "side-effect call argument cannot be combined with sibling argument reading modified variable {assigned_var}"
                ));
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
        IrExpr::AddrOf { operand, .. } => find_call_callee(operand),
        IrExpr::LitInt { .. }
        | IrExpr::NullPtr { .. }
        | IrExpr::Var { .. }
        | IrExpr::Unsupported { .. } => None,
    }
}
