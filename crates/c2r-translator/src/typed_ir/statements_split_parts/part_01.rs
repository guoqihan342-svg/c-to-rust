fn emit_opaque_record_pointer_field_value_var(
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
    if !context.is_opaque_record_pointer_field_value_param(name) {
        return Err(format!(
            "{path} {name} requires opaque record pointer field value evidence"
        ));
    }
    let source_pointer_ty = emit_opaque_void_pointer_type(ty)
        .ok_or_else(|| format!("{path} {} is unsupported", type_label(ty)))?;
    if source_pointer_ty != expected_pointer_ty {
        return Err(format!(
            "{path} type {source_pointer_ty} does not match expected type {expected_pointer_ty}"
        ));
    }
    emit_identifier(name, "opaque pointer field value")
}

fn direct_mutable_record_pointer_opaque_member_parts<'a>(
    expr: &'a IrExpr,
    context: &EmitContext,
) -> Result<Option<(&'a str, &'a IrType, &'a str, &'a IrType)>, String> {
    let Some((base, base_ty, field, ty)) =
        direct_mutable_record_pointer_member_parts_any_field(expr, context)?
    else {
        return Ok(None);
    };
    emit_opaque_void_pointer_type(ty).ok_or_else(|| {
        format!(
            "mutable record pointer opaque field {base}.{field} has unsupported type {}",
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

fn emit_index_assignment_target(
    base: &IrExpr,
    index: &IrExpr,
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
        return Err("assign index base must be Var".to_string());
    };
    if context.readonly_global(base_name).is_some() {
        return Err(format!(
            "assign index base {base_name} is a readonly global"
        ));
    }
    if !symbols.contains(base_name) {
        return Err(format!("assign index base {base_name} is not declared"));
    }
    if base_ty.is_const {
        return Err(format!(
            "assign index base {base_name} has const type {}",
            type_label(base_ty)
        ));
    }
    let element_ty = fixed_integer_array_element_type(base_ty)
        .or_else(|| mutable_pointer_slice_element_type(base_ty))
        .ok_or_else(|| {
            format!(
                "assign index base {base_name} has unsupported type {}",
                type_label(base_ty)
            )
        })?;
    let element_ty = emit_scalar_type(element_ty)
        .map_err(|detail| format!("assign index element has {detail}"))?;
    let result_ty =
        emit_scalar_type(ty).map_err(|detail| format!("assign index result has {detail}"))?;
    if result_ty != element_ty {
        return Err(format!(
            "assign index result type {result_ty} does not match element type {element_ty}"
        ));
    }
    let index_ty =
        expr_type(index).ok_or_else(|| "assign index operand type is unsupported".to_string())?;
    if !is_integer_type(index_ty) {
        return Err(format!(
            "assign index operand type {} is unsupported",
            type_label(index_ty)
        ));
    }
    let base = emit_identifier(base_name, "assign index base")?;
    let index = emit_expr(index, symbols, context)
        .map_err(|detail| format!("assign index operand {detail}"))?;
    Ok(format!("{base}[{index} as usize]"))
}

fn emit_mutable_pointer_deref_assignment_target(
    ptr: &IrExpr,
    ty: &IrType,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<String, String> {
    if let Some(target) =
        emit_mutable_pointer_add_deref_assignment_target(ptr, ty, symbols, context)?
    {
        return Ok(target);
    }
    let IrExpr::Var {
        name: ptr_name,
        ty: ptr_ty,
        ..
    } = ptr
    else {
        return Err("deref assignment pointer must be Var".to_string());
    };
    if !symbols.contains(ptr_name) {
        return Err(format!(
            "deref assignment pointer {ptr_name} is not declared"
        ));
    }
    if context.is_nullable_pointer_param(ptr_name) {
        return Err(format!(
            "nullable pointer param {ptr_name} cannot be dereference-assigned in the bounded emitter"
        ));
    }
    let element_ty = mutable_pointer_slice_element_type(ptr_ty).ok_or_else(|| {
        format!(
            "deref assignment pointer {ptr_name} has unsupported type {}",
            type_label(ptr_ty)
        )
    })?;
    let element_ty = emit_scalar_type(element_ty)
        .map_err(|detail| format!("deref assignment element has {detail}"))?;
    let deref_ty =
        emit_scalar_type(ty).map_err(|detail| format!("deref assignment result has {detail}"))?;
    if deref_ty != element_ty {
        return Err(format!(
            "deref assignment result type {deref_ty} does not match pointer element type {element_ty}"
        ));
    }
    let ptr_name = emit_identifier(ptr_name, "deref assignment pointer")?;
    Ok(format!("{ptr_name}[0usize]"))
}

fn emit_mutable_pointer_add_deref_assignment_target(
    ptr: &IrExpr,
    ty: &IrType,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<Option<String>, String> {
    let IrExpr::Binary {
        op: IrBinOp::Add,
        lhs,
        rhs,
        ty: add_ty,
        ..
    } = ptr
    else {
        return Ok(None);
    };
    let Some((base, index)) = mutable_pointer_add_operands(lhs, rhs) else {
        return Ok(None);
    };
    let IrExpr::Var {
        name: base_name,
        ty: base_ty,
        ..
    } = base
    else {
        return Err("deref pointer add assignment base must be Var".to_string());
    };
    if add_ty != base_ty {
        return Err(format!(
            "deref pointer add assignment result type {} does not match base type {}",
            type_label(add_ty),
            type_label(base_ty)
        ));
    }
    if !symbols.contains(base_name) {
        return Err(format!(
            "deref pointer add assignment base {base_name} is not declared"
        ));
    }
    if context.is_nullable_pointer_param(base_name) {
        return Err(format!(
            "nullable pointer param {base_name} cannot be offset-dereference-assigned in the bounded emitter"
        ));
    }
    let element_ty = mutable_pointer_slice_element_type(base_ty).ok_or_else(|| {
        format!(
            "deref pointer add assignment base {base_name} has unsupported type {}",
            type_label(base_ty)
        )
    })?;
    let element_ty = emit_scalar_type(element_ty)
        .map_err(|detail| format!("deref assignment element has {detail}"))?;
    let deref_ty =
        emit_scalar_type(ty).map_err(|detail| format!("deref assignment result has {detail}"))?;
    if deref_ty != element_ty {
        return Err(format!(
            "deref assignment result type {deref_ty} does not match pointer element type {element_ty}"
        ));
    }
    let index_ty = expr_type(index)
        .ok_or_else(|| "deref pointer add index type is unsupported".to_string())?;
    if !is_integer_type(index_ty) {
        return Err(format!(
            "deref pointer add index type {} is unsupported",
            type_label(index_ty)
        ));
    }
    validate_readonly_pointer_add_index_expr(index)?;
    let base = emit_identifier(base_name, "deref pointer add assignment base")?;
    let index = emit_expr(index, symbols, context)
        .map_err(|detail| format!("deref pointer add index {detail}"))?;
    Ok(Some(format!("{base}[{index} as usize]")))
}

fn emit_postfix_decrement_while_loop(
    condition: &IrExpr,
    body: &[IrStmt],
    return_type: &IrType,
    indent_level: usize,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<Option<String>, String> {
    let IrExpr::IncDec {
        target,
        op: IrIncDecOp::Dec,
        prefix: false,
        ty,
        ..
    } = condition
    else {
        return Ok(None);
    };
    let IrExpr::Var {
        name,
        ty: target_ty,
        ..
    } = target.as_ref()
    else {
        return Ok(None);
    };
    if !symbols.contains(name) {
        return Err(format!(
            "while condition decrement target {name} is not declared"
        ));
    }
    if !is_usize(target_ty) || !is_usize(ty) {
        return Ok(None);
    }

    let name = emit_identifier(name, "while condition decrement target")?;
    let counter_ty = emit_scalar_type(target_ty)
        .map_err(|detail| format!("while condition decrement target has {detail}"))?;
    let zero = zero_literal_for_type(target_ty)
        .map_err(|detail| format!("while condition decrement zero {detail}"))?;
    let one = emit_integer_literal(1, target_ty)
        .map_err(|detail| format!("while condition decrement step {detail}"))?;
    let snapshot = emit_identifier(
        &first_available_temp_name(&format!("{name}_before_dec"), symbols),
        "while condition decrement snapshot",
    )?;

    let indent = "    ".repeat(indent_level);
    let inner_indent = "    ".repeat(indent_level + 1);
    let break_indent = "    ".repeat(indent_level + 2);
    let mut block = String::new();
    block.push_str(&format!("{indent}loop {{\n"));
    block.push_str(&format!(
        "{inner_indent}let {snapshot}: {counter_ty} = {name};\n"
    ));
    block.push_str(&format!(
        "{inner_indent}{name} = {name}.wrapping_sub({one});\n"
    ));
    block.push_str(&format!("{inner_indent}if {snapshot} == {zero} {{\n"));
    block.push_str(&format!("{break_indent}break;\n"));
    block.push_str(&format!("{inner_indent}}}\n"));

    let mut loop_symbols = symbols.clone();
    for (index, stmt) in body.iter().enumerate() {
        let line = emit_stmt(
            stmt,
            return_type,
            indent_level + 1,
            &mut loop_symbols,
            context,
            LoopContext::While,
        )
        .map_err(|detail| format!("while body[{index}].{detail}"))?;
        block.push_str(&line);
    }
    block.push_str(&format!("{indent}}}\n"));
    Ok(Some(block))
}

fn emit_prefix_decrement_while_loop(
    condition: &IrExpr,
    body: &[IrStmt],
    return_type: &IrType,
    indent_level: usize,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<Option<String>, String> {
    let IrExpr::IncDec {
        target,
        op: IrIncDecOp::Dec,
        prefix: true,
        ty,
        ..
    } = condition
    else {
        return Ok(None);
    };
    let IrExpr::Var {
        name,
        ty: target_ty,
        ..
    } = target.as_ref()
    else {
        return Ok(None);
    };
    if !symbols.contains(name) {
        return Err(format!(
            "while condition prefix decrement target {name} is not declared"
        ));
    }
    if !is_usize(target_ty) || !is_usize(ty) {
        return Ok(None);
    }

    let name = emit_identifier(name, "while condition prefix decrement target")?;
    let _counter_ty = emit_scalar_type(target_ty)
        .map_err(|detail| format!("while condition prefix decrement target has {detail}"))?;
    let zero = zero_literal_for_type(target_ty)
        .map_err(|detail| format!("while condition prefix decrement zero {detail}"))?;
    let one = emit_integer_literal(1, target_ty)
        .map_err(|detail| format!("while condition prefix decrement step {detail}"))?;

    let indent = "    ".repeat(indent_level);
    let inner_indent = "    ".repeat(indent_level + 1);
    let break_indent = "    ".repeat(indent_level + 2);
    let mut block = String::new();
    block.push_str(&format!("{indent}loop {{\n"));
    block.push_str(&format!(
        "{inner_indent}{name} = {name}.wrapping_sub({one});\n"
    ));
    block.push_str(&format!("{inner_indent}if {name} == {zero} {{\n"));
    block.push_str(&format!("{break_indent}break;\n"));
    block.push_str(&format!("{inner_indent}}}\n"));

    let mut loop_symbols = symbols.clone();
    for (index, stmt) in body.iter().enumerate() {
        let line = emit_stmt(
            stmt,
            return_type,
            indent_level + 1,
            &mut loop_symbols,
            context,
            LoopContext::While,
        )
        .map_err(|detail| format!("while body[{index}].{detail}"))?;
        block.push_str(&line);
    }
    block.push_str(&format!("{indent}}}\n"));
    Ok(Some(block))
}
