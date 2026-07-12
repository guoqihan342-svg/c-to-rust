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
