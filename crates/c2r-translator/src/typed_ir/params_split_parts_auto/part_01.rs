
fn emit_value_type(ty: &IrType) -> Result<String, String> {
    if let IrTypeKind::Record { name, .. } = &ty.kind {
        return emit_record_type_name(name);
    }
    emit_scalar_type(ty)
}

fn emit_opaque_void_pointer_param_type(ty: &IrType) -> Result<String, String> {
    emit_opaque_void_pointer_type(ty).ok_or_else(|| {
        format!(
            "opaque pointer param type {} is unsupported",
            type_label(ty)
        )
    })
}

fn emit_record_pointer_field_value_param_type(ty: &IrType) -> Result<String, String> {
    emit_record_pointer_field_type(ty).ok_or_else(|| {
        format!(
            "record pointer field value param type {} is unsupported",
            type_label(ty)
        )
    })
}

fn emit_raw_direct_call_pointer_param_type(ty: &IrType) -> Option<String> {
    if let Some(pointer_ty) = emit_opaque_void_pointer_type(ty) {
        return Some(pointer_ty);
    }
    if mutable_record_pointer_pointee_type(ty)
        .is_some_and(|pointee| !is_incomplete_record_type(pointee))
    {
        return emit_mutable_record_pointer_param_type(ty).ok();
    }
    if readonly_record_pointer_pointee_type(ty)
        .is_some_and(|pointee| !is_incomplete_record_type(pointee))
    {
        return emit_readonly_record_pointer_param_type(ty).ok();
    }
    let IrTypeKind::Pointer { pointee } = &ty.kind else {
        return None;
    };
    if is_incomplete_record_type(pointee) {
        let mutability = if pointee.is_const { "const" } else { "mut" };
        return Some(format!("*{mutability} core::ffi::c_void"));
    }
    if is_readonly_8_bit_pointer_type(ty) {
        return Some("*const core::ffi::c_void".to_string());
    }
    None
}

fn should_emit_raw_direct_call_pointer_param(
    name: &str,
    ty: &IrType,
    context: &EmitContext,
) -> bool {
    context.is_raw_direct_call_pointer_param(name)
        && emit_raw_direct_call_pointer_param_type(ty).is_some()
        && !(is_readonly_8_bit_pointer_type(ty) && context.is_readonly_pointer_read_param(name))
}

fn should_emit_unused_readonly_8_bit_pointer_param(
    name: &str,
    ty: &IrType,
    context: &EmitContext,
) -> bool {
    is_unused_readonly_8_bit_pointer_param(
        name,
        ty,
        &context.readonly_pointer_read_params,
        &context.readonly_pointer_mentioned_params,
    ) && emit_unused_readonly_8_bit_pointer_param_type(ty).is_some()
}

fn is_unused_readonly_8_bit_pointer_param(
    name: &str,
    ty: &IrType,
    readonly_pointer_read_params: &HashSet<String>,
    readonly_pointer_mentioned_params: &HashSet<String>,
) -> bool {
    is_readonly_8_bit_pointer_type(ty)
        && !readonly_pointer_read_params.contains(name)
        && !readonly_pointer_mentioned_params.contains(name)
}

fn emit_unused_readonly_8_bit_pointer_param_type(ty: &IrType) -> Option<String> {
    is_readonly_8_bit_pointer_type(ty).then(|| "*const core::ffi::c_void".to_string())
}

fn emit_record_field_type(ty: &IrType) -> Result<String, String> {
    if let Some(pointer_ty) = emit_record_pointer_field_type(ty) {
        return Ok(pointer_ty);
    }
    if matches!(ty.kind, IrTypeKind::Array { .. }) {
        return emit_fixed_array_type(ty);
    }
    if let IrTypeKind::Record {
        fields: Some(_), ..
    } = &ty.kind
    {
        return emit_value_type(ty);
    }
    emit_scalar_type(ty)
}

fn emit_mutable_record_pointer_field_type(ty: &IrType) -> Result<String, String> {
    if let Some(pointer_ty) = emit_record_pointer_field_type(ty) {
        return Ok(pointer_ty);
    }
    emit_scalar_type(ty)
}

