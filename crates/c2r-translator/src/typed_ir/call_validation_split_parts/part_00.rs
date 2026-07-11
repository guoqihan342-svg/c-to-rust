fn reserved_c_macro_or_stdlib_callee(callee: &str) -> bool {
    matches!(
        callee,
        // Keep modeled macro names here as a fail-closed backstop; modeled
        // forms must be intercepted before this reserved-surface guard.
        "assert"
            | "abs"
            | "labs"
            | "llabs"
            | "fabs"
            | "fabsf"
            | "fabsl"
            | "static_assert"
            | "_Static_assert"
            | "sizeof"
            | "offsetof"
            | "malloc"
            | "calloc"
            | "realloc"
            | "free"
            | "memcpy"
            | "memmove"
            | "memset"
            | "strlen"
            | "strnlen"
            | "strnlen_s"
            | "printf"
            | "fprintf"
            | "sprintf"
            | "snprintf"
            | "puts"
            | "putchar"
            | "getchar"
            | "exit"
            | "abort"
    )
}

fn validate_bounded_call_args(args: &[IrExpr], context: &EmitContext) -> Result<(), String> {
    let nested_call_count = args
        .iter()
        .filter(|arg| matches!(arg, IrExpr::Call { .. }))
        .count();
    if nested_call_count > 1 {
        return Err(
            "multiple nested call arguments are outside the bounded call subset".to_string(),
        );
    }
    if nested_call_count > 0 && args.iter().any(is_direct_record_scalar_member_call_arg) {
        return Err(
            "direct record scalar member call argument cannot be combined with an additional call"
                .to_string(),
        );
    }
    let mutable_record_borrows = args
        .iter()
        .enumerate()
        .filter_map(|(index, arg)| match arg {
            IrExpr::Var { name, ty, .. }
                if validate_mutable_record_pointer_call_arg(name, ty, context).is_ok() =>
            {
                Some((index, name.as_str()))
            }
            _ => None,
        })
        .collect::<Vec<_>>();
    let interior_reborrow_pair = match mutable_record_borrows.as_slice() {
        [(_, left), (_, right)] => context.is_interior_reborrow_call_pair(left, right),
        _ => false,
    };
    if mutable_record_borrows.len() > 1 && !interior_reborrow_pair {
        return Err(
            "one direct call cannot borrow multiple mutable record pointer parameters"
                .to_string(),
        );
    }
    for (borrow_index, borrowed_name) in &mutable_record_borrows {
        if args.iter().enumerate().any(|(index, arg)| {
            index != *borrow_index && expr_mentions_var(arg, borrowed_name)
        }) {
            return Err(format!(
                "mutable record pointer call argument {borrowed_name} cannot have a sibling argument that reads the same record"
            ));
        }
    }
    let side_effect_args = side_effect_call_args(args)?;
    for (index, arg) in args.iter().enumerate() {
        if !side_effect_args.is_empty() {
            if side_effect_args
                .iter()
                .any(|(side_effect_index, _)| *side_effect_index == index)
            {
                continue;
            }
            for (_, assigned_var) in &side_effect_args {
                if expr_mentions_var(arg, assigned_var) {
                    return Err(format!(
                        "side-effect call argument cannot be combined with sibling argument reading modified variable {assigned_var}"
                    ));
                }
            }
            validate_bounded_call_arg_with_context(arg, false, Some(context))
        } else {
            validate_bounded_call_arg_with_context(arg, true, Some(context))
        }
        .map_err(|detail| format!("call arg[{index}] {detail}"))?;
    }
    Ok(())
}
fn is_direct_record_scalar_member_call_arg(expr: &IrExpr) -> bool {
    match expr {
        IrExpr::Member { .. } => true,
        IrExpr::Cast { expr, .. } | IrExpr::LValueToRValue { expr, .. } => {
            is_direct_record_scalar_member_call_arg(expr)
        }
        _ => false,
    }
}

