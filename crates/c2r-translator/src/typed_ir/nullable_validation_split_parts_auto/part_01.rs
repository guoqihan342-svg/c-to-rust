
fn validate_nullable_pointer_param_uses_in_expr(
    expr: &IrExpr,
    nullable_params: &HashSet<String>,
    proven_nonnull_params: &HashSet<String>,
) -> Result<(), String> {
    if let IrExpr::Binary {
        op: IrBinOp::Eq | IrBinOp::Neq,
        lhs,
        rhs,
        ..
    } = expr
    {
        if null_pointer_comparison_var(lhs, rhs)
            .is_some_and(|(name, _)| nullable_params.contains(name))
        {
            return Ok(());
        }
    }
    if nullable_record_pointer_arrow_read_is_proven_nonnull(
        expr,
        nullable_params,
        proven_nonnull_params,
    )? {
        return Ok(());
    }
    match expr {
        IrExpr::Var { name, ty, .. } if nullable_params.contains(name) => {
            validate_nullable_pointer_type(name, ty)?;
            Err(format!(
                "nullable pointer param {name} is only supported in null comparisons"
            ))
        }
        IrExpr::Binary { lhs, rhs, .. } => {
            validate_nullable_pointer_param_uses_in_expr(
                lhs,
                nullable_params,
                proven_nonnull_params,
            )?;
            validate_nullable_pointer_param_uses_in_expr(
                rhs,
                nullable_params,
                proven_nonnull_params,
            )
        }
        IrExpr::Unary { operand, .. }
        | IrExpr::Cast { expr: operand, .. }
        | IrExpr::LValueToRValue { expr: operand, .. }
        | IrExpr::ArrayToPointerDecay { expr: operand, .. }
        | IrExpr::FunctionToPointerDecay { expr: operand, .. }
        | IrExpr::AddrOf { operand, .. }
        | IrExpr::MutableVoidPointerAddress { operand, .. } => validate_nullable_pointer_param_uses_in_expr(
            operand,
            nullable_params,
            proven_nonnull_params,
        ),
        IrExpr::Conditional {
            condition,
            then_expr,
            else_expr,
            ..
        } => {
            validate_nullable_pointer_param_uses_in_expr(
                condition,
                nullable_params,
                proven_nonnull_params,
            )?;
            validate_nullable_pointer_param_uses_in_expr(
                then_expr,
                nullable_params,
                proven_nonnull_params,
            )?;
            validate_nullable_pointer_param_uses_in_expr(
                else_expr,
                nullable_params,
                proven_nonnull_params,
            )
        }
        IrExpr::Index { base, index, .. } => {
            validate_nullable_pointer_param_uses_in_expr(
                base,
                nullable_params,
                proven_nonnull_params,
            )?;
            validate_nullable_pointer_param_uses_in_expr(
                index,
                nullable_params,
                proven_nonnull_params,
            )
        }
        IrExpr::Member { base, .. } => validate_nullable_pointer_param_uses_in_expr(
            base,
            nullable_params,
            proven_nonnull_params,
        ),
        IrExpr::ArrayLiteral { elements, .. } => {
            for element in elements {
                validate_nullable_pointer_param_uses_in_expr(
                    element,
                    nullable_params,
                    proven_nonnull_params,
                )?;
            }
            Ok(())
        }
        IrExpr::Call {
            callee, args, ty, ..
        } => {
            if nullable_strlen_call_is_proven_nonnull(
                callee,
                args,
                ty,
                nullable_params,
                proven_nonnull_params,
            ) {
                return Ok(());
            }
            if mutable_record_pointer_pointee_type(ty).is_some() {
                match validate_record_pointer_return_nested_call_arg(callee, args, ty, None) {
                    Ok(()) => {
                        for (index, arg) in args.iter().enumerate() {
                            if index > 0
                                && nullable_record_pointer_return_call_inner_arg_is_proven_nonnull(
                                    arg,
                                    nullable_params,
                                    proven_nonnull_params,
                                )
                            {
                                continue;
                            }
                            validate_nullable_pointer_param_uses_in_expr(
                                arg,
                                nullable_params,
                                proven_nonnull_params,
                            )
                            .map_err(|detail| {
                                format!("record pointer return call {callee} arg[{index}] {detail}")
                            })?;
                        }
                        return Ok(());
                    }
                    Err(detail) => {
                        return Err(format!(
                            "record pointer return call {callee} failed validation before nullable arg handling: {detail}"
                        ));
                    }
                }
            }
            for (index, arg) in args.iter().enumerate() {
                validate_nullable_pointer_param_uses_in_expr(
                    arg,
                    nullable_params,
                    proven_nonnull_params,
                )
                .map_err(|detail| format!("call {callee} arg[{index}] {detail}"))?;
            }
            Ok(())
        }
        IrExpr::IncDec { target, .. } => validate_nullable_pointer_param_uses_in_expr(
            target,
            nullable_params,
            proven_nonnull_params,
        ),
        IrExpr::Deref { ptr, .. } => validate_nullable_pointer_param_uses_in_expr(
            ptr,
            nullable_params,
            proven_nonnull_params,
        ),
        IrExpr::LitInt { .. }
        | IrExpr::NullPtr { .. }
        | IrExpr::Var { .. }
        | IrExpr::Unsupported { .. } => Ok(()),
    }
}