fn emit_record_zero_initializer(ty: &IrType) -> Result<String, String> {
    let IrTypeKind::Record {
        name,
        fields: Some(fields),
    } = &ty.kind
    else {
        return Err(format!(
            "record type {} requires complete field inventory for local zero initializer",
            type_label(ty)
        ));
    };
    if fields.is_empty() {
        return Err(format!("record {name} has no modeled fields"));
    }
    let rust_name = emit_record_type_name(name)?;
    let fields = fields
        .iter()
        .map(|field| {
            let field_name = emit_identifier(&field.name, "record zero initializer field")?;
            let value = emit_record_zero_field_value(&field.ty).map_err(|detail| {
                format!(
                    "record {name} field {} zero initializer {detail}",
                    field.name
                )
            })?;
            Ok(format!("{field_name}: {value}"))
        })
        .collect::<Result<Vec<_>, String>>()?
        .join(", ");
    Ok(format!("{rust_name} {{ {fields} }}"))
}

fn emit_record_zero_field_value(ty: &IrType) -> Result<String, String> {
    if let Some(value) = emit_record_pointer_field_zero_value(ty) {
        return Ok(value.to_string());
    }
    if is_integer_type(ty) {
        return emit_integer_literal(0, ty);
    }
    if let IrTypeKind::Record {
        fields: Some(_), ..
    } = &ty.kind
    {
        return emit_record_zero_initializer(ty);
    }
    Err(format!("type {} is unsupported", type_label(ty)))
}

fn emit_opaque_void_pointer_type(ty: &IrType) -> Option<String> {
    let IrTypeKind::Pointer { pointee } = &ty.kind else {
        return None;
    };
    if !matches!(pointee.kind, IrTypeKind::Void) {
        return None;
    }
    let mutability = if pointee.is_const { "const" } else { "mut" };
    Some(format!("*{mutability} core::ffi::c_void"))
}

fn emit_record_pointer_field_type(ty: &IrType) -> Option<String> {
    emit_opaque_void_pointer_type(ty).or_else(|| emit_integer_pointer_type(ty))
}

fn emit_integer_pointer_type(ty: &IrType) -> Option<String> {
    let IrTypeKind::Pointer { pointee } = &ty.kind else {
        return None;
    };
    if !is_integer_type(pointee) {
        return None;
    }
    let pointee_ty = emit_scalar_type(pointee).ok()?;
    let mutability = if pointee.is_const { "const" } else { "mut" };
    Some(format!("*{mutability} {pointee_ty}"))
}

fn emit_record_pointer_field_zero_value(ty: &IrType) -> Option<&'static str> {
    let IrTypeKind::Pointer { pointee } = &ty.kind else {
        return None;
    };
    emit_record_pointer_field_type(ty)?;
    if pointee.is_const {
        Some("core::ptr::null()")
    } else {
        Some("core::ptr::null_mut()")
    }
}

fn emit_nullable_pointer_param_type(ty: &IrType) -> Result<String, String> {
    if let Some(element_ty) = readonly_pointer_slice_element_type(ty) {
        let element_ty = emit_scalar_type(element_ty)?;
        return Ok(format!("Option<&[{element_ty}]>"));
    }
    if let Some(pointee) = readonly_record_pointer_pointee_type(ty) {
        let pointee = emit_value_type(pointee)?;
        return Ok(format!("Option<&{pointee}>"));
    }
    Err(format!(
        "nullable pointer param type {} is unsupported",
        type_label(ty)
    ))
}

fn emit_readonly_record_pointer_param_type(ty: &IrType) -> Result<String, String> {
    let pointee =
        readonly_record_pointer_pointee_type(ty).or_else(|| mutable_record_pointer_pointee_type(ty));
    if let Some(pointee) = pointee {
        let pointee = emit_value_type(pointee)?;
        return Ok(format!("&{pointee}"));
    }
    Err(format!(
        "readonly record pointer param type {} is unsupported",
        type_label(ty)
    ))
}

fn emit_mutable_record_pointer_param_type(ty: &IrType) -> Result<String, String> {
    if let Some(pointee) = mutable_record_pointer_pointee_type(ty) {
        let pointee = emit_value_type(pointee)?;
        return Ok(format!("&mut {pointee}"));
    }
    Err(format!(
        "mutable record pointer param type {} is unsupported",
        type_label(ty)
    ))
}
