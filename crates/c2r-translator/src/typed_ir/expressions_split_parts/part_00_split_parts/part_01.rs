fn emit_local_record_member_expr(
    expr: &IrExpr,
    symbols: &HashSet<String>,
) -> Result<Option<String>, String> {
    let Some(path) = local_record_member_path_from_expr(expr)? else {
        return Ok(None);
    };
    emit_local_record_member_path(&path, symbols).map(Some)
}

fn emit_local_record_member_path(
    path: &LocalRecordMemberPath<'_>,
    symbols: &HashSet<String>,
) -> Result<String, String> {
    if !symbols.contains(path.root_name) {
        return Err(format!(
            "local record member base {} is not declared",
            path.root_name
        ));
    }
    emit_scalar_type(path.ty).map_err(|detail| {
        format!(
            "local record member {}.{} has {detail}",
            path.root_name,
            path.fields.join(".")
        )
    })?;
    let root = emit_identifier(path.root_name, "local record member base")?;
    let fields = path
        .fields
        .iter()
        .map(|field| emit_identifier(field, "local record member field"))
        .collect::<Result<Vec<_>, _>>()?
        .join(".");
    Ok(format!("{root}.{fields}"))
}

fn emit_nested_record_pointer_member_expr(
    expr: &IrExpr,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<Option<String>, String> {
    let Some(path) = record_pointer_member_path_from_expr(expr)? else {
        return Ok(None);
    };
    if path.fields.len() <= 1 {
        return Ok(None);
    }
    if !symbols.contains(path.root_name) {
        return Err(format!(
            "nested arrow member base {} is not declared",
            path.root_name
        ));
    }
    let field_path = record_pointer_member_path_key(&path);
    if mutable_record_pointer_pointee_type(path.root_ty).is_some()
        && context.is_mutable_record_pointer_write_param(path.root_name)
    {
        emit_scalar_type(path.ty).map_err(|detail| {
            format!(
                "nested mutable record pointer field {}.{field_path} has {detail}",
                path.root_name
            )
        })?;
        if !context.is_mutable_record_pointer_read_field(path.root_name, &field_path) {
            return Err(format!(
                "mutable record pointer field {}.{field_path} lacks definite assignment evidence",
                path.root_name
            ));
        }
        return emit_record_pointer_member_path(
            &path,
            "nested mutable arrow member base",
            "nested mutable arrow member field",
        )
        .map(Some);
    }
    if mutable_record_pointer_pointee_type(path.root_ty).is_some()
        && !context.is_readonly_record_pointer_read_param(path.root_name)
    {
        return Err(format!(
            "nested mutable record pointer field {}.{field_path} requires mutable record pointer ownership evidence",
            path.root_name
        ));
    }
    readonly_record_pointer_read_pointee_type(path.root_name, path.root_ty, context).ok_or_else(
        || {
            format!(
                "nested arrow member base {} has unsupported type {}",
                path.root_name,
                type_label(path.root_ty)
            )
        },
    )?;
    if context.is_nullable_pointer_param(path.root_name) {
        return Err(format!(
            "nullable pointer param {} cannot use nested record pointer member path in the bounded emitter",
            path.root_name
        ));
    }
    emit_scalar_type(path.ty).map_err(|detail| {
        format!(
            "nested readonly record pointer field {}.{field_path} has {detail}",
            path.root_name
        )
    })?;
    emit_record_pointer_member_path(
        &path,
        "nested readonly arrow member base",
        "nested readonly arrow member field",
    )
    .map(Some)
}

fn emit_mutable_record_pointer_member_expr(
    base: &IrExpr,
    field: &str,
    ty: &IrType,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<Option<String>, String> {
    let IrExpr::Var {
        name: base_name,
        ty: base_ty,
        ..
    } = base
    else {
        return Ok(None);
    };
    if !context.is_mutable_record_pointer_write_param(base_name) {
        return Ok(None);
    }
    if !symbols.contains(base_name) {
        return Err(format!("arrow member base {base_name} is not declared"));
    }
    mutable_record_pointer_pointee_type(base_ty).ok_or_else(|| {
        format!(
            "arrow member base {base_name} has unsupported type {}",
            type_label(base_ty)
        )
    })?;
    emit_scalar_type(ty)
        .map_err(|detail| format!("mutable arrow member field {field} has {detail}"))?;
    if !context.is_mutable_record_pointer_read_field(base_name, field) {
        return Err(format!(
            "mutable record pointer field {base_name}.{field} lacks definite assignment evidence"
        ));
    }
    let base_name = emit_identifier(base_name, "mutable arrow member base")?;
    let field = emit_identifier(field, "mutable arrow member field")?;
    Ok(Some(format!("{base_name}.{field}")))
}

fn emit_readonly_record_pointer_member_expr(
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
        return Err("arrow member expression base must be a record pointer variable".to_string());
    };
    if !symbols.contains(base_name) {
        return Err(format!("arrow member base {base_name} is not declared"));
    }
    readonly_record_pointer_read_pointee_type(base_name, base_ty, context).ok_or_else(|| {
        format!(
            "arrow member base {base_name} has unsupported type {}",
            type_label(base_ty)
        )
    })?;
    emit_scalar_type(ty).map_err(|detail| format!("arrow member field {field} has {detail}"))?;
    let base_name = emit_identifier(base_name, "arrow member base")?;
    let field = emit_identifier(field, "arrow member field")?;
    if context.is_nullable_pointer_param(&base_name) {
        return Ok(format!("{base_name}.unwrap().{field}"));
    }
    Ok(format!("{base_name}.{field}"))
}

fn readonly_record_pointer_read_pointee_type<'a>(
    name: &str,
    ty: &'a IrType,
    context: &EmitContext,
) -> Option<&'a IrType> {
    readonly_record_pointer_pointee_type(ty).or_else(|| {
        context
            .is_readonly_record_pointer_read_param(name)
            .then(|| mutable_record_pointer_pointee_type(ty))
            .flatten()
    })
}

