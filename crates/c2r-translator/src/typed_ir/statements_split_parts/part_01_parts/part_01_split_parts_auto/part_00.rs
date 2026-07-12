
fn emit_mutable_record_pointer_member_assignment_target(
    expr: &IrExpr,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<Option<String>, String> {
    let Some(path) = record_pointer_member_path_from_expr(expr)? else {
        return Ok(None);
    };
    if !symbols.contains(path.root_name) {
        return Err(format!(
            "arrow member assignment base {} is not declared",
            path.root_name
        ));
    }
    let field_path = record_pointer_member_path_key(&path);
    if !context.is_mutable_record_pointer_write_param(path.root_name) {
        return Err(format!(
            "arrow member assignment base {} requires mutable record pointer ownership evidence",
            path.root_name
        ));
    }
    mutable_record_pointer_pointee_type(path.root_ty).ok_or_else(|| {
        format!(
            "arrow member assignment base {} has unsupported type {}",
            path.root_name,
            type_label(path.root_ty)
        )
    })?;
    emit_mutable_record_pointer_field_type(path.ty).map_err(|detail| {
        format!("mutable record pointer arrow field {field_path} has {detail}")
    })?;
    emit_record_pointer_member_path(
        &path,
        "arrow member assignment base",
        "arrow member assignment field",
    )
    .map(Some)
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
    if let Some(reason) =
        record_field_compound_assignment_value_rejection_reason(rhs, symbols, context)?
    {
        return Err(format!(
            "mutable record pointer field compound assignment RHS rejected: {reason}"
        ));
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
