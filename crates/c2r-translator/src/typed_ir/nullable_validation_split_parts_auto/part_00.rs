fn validate_nullable_pointer_param_uses_in_body(
    body: &[IrStmt],
    nullable_params: &HashSet<String>,
    proven_nonnull_params: &mut HashSet<String>,
) -> Result<(), String> {
    for stmt in body {
        validate_nullable_pointer_param_uses_in_stmt(stmt, nullable_params, proven_nonnull_params)?;
        if let Some(param) = null_return_guard_proves_nonnull(stmt, nullable_params) {
            proven_nonnull_params.insert(param.to_string());
        }
    }
    Ok(())
}

/// Enforces the semantic boundary for nullable pointer parameters in one stmt.
///
/// Nullable pointers may only be used in null comparisons, except for guarded
/// readonly record arrow field reads. The checker carries simple branch and
/// early-return facts but does not infer loop invariants or global alias
/// guarantees.
fn validate_nullable_pointer_param_uses_in_stmt(
    stmt: &IrStmt,
    nullable_params: &HashSet<String>,
    proven_nonnull_params: &HashSet<String>,
) -> Result<(), String> {
    if nullable_params.is_empty() {
        return Ok(());
    }
    match stmt {
        IrStmt::Decl { init, .. } => {
            if let Some(init) = init {
                validate_nullable_pointer_param_uses_in_expr(
                    init,
                    nullable_params,
                    proven_nonnull_params,
                )?;
            }
        }
        IrStmt::Assign { target, value, .. } => {
            validate_nullable_pointer_param_uses_in_expr(
                target,
                nullable_params,
                proven_nonnull_params,
            )?;
            validate_nullable_pointer_param_uses_in_expr(
                value,
                nullable_params,
                proven_nonnull_params,
            )?;
        }
        IrStmt::If {
            condition,
            then_body,
            else_body,
            ..
        } => {
            validate_nullable_pointer_param_uses_in_condition(
                condition,
                nullable_params,
                proven_nonnull_params,
            )?;
            let mut then_nonnull_params = proven_nonnull_params.clone();
            let mut else_nonnull_params = proven_nonnull_params.clone();
            match null_comparison_nonnull_branch(condition, nullable_params) {
                Some(NullComparisonNonnullBranch::Then { param }) => {
                    then_nonnull_params.insert(param.to_string());
                }
                Some(NullComparisonNonnullBranch::Else { param }) => {
                    else_nonnull_params.insert(param.to_string());
                }
                None => {}
            }
            validate_nullable_pointer_param_uses_in_body(
                then_body,
                nullable_params,
                &mut then_nonnull_params,
            )
            .map_err(|detail| format!("if then branch {detail}"))?;
            validate_nullable_pointer_param_uses_in_body(
                else_body,
                nullable_params,
                &mut else_nonnull_params,
            )
            .map_err(|detail| format!("if else branch {detail}"))?;
        }
        IrStmt::While {
            condition, body, ..
        } => {
            validate_nullable_pointer_param_uses_in_expr(
                condition,
                nullable_params,
                proven_nonnull_params,
            )?;
            let mut loop_nonnull_params = proven_nonnull_params.clone();
            validate_nullable_pointer_param_uses_in_body(
                body,
                nullable_params,
                &mut loop_nonnull_params,
            )?;
        }
        IrStmt::DoWhile {
            body, condition, ..
        } => {
            let mut loop_nonnull_params = proven_nonnull_params.clone();
            validate_nullable_pointer_param_uses_in_body(
                body,
                nullable_params,
                &mut loop_nonnull_params,
            )?;
            validate_nullable_pointer_param_uses_in_expr(
                condition,
                nullable_params,
                proven_nonnull_params,
            )?;
        }
        IrStmt::For {
            init,
            condition,
            step,
            body,
            ..
        } => {
            let mut loop_nonnull_params = proven_nonnull_params.clone();
            validate_nullable_pointer_param_uses_in_body(
                init,
                nullable_params,
                &mut loop_nonnull_params,
            )
            .map_err(|detail| format!("for init {detail}"))?;
            if let Some(condition) = condition {
                validate_nullable_pointer_param_uses_in_expr(
                    condition,
                    nullable_params,
                    &loop_nonnull_params,
                )?;
            }
            if let Some(step) = step {
                validate_nullable_pointer_param_uses_in_stmt(
                    step,
                    nullable_params,
                    &loop_nonnull_params,
                )?;
            }
            validate_nullable_pointer_param_uses_in_body(
                body,
                nullable_params,
                &mut loop_nonnull_params,
            )?;
        }
        IrStmt::Return { value, .. } => {
            if let Some(value) = value {
                validate_nullable_pointer_param_uses_in_expr(
                    value,
                    nullable_params,
                    proven_nonnull_params,
                )?;
            }
        }
        IrStmt::Break { .. } | IrStmt::Continue { .. } => {}
        IrStmt::Expr { expr, .. } => {
            validate_nullable_pointer_param_uses_in_expr(
                expr,
                nullable_params,
                proven_nonnull_params,
            )?;
        }
        IrStmt::RecordMemset { destination, .. } => {
            validate_nullable_pointer_param_uses_in_expr(
                destination,
                nullable_params,
                proven_nonnull_params,
            )?;
        }
        IrStmt::Unsupported { .. } => {}
    }
    Ok(())
}

fn validate_nullable_pointer_param_uses_in_condition(
    condition: &IrExpr,
    nullable_params: &HashSet<String>,
    proven_nonnull_params: &HashSet<String>,
) -> Result<(), String> {
    if nullable_pointer_truthiness_var(condition, nullable_params).is_some() {
        return Ok(());
    }
    validate_nullable_pointer_param_uses_in_expr(condition, nullable_params, proven_nonnull_params)
}
