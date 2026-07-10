fn emit_param(
    param: &IrParam,
    assigned_vars: &HashSet<String>,
    context: &EmitContext,
    explicit_lifetime: Option<&str>,
) -> Result<String, String> {
    let mut ty = if context.is_nullable_pointer_param(&param.name) {
        emit_nullable_pointer_param_type(&param.ty)
            .map_err(|detail| format!("param {} has {}", param.name, detail))?
    } else if context.is_mutable_record_pointer_write_param(&param.name) {
        emit_mutable_record_pointer_param_type(&param.ty)
            .map_err(|detail| format!("param {} has {}", param.name, detail))?
    } else if context.is_readonly_record_pointer_read_param(&param.name) {
        emit_readonly_record_pointer_param_type(&param.ty)
            .map_err(|detail| format!("param {} has {}", param.name, detail))?
    } else if context.is_readonly_mutable_pointer_index_param(&param.name) {
        let element_ty = mutable_pointer_slice_element_type(&param.ty).ok_or_else(|| {
            format!(
                "param {} has unsupported body-proven readonly pointer type {}",
                param.name,
                type_label(&param.ty)
            )
        })?;
        let element_ty = emit_scalar_type(element_ty)
            .map_err(|detail| format!("param {} has {detail}", param.name))?;
        format!("&[{element_ty}]")
    } else if context.is_byte_slice_param(&param.name) {
        "&[u8]".to_string()
    } else if context.is_record_pointer_field_value_param(&param.name) {
        emit_record_pointer_field_value_param_type(&param.ty)
            .map_err(|detail| format!("param {} has {}", param.name, detail))?
    } else if context.is_opaque_pointer_call_arg_param(&param.name) {
        emit_opaque_void_pointer_param_type(&param.ty)
            .map_err(|detail| format!("param {} has {}", param.name, detail))?
    } else if should_emit_raw_direct_call_pointer_param(&param.name, &param.ty, context) {
        emit_raw_direct_call_pointer_param_type(&param.ty).ok_or_else(|| {
            format!(
                "param {} has raw direct call pointer type {} unsupported",
                param.name,
                type_label(&param.ty)
            )
        })?
    } else if should_emit_unused_readonly_8_bit_pointer_param(&param.name, &param.ty, context) {
        emit_unused_readonly_8_bit_pointer_param_type(&param.ty).ok_or_else(|| {
            format!(
                "param {} has unused readonly 8-bit pointer type {} unsupported",
                param.name,
                type_label(&param.ty)
            )
        })?
    } else if readonly_pointer_slice_element_type(&param.ty).is_some()
        && !context.is_readonly_pointer_read_param(&param.name)
        && !context.is_readonly_pointer_mentioned_param(&param.name)
    {
        return Err(format!(
            "param {} requires pointer-to-slice lowering evidence before lowering {} to &[T]",
            param.name,
            type_label(&param.ty)
        ));
    } else if assigned_vars.contains(&param.name) {
        emit_assigned_param_type(&param.ty)
            .map_err(|detail| format!("param {} has {}", param.name, detail))?
    } else {
        emit_param_type(&param.ty)
            .map_err(|detail| format!("param {} has {}", param.name, detail))?
    };
    if let Some(lifetime) = explicit_lifetime {
        ty = add_explicit_borrow_lifetime(&ty, lifetime)
            .map_err(|detail| format!("param {} {detail}", param.name))?;
    }
    let name = emit_identifier(&param.name, "param")?;
    let mut_prefix = if assigned_vars.contains(&param.name) {
        "mut "
    } else {
        ""
    };
    Ok(format!("{mut_prefix}{name}: {ty}"))
}

fn add_explicit_borrow_lifetime(ty: &str, lifetime: &str) -> Result<String, String> {
    if let Some(rest) = ty.strip_prefix("&mut ") {
        return Ok(format!("&'{lifetime} mut {rest}"));
    }
    if let Some(rest) = ty.strip_prefix('&') {
        return Ok(format!("&'{lifetime} {rest}"));
    }
    Err(format!(
        "requires a borrowed type for explicit lifetime, got {ty}"
    ))
}

fn returned_mutable_record_pointer_param<'a>(
    function: &'a IrFunction,
    context: &EmitContext,
) -> Result<Option<&'a str>, String> {
    if mutable_record_pointer_pointee_type(&function.return_type).is_none() {
        return Ok(None);
    }
    let Some(IrStmt::Return {
        value: Some(IrExpr::Var { name, ty, .. }),
        ..
    }) = function.body.last()
    else {
        return Ok(None);
    };
    if !record_pointer_types_match_ignoring_spelling(ty, &function.return_type) {
        return Err(format!(
            "mutable record pointer return type {} does not match function return type {}",
            type_label(ty),
            type_label(&function.return_type)
        ));
    }
    if !context.is_mutable_record_pointer_write_param(name) {
        return Ok(None);
    }
    Ok(Some(name.as_str()))
}