fn validate_bounded_side_effect_call_args(args: &[IrExpr]) -> Result<Vec<(usize, &str)>, String> {
    let side_effect_args = side_effect_call_args(args)?;
    for (side_effect_index, assigned_var) in &side_effect_args {
        for (index, arg) in args.iter().enumerate() {
            if index == *side_effect_index {
                continue;
            }
            if expr_mentions_var(arg, assigned_var) {
                return Err(format!(
                    "side-effect call argument cannot be combined with sibling argument reading modified variable {assigned_var}"
                ));
            }
        }
    }
    Ok(side_effect_args)
}

fn validate_bounded_call_arg(
    expr: &IrExpr,
    allow_immediate_nested_call: bool,
) -> Result<(), String> {
    validate_bounded_call_arg_with_context(expr, allow_immediate_nested_call, None)
}

fn validate_bounded_call_arg_with_context(
    expr: &IrExpr,
    allow_immediate_nested_call: bool,
    context: Option<&EmitContext>,
) -> Result<(), String> {
    match expr {
        IrExpr::LitInt { ty, .. } => {
            if matches!(ty.kind, IrTypeKind::Pointer { .. }) {
                if emit_opaque_void_pointer_type(ty).is_some() {
                    return Ok(());
                }
                return Err(format!(
                    "pointer value argument {} requires explicit ownership/lifetime/ABI lowering",
                    type_label(ty)
                ));
            }
            emit_scalar_type(ty)?;
            Ok(())
        }
        IrExpr::Var { name, ty, .. } => {
            if matches!(ty.kind, IrTypeKind::Pointer { .. }) {
                if emit_opaque_void_pointer_type(ty).is_some() {
                    return Ok(());
                }
                if let Some(context) = context {
                    if validate_mutable_record_pointer_call_arg(name, ty, context).is_ok() {
                        return Ok(());
                    }
                    if validate_raw_direct_call_pointer_arg(name, ty, context).is_ok() {
                        return Ok(());
                    }
                }
                return Err(format!(
                    "pointer value argument {} requires explicit ownership/lifetime/ABI lowering",
                    type_label(ty)
                ));
            }
            emit_scalar_type(ty)?;
            Ok(())
        }
        IrExpr::NullPtr { ty, .. } => validate_null_pointer_call_arg(ty),
        IrExpr::Binary { lhs, rhs, .. } => {
            validate_bounded_call_arg_with_context(lhs, false, context)?;
            validate_bounded_call_arg_with_context(rhs, false, context)
        }
        IrExpr::Unary { operand, .. }
        | IrExpr::Cast { expr: operand, .. }
        | IrExpr::LValueToRValue { expr: operand, .. } => {
            validate_bounded_call_arg_with_context(operand, false, context)
        }
        IrExpr::ArrayToPointerDecay { target, expr, .. } => {
            validate_array_decay_direct_call_arg(target, expr).map(|_| ())
        }
        IrExpr::FunctionToPointerDecay { target, expr, .. } => {
            validate_function_pointer_decay_call_arg(target, expr).map(|_| ())
        }
        IrExpr::Conditional { .. } => {
            Err("conditional call arguments are outside the bounded call subset".to_string())
        }
        IrExpr::Index { base, index, .. } => {
            validate_bounded_call_arg_with_context(base, false, context)?;
            validate_bounded_call_arg_with_context(index, false, context)
        }
        IrExpr::Member {
            base,
            field,
            ty,
            is_arrow,
            ..
        } => validate_direct_record_scalar_member_call_arg(
            base, field, ty, *is_arrow, context,
        ),
        IrExpr::ArrayLiteral { .. } => {
            Err("array literal arguments are outside the bounded call subset".to_string())
        }
        IrExpr::Call {
            callee, args, ty, ..
        } if allow_immediate_nested_call => {
            validate_bounded_nested_call_arg(callee, args, ty, context)
        }
        IrExpr::Call { .. } => {
            Err("nested call expressions are outside the bounded call subset".to_string())
        }
        IrExpr::IncDec { .. } => {
            Err("call arguments cannot use increment/decrement value semantics".to_string())
        }
        IrExpr::Deref { .. } => {
            Err("call arguments cannot use dereference value semantics".to_string())
        }
        IrExpr::AddrOf { operand, ty, .. } => {
            validate_local_record_address_call_arg(operand, ty).map(|_| ())
        }
        IrExpr::Unsupported { node, reason, .. } => {
            Err(format!("unsupported argument expression {node}: {reason}"))
        }
    }
}

