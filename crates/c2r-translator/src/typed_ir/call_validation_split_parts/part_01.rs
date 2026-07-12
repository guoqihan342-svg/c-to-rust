fn validate_null_pointer_call_arg(ty: &IrType) -> Result<(), String> {
    if matches!(&ty.kind, IrTypeKind::Pointer { .. }) {
        return Ok(());
    }
    Err(format!(
        "null pointer call argument type {} is not a pointer",
        type_label(ty)
    ))
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
) -> Result<ArrayDecayDirectCallArg<'a>, String> {
    if matches!(expr, IrExpr::ArrayLiteral { .. }) {
        let bytes = byte_string_array_literal_values(expr)?;
        let target_element = byte_string_pointer_element_type(target)?;
        emit_scalar_type(target_element).map_err(|detail| {
            format!("string literal array-to-pointer decay target element has {detail}")
        })?;
        return Ok(ArrayDecayDirectCallArg::ByteStringLiteral(bytes));
    }

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
    Ok(ArrayDecayDirectCallArg::Binding(name))
}

enum ArrayDecayDirectCallArg<'a> {
    Binding(&'a str),
    ByteStringLiteral(Vec<u8>),
}

fn byte_string_pointer_element_type(target: &IrType) -> Result<&IrType, String> {
    let IrTypeKind::Pointer { pointee } = &target.kind else {
        return Err(format!(
            "string literal array-to-pointer decay target {} must be an 8-bit integer pointer",
            type_label(target)
        ));
    };
    if !is_8_bit_integer_type(pointee) {
        return Err(format!(
            "string literal array-to-pointer decay target element {} is unsupported",
            type_label(pointee)
        ));
    }
    Ok(pointee)
}

fn byte_string_array_literal_values(expr: &IrExpr) -> Result<Vec<u8>, String> {
    let IrExpr::ArrayLiteral { elements, ty, .. } = expr else {
        return Err(
            "string literal array-to-pointer decay requires a byte array literal".to_string(),
        );
    };
    let IrTypeKind::Array {
        element,
        len: Some(len),
    } = &ty.kind
    else {
        return Err(format!(
            "string literal array-to-pointer decay source {} must be a complete byte array",
            type_label(ty)
        ));
    };
    if *len != elements.len() {
        return Err(format!(
            "string literal array-to-pointer decay source {} length does not match element count",
            type_label(ty)
        ));
    }
    if !is_8_bit_integer_type(element) {
        return Err(format!(
            "string literal array-to-pointer decay element type {} is unsupported",
            type_label(element)
        ));
    }

    let mut bytes = Vec::with_capacity(elements.len());
    for element in elements {
        let IrExpr::LitInt { value, ty, .. } = element else {
            return Err(
                "string literal array-to-pointer decay requires integer literal elements"
                    .to_string(),
            );
        };
        if !is_8_bit_integer_type(ty) {
            return Err(format!(
                "string literal array-to-pointer decay element literal type {} is unsupported",
                type_label(ty)
            ));
        }
        let byte = u8::try_from(*value).map_err(|_| {
            format!("string literal array-to-pointer decay element value {value} exceeds u8")
        })?;
        bytes.push(byte);
    }
    if bytes.last().copied() != Some(0) {
        return Err(
            "string literal array-to-pointer decay byte array must be NUL terminated"
                .to_string(),
        );
    }
    Ok(bytes)
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

fn validate_mutable_void_pointer_address_call_arg<'a>(
    operand: &'a IrExpr,
    source_pointer: &IrType,
    target: &IrType,
    context: Option<&EmitContext>,
) -> Result<&'a str, String> {
    let IrTypeKind::Pointer { pointee: target_pointee } = &target.kind else {
        return Err(format!(
            "mutable void pointer address target {} is not a pointer",
            type_label(target)
        ));
    };
    if target_pointee.is_const || !matches!(target_pointee.kind, IrTypeKind::Void) {
        return Err(format!(
            "mutable void pointer address target {} is not mutable void *",
            type_label(target)
        ));
    }
    let source_pointee = mutable_pointer_slice_element_type(source_pointer).ok_or_else(|| {
        format!(
            "mutable void pointer address source {} is not a mutable integer pointer",
            type_label(source_pointer)
        )
    })?;
    let path = record_pointer_member_path_from_expr(operand)?.ok_or_else(|| {
        "mutable void pointer address operand must be a bounded record scalar member path"
            .to_string()
    })?;
    if !is_integer_type(path.ty) {
        return Err(format!(
            "mutable void pointer address field {} must be a fixed-width integer scalar, got {}",
            record_pointer_member_path_key(&path),
            type_label(path.ty)
        ));
    }
    emit_scalar_type(path.ty).map_err(|detail| {
        format!(
            "mutable void pointer address field {} has {detail}",
            record_pointer_member_path_key(&path)
        )
    })?;
    if !types_match_ignoring_spelling(source_pointee, path.ty) {
        return Err(format!(
            "mutable void pointer address source pointee {} does not match field type {}",
            type_label(source_pointee),
            type_label(path.ty)
        ));
    }
    validate_complete_record_member_path(operand)?;
    let context = context.ok_or_else(|| {
        "mutable void pointer address requires mutable record ownership context".to_string()
    })?;
    if !context.is_mutable_record_pointer_write_param(path.root_name) {
        return Err(format!(
            "mutable void pointer address root {} lacks ownership evidence",
            path.root_name
        ));
    }
    if context.is_nullable_pointer_param(path.root_name) {
        return Err(format!(
            "nullable mutable record pointer {} cannot provide a scalar address",
            path.root_name
        ));
    }
    Ok(path.root_name)
}

fn mutable_void_pointer_address_root(expr: &IrExpr) -> Option<&str> {
    let path = record_pointer_member_path_from_expr(expr).ok()??;
    Some(path.root_name)
}

fn validate_complete_record_member_path(expr: &IrExpr) -> Result<(), String> {
    let IrExpr::Member {
        base,
        field,
        ty,
        is_arrow,
        ..
    } = expr
    else {
        return Err("mutable void pointer address operand is not a record member".to_string());
    };
    let record_ty = if *is_arrow {
        let IrExpr::Var { ty: root_ty, .. } = base.as_ref() else {
            return Err(
                "mutable void pointer address must have one direct record pointer root"
                    .to_string(),
            );
        };
        mutable_record_pointer_pointee_type(root_ty).ok_or_else(|| {
            format!(
                "mutable void pointer address root has unsupported type {}",
                type_label(root_ty)
            )
        })?
    } else {
        validate_complete_record_member_path(base)?;
        expr_type(base).ok_or_else(|| {
            "mutable void pointer address nested member base lacks a type".to_string()
        })?
    };
    let IrTypeKind::Record {
        name,
        fields: Some(fields),
    } = &record_ty.kind
    else {
        return Err(format!(
            "mutable void pointer address record {} lacks a complete field inventory",
            type_label(record_ty)
        ));
    };
    let declared = fields
        .iter()
        .find(|candidate| candidate.name == *field)
        .ok_or_else(|| {
            format!("mutable void pointer address record {name} has no field {field}")
        })?;
    if !types_match_ignoring_spelling(&declared.ty, ty) {
        return Err(format!(
            "mutable void pointer address field {name}.{field} type {} does not match declared type {}",
            type_label(ty),
            type_label(&declared.ty)
        ));
    }
    Ok(())
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
