fn emit_call_expr(
    callee: &str,
    args: &[IrExpr],
    ty: &IrType,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<String, String> {
    let callee = emit_identifier(callee, "call callee")?;
    if callee == "assert" {
        return emit_c_assert_call_expr(args, ty, symbols, context);
    }
    if callee == "abs" {
        return emit_c_abs_call_expr(args, ty, symbols, context);
    }
    if callee == "strlen" {
        return emit_c_strlen_call_expr(args, ty, symbols, context);
    }
    if callee == "strnlen" {
        return emit_c_strnlen_call_expr(args, ty, symbols, context);
    }
    if callee == "memcmp" {
        return emit_c_memcmp_call_expr(args, ty, symbols, context);
    }
    if reserved_c_macro_or_stdlib_callee(&callee) {
        return Err(format!(
            "call callee \"{callee}\" is reserved C macro/stdlib/extern surface and requires explicit lowering or extern binding"
        ));
    }
    if matches!(ty.kind, IrTypeKind::Pointer { .. }) {
        return Err(format!(
            "call result has pointer value return {} requires explicit ownership/lifetime/ABI lowering",
            type_label(ty)
        ));
    }
    if !is_void_type(ty) {
        emit_scalar_type(ty).map_err(|detail| format!("call result has {detail}"))?;
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
    Ok(format!("{callee}({args})"))
}

fn emit_call_arg_expr(
    arg: &IrExpr,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<String, String> {
    match arg {
        IrExpr::ArrayToPointerDecay { target, expr, .. } => {
            emit_array_decay_call_arg_expr(target, expr, symbols, context)
        }
        IrExpr::FunctionToPointerDecay { target, expr, .. } => {
            emit_function_pointer_decay_call_arg(target, expr)
        }
        IrExpr::Call {
            callee, args, ty, ..
        } if mutable_record_pointer_pointee_type(ty).is_some() => {
            emit_record_pointer_return_call_arg_expr(callee, args, ty, symbols, context)
        }
        IrExpr::Var { name, ty, .. } if emit_opaque_void_pointer_type(ty).is_some() => {
            emit_opaque_pointer_call_arg_var(name, symbols, context)
        }
        IrExpr::Var { name, ty, .. }
            if should_emit_raw_direct_call_pointer_param(name, ty, context) =>
        {
            emit_raw_direct_call_pointer_arg_var(name, ty, symbols, context)
        }
        IrExpr::AddrOf { operand, ty, .. } => {
            emit_local_record_address_call_arg(operand, ty, symbols)
        }
        _ => emit_expr(arg, symbols, context),
    }
}

fn emit_array_decay_call_arg_expr(
    target: &IrType,
    expr: &IrExpr,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<String, String> {
    let name = validate_array_decay_direct_call_arg(target, expr)?;
    if !symbols.contains(name) {
        if let IrExpr::Var { ty, .. } = expr {
            if let Some(global) = context.readonly_global(name) {
                validate_global_expr_type(global, ty)?;
                let name = context.global_rust_name(name)?;
                return Ok(format!("&{name}"));
            }
        }
        return Err(format!(
            "array-to-pointer decay call argument {name} is not a local fixed array binding"
        ));
    }
    let name = emit_identifier(name, "array-to-pointer decay call argument")?;
    Ok(format!("&{name}"))
}

fn emit_record_pointer_return_call_arg_expr(
    callee: &str,
    args: &[IrExpr],
    ty: &IrType,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<String, String> {
    validate_record_pointer_return_nested_call_arg(callee, args, ty, Some(context))?;
    let callee = emit_identifier(callee, "record pointer return call argument callee")?;
    let args = args
        .iter()
        .enumerate()
        .map(|(index, arg)| {
            emit_record_pointer_return_call_inner_arg_expr(arg, symbols, context)
                .map_err(|detail| format!("record pointer return call arg[{index}] {detail}"))
        })
        .collect::<Result<Vec<_>, _>>()?
        .join(", ");
    Ok(format!("{callee}({args})"))
}

fn emit_record_pointer_return_call_inner_arg_expr(
    arg: &IrExpr,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<String, String> {
    match arg {
        IrExpr::Var { name, ty, .. } if is_readonly_8_bit_pointer_type(ty) => {
            emit_readonly_byte_pointer_const_void_call_arg_var(name, symbols, context)
        }
        IrExpr::Call {
            callee, args, ty, ..
        } if callee == "strlen" => emit_c_strlen_call_expr(args, ty, symbols, context),
        _ => emit_call_arg_expr(arg, symbols, context),
    }
}

fn emit_local_record_address_call_arg(
    operand: &IrExpr,
    ty: &IrType,
    symbols: &HashSet<String>,
) -> Result<String, String> {
    let name = validate_local_record_address_call_arg(operand, ty)?;
    if !symbols.contains(name) {
        return Err(format!("address-of call argument {name} is not declared"));
    }
    let name = emit_identifier(name, "address-of call argument")?;
    Ok(format!("&mut {name}"))
}

fn emit_raw_direct_call_pointer_arg_var(
    name: &str,
    ty: &IrType,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<String, String> {
    if !symbols.contains(name) {
        return Err(format!(
            "raw direct call pointer argument {name} is not declared"
        ));
    }
    validate_raw_direct_call_pointer_arg(name, ty, context)?;
    emit_identifier(name, "raw direct call pointer argument")
}

fn emit_opaque_pointer_call_arg_var(
    name: &str,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<String, String> {
    if !symbols.contains(name) {
        return Err(format!(
            "opaque pointer call argument {name} is not declared"
        ));
    }
    if !context.is_opaque_pointer_call_arg_param(name) {
        return Err(format!(
            "opaque pointer call argument {name} requires direct call argument provenance"
        ));
    }
    emit_identifier(name, "opaque pointer call argument")
}

fn emit_readonly_byte_pointer_const_void_call_arg_var(
    name: &str,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<String, String> {
    if !symbols.contains(name) {
        return Err(format!(
            "readonly byte pointer call argument {name} is not declared"
        ));
    }
    let name = emit_identifier(name, "readonly byte pointer call argument")?;
    let receiver = if context.is_nullable_pointer_param(&name) {
        format!("{name}.unwrap()")
    } else {
        name
    };
    Ok(format!("{receiver}.as_ptr() as *const core::ffi::c_void"))
}

fn emit_function_pointer_decay_call_arg(target: &IrType, expr: &IrExpr) -> Result<String, String> {
    let name = validate_function_pointer_decay_call_arg(target, expr)?;
    emit_identifier(name, "function pointer decay argument")
}

fn validate_function_pointer_decay_call_arg<'a>(
    target: &IrType,
    expr: &'a IrExpr,
) -> Result<&'a str, String> {
    let Some(target_signature) = emit_function_pointer_param_type(target)? else {
        return Err(format!(
            "function-to-pointer decay target {} is outside the simple function pointer argument subset",
            type_label(target)
        ));
    };
    let IrTypeKind::Pointer { pointee } = &target.kind else {
        return Err(format!(
            "function-to-pointer decay target {} is not a function pointer",
            type_label(target)
        ));
    };
    let IrExpr::Var { name, ty, .. } = expr else {
        return Err(
            "function-to-pointer decay argument must be a direct function name".to_string(),
        );
    };
    if !matches!(ty.kind, IrTypeKind::Function) {
        return Err(format!(
            "function-to-pointer decay argument {name} has unsupported source type {}",
            type_label(ty)
        ));
    }
    let source_signature = emit_function_pointer_signature_type(&ty.spelled).map_err(|detail| {
        format!(
            "function-to-pointer decay argument {name} source type {} is unsupported: {detail}",
            type_label(ty)
        )
    })?;
    let pointee_signature =
        emit_function_pointer_signature_type(&pointee.spelled).map_err(|detail| {
            format!(
                "function-to-pointer decay target pointee {} is unsupported: {detail}",
                type_label(pointee)
            )
        })?;
    if source_signature != target_signature || source_signature != pointee_signature {
        return Err(format!(
            "function-to-pointer decay argument {name} signature {source_signature} does not match target {target_signature}"
        ));
    }
    Ok(name)
}

fn emit_c_assert_call_expr(
    args: &[IrExpr],
    ty: &IrType,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<String, String> {
    if !is_void_type(ty) {
        return Err(format!(
            "C assert model requires void result type, got {}",
            type_label(ty)
        ));
    }
    let [condition] = args else {
        return Err(format!(
            "C assert model requires exactly one condition argument, got {}",
            args.len()
        ));
    };
    validate_bounded_call_arg_with_context(condition, false, Some(context))
        .map_err(|detail| format!("C assert condition {detail}"))?;
    let condition = emit_condition_expr(condition, symbols, context)
        .map_err(|detail| format!("C assert condition {detail}"))?;
    Ok(format!("assert!({condition})"))
}

fn emit_c_abs_call_expr(
    args: &[IrExpr],
    ty: &IrType,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<String, String> {
    if !is_c_int_type(ty) {
        return Err(format!(
            "C abs(int) model requires i32 result type, got {}",
            type_label(ty)
        ));
    }
    let [arg] = args else {
        return Err(format!(
            "C abs(int) model requires exactly one i32 argument, got {}",
            args.len()
        ));
    };
    validate_bounded_call_arg_with_context(arg, false, Some(context))
        .map_err(|detail| format!("C abs argument {detail}"))?;
    let arg_ty = expr_type(arg).ok_or_else(|| "C abs argument type is unsupported".to_string())?;
    if !is_c_int_type(arg_ty) {
        return Err(format!(
            "C abs(int) argument must be i32, got {}",
            type_label(arg_ty)
        ));
    }
    let arg =
        emit_expr(arg, symbols, context).map_err(|detail| format!("C abs argument {detail}"))?;
    Ok(format!(
        "{arg}.checked_abs().expect(\"C abs(int) precondition violated\")"
    ))
}

fn emit_c_strlen_call_expr(
    args: &[IrExpr],
    ty: &IrType,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<String, String> {
    let name = validate_c_strlen_call_shape(args, ty)?;
    let name = emit_identifier(name, "C strlen argument")?;
    if !symbols.contains(&name) {
        return Err(format!(
            "C strlen argument {name} is not a function parameter or local binding"
        ));
    }
    let receiver = if context.is_nullable_pointer_param(&name) {
        format!("{name}.unwrap()")
    } else {
        name
    };
    Ok(format!(
        "{receiver}.iter().position(|&byte| byte == 0).expect(\"C strlen precondition violated\")"
    ))
}

fn validate_c_strlen_call_shape<'a>(args: &'a [IrExpr], ty: &IrType) -> Result<&'a str, String> {
    if !is_c_strlen_result_type(ty) {
        return Err(format!(
            "C strlen model requires size_t/usize result type, got {}",
            type_label(ty)
        ));
    }
    let [arg] = args else {
        return Err(format!(
            "C strlen model requires exactly one string pointer argument, got {}",
            args.len()
        ));
    };
    let IrExpr::Var {
        name, ty: arg_ty, ..
    } = arg
    else {
        return Err("C strlen argument must be a direct readonly pointer parameter".to_string());
    };
    let pointee = readonly_pointer_slice_element_type(arg_ty).ok_or_else(|| {
        format!(
            "C strlen argument must be a readonly 8-bit integer pointer, got {}",
            type_label(arg_ty)
        )
    })?;
    if !is_8_bit_integer_type(pointee) {
        return Err(format!(
            "C strlen argument must be a readonly 8-bit integer pointer, got {}",
            type_label(arg_ty)
        ));
    }
    Ok(name)
}

fn emit_c_strnlen_call_expr(
    args: &[IrExpr],
    ty: &IrType,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<String, String> {
    let (name, max) = validate_c_strnlen_call_shape(args, ty)?;
    let name = emit_identifier(name, "C strnlen argument")?;
    if !symbols.contains(&name) {
        return Err(format!(
            "C strnlen argument {name} is not a function parameter or local binding"
        ));
    }
    let max =
        emit_expr(max, symbols, context).map_err(|detail| format!("C strnlen size {detail}"))?;
    Ok(format!(
        "{{ let bytes = {name}.get(..({max} as usize)).expect(\"C strnlen precondition violated\"); bytes.iter().position(|&byte| byte == 0).unwrap_or(bytes.len()) }}"
    ))
}

fn validate_c_strnlen_call_shape<'a>(
    args: &'a [IrExpr],
    ty: &IrType,
) -> Result<(&'a str, &'a IrExpr), String> {
    if !is_c_strlen_result_type(ty) {
        return Err(format!(
            "C strnlen model requires size_t/usize result type, got {}",
            type_label(ty)
        ));
    }
    let [arg, max] = args else {
        return Err(format!(
            "C strnlen model requires exactly one string pointer and one size argument, got {}",
            args.len()
        ));
    };
    let name = validate_direct_readonly_8_bit_pointer_arg(arg, "C strnlen")?;
    let max_ty =
        expr_type(max).ok_or_else(|| "C strnlen size argument type is unsupported".to_string())?;
    if !is_c_size_argument_type(max_ty) {
        return Err(format!(
            "C strnlen size argument must be size_t/usize, got {}",
            type_label(max_ty)
        ));
    }
    validate_bounded_call_arg(max, false).map_err(|detail| format!("C strnlen size {detail}"))?;
    Ok((name, max))
}

fn emit_c_memcmp_call_expr(
    args: &[IrExpr],
    ty: &IrType,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<String, String> {
    let (left, right, count) = validate_c_memcmp_call_shape(args, ty)?;
    let left = emit_identifier(left, "C memcmp left argument")?;
    let right = emit_identifier(right, "C memcmp right argument")?;
    if !symbols.contains(&left) {
        return Err(format!(
            "C memcmp left argument {left} is not a function parameter or local binding"
        ));
    }
    if !symbols.contains(&right) {
        return Err(format!(
            "C memcmp right argument {right} is not a function parameter or local binding"
        ));
    }
    let count =
        emit_expr(count, symbols, context).map_err(|detail| format!("C memcmp size {detail}"))?;
    Ok(format!(
        "{{ let left_bytes = {left}.get(..({count} as usize)).expect(\"C memcmp precondition violated\"); let right_bytes = {right}.get(..({count} as usize)).expect(\"C memcmp precondition violated\"); left_bytes.iter().zip(right_bytes.iter()).find_map(|(&left_byte, &right_byte)| ((left_byte as u8) != (right_byte as u8)).then_some(((left_byte as u8) as i32) - ((right_byte as u8) as i32))).unwrap_or(0) }}"
    ))
}

fn validate_c_memcmp_call_shape<'a>(
    args: &'a [IrExpr],
    ty: &IrType,
) -> Result<(&'a str, &'a str, &'a IrExpr), String> {
    if !is_c_int_type(ty) {
        return Err(format!(
            "C memcmp model requires i32 result type, got {}",
            type_label(ty)
        ));
    }
    let [left, right, count] = args else {
        return Err(format!(
            "C memcmp model requires exactly two readonly byte pointers and one size argument, got {}",
            args.len()
        ));
    };
    let left = validate_direct_readonly_8_bit_pointer_arg(left, "C memcmp left")?;
    let right = validate_direct_readonly_8_bit_pointer_arg(right, "C memcmp right")?;
    let count_ty =
        expr_type(count).ok_or_else(|| "C memcmp size argument type is unsupported".to_string())?;
    if !is_c_size_argument_type(count_ty) {
        return Err(format!(
            "C memcmp size argument must be size_t/usize, got {}",
            type_label(count_ty)
        ));
    }
    validate_bounded_call_arg(count, false).map_err(|detail| format!("C memcmp size {detail}"))?;
    Ok((left, right, count))
}

fn validate_direct_readonly_8_bit_pointer_arg<'a>(
    arg: &'a IrExpr,
    context: &str,
) -> Result<&'a str, String> {
    let IrExpr::Var {
        name, ty: arg_ty, ..
    } = arg
    else {
        return Err(format!(
            "{context} argument must be a direct readonly pointer parameter"
        ));
    };
    let pointee = readonly_pointer_slice_element_type(arg_ty).ok_or_else(|| {
        format!(
            "{context} argument must be a readonly 8-bit integer pointer, got {}",
            type_label(arg_ty)
        )
    })?;
    if !is_8_bit_integer_type(pointee) {
        return Err(format!(
            "{context} argument must be a readonly 8-bit integer pointer, got {}",
            type_label(arg_ty)
        ));
    }
    Ok(name)
}
