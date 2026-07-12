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
    if !fixed_width_integer_types_match(source_pointee, path.ty) {
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

fn fixed_width_integer_types_match(lhs: &IrType, rhs: &IrType) -> bool {
    lhs.is_const == rhs.is_const
        && matches!(
            (&lhs.kind, &rhs.kind),
            (
                IrTypeKind::Integer {
                    signed: lhs_signed,
                    width: lhs_width,
                },
                IrTypeKind::Integer {
                    signed: rhs_signed,
                    width: rhs_width,
                },
            ) if lhs_signed == rhs_signed && lhs_width == rhs_width
        )
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
