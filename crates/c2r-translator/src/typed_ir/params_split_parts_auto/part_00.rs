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

pub(crate) fn emit_function_pointer_param_type(ty: &IrType) -> Result<Option<String>, String> {
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
