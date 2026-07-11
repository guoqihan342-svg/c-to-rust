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
            if let Some(target) =
                emit_mutable_record_pointer_member_assignment_target(target, symbols, context)?
            {
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

#[derive(Clone, Debug, Eq, PartialEq)]
struct AssignmentCallSiblingRecordRead {
    key: MutableRecordPointerFieldKey,
    arg_index: usize,
}

fn assignment_call_sibling_record_read(
    target: &IrExpr,
    value: &IrExpr,
) -> Result<Option<AssignmentCallSiblingRecordRead>, String> {
    let Some(target_path) = record_pointer_member_path_from_expr(target)? else {
        return Ok(None);
    };
    let IrExpr::Call { args, .. } = value else {
        return Ok(None);
    };
    let Some(target_record_ty) = mutable_record_pointer_pointee_type(target_path.root_ty) else {
        return Ok(None);
    };
    let IrTypeKind::Record {
        fields: Some(_), ..
    } = &target_record_ty.kind
    else {
        return Ok(None);
    };
    emit_scalar_type(target_path.ty).map_err(|detail| {
        format!(
            "assignment-call target field {} has {detail}",
            record_pointer_member_path_key(&target_path)
        )
    })?;
    let owner_arg_indices = args
        .iter()
        .enumerate()
        .filter_map(|(index, arg)| {
            expr_mentions_var(arg, target_path.root_name).then_some(index)
        })
        .collect::<Vec<_>>();
    let [arg_index] = owner_arg_indices.as_slice() else {
        return Ok(None);
    };
    let IrExpr::LValueToRValue {
        target: read_ty,
        expr,
        ..
    } = &args[*arg_index]
    else {
        return Ok(None);
    };
    let IrExpr::Member {
        base,
        field,
        ty: member_ty,
        is_arrow: true,
        ..
    } = expr.as_ref()
    else {
        return Ok(None);
    };
    let IrExpr::Var {
        name: owner,
        ty: owner_ty,
        ..
    } = base.as_ref()
    else {
        return Ok(None);
    };
    if owner != target_path.root_name
        || !record_pointer_types_match_ignoring_spelling(owner_ty, target_path.root_ty)
        || !types_match_ignoring_spelling(read_ty, member_ty)
        || record_pointer_member_path_key(&target_path) == *field
    {
        return Ok(None);
    }
    emit_scalar_type(member_ty)
        .map_err(|detail| format!("assignment-call sibling field {owner}.{field} has {detail}"))?;
    let IrTypeKind::Record {
        name: record_name,
        fields: Some(fields),
    } = &target_record_ty.kind
    else {
        return Ok(None);
    };
    let Some(declared) = fields.iter().find(|declared| declared.name == *field) else {
        return Err(format!(
            "assignment-call sibling field {record_name}.{field} is not declared"
        ));
    };
    if !types_match_ignoring_spelling(member_ty, &declared.ty) {
        return Err(format!(
            "assignment-call sibling field {record_name}.{field} type {} does not match declared type {}",
            type_label(member_ty),
            type_label(&declared.ty)
        ));
    }
    Ok(Some(AssignmentCallSiblingRecordRead {
        key: MutableRecordPointerFieldKey {
            base: owner.clone(),
            field: field.clone(),
        },
        arg_index: *arg_index,
    }))
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
