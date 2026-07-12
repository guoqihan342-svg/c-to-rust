
fn emit_mutable_record_pointer_identity_return(
    value: &IrExpr,
    return_type: &IrType,
    indent_level: usize,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<Option<String>, String> {
    if mutable_record_pointer_pointee_type(return_type).is_none() {
        return Ok(None);
    }
    let IrExpr::Var { name, ty, .. } = value else {
        return Err(
            "mutable record pointer return must return the owned record pointer parameter"
                .to_string(),
        );
    };
    if !record_pointer_types_match_ignoring_spelling(ty, return_type) {
        return Err(format!(
            "mutable record pointer return type {} does not match function return type {}",
            type_label(ty),
            type_label(return_type)
        ));
    }
    if !symbols.contains(name) {
        return Err(format!(
            "mutable record pointer return value {name} is not declared"
        ));
    }
    if !context.is_mutable_record_pointer_write_param(name) {
        return Err(format!(
            "mutable record pointer return {name} requires mutable record pointer ownership evidence"
        ));
    }
    let indent = "    ".repeat(indent_level);
    let name = emit_identifier(name, "mutable record pointer return value")?;
    Ok(Some(format!("{indent}return {name};\n")))
}

fn emit_function_pointer_decay_return(
    value: &IrExpr,
    return_type: &IrType,
    indent_level: usize,
) -> Result<Option<String>, String> {
    if emit_function_pointer_param_type(return_type)?.is_none() {
        return Ok(None);
    }
    let IrExpr::FunctionToPointerDecay { target, expr, .. } = value else {
        return Err(
            "function pointer return must be a direct function-to-pointer decay".to_string(),
        );
    };
    if target != return_type {
        return Err(format!(
            "function pointer return target {} does not match function return type {}",
            type_label(target),
            type_label(return_type)
        ));
    }
    let value = emit_function_pointer_decay_call_arg(target, expr)
        .map_err(|detail| format!("function pointer return {detail}"))?;
    let indent = "    ".repeat(indent_level);
    Ok(Some(format!("{indent}return {value};\n")))
}

fn emit_record_pointer_field_raw_pointer_return(
    value: &IrExpr,
    return_type: &IrType,
    indent_level: usize,
    symbols: &HashSet<String>,
) -> Result<Option<String>, String> {
    let Some(expected_pointer_ty) = emit_record_pointer_field_type(return_type) else {
        return Ok(None);
    };
    let IrExpr::Member {
        base,
        field,
        ty,
        is_arrow: true,
        ..
    } = value
    else {
        return Err(format!(
            "pointer value return {} requires explicit ownership/lifetime/ABI lowering",
            type_label(return_type)
        ));
    };
    if ty != return_type {
        return Err(format!(
            "record pointer field return type {} does not match function return type {}",
            type_label(ty),
            type_label(return_type)
        ));
    }
    let source_pointer_ty = emit_record_pointer_field_type(ty).ok_or_else(|| {
        format!(
            "record pointer field return field {field} has unsupported type {}",
            type_label(ty)
        )
    })?;
    if source_pointer_ty != expected_pointer_ty {
        return Err(format!(
            "record pointer field return type {source_pointer_ty} does not match expected type {expected_pointer_ty}"
        ));
    }
    let IrExpr::Var {
        name: base_name,
        ty: base_ty,
        ..
    } = base.as_ref()
    else {
        return Err(
            "record pointer field return base must be a direct readonly record pointer variable"
                .to_string(),
        );
    };
    if !symbols.contains(base_name) {
        return Err(format!(
            "record pointer field return base {base_name} is not declared"
        ));
    }
    readonly_record_pointer_pointee_type(base_ty).ok_or_else(|| {
        format!(
            "record pointer field return base {base_name} has unsupported type {}",
            type_label(base_ty)
        )
    })?;
    let base_name = emit_identifier(base_name, "record pointer field return base")?;
    let field = emit_identifier(field, "record pointer field return field")?;
    let indent = "    ".repeat(indent_level);
    Ok(Some(format!("{indent}return {base_name}.{field};\n")))
}

fn emit_function_pointer_decay_assignment(
    target: &IrExpr,
    value: &IrExpr,
    target_name: &str,
    target_ty: &IrType,
) -> Result<Option<String>, String> {
    if emit_function_pointer_param_type(target_ty)?.is_none() {
        return Ok(None);
    }
    let IrExpr::Var { .. } = target else {
        return Err("function pointer assignment target must be a local variable".to_string());
    };
    let IrExpr::FunctionToPointerDecay {
        target: decay_target,
        expr,
        ..
    } = value
    else {
        return Err(
            "function pointer assignment value must be a direct function-to-pointer decay"
                .to_string(),
        );
    };
    if decay_target != target_ty {
        return Err(format!(
            "function pointer assignment target {} does not match assigned value target {}",
            type_label(target_ty),
            type_label(decay_target)
        ));
    }
    let value = emit_function_pointer_decay_call_arg(decay_target, expr)
        .map_err(|detail| format!("function pointer assignment {detail}"))?;
    Ok(Some(format!("{target_name} = {value};")))
}