fn emitted_borrow_param_count(function: &IrFunction, context: &EmitContext) -> usize {
    function
        .params
        .iter()
        .filter(|param| emitted_param_type_is_borrow(param, &context.assigned_vars, context))
        .count()
}

fn emitted_param_type_is_borrow(
    param: &IrParam,
    assigned_vars: &HashSet<String>,
    context: &EmitContext,
) -> bool {
    if context.is_record_pointer_field_value_param(&param.name)
        || context.is_opaque_pointer_call_arg_param(&param.name)
        || should_emit_raw_direct_call_pointer_param(&param.name, &param.ty, context)
        || should_emit_unused_readonly_8_bit_pointer_param(&param.name, &param.ty, context)
    {
        return false;
    }
    context.is_nullable_pointer_param(&param.name)
        || context.is_mutable_record_pointer_write_param(&param.name)
        || context.is_readonly_record_pointer_read_param(&param.name)
        || context.is_readonly_mutable_pointer_index_param(&param.name)
        || context.is_byte_slice_param(&param.name)
        || (assigned_vars.contains(&param.name)
            && mutable_pointer_slice_element_type(&param.ty).is_some())
        || (readonly_pointer_slice_element_type(&param.ty).is_some()
            && (context.is_readonly_pointer_read_param(&param.name)
                || context.is_readonly_pointer_mentioned_param(&param.name)))
        || readonly_record_pointer_pointee_type(&param.ty).is_some()
}

fn emit_assigned_param_type(ty: &IrType) -> Result<String, String> {
    if let Some(element_ty) = mutable_pointer_slice_element_type(ty) {
        let element_ty = emit_scalar_type(element_ty)?;
        return Ok(format!("&mut [{element_ty}]"));
    }
    emit_param_type(ty)
}

fn emit_param_type(ty: &IrType) -> Result<String, String> {
    if let Some(function_pointer_ty) = emit_function_pointer_param_type(ty)? {
        return Ok(function_pointer_ty);
    }
    if let Some(element_ty) = readonly_pointer_slice_element_type(ty) {
        let element_ty = emit_scalar_type(element_ty)?;
        return Ok(format!("&[{element_ty}]"));
    }
    if let Some(pointee) = readonly_record_pointer_pointee_type(ty) {
        return emit_value_type(pointee).map(|ty| format!("&{ty}"));
    }
    emit_value_type(ty)
}

fn emit_function_pointer_param_type(ty: &IrType) -> Result<Option<String>, String> {
    let IrTypeKind::Pointer { pointee } = &ty.kind else {
        return Ok(None);
    };
    if !matches!(pointee.kind, IrTypeKind::Function) {
        return Ok(None);
    }
    emit_function_pointer_signature_type(&pointee.spelled)
        .map(Some)
        .map_err(|detail| {
            format!(
                "function pointer type {} is unsupported: {detail}",
                type_label(ty)
            )
        })
}

fn emit_function_pointer_signature_type(spelling: &str) -> Result<String, String> {
    let trimmed = spelling.trim();
    let Some(open) = trimmed.find('(') else {
        return Err("missing parameter list".to_string());
    };
    if !trimmed.ends_with(')') {
        return Err("missing closing parameter list".to_string());
    }
    let return_type = trimmed[..open].trim();
    let params = trimmed[open + 1..trimmed.len() - 1].trim();
    let rust_return = emit_function_pointer_signature_scalar(return_type, true)?;
    let rust_params = if params.is_empty() || params == "void" {
        Vec::new()
    } else {
        params
            .split(',')
            .map(|param| emit_function_pointer_signature_scalar(param.trim(), false))
            .collect::<Result<Vec<_>, _>>()?
    };
    let params = rust_params.join(", ");
    if rust_return == "()" {
        Ok(format!("fn({params})"))
    } else {
        Ok(format!("fn({params}) -> {rust_return}"))
    }
}

fn emit_function_pointer_signature_scalar(
    spelling: &str,
    allow_void: bool,
) -> Result<String, String> {
    if spelling.contains('(') || spelling.contains(')') || spelling.contains('*') {
        return Err(format!(
            "{spelling} is outside the simple scalar signature subset"
        ));
    }
    match spelling {
        "void" if allow_void => Ok("()".to_string()),
        "int" => Ok("i32".to_string()),
        "signed char" | "int8_t" => Ok("i8".to_string()),
        "unsigned char" | "uint8_t" => Ok("u8".to_string()),
        "int16_t" => Ok("i16".to_string()),
        "uint16_t" => Ok("u16".to_string()),
        "unsigned int" | "uint32_t" => Ok("u32".to_string()),
        "int64_t" => Ok("i64".to_string()),
        "uint64_t" => Ok("u64".to_string()),
        "size_t" => Ok("usize".to_string()),
        _ => Err(format!(
            "{spelling} is outside the simple scalar signature subset"
        )),
    }
}

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
