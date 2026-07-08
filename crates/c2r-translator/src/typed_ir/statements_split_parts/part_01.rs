fn emit_for_stmt(
    init: &[IrStmt],
    condition: Option<&IrExpr>,
    step: Option<&IrStmt>,
    body: &[IrStmt],
    return_type: &IrType,
    indent_level: usize,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<String, String> {
    let indent = "    ".repeat(indent_level);
    let inner_indent = "    ".repeat(indent_level + 1);
    let mut loop_symbols = symbols.clone();
    let mut block = String::new();
    block.push_str(&format!("{indent}{{\n"));

    for (index, init) in init.iter().enumerate() {
        validate_for_init_stmt(init)?;
        let line = emit_stmt(
            init,
            return_type,
            indent_level + 1,
            &mut loop_symbols,
            context,
            LoopContext::None,
        )
        .map_err(|detail| format!("for init[{index}] {detail}"))?;
        block.push_str(&line);
    }

    let condition = match condition {
        Some(condition) => emit_condition_expr(condition, &loop_symbols, context)
            .map_err(|detail| format!("for condition {detail}"))?,
        None => "true".to_string(),
    };
    block.push_str(&format!("{inner_indent}while {condition} {{\n"));

    let mut body_symbols = loop_symbols.clone();
    let body_loop_context = step
        .map(|step| LoopContext::For { step })
        .unwrap_or(LoopContext::While);
    for (index, stmt) in body.iter().enumerate() {
        let line = emit_stmt(
            stmt,
            return_type,
            indent_level + 2,
            &mut body_symbols,
            context,
            body_loop_context,
        )
        .map_err(|detail| format!("for body[{index}].{detail}"))?;
        block.push_str(&line);
    }

    if let Some(step) = step {
        validate_for_step_stmt(step)?;
        let line = emit_stmt(
            step,
            return_type,
            indent_level + 2,
            &mut loop_symbols,
            context,
            LoopContext::None,
        )
        .map_err(|detail| format!("for step {detail}"))?;
        block.push_str(&line);
    }

    block.push_str(&format!("{inner_indent}}}\n"));
    block.push_str(&format!("{indent}}}\n"));
    Ok(block)
}

fn validate_for_init_stmt(stmt: &IrStmt) -> Result<(), String> {
    match stmt {
        IrStmt::Decl { .. } | IrStmt::Assign { .. } => Ok(()),
        _ => Err("for init must be a Decl or Assign statement".to_string()),
    }
}

fn validate_for_step_stmt(stmt: &IrStmt) -> Result<(), String> {
    match stmt {
        IrStmt::Assign { .. } => Ok(()),
        _ => Err("for step must be an Assign statement".to_string()),
    }
}

fn emit_assignment_target<'a>(
    target: &'a IrExpr,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<(String, &'a IrType), String> {
    match target {
        IrExpr::Var { name, ty, .. } => {
            if !symbols.contains(name) {
                return Err(format!("assign target {name} is not declared"));
            }
            let name = emit_identifier(name, "assign target")?;
            Ok((name, ty))
        }
        IrExpr::Index {
            base, index, ty, ..
        } => {
            let target = emit_index_assignment_target(base, index, ty, symbols, context)?;
            Ok((target, ty))
        }
        IrExpr::Deref { ptr, ty, .. } => {
            let target = emit_mutable_pointer_deref_assignment_target(ptr, ty, symbols, context)?;
            Ok((target, ty))
        }
        IrExpr::Member {
            base,
            field,
            ty,
            is_arrow,
            ..
        } => {
            if *is_arrow {
                let target = emit_mutable_record_pointer_member_assignment_target(
                    base, field, ty, symbols, context,
                )?;
                return Ok((target, ty));
            }
            let target = emit_member_expr(base, field, ty, *is_arrow, symbols, context)?;
            Ok((target, ty))
        }
        _ => Err(
            "assign target must be Var, local fixed array Index, pointer Deref, or by-value record Member"
                .to_string(),
        ),
    }
}

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
    if ty != return_type {
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

fn emit_mutable_record_pointer_member_assignment_target(
    base: &IrExpr,
    field: &str,
    ty: &IrType,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<String, String> {
    let IrExpr::Var {
        name: base_name,
        ty: base_ty,
        ..
    } = base
    else {
        return Err("arrow member assignment base must be a record pointer variable".to_string());
    };
    if !symbols.contains(base_name) {
        return Err(format!(
            "arrow member assignment base {base_name} is not declared"
        ));
    }
    if !context.is_mutable_record_pointer_write_param(base_name) {
        return Err(format!(
            "arrow member assignment base {base_name} requires mutable record pointer ownership evidence"
        ));
    }
    mutable_record_pointer_pointee_type(base_ty).ok_or_else(|| {
        format!(
            "arrow member assignment base {base_name} has unsupported type {}",
            type_label(base_ty)
        )
    })?;
    emit_mutable_record_pointer_field_type(ty)
        .map_err(|detail| format!("mutable record pointer arrow field {field} has {detail}"))?;
    let base_name = emit_identifier(base_name, "arrow member assignment base")?;
    let field = emit_identifier(field, "arrow member assignment field")?;
    Ok(format!("{base_name}.{field}"))
}

fn emit_mutable_record_pointer_member_compound_assignment_value(
    target: &IrExpr,
    value: &IrExpr,
    emitted_target: &str,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<Option<String>, String> {
    let IrExpr::Binary {
        op, lhs, rhs, ty, ..
    } = value
    else {
        return Ok(None);
    };
    if !same_direct_mutable_record_pointer_member(lhs, target, context)? {
        return Ok(None);
    }
    if let Some(reason) = mutable_record_pointer_field_compound_rhs_rejection_reason(rhs) {
        return Err(reason);
    }
    let op_token = emit_binary_op(op)?;
    validate_binary_operand_types(op_token, lhs, rhs, ty)?;
    validate_binary_runtime_contract(op, lhs, rhs, ty, &context.policy)?;
    let rhs = emit_expr(rhs, symbols, context).map_err(|detail| {
        format!("mutable record pointer field compound assignment RHS {detail}")
    })?;
    Ok(Some(emit_binary_result_expr(
        op,
        op_token,
        emitted_target,
        &rhs,
        ty,
    )))
}

fn emit_record_pointer_field_assignment_value(
    target: &IrExpr,
    value: &IrExpr,
    target_ty: &IrType,
    symbols: &HashSet<String>,
    context: &EmitContext,
    path: &str,
) -> Result<Option<EmittedExpr>, String> {
    let Some(target_pointer_ty) = emit_record_pointer_field_type(target_ty) else {
        return Ok(None);
    };
    let Some((base_name, _, _, _)) =
        direct_mutable_record_pointer_pointer_member_parts(target, context)?
    else {
        return Err(format!(
            "{path} pointer field target requires direct mutable record pointer ownership evidence"
        ));
    };
    if !context.is_mutable_record_pointer_write_param(base_name) {
        return Err(format!(
            "{path} pointer field target {base_name} requires mutable record pointer ownership evidence"
        ));
    }
    let expr = match value {
        IrExpr::Var { .. } => emit_record_pointer_field_value_var(
            value,
            &target_pointer_ty,
            symbols,
            context,
            path,
        )?,
        IrExpr::Cast {
            target: cast_target,
            expr,
            ..
        } => {
            let cast_target_ty = emit_opaque_void_pointer_type(cast_target).ok_or_else(|| {
                format!(
                    "{path} opaque pointer cast target {} is unsupported",
                    type_label(cast_target)
                )
            })?;
            if cast_target_ty != target_pointer_ty {
                return Err(format!(
                    "{path} opaque pointer cast target {cast_target_ty} does not match field type {target_pointer_ty}"
                ));
            }
            let source_ty = expr_type(expr)
                .ok_or_else(|| format!("{path} opaque pointer cast source type is unsupported"))?;
            let source_pointer_ty = emit_opaque_void_pointer_type(source_ty).ok_or_else(|| {
                format!(
                    "{path} opaque pointer cast source {} is unsupported",
                    type_label(source_ty)
                )
            })?;
            let expr = emit_record_pointer_field_value_var(
                expr,
                &source_pointer_ty,
                symbols,
                context,
                &format!("{path} opaque pointer cast source"),
            )?;
            format!("({expr} as {target_pointer_ty})")
        }
        IrExpr::Member { .. } => emit_record_pointer_field_value_member(
            value,
            &target_pointer_ty,
            base_name,
            symbols,
            context,
            path,
        )?,
        _ => {
            return Err(format!(
                "{path} pointer field write requires a pointer param value or pointer cast"
            ))
        }
    };
    Ok(Some(EmittedExpr {
        prelude: String::new(),
        expr,
    }))
}

fn emit_record_pointer_field_value_var(
    expr: &IrExpr,
    expected_pointer_ty: &str,
    symbols: &HashSet<String>,
    context: &EmitContext,
    path: &str,
) -> Result<String, String> {
    let IrExpr::Var { name, ty, .. } = expr else {
        let source_ty = expr_type(expr).ok_or_else(|| format!("{path} type is unsupported"))?;
        return Err(format!("{path} {} is unsupported", type_label(source_ty)));
    };
    if !symbols.contains(name) {
        return Err(format!("{path} {name} is not declared"));
    }
    if !context.is_record_pointer_field_value_param(name) {
        return Err(format!(
            "{path} {name} requires record pointer field value evidence"
        ));
    }
    let source_pointer_ty = emit_record_pointer_field_type(ty)
        .ok_or_else(|| format!("{path} {} is unsupported", type_label(ty)))?;
    if source_pointer_ty != expected_pointer_ty {
        return Err(format!(
            "{path} type {source_pointer_ty} does not match expected type {expected_pointer_ty}"
        ));
    }
    emit_identifier(name, "pointer field value")
}

fn emit_record_pointer_field_value_member(
    expr: &IrExpr,
    expected_pointer_ty: &str,
    target_base_name: &str,
    symbols: &HashSet<String>,
    context: &EmitContext,
    path: &str,
) -> Result<String, String> {
    let Some((base_name, _, field, ty)) =
        direct_mutable_record_pointer_pointer_member_parts(expr, context)?
    else {
        let source_ty = expr_type(expr).ok_or_else(|| format!("{path} type is unsupported"))?;
        return Err(format!("{path} {} is unsupported", type_label(source_ty)));
    };
    if base_name != target_base_name {
        return Err(format!(
            "{path} pointer field read base {base_name} does not match target base {target_base_name}"
        ));
    }
    if !symbols.contains(base_name) {
        return Err(format!("{path} pointer field read base {base_name} is not declared"));
    }
    if !context.is_mutable_record_pointer_read_field(base_name, field) {
        return Err(format!(
            "{path} pointer field {base_name}.{field} lacks definite assignment evidence"
        ));
    }
    if emit_opaque_void_pointer_type(ty).is_some() {
        return Err(format!(
            "{path} opaque pointer field {base_name}.{field} read still requires pointer provenance evidence"
        ));
    }
    let source_pointer_ty = emit_record_pointer_field_type(ty)
        .ok_or_else(|| format!("{path} {} is unsupported", type_label(ty)))?;
    if source_pointer_ty != expected_pointer_ty {
        return Err(format!(
            "{path} pointer field read type {source_pointer_ty} does not match expected type {expected_pointer_ty}"
        ));
    }
    let base_name = emit_identifier(base_name, "pointer field read base")?;
    let field = emit_identifier(field, "pointer field read field")?;
    Ok(format!("{base_name}.{field}"))
}

fn direct_mutable_record_pointer_pointer_member_parts<'a>(
    expr: &'a IrExpr,
    context: &EmitContext,
) -> Result<Option<(&'a str, &'a IrType, &'a str, &'a IrType)>, String> {
    let Some((base, base_ty, field, ty)) =
        direct_mutable_record_pointer_member_parts_any_field(expr, context)?
    else {
        return Ok(None);
    };
    emit_record_pointer_field_type(ty).ok_or_else(|| {
        format!(
            "mutable record pointer raw pointer field {base}.{field} has unsupported type {}",
            type_label(ty)
        )
    })?;
    Ok(Some((base, base_ty, field, ty)))
}

fn same_direct_mutable_record_pointer_member(
    lhs: &IrExpr,
    target: &IrExpr,
    context: &EmitContext,
) -> Result<bool, String> {
    let Some((target_base, target_base_ty, target_field, target_ty)) =
        direct_mutable_record_pointer_member_parts(target, context)?
    else {
        return Ok(false);
    };
    let Some((lhs_base, lhs_base_ty, lhs_field, lhs_ty)) =
        direct_mutable_record_pointer_member_parts(lhs, context)?
    else {
        return Ok(false);
    };
    Ok(target_base == lhs_base
        && target_base_ty == lhs_base_ty
        && target_field == lhs_field
        && target_ty == lhs_ty)
}

fn direct_mutable_record_pointer_member_parts<'a>(
    expr: &'a IrExpr,
    context: &EmitContext,
) -> Result<Option<(&'a str, &'a IrType, &'a str, &'a IrType)>, String> {
    let Some((base, base_ty, field, ty)) =
        direct_mutable_record_pointer_member_parts_any_field(expr, context)?
    else {
        return Ok(None);
    };
    emit_scalar_type(ty).map_err(|detail| {
        format!("mutable record pointer field compound assignment field {field} has {detail}")
    })?;
    Ok(Some((base, base_ty, field, ty)))
}

fn direct_mutable_record_pointer_member_parts_any_field<'a>(
    expr: &'a IrExpr,
    context: &EmitContext,
) -> Result<Option<(&'a str, &'a IrType, &'a str, &'a IrType)>, String> {
    let IrExpr::Member {
        base,
        field,
        ty,
        is_arrow: true,
        ..
    } = expr
    else {
        return Ok(None);
    };
    let IrExpr::Var {
        name, ty: base_ty, ..
    } = base.as_ref()
    else {
        return Ok(None);
    };
    if !context.is_mutable_record_pointer_write_param(name) {
        return Ok(None);
    }
    mutable_record_pointer_pointee_type(base_ty).ok_or_else(|| {
        format!(
            "mutable record pointer field compound assignment base {name} has unsupported type {}",
            type_label(base_ty)
        )
    })?;
    Ok(Some((name.as_str(), base_ty, field.as_str(), ty)))
}

fn mutable_record_pointer_field_compound_rhs_rejection_reason(value: &IrExpr) -> Option<String> {
    match value {
        IrExpr::Var { ty, .. } | IrExpr::LitInt { ty, .. } => {
            if is_integer_type(ty) {
                None
            } else {
                Some(format!(
                    "mutable record pointer field compound assignment RHS must be a simple integer variable, literal, or integral cast; got {}",
                    type_label(ty)
                ))
            }
        }
        IrExpr::Cast { target, expr, .. } => {
            if !is_integer_type(target) {
                return Some(format!(
                    "mutable record pointer field compound assignment RHS cast target must be an integer; got {}",
                    type_label(target)
                ));
            }
            mutable_record_pointer_field_compound_rhs_rejection_reason(expr)
        }
        IrExpr::Unsupported { node, reason, .. } => Some(format!(
            "mutable record pointer field compound assignment RHS uses unsupported expression {node}: {reason}"
        )),
        _ => Some(
            "mutable record pointer field compound assignment RHS must be a simple integer variable, literal, or integral cast"
                .to_string(),
        ),
    }
}
