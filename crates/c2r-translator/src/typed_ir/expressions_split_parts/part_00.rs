fn emit_expr(
    expr: &IrExpr,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<String, String> {
    match expr {
        IrExpr::LitInt { value, ty, .. } => emit_integer_literal(*value, ty),
        IrExpr::NullPtr { .. } => {
            Err("null pointer literal is only supported in pointer null comparisons".to_string())
        }
        IrExpr::Var { name, ty, .. } => {
            if let Some(global) = context.readonly_global(name) {
                validate_global_expr_type(global, ty)?;
                return context.global_rust_name(name);
            }
            if !symbols.contains(name) {
                return Err(format!("var {name} is not declared"));
            }
            emit_value_type(ty).map_err(|detail| format!("var {name} has {detail}"))?;
            emit_identifier(name, "var")
        }
        IrExpr::Binary {
            op, lhs, rhs, ty, ..
        } => {
            if let Some(expr) = emit_short_circuit_value_expr(op, lhs, rhs, ty, symbols, context)? {
                return Ok(expr);
            }
            if let Some(expr) = emit_comparison_value_expr(op, lhs, rhs, ty, symbols, context)? {
                return Ok(expr);
            }
            let op_token = emit_binary_op(op)?;
            validate_binary_operand_types(op_token, lhs, rhs, ty)?;
            validate_binary_runtime_contract(op, lhs, rhs, ty, &context.policy)?;
            let lhs = emit_expr(lhs, symbols, context)
                .map_err(|detail| format!("binary lhs {detail}"))?;
            let rhs = emit_expr(rhs, symbols, context)
                .map_err(|detail| format!("binary rhs {detail}"))?;
            Ok(emit_binary_result_expr(op, op_token, &lhs, &rhs, ty))
        }
        IrExpr::Unary {
            op, operand, ty, ..
        } => match op {
            IrUnOp::Neg => {
                validate_signed_unary_minus_operand(operand, ty)?;
                let operand = emit_expr(operand, symbols, context)
                    .map_err(|detail| format!("unary minus operand {detail}"))?;
                Ok(format!("(-{operand})"))
            }
            IrUnOp::Not => emit_logical_not_value_expr(operand, ty, symbols, context),
            IrUnOp::BitNot => {
                validate_expr_matches_type(operand, ty, "bitnot operand")?;
                let operand = emit_expr(operand, symbols, context)
                    .map_err(|detail| format!("bitnot operand {detail}"))?;
                Ok(format!("!{operand}"))
            }
        },
        IrExpr::Conditional {
            condition,
            then_expr,
            else_expr,
            ty,
            ..
        } => emit_conditional_value_expr(condition, then_expr, else_expr, ty, symbols, context),
        IrExpr::Cast { target, expr, .. } => {
            if !is_integer_type(target) {
                return Err(format!("cast target {} is unsupported", type_label(target)));
            }
            let source_type =
                expr_type(expr).ok_or_else(|| "cast source type is unsupported".to_string())?;
            if !is_integer_type(source_type) {
                return Err(format!(
                    "cast source {} is unsupported",
                    type_label(source_type)
                ));
            }
            let target =
                emit_scalar_type(target).map_err(|detail| format!("cast target has {detail}"))?;
            let expr = emit_expr(expr, symbols, context)
                .map_err(|detail| format!("cast expr {detail}"))?;
            Ok(format!("({expr} as {target})"))
        }
        IrExpr::LValueToRValue { target, expr, .. } => {
            if !is_integer_type(target) {
                return Err(format!(
                    "lvalue-to-rvalue target {} is unsupported",
                    type_label(target)
                ));
            }
            let source_type = expr_type(expr)
                .ok_or_else(|| "lvalue-to-rvalue source type is unsupported".to_string())?;
            if !is_integer_type(source_type) {
                return Err(format!(
                    "lvalue-to-rvalue source {} is unsupported",
                    type_label(source_type)
                ));
            }
            validate_expr_matches_type(expr, target, "lvalue-to-rvalue expr")?;
            emit_expr(expr, symbols, context)
                .map_err(|detail| format!("lvalue-to-rvalue expr {detail}"))
        }
        IrExpr::ArrayToPointerDecay { .. } => {
            Err("array-to-pointer decay requires explicit lowering evidence".to_string())
        }
        IrExpr::FunctionToPointerDecay { .. } => Err(
            "function-to-pointer decay creates a function pointer value and requires explicit function-pointer lowering evidence".to_string(),
        ),
        IrExpr::Index {
            base, index, ty, ..
        } => emit_index_expr(base, index, ty, symbols, context),
        IrExpr::Member {
            base,
            field,
            ty,
            is_arrow,
            ..
        } => {
            if let Some(path_expr) = emit_local_record_member_expr(expr, symbols)? {
                return Ok(path_expr);
            }
            if let Some(path_expr) = emit_nested_record_pointer_member_expr(expr, symbols, context)?
            {
                return Ok(path_expr);
            }
            emit_member_expr(base, field, ty, *is_arrow, symbols, context)
        }
        IrExpr::ArrayLiteral { .. } => Err(
            "array literal expression is only supported as a declaration initializer".to_string(),
        ),
        IrExpr::Call {
            callee, args, ty, ..
        } => emit_call_expr(callee, args, ty, symbols, context),
        IrExpr::IncDec { .. } => Err("inc/dec expression is unsupported".to_string()),
        IrExpr::Deref { ptr, ty, .. } => {
            if let Some(expr) = emit_mutable_pointer_deref_expr(ptr, ty, symbols, context)? {
                return Ok(expr);
            }
            emit_readonly_pointer_deref_expr(ptr, ty, symbols, context)
        }
        IrExpr::AddrOf { .. } => Err("address-of expression is unsupported".to_string()),
        IrExpr::Unsupported { node, reason, .. } => {
            Err(format!("unsupported expression {node}: {reason}"))
        }
    }
}

fn emit_mutable_pointer_deref_expr(
    ptr: &IrExpr,
    ty: &IrType,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<Option<String>, String> {
    let IrExpr::Var {
        name: ptr_name,
        ty: ptr_ty,
        ..
    } = ptr
    else {
        return Ok(None);
    };
    if !context.is_mutable_pointer_write_param(ptr_name) {
        return Ok(None);
    }
    if !symbols.contains(ptr_name) {
        return Err(format!("mutable deref pointer {ptr_name} is not declared"));
    }
    if context.is_nullable_pointer_param(ptr_name) {
        return Err(format!(
            "nullable pointer param {ptr_name} cannot be dereferenced in the bounded emitter"
        ));
    }
    let element_ty = mutable_pointer_slice_element_type(ptr_ty).ok_or_else(|| {
        format!(
            "mutable deref pointer {ptr_name} has unsupported type {}",
            type_label(ptr_ty)
        )
    })?;
    let element_ty = emit_scalar_type(element_ty)
        .map_err(|detail| format!("mutable deref element has {detail}"))?;
    let deref_ty =
        emit_scalar_type(ty).map_err(|detail| format!("mutable deref result has {detail}"))?;
    if deref_ty != element_ty {
        return Err(format!(
            "mutable deref result type {deref_ty} does not match pointer element type {element_ty}"
        ));
    }
    if !context.is_mutable_pointer_read_slot(ptr_name) {
        return Err(format!(
            "mutable pointer slot {ptr_name}[0] lacks definite assignment evidence"
        ));
    }
    let ptr_name = emit_identifier(ptr_name, "mutable deref pointer")?;
    Ok(Some(format!("{ptr_name}[0usize]")))
}

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
    if is_arrow {
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
        IrExpr::AddrOf { .. } => {
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
