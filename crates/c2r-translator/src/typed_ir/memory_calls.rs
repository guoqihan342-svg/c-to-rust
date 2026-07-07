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

fn validate_c_memset_statement_shape<'a>(
    args: &'a [IrExpr],
    ty: &IrType,
) -> Result<(&'a str, u8, &'a IrExpr), String> {
    if !is_c_memset_discarded_result_type(ty) {
        return Err(format!(
            "C memset statement model requires void or discarded void * result type, got {}",
            type_label(ty)
        ));
    }
    let [dest, value, count] = args else {
        return Err(format!(
            "C memset statement model requires destination, byte value, and size arguments, got {}",
            args.len()
        ));
    };
    let dest = validate_direct_mutable_unsigned_8_bit_pointer_arg(dest, "C memset destination")?;
    let byte = validate_c_memset_byte_value(value)?;
    let count_ty =
        expr_type(count).ok_or_else(|| "C memset size argument type is unsupported".to_string())?;
    if !is_c_size_argument_type(count_ty) {
        return Err(format!(
            "C memset size argument must be size_t/usize, got {}",
            type_label(count_ty)
        ));
    }
    validate_bounded_call_arg(count, false).map_err(|detail| format!("C memset size {detail}"))?;
    Ok((dest, byte, count))
}

fn validate_c_memcpy_statement_shape<'a>(
    args: &'a [IrExpr],
    ty: &IrType,
) -> Result<(&'a str, &'a str, &'a IrExpr), String> {
    if !is_c_memcpy_discarded_result_type(ty) {
        return Err(format!(
            "C memcpy statement model requires void or discarded void * result type, got {}",
            type_label(ty)
        ));
    }
    let [dest, src, count] = args else {
        return Err(format!(
            "C memcpy statement model requires destination, source, and size arguments, got {}",
            args.len()
        ));
    };
    let dest = validate_direct_mutable_unsigned_8_bit_pointer_arg(dest, "C memcpy destination")?;
    let src = validate_direct_readonly_8_bit_pointer_arg(src, "C memcpy source")?;
    let count_ty =
        expr_type(count).ok_or_else(|| "C memcpy size argument type is unsupported".to_string())?;
    if !is_c_size_argument_type(count_ty) {
        return Err(format!(
            "C memcpy size argument must be size_t/usize, got {}",
            type_label(count_ty)
        ));
    }
    validate_bounded_call_arg(count, false).map_err(|detail| format!("C memcpy size {detail}"))?;
    Ok((dest, src, count))
}

fn validate_direct_mutable_unsigned_8_bit_pointer_arg<'a>(
    arg: &'a IrExpr,
    context: &str,
) -> Result<&'a str, String> {
    let IrExpr::Var {
        name, ty: arg_ty, ..
    } = arg
    else {
        return Err(format!(
            "{context} argument must be a direct mutable pointer parameter"
        ));
    };
    let pointee = mutable_pointer_slice_element_type(arg_ty).ok_or_else(|| {
        format!(
            "{context} argument must be a mutable unsigned 8-bit integer pointer, got {}",
            type_label(arg_ty)
        )
    })?;
    if !is_unsigned_8_bit_integer_type(pointee) {
        return Err(format!(
            "{context} argument must be a mutable unsigned 8-bit integer pointer, got {}",
            type_label(arg_ty)
        ));
    }
    Ok(name)
}

fn validate_c_memset_byte_value(value: &IrExpr) -> Result<u8, String> {
    let IrExpr::LitInt { value: raw, .. } = value else {
        return Err("C memset byte value currently supports only literal byte values".to_string());
    };
    if *raw > u8::MAX as u64 {
        return Err("C memset byte value literal must fit in unsigned char".to_string());
    }
    Ok(*raw as u8)
}
