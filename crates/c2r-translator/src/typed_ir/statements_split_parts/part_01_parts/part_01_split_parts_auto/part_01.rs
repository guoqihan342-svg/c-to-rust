
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
