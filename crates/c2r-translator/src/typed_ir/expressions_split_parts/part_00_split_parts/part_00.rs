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
        IrExpr::MutableVoidPointerAddress { .. } => Err(
            "mutable void pointer address is only supported as a direct call argument"
                .to_string(),
        ),
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
