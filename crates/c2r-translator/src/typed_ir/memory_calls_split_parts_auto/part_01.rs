
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
    let dest = validate_c_memset_destination_arg(dest)?;
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
    let dest = validate_c_memcpy_destination_arg(dest)?;
    let src = validate_c_memcpy_source_arg(src)?;
    if dest == src {
        return Err("C memcpy source and destination must be distinct bindings".to_string());
    }
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

fn validate_c_memset_destination_arg(arg: &IrExpr) -> Result<&str, String> {
    match arg {
        IrExpr::Var { .. } => {
            validate_direct_mutable_unsigned_8_bit_pointer_arg(arg, "C memset destination")
        }
        IrExpr::ArrayToPointerDecay { target, expr, .. } => {
            validate_local_fixed_unsigned_8_bit_array_decay_mutable_destination(
                target,
                expr,
                "C memset destination",
            )
        }
        _ => Err(
            "C memset destination argument must be a direct mutable pointer parameter or local fixed byte array decay"
                .to_string(),
        ),
    }
}

fn validate_c_memcpy_destination_arg(arg: &IrExpr) -> Result<&str, String> {
    match arg {
        IrExpr::Var { .. } => {
            validate_direct_mutable_unsigned_8_bit_pointer_arg(arg, "C memcpy destination")
        }
        IrExpr::ArrayToPointerDecay { target, expr, .. } => {
            validate_local_fixed_unsigned_8_bit_array_decay_mutable_destination(
                target,
                expr,
                "C memcpy destination",
            )
        }
        _ => Err(
            "C memcpy destination argument must be a direct mutable pointer parameter or local fixed byte array decay"
                .to_string(),
        ),
    }
}

fn validate_c_memcpy_source_arg(arg: &IrExpr) -> Result<&str, String> {
    match arg {
        IrExpr::Var { .. } => validate_direct_readonly_8_bit_pointer_arg(arg, "C memcpy source"),
        IrExpr::ArrayToPointerDecay { target, expr, .. } => {
            validate_local_fixed_8_bit_array_decay_readonly_source(
                target,
                expr,
                "C memcpy source",
            )
        }
        _ => Err(
            "C memcpy source argument must be a direct readonly pointer parameter or local fixed byte array decay"
                .to_string(),
        ),
    }
}

fn validate_local_fixed_unsigned_8_bit_array_decay_mutable_destination<'a>(
    target: &IrType,
    expr: &'a IrExpr,
    context: &str,
) -> Result<&'a str, String> {
    let target_element = mutable_pointer_slice_element_type(target).ok_or_else(|| {
        format!(
            "{context} array decay target must be a mutable unsigned 8-bit integer pointer, got {}",
            type_label(target)
        )
    })?;
    if !is_unsigned_8_bit_integer_type(target_element) {
        return Err(format!(
            "{context} array decay target must be a mutable unsigned 8-bit integer pointer, got {}",
            type_label(target)
        ));
    }
    let IrExpr::Var {
        name,
        ty: array_ty,
        ..
    } = expr
    else {
        return Err(
            format!("{context} array decay must be a direct fixed byte array variable"),
        );
    };
    let array_element = fixed_integer_array_element_type(array_ty).ok_or_else(|| {
        format!(
            "{context} array decay {name} has unsupported array type {}",
            type_label(array_ty)
        )
    })?;
    if !is_unsigned_8_bit_integer_type(array_element) {
        return Err(format!(
            "{context} array decay {name} must be a fixed unsigned 8-bit integer array, got {}",
            type_label(array_ty)
        ));
    }
    Ok(name)
}

fn validate_local_fixed_8_bit_array_decay_readonly_source<'a>(
    target: &IrType,
    expr: &'a IrExpr,
    context: &str,
) -> Result<&'a str, String> {
    let target_element = readonly_pointer_slice_element_type(target)
        .or_else(|| mutable_pointer_slice_element_type(target))
        .ok_or_else(|| format!(
            "{context} array decay target must be an 8-bit integer pointer, got {}",
            type_label(target)
        ))?;
    if !is_8_bit_integer_type(target_element) {
        return Err(format!(
            "{context} array decay target must be an 8-bit integer pointer, got {}",
            type_label(target)
        ));
    }
    let IrExpr::Var {
        name,
        ty: array_ty,
        ..
    } = expr
    else {
        return Err(format!(
            "{context} array decay must be a direct fixed byte array variable"
        ));
    };
    let array_element = fixed_integer_array_element_type(array_ty).ok_or_else(|| {
        format!(
            "{context} array decay {name} has unsupported array type {}",
            type_label(array_ty)
        )
    })?;
    if !is_8_bit_integer_type(array_element) {
        return Err(format!(
            "{context} array decay {name} must be a fixed 8-bit integer array, got {}",
            type_label(array_ty)
        ));
    }
    let target_element = emit_scalar_type(target_element)
        .map_err(|detail| format!("{context} target element has {detail}"))?;
    let array_element = emit_scalar_type(array_element)
        .map_err(|detail| format!("{context} array element has {detail}"))?;
    if target_element != array_element {
        return Err(format!(
            "{context} array decay element type {array_element} does not match target element type {target_element}"
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
