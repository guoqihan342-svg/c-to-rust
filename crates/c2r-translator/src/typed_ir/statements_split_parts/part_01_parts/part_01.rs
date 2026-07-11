
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

fn record_field_compound_assignment_value_rejection_reason(
    value: &IrExpr,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<Option<String>, String> {
    match value {
        IrExpr::Var { ty, .. } | IrExpr::LitInt { ty, .. } => {
            if is_integer_type(ty) {
                Ok(None)
            } else {
                Ok(Some(format!(
                    "record field compound assignment RHS must be a simple integer variable, literal, integral cast, or direct integer record field read; got {}",
                    type_label(ty)
                )))
            }
        }
        IrExpr::Cast { target, expr, .. } => {
            if !is_integer_type(target) {
                return Ok(Some(format!(
                    "record field compound assignment RHS cast target must be an integer; got {}",
                    type_label(target)
                )));
            }
            record_field_compound_assignment_value_rejection_reason(expr, symbols, context)
        }
        IrExpr::LValueToRValue { target, expr, .. } => {
            if !is_integer_type(target) {
                return Ok(Some(format!(
                    "record field compound assignment RHS lvalue-to-rvalue target must be an integer; got {}",
                    type_label(target)
                )));
            }
            let source_ty = match expr_type(expr) {
                Some(source_ty) if is_integer_type(source_ty) => source_ty,
                Some(source_ty) => {
                    return Ok(Some(format!(
                        "record field compound assignment RHS lvalue-to-rvalue source must be an integer; got {}",
                        type_label(source_ty)
                    )))
                }
                None => {
                    return Ok(Some(
                        "record field compound assignment RHS lvalue-to-rvalue source type is unsupported"
                            .to_string(),
                    ))
                }
            };
            if let Err(detail) = validate_expr_matches_type(
                expr,
                target,
                "record field compound assignment RHS lvalue-to-rvalue expr",
            ) {
                return Ok(Some(detail));
            }
            if !direct_record_scalar_member_is_readable(expr, source_ty, symbols, context)? {
                return Ok(Some(
                    "record field compound assignment RHS lvalue-to-rvalue read must be a direct by-value or readonly record pointer scalar field"
                        .to_string(),
                ));
            }
            Ok(None)
        }
        IrExpr::Unsupported { node, reason, .. } => Ok(Some(format!(
            "record field compound assignment RHS uses unsupported expression {node}: {reason}"
        ))),
        _ => Ok(Some(
            "record field compound assignment RHS must be a simple integer variable, literal, integral cast, or direct integer record field read"
                .to_string(),
        )),
    }
}

fn direct_record_scalar_member_is_readable(
    expr: &IrExpr,
    ty: &IrType,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<bool, String> {
    let IrExpr::Member {
        base,
        field,
        ty: member_ty,
        is_arrow,
        ..
    } = expr
    else {
        return Ok(false);
    };
    if !is_integer_type(ty) || !is_integer_type(member_ty) {
        return Ok(false);
    }
    let IrExpr::Var {
        name: base_name,
        ty: base_ty,
        ..
    } = base.as_ref()
    else {
        return Ok(false);
    };
    let supported_base = if *is_arrow {
        readonly_record_pointer_read_pointee_type(base_name, base_ty, context).is_some()
            || (context.allows_owner_sibling_size_add_read(base_name)
                && mutable_record_pointer_pointee_type(base_ty).is_some())
            || (context.is_interior_reborrow_call_root(base_name)
                && mutable_record_pointer_pointee_type(base_ty).is_some())
    } else {
        matches!(&base_ty.kind, IrTypeKind::Record { .. })
    };
    if !supported_base {
        return Ok(false);
    }
    emit_member_expr(base, field, member_ty, *is_arrow, symbols, context)?;
    Ok(true)
}
