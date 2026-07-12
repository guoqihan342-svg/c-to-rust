
fn emit_readonly_pointer_deref_expr(
    ptr: &IrExpr,
    ty: &IrType,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<String, String> {
    if let Some(expr) = emit_readonly_pointer_add_deref_expr(ptr, ty, symbols, context)? {
        return Ok(expr);
    }
    let IrExpr::Var {
        name: ptr_name,
        ty: ptr_ty,
        ..
    } = ptr
    else {
        return Err("deref pointer must be Var".to_string());
    };
    if !symbols.contains(ptr_name) {
        return Err(format!("deref pointer {ptr_name} is not declared"));
    }
    if context.is_nullable_pointer_param(ptr_name) {
        return Err(format!(
            "nullable pointer param {ptr_name} cannot be dereferenced in the bounded emitter"
        ));
    }
    let element_ty = readonly_pointer_slice_element_type(ptr_ty).ok_or_else(|| {
        format!(
            "deref pointer {ptr_name} has unsupported type {}",
            type_label(ptr_ty)
        )
    })?;
    let element_ty =
        emit_scalar_type(element_ty).map_err(|detail| format!("deref element has {detail}"))?;
    let deref_ty = emit_scalar_type(ty).map_err(|detail| format!("deref result has {detail}"))?;
    if deref_ty != element_ty {
        return Err(format!(
            "deref result type {deref_ty} does not match pointer element type {element_ty}"
        ));
    }
    let ptr_name = emit_identifier(ptr_name, "deref pointer")?;
    Ok(format!("{ptr_name}[0usize]"))
}

fn emit_member_expr(
    base: &IrExpr,
    field: &str,
    ty: &IrType,
    is_arrow: bool,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<String, String> {
    if is_arrow {
        if let Some(expr) =
            emit_mutable_record_pointer_member_expr(base, field, ty, symbols, context)?
        {
            return Ok(expr);
        }
        return emit_readonly_record_pointer_member_expr(base, field, ty, symbols, context);
    }
    if let Some(path) = local_record_member_path_from_parts(base, field, ty, is_arrow)? {
        return emit_local_record_member_path(&path, symbols);
    }
    let IrExpr::Var {
        name: base_name,
        ty: base_ty,
        ..
    } = base
    else {
        return Err("member expression base must be a record variable".to_string());
    };
    if !symbols.contains(base_name) {
        return Err(format!("member base {base_name} is not declared"));
    }
    if !matches!(base_ty.kind, IrTypeKind::Record { .. }) {
        return Err(format!(
            "member base {base_name} has unsupported type {}",
            type_label(base_ty)
        ));
    }
    emit_scalar_type(ty).map_err(|detail| format!("member field {field} has {detail}"))?;
    let base_name = emit_identifier(base_name, "member base")?;
    let field = emit_identifier(field, "member field")?;
    Ok(format!("{base_name}.{field}"))
}

#[derive(Clone, Debug)]
struct LocalRecordMemberPath<'a> {
    root_name: &'a str,
    fields: Vec<&'a str>,
    ty: &'a IrType,
}

fn local_record_member_path_from_expr(
    expr: &IrExpr,
) -> Result<Option<LocalRecordMemberPath<'_>>, String> {
    let IrExpr::Member {
        base,
        field,
        ty,
        is_arrow,
        ..
    } = expr
    else {
        return Ok(None);
    };
    local_record_member_path_from_parts(base, field, ty, *is_arrow)
}

fn local_record_member_path_from_parts<'a>(
    base: &'a IrExpr,
    field: &'a str,
    ty: &'a IrType,
    is_arrow: bool,
) -> Result<Option<LocalRecordMemberPath<'a>>, String> {
    if is_arrow
        || !matches!(
            base,
            IrExpr::Member {
                is_arrow: false,
                ..
            }
        )
    {
        return Ok(None);
    }
    let mut members = Vec::new();
    let Some((root_name, root_ty)) = collect_local_record_member_path_parts(base, &mut members)?
    else {
        return Ok(None);
    };
    members.push((field, ty));

    let mut current_ty = root_ty;
    let mut fields = Vec::with_capacity(members.len());
    for (member_field, member_ty) in members {
        let IrTypeKind::Record {
            name: record_name,
            fields: Some(record_fields),
        } = &current_ty.kind
        else {
            return Err(format!(
                "local record member base {} has incomplete or non-record type {}",
                root_name,
                type_label(current_ty)
            ));
        };
        let declared_field = record_fields
            .iter()
            .find(|declared| declared.name == member_field)
            .ok_or_else(|| {
                format!("complete local record {record_name} has no field {member_field}")
            })?;
        if !local_record_member_types_match(member_ty, &declared_field.ty) {
            return Err(format!(
                "local record member {record_name}.{member_field} type {} does not match declared type {}",
                type_label(member_ty),
                type_label(&declared_field.ty)
            ));
        }
        fields.push(member_field);
        current_ty = &declared_field.ty;
    }
    emit_scalar_type(current_ty).map_err(|detail| {
        format!(
            "local record member {}.{} has {detail}",
            root_name,
            fields.join(".")
        )
    })?;
    Ok(Some(LocalRecordMemberPath {
        root_name,
        fields,
        ty: current_ty,
    }))
}

fn collect_local_record_member_path_parts<'a>(
    expr: &'a IrExpr,
    members: &mut Vec<(&'a str, &'a IrType)>,
) -> Result<Option<(&'a str, &'a IrType)>, String> {
    match expr {
        IrExpr::Var { name, ty, .. } => Ok(Some((name, ty))),
        IrExpr::Member {
            base,
            field,
            ty,
            is_arrow: false,
            ..
        } => {
            let Some(root) = collect_local_record_member_path_parts(base, members)? else {
                return Ok(None);
            };
            members.push((field, ty));
            Ok(Some(root))
        }
        IrExpr::Member { is_arrow: true, .. } => Ok(None),
        _ => Ok(None),
    }
}

fn local_record_member_types_match(actual: &IrType, declared: &IrType) -> bool {
    match (&actual.kind, &declared.kind) {
        (
            IrTypeKind::Record {
                name: actual_name, ..
            },
            IrTypeKind::Record {
                name: declared_name,
                ..
            },
        ) => actual_name == declared_name && actual.is_const == declared.is_const,
        _ => types_match_ignoring_spelling(actual, declared),
    }
}
