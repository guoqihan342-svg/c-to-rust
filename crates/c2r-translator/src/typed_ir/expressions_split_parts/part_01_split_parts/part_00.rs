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
        IrExpr::Call {
            callee, args, ty, ..
        } if pointer_return_nested_call_arg_type_allowed(ty) => {
            emit_pointer_return_nested_call_arg_expr(callee, args, ty, symbols, context)
        }
        IrExpr::Var { name, ty, .. } if emit_opaque_void_pointer_type(ty).is_some() => {
            emit_opaque_pointer_call_arg_var(name, symbols, context)
        }
        IrExpr::Var { name, ty, .. }
            if validate_mutable_record_pointer_call_arg(name, ty, context).is_ok() =>
        {
            emit_mutable_record_pointer_call_arg_var(name, ty, symbols, context)
        }
        IrExpr::Var { name, ty, .. }
            if should_emit_raw_direct_call_pointer_param(name, ty, context) =>
        {
            emit_raw_direct_call_pointer_arg_var(name, ty, symbols, context)
        }
        IrExpr::NullPtr { ty, .. } => emit_null_pointer_call_arg_expr(ty),
        IrExpr::AddrOf { operand, ty, .. } => {
            emit_local_record_address_call_arg(operand, ty, symbols)
        }
        IrExpr::MutableVoidPointerAddress {
            operand,
            source_pointer,
            target,
            ..
        } => emit_mutable_void_pointer_address_call_arg(
            operand,
            source_pointer,
            target,
            symbols,
            context,
        ),
        _ => emit_expr(arg, symbols, context),
    }
}

fn emit_mutable_void_pointer_address_call_arg(
    operand: &IrExpr,
    source_pointer: &IrType,
    target: &IrType,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<String, String> {
    let root = validate_mutable_void_pointer_address_call_arg(
        operand,
        source_pointer,
        target,
        Some(context),
    )?;
    if !symbols.contains(root) {
        return Err(format!(
            "mutable void pointer address root {root} is not declared"
        ));
    }
    let path = record_pointer_member_path_from_expr(operand)?
        .ok_or_else(|| "mutable void pointer address operand path disappeared".to_string())?;
    let value = emit_record_pointer_member_path(
        &path,
        "mutable void pointer address root",
        "mutable void pointer address field",
    )?;
    Ok(format!("&mut {value}"))
}

fn emit_pointer_return_nested_call_arg_expr(
    callee: &str,
    args: &[IrExpr],
    ty: &IrType,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<String, String> {
    validate_pointer_return_nested_call_arg(callee, args, ty, Some(context))?;
    let callee = emit_identifier(callee, "pointer return nested call callee")?;
    let args = args
        .iter()
        .enumerate()
        .map(|(index, arg)| {
            emit_call_arg_expr(arg, symbols, context).map_err(|detail| {
                format!("pointer return nested call arg[{index}] {detail}")
            })
        })
        .collect::<Result<Vec<_>, _>>()?
        .join(", ");
    Ok(format!("{callee}({args})"))
}

fn emit_null_pointer_call_arg_expr(ty: &IrType) -> Result<String, String> {
    let IrTypeKind::Pointer { pointee } = &ty.kind else {
        return Err(format!(
            "null pointer call argument type {} is not a pointer",
            type_label(ty)
        ));
    };
    if pointee.is_const {
        Ok("core::ptr::null()".to_string())
    } else {
        Ok("core::ptr::null_mut()".to_string())
    }
}

fn emit_array_decay_call_arg_expr(
    target: &IrType,
    expr: &IrExpr,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<String, String> {
    let name = match validate_array_decay_direct_call_arg(target, expr)? {
        ArrayDecayDirectCallArg::Binding(name) => name,
        ArrayDecayDirectCallArg::ByteStringLiteral(bytes) => {
            return emit_byte_string_literal_decay_call_arg(target, &bytes);
        }
    };
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

fn emit_byte_string_literal_decay_call_arg(
    target: &IrType,
    bytes: &[u8],
) -> Result<String, String> {
    let target_element = byte_string_pointer_element_type(target)?;
    let target = emit_scalar_type(target_element)
        .map_err(|detail| format!("string literal pointer target has {detail}"))?;
    Ok(format!(
        "{}.as_ptr().cast::<{}>()",
        emit_rust_byte_string_literal(bytes),
        target
    ))
}

fn emit_rust_byte_string_literal(bytes: &[u8]) -> String {
    let mut literal = String::from("b\"");
    for byte in bytes {
        match *byte {
            b'\n' => literal.push_str("\\n"),
            b'\r' => literal.push_str("\\r"),
            b'\t' => literal.push_str("\\t"),
            b'\\' => literal.push_str("\\\\"),
            b'"' => literal.push_str("\\\""),
            0 => literal.push_str("\\0"),
            0x20..=0x7e => literal.push(*byte as char),
            byte => literal.push_str(&format!("\\x{byte:02x}")),
        }
    }
    literal.push('"');
    literal
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

fn emit_mutable_record_pointer_call_arg_var(
    name: &str,
    ty: &IrType,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<String, String> {
    if !symbols.contains(name) {
        return Err(format!(
            "mutable record pointer call argument {name} is not declared"
        ));
    }
    validate_mutable_record_pointer_call_arg(name, ty, context)?;
    emit_identifier(name, "mutable record pointer call argument")
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