fn null_return_guard_proves_nonnull<'a>(
    stmt: &'a IrStmt,
    nullable_params: &HashSet<String>,
) -> Option<&'a str> {
    let IrStmt::If {
        condition,
        then_body,
        else_body,
        ..
    } = stmt
    else {
        return None;
    };
    if !else_body.is_empty() || !matches!(then_body.as_slice(), [IrStmt::Return { .. }]) {
        return None;
    }
    let IrExpr::Binary {
        op: IrBinOp::Eq,
        lhs,
        rhs,
        ..
    } = condition
    else {
        return None;
    };
    let (name, _) = null_pointer_comparison_var(lhs, rhs)?;
    nullable_params.contains(name).then_some(name)
}

fn nullable_strlen_call_is_proven_nonnull(
    callee: &str,
    args: &[IrExpr],
    ty: &IrType,
    nullable_params: &HashSet<String>,
    proven_nonnull_params: &HashSet<String>,
) -> bool {
    if callee != "strlen" || validate_c_strlen_call_shape(args, ty).is_err() {
        return false;
    }
    let [IrExpr::Var { name, ty, .. }] = args else {
        return false;
    };
    nullable_params.contains(name)
        && proven_nonnull_params.contains(name)
        && is_readonly_8_bit_pointer_type(ty)
}

fn nullable_record_pointer_return_call_inner_arg_is_proven_nonnull(
    arg: &IrExpr,
    nullable_params: &HashSet<String>,
    proven_nonnull_params: &HashSet<String>,
) -> bool {
    match arg {
        IrExpr::Var { name, ty, .. } => {
            nullable_params.contains(name)
                && proven_nonnull_params.contains(name)
                && is_readonly_8_bit_pointer_type(ty)
        }
        IrExpr::Call {
            callee, args, ty, ..
        } => nullable_strlen_call_is_proven_nonnull(
            callee,
            args,
            ty,
            nullable_params,
            proven_nonnull_params,
        ),
        _ => false,
    }
}

enum NullComparisonNonnullBranch<'a> {
    Then { param: &'a str },
    Else { param: &'a str },
}

fn null_comparison_nonnull_branch<'a>(
    condition: &'a IrExpr,
    nullable_params: &HashSet<String>,
) -> Option<NullComparisonNonnullBranch<'a>> {
    if let Some(name) = nullable_pointer_truthiness_var(condition, nullable_params) {
        return Some(NullComparisonNonnullBranch::Then { param: name });
    }
    let IrExpr::Binary { op, lhs, rhs, .. } = condition else {
        return None;
    };
    let (name, _) = null_pointer_comparison_var(lhs, rhs)?;
    if !nullable_params.contains(name) {
        return None;
    }
    match op {
        IrBinOp::Neq => Some(NullComparisonNonnullBranch::Then { param: name }),
        IrBinOp::Eq => Some(NullComparisonNonnullBranch::Else { param: name }),
        _ => None,
    }
}

fn nullable_pointer_truthiness_var<'a>(
    condition: &'a IrExpr,
    nullable_params: &HashSet<String>,
) -> Option<&'a str> {
    let (name, _) = nullable_pointer_truthiness_var_parts(condition)?;
    nullable_params.contains(name).then_some(name)
}

fn nullable_pointer_truthiness_var_parts(expr: &IrExpr) -> Option<(&str, &IrType)> {
    match expr {
        IrExpr::Var { name, ty, .. } => Some((name.as_str(), ty)),
        IrExpr::LValueToRValue { expr, target, .. } | IrExpr::Cast { expr, target, .. }
            if matches!(target.kind, IrTypeKind::Pointer { .. }) =>
        {
            nullable_pointer_truthiness_var_parts(expr)
        }
        _ => None,
    }
}

fn nullable_record_pointer_arrow_read_is_proven_nonnull(
    expr: &IrExpr,
    nullable_params: &HashSet<String>,
    proven_nonnull_params: &HashSet<String>,
) -> Result<bool, String> {
    let IrExpr::Member {
        base,
        field,
        ty: member_ty,
        is_arrow: true,
        ..
    } = expr
    else {
        return Ok(false);
    };
    let IrExpr::Var {
        name, ty: base_ty, ..
    } = base.as_ref()
    else {
        return Ok(false);
    };
    if !nullable_params.contains(name) || !proven_nonnull_params.contains(name) {
        return Ok(false);
    }
    if readonly_record_pointer_pointee_type(base_ty).is_none() {
        return Ok(false);
    }
    emit_scalar_type(member_ty)
        .map_err(|detail| format!("nullable record pointer arrow field {field} has {detail}"))?;
    Ok(true)
}