fn emit_readonly_pointer_add_deref_expr(
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
    let Some((base, index)) = readonly_pointer_add_operands(lhs, rhs) else {
        return Ok(None);
    };
    let IrExpr::Var {
        name: base_name,
        ty: base_ty,
        ..
    } = base
    else {
        return Err("deref pointer add base must be Var".to_string());
    };
    if add_ty != base_ty {
        return Err(format!(
            "deref pointer add result type {} does not match base type {}",
            type_label(add_ty),
            type_label(base_ty)
        ));
    }
    if !symbols.contains(base_name) {
        return Err(format!(
            "deref pointer add base {base_name} is not declared"
        ));
    }
    if context.is_nullable_pointer_param(base_name) {
        return Err(format!(
            "nullable pointer param {base_name} cannot be offset-dereferenced in the bounded emitter"
        ));
    }
    let element_ty = readonly_pointer_slice_element_type(base_ty).ok_or_else(|| {
        format!(
            "deref pointer add base {base_name} has unsupported type {}",
            type_label(base_ty)
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
    let index_ty = expr_type(index)
        .ok_or_else(|| "deref pointer add index type is unsupported".to_string())?;
    if !is_integer_type(index_ty) {
        return Err(format!(
            "deref pointer add index type {} is unsupported",
            type_label(index_ty)
        ));
    }
    validate_readonly_pointer_add_index_expr(index)?;
    let base = emit_identifier(base_name, "deref pointer add base")?;
    let index = emit_expr(index, symbols, context)
        .map_err(|detail| format!("deref pointer add index {detail}"))?;
    Ok(Some(format!("{base}[{index} as usize]")))
}

fn validate_readonly_pointer_add_index_expr(expr: &IrExpr) -> Result<(), String> {
    match expr {
        IrExpr::LitInt { ty, .. } | IrExpr::Var { ty, .. } => {
            if is_integer_type(ty) {
                Ok(())
            } else {
                Err(format!(
                    "deref pointer add index type {} is unsupported",
                    type_label(ty)
                ))
            }
        }
        IrExpr::Cast { target, expr, .. } => {
            if !is_integer_type(target) {
                return Err(format!(
                    "deref pointer add index cast target {} is unsupported",
                    type_label(target)
                ));
            }
            validate_readonly_pointer_add_index_expr(expr)
        }
        IrExpr::LValueToRValue { target, expr, .. } => {
            if !is_integer_type(target) {
                return Err(format!(
                    "deref pointer add index lvalue-to-rvalue target {} is unsupported",
                    type_label(target)
                ));
            }
            validate_readonly_pointer_add_index_expr(expr)
        }
        IrExpr::ArrayToPointerDecay { .. } => {
            Err("deref pointer add index cannot use array-to-pointer decay".to_string())
        }
        IrExpr::FunctionToPointerDecay { .. } => {
            Err("deref pointer add index cannot use function-to-pointer decay".to_string())
        }
        IrExpr::Call { callee, .. } => Err(format!(
            "deref pointer add index call expression {callee} is unsupported"
        )),
        IrExpr::Conditional { .. } => {
            Err("deref pointer add index cannot use conditional expression".to_string())
        }
        IrExpr::IncDec { .. } => {
            Err("deref pointer add index cannot use increment/decrement".to_string())
        }
        IrExpr::Deref { .. } => Err("deref pointer add index cannot use dereference".to_string()),
        IrExpr::Binary { .. } => {
            Err("deref pointer add index cannot use compound expression".to_string())
        }
        IrExpr::Unary { .. } => {
            Err("deref pointer add index cannot use unary expression".to_string())
        }
        IrExpr::Index { .. } => {
            Err("deref pointer add index cannot use index expression".to_string())
        }
        IrExpr::Member { .. } => {
            Err("deref pointer add index cannot use member expression".to_string())
        }
        IrExpr::AddrOf { .. } | IrExpr::MutableVoidPointerAddress { .. } => {
            Err("deref pointer add index cannot use address-of expression".to_string())
        }
        IrExpr::NullPtr { .. } => {
            Err("deref pointer add index cannot use null pointer".to_string())
        }
        IrExpr::ArrayLiteral { .. } => {
            Err("deref pointer add index cannot use array literal".to_string())
        }
        IrExpr::Unsupported { node, reason, .. } => Err(format!(
            "deref pointer add index unsupported expression {node}: {reason}"
        )),
    }
}

fn readonly_pointer_add_operands<'a>(
    lhs: &'a IrExpr,
    rhs: &'a IrExpr,
) -> Option<(&'a IrExpr, &'a IrExpr)> {
    match (expr_type(lhs), expr_type(rhs)) {
        (Some(lhs_ty), Some(rhs_ty))
            if readonly_pointer_slice_element_type(lhs_ty).is_some() && is_integer_type(rhs_ty) =>
        {
            Some((lhs, rhs))
        }
        (Some(lhs_ty), Some(rhs_ty))
            if is_integer_type(lhs_ty) && readonly_pointer_slice_element_type(rhs_ty).is_some() =>
        {
            Some((rhs, lhs))
        }
        _ => None,
    }
}

fn mutable_pointer_add_operands<'a>(
    lhs: &'a IrExpr,
    rhs: &'a IrExpr,
) -> Option<(&'a IrExpr, &'a IrExpr)> {
    match (expr_type(lhs), expr_type(rhs)) {
        (Some(lhs_ty), Some(rhs_ty))
            if mutable_pointer_slice_element_type(lhs_ty).is_some() && is_integer_type(rhs_ty) =>
        {
            Some((lhs, rhs))
        }
        (Some(lhs_ty), Some(rhs_ty))
            if is_integer_type(lhs_ty) && mutable_pointer_slice_element_type(rhs_ty).is_some() =>
        {
            Some((rhs, lhs))
        }
        _ => None,
    }
}
