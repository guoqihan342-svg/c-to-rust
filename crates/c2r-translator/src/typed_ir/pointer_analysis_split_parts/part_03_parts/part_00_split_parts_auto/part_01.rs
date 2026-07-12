
fn readonly_pointer_add_operands_from_expr(expr: &IrExpr) -> Option<(&IrExpr, &IrExpr)> {
    let IrExpr::Binary { lhs, rhs, .. } = expr else {
        return None;
    };
    readonly_pointer_add_operands(lhs, rhs)
}

fn collect_direct_readonly_pointer_read_param(
    expr: &IrExpr,
    readonly_pointer_params: &HashMap<&str, &IrType>,
    uses: &mut ReadonlyPointerParamUses,
) -> Result<(), String> {
    match expr {
        IrExpr::Var { name, ty, .. }
            if readonly_pointer_params
                .get(name.as_str())
                .is_some_and(|param_ty| *param_ty == ty) =>
        {
            uses.read_params.insert(name.to_string());
            uses.mentioned_params.insert(name.to_string());
        }
        IrExpr::IncDec { target, .. } => {
            collect_direct_readonly_pointer_read_param(target, readonly_pointer_params, uses)?
        }
        _ => {}
    }
    Ok(())
}

fn collect_direct_readonly_pointer_mentioned_param(
    expr: &IrExpr,
    readonly_pointer_params: &HashMap<&str, &IrType>,
    uses: &mut ReadonlyPointerParamUses,
) -> Result<(), String> {
    let IrExpr::Var { name, ty, .. } = expr else {
        return Ok(());
    };
    if readonly_pointer_params
        .get(name.as_str())
        .is_some_and(|param_ty| *param_ty == ty)
    {
        uses.mentioned_params.insert(name.to_string());
    }
    Ok(())
}

fn collect_mutable_record_pointer_write_params_from_body(
    body: &[IrStmt],
    mutable_record_pointer_params: &HashMap<&str, &IrType>,
    write_params: &mut HashSet<String>,
) -> Result<(), String> {
    for stmt in body {
        match stmt {
            IrStmt::Decl { init, .. } => {
                if let Some(init) = init {
                    collect_mutable_record_pointer_write_params_from_expr(
                        init,
                        mutable_record_pointer_params,
                        write_params,
                    )?;
                }
            }
            IrStmt::Assign { target, value, .. } => {
                collect_mutable_record_pointer_write_param_from_target(
                    target,
                    mutable_record_pointer_params,
                    write_params,
                )?;
                collect_mutable_record_pointer_write_params_from_expr(
                    value,
                    mutable_record_pointer_params,
                    write_params,
                )?;
            }
            IrStmt::If {
                condition,
                then_body,
                else_body,
                ..
            } => {
                collect_mutable_record_pointer_write_params_from_expr(
                    condition,
                    mutable_record_pointer_params,
                    write_params,
                )?;
                collect_mutable_record_pointer_write_params_from_body(
                    then_body,
                    mutable_record_pointer_params,
                    write_params,
                )?;
                collect_mutable_record_pointer_write_params_from_body(
                    else_body,
                    mutable_record_pointer_params,
                    write_params,
                )?;
            }
            IrStmt::While { condition, body, .. } => {
                collect_mutable_record_pointer_write_params_from_expr(
                    condition,
                    mutable_record_pointer_params,
                    write_params,
                )?;
                collect_mutable_record_pointer_write_params_from_body(
                    body,
                    mutable_record_pointer_params,
                    write_params,
                )?;
            }
            IrStmt::DoWhile {
                body, condition, ..
            } => {
                collect_mutable_record_pointer_write_params_from_body(
                    body,
                    mutable_record_pointer_params,
                    write_params,
                )?;
                collect_mutable_record_pointer_write_params_from_expr(
                    condition,
                    mutable_record_pointer_params,
                    write_params,
                )?;
            }
            IrStmt::For {
                init,
                condition,
                step,
                body,
                ..
            } => {
                collect_mutable_record_pointer_write_params_from_body(
                    init,
                    mutable_record_pointer_params,
                    write_params,
                )?;
                if let Some(condition) = condition {
                    collect_mutable_record_pointer_write_params_from_expr(
                        condition,
                        mutable_record_pointer_params,
                        write_params,
                    )?;
                }
                if let Some(step) = step {
                    collect_mutable_record_pointer_write_params_from_body(
                        std::slice::from_ref(step.as_ref()),
                        mutable_record_pointer_params,
                        write_params,
                    )?;
                }
                collect_mutable_record_pointer_write_params_from_body(
                    body,
                    mutable_record_pointer_params,
                    write_params,
                )?;
            }
            IrStmt::Return { value, .. } => {
                if let Some(value) = value {
                    collect_mutable_record_pointer_write_params_from_expr(
                        value,
                        mutable_record_pointer_params,
                        write_params,
                    )?;
                }
            }
            IrStmt::Expr { expr, .. } => {
                collect_mutable_record_pointer_write_params_from_expr(
                    expr,
                    mutable_record_pointer_params,
                    write_params,
                )?;
            }
            IrStmt::RecordMemset { destination, .. } => {
                let IrExpr::Var { name, ty, .. } = destination else {
                    return Err("record memset destination must be a direct parameter".to_string());
                };
                if mutable_record_pointer_params.get(name.as_str()).is_some_and(|param_ty| {
                    record_pointer_types_match_ignoring_spelling(param_ty, ty)
                }) {
                    write_params.insert(name.clone());
                }
            }
            IrStmt::Break { .. } | IrStmt::Continue { .. } | IrStmt::Unsupported { .. } => {}
        }
    }
    Ok(())
}