fn validate_mutable_record_pointer_call_arg(
    name: &str,
    ty: &IrType,
    context: &EmitContext,
) -> Result<(), String> {
    if !context.is_mutable_record_pointer_write_param(name) {
        return Err(format!(
            "mutable record pointer call argument {name} lacks ownership evidence"
        ));
    }
    mutable_record_pointer_pointee_type(ty).ok_or_else(|| {
        format!(
            "mutable record pointer call argument {name} has unsupported type {}",
            type_label(ty)
        )
    })?;
    if context.is_nullable_pointer_param(name) {
        return Err(format!(
            "nullable mutable record pointer {name} cannot be passed to a direct call"
        ));
    }
    Ok(())
}

fn validate_direct_record_scalar_member_call_arg(
    base: &IrExpr,
    field: &str,
    ty: &IrType,
    is_arrow: bool,
    context: Option<&EmitContext>,
) -> Result<(), String> {
    if !is_integer_type(ty) {
        return Err(format!(
            "direct record call argument field {field} must be a fixed-width integer scalar, got {}",
            type_label(ty)
        ));
    }
    emit_scalar_type(ty)
        .map_err(|detail| format!("direct record call argument field {field} has {detail}"))?;
    let IrExpr::Var {
        name: root_name,
        ty: root_ty,
        ..
    } = base
    else {
        return Err(
            "direct record scalar member call argument base must be a direct DeclRef root"
                .to_string(),
        );
    };

    let record_ty = if is_arrow {
        let context = context.ok_or_else(|| {
            "direct record pointer scalar member call argument requires readonly/noalias context"
                .to_string()
        })?;
        if context.is_nullable_pointer_param(root_name) {
            return Err(format!(
                "nullable record pointer param {root_name} cannot be a direct scalar member call argument"
            ));
        }
        if context.is_assignment_call_sibling_record_read(root_name, field) {
            mutable_record_pointer_pointee_type(root_ty).ok_or_else(|| {
                format!(
                    "assignment-call sibling record pointer {root_name} has unsupported type {}",
                    type_label(root_ty)
                )
            })?
        } else {
            readonly_record_pointer_read_pointee_type(root_name, root_ty, context).ok_or_else(
                || {
                    format!(
                        "record pointer call argument base {root_name} lacks readonly/noalias read proof for {}",
                        type_label(root_ty)
                    )
                },
            )?
        }
    } else {
        root_ty
    };
    let IrTypeKind::Record {
        name: record_name,
        fields: Some(fields),
    } = &record_ty.kind
    else {
        return Err(format!(
            "direct record scalar member call argument base {root_name} is not a complete record type"
        ));
    };
    let declared = fields
        .iter()
        .find(|declared| declared.name == field)
        .ok_or_else(|| format!("complete record {record_name} has no field {field}"))?;
    if !is_integer_type(&declared.ty) {
        return Err(format!(
            "direct record call argument field {record_name}.{field} is not a fixed-width integer scalar"
        ));
    }
    emit_scalar_type(&declared.ty).map_err(|detail| {
        format!("direct record call argument field {record_name}.{field} has {detail}")
    })?;
    if !types_match_ignoring_spelling(ty, &declared.ty) {
        return Err(format!(
            "direct record call argument field {record_name}.{field} type {} does not match declared type {}",
            type_label(ty),
            type_label(&declared.ty)
        ));
    }
    Ok(())
}
