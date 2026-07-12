
fn collect_mutable_record_pointer_write_params_from_expr(
    expr: &IrExpr,
    mutable_record_pointer_params: &HashMap<&str, &IrType>,
    write_params: &mut HashSet<String>,
) -> Result<(), String> {
    match expr {
        IrExpr::IncDec { target, .. } => {
            collect_mutable_record_pointer_write_param_from_target(
                target,
                mutable_record_pointer_params,
                write_params,
            )?;
            collect_mutable_record_pointer_write_params_from_expr(
                target,
                mutable_record_pointer_params,
                write_params,
            )
        }
        IrExpr::Binary { lhs, rhs, .. } => {
            collect_mutable_record_pointer_write_params_from_expr(
                lhs,
                mutable_record_pointer_params,
                write_params,
            )?;
            collect_mutable_record_pointer_write_params_from_expr(
                rhs,
                mutable_record_pointer_params,
                write_params,
            )
        }
        IrExpr::Unary { operand, .. }
        | IrExpr::Cast { expr: operand, .. }
        | IrExpr::LValueToRValue { expr: operand, .. }
        | IrExpr::ArrayToPointerDecay { expr: operand, .. }
        | IrExpr::FunctionToPointerDecay { expr: operand, .. }
        | IrExpr::Member { base: operand, .. }
        | IrExpr::Deref { ptr: operand, .. }
        | IrExpr::AddrOf { operand, .. } => {
            collect_mutable_record_pointer_write_params_from_expr(
                operand,
                mutable_record_pointer_params,
                write_params,
            )
        }
        IrExpr::Conditional {
            condition,
            then_expr,
            else_expr,
            ..
        } => {
            collect_mutable_record_pointer_write_params_from_expr(
                condition,
                mutable_record_pointer_params,
                write_params,
            )?;
            collect_mutable_record_pointer_write_params_from_expr(
                then_expr,
                mutable_record_pointer_params,
                write_params,
            )?;
            collect_mutable_record_pointer_write_params_from_expr(
                else_expr,
                mutable_record_pointer_params,
                write_params,
            )
        }
        IrExpr::Index { base, index, .. } => {
            collect_mutable_record_pointer_write_params_from_expr(
                base,
                mutable_record_pointer_params,
                write_params,
            )?;
            collect_mutable_record_pointer_write_params_from_expr(
                index,
                mutable_record_pointer_params,
                write_params,
            )
        }
        IrExpr::ArrayLiteral { elements, .. } => {
            for element in elements {
                collect_mutable_record_pointer_write_params_from_expr(
                    element,
                    mutable_record_pointer_params,
                    write_params,
                )?;
            }
            Ok(())
        }
        IrExpr::Call { args, .. } => {
            for arg in args {
                collect_mutable_record_pointer_write_params_from_expr(
                    arg,
                    mutable_record_pointer_params,
                    write_params,
                )?;
            }
            Ok(())
        }
        IrExpr::LitInt { .. }
        | IrExpr::NullPtr { .. }
        | IrExpr::Var { .. }
        | IrExpr::Unsupported { .. } => Ok(()),
    }
}

fn collect_mutable_record_pointer_write_param_from_target(
    target: &IrExpr,
    mutable_record_pointer_params: &HashMap<&str, &IrType>,
    write_params: &mut HashSet<String>,
) -> Result<(), String> {
    let Some(path) = record_pointer_member_path_from_expr(target)? else {
        return Ok(());
    };
    if !mutable_record_pointer_params
        .get(path.root_name)
        .is_some_and(|param_ty| record_pointer_types_match_ignoring_spelling(param_ty, path.root_ty))
    {
        return Ok(());
    }
    let field_path = record_pointer_member_path_key(&path);
    emit_mutable_record_pointer_field_type(path.ty).map_err(|detail| {
        format!("mutable record pointer arrow field {field_path} has {detail}")
    })?;
    write_params.insert(path.root_name.to_string());
    Ok(())
}

fn collect_readonly_record_pointer_read_params(
    body: &[IrStmt],
    params: &[IrParam],
    mutable_record_pointer_write_params: &HashSet<String>,
    policy: &EmitPolicy,
) -> Result<HashSet<String>, String> {
    let params_by_name = params
        .iter()
        .map(|param| (param.name.as_str(), param))
        .collect::<HashMap<_, _>>();
    let mutable_record_pointer_params = params
        .iter()
        .filter(|param| {
            mutable_record_pointer_pointee_type(&param.ty).is_some()
                && !mutable_record_pointer_write_params.contains(&param.name)
                && mutable_record_pointer_write_params
                    .iter()
                    .any(|mutable_param| {
                        explicit_noalias_pair(policy, &param.name, mutable_param)
                            || params_have_restrict_noalias(
                                &params_by_name,
                                &param.name,
                                mutable_param,
                            )
                    })
        })
        .map(|param| (param.name.as_str(), &param.ty))
        .collect::<HashMap<_, _>>();
    let mut read_params = HashSet::new();
    collect_readonly_record_pointer_read_params_from_body(
        body,
        &mutable_record_pointer_params,
        &mut read_params,
    )?;
    Ok(read_params)
}

fn collect_readonly_record_pointer_read_params_from_body(
    body: &[IrStmt],
    mutable_record_pointer_params: &HashMap<&str, &IrType>,
    read_params: &mut HashSet<String>,
) -> Result<(), String> {
    for stmt in body {
        match stmt {
            IrStmt::Decl { init, .. } => {
                if let Some(init) = init {
                    collect_readonly_record_pointer_read_params_from_expr(
                        init,
                        mutable_record_pointer_params,
                        read_params,
                    )?;
                }
            }
            IrStmt::Assign { target, value, .. } => {
                collect_readonly_record_pointer_read_params_from_expr(
                    target,
                    mutable_record_pointer_params,
                    read_params,
                )?;
                collect_readonly_record_pointer_read_params_from_expr(
                    value,
                    mutable_record_pointer_params,
                    read_params,
                )?;
            }
            IrStmt::If {
                condition,
                then_body,
                else_body,
                ..
            } => {
                collect_readonly_record_pointer_read_params_from_expr(
                    condition,
                    mutable_record_pointer_params,
                    read_params,
                )?;
                collect_readonly_record_pointer_read_params_from_body(
                    then_body,
                    mutable_record_pointer_params,
                    read_params,
                )?;
                collect_readonly_record_pointer_read_params_from_body(
                    else_body,
                    mutable_record_pointer_params,
                    read_params,
                )?;
            }
            IrStmt::While {
                condition, body, ..
            } => {
                collect_readonly_record_pointer_read_params_from_expr(
                    condition,
                    mutable_record_pointer_params,
                    read_params,
                )?;
                collect_readonly_record_pointer_read_params_from_body(
                    body,
                    mutable_record_pointer_params,
                    read_params,
                )?;
            }
            IrStmt::DoWhile { body, condition, .. } => {
                collect_readonly_record_pointer_read_params_from_body(
                    body,
                    mutable_record_pointer_params,
                    read_params,
                )?;
                collect_readonly_record_pointer_read_params_from_expr(
                    condition,
                    mutable_record_pointer_params,
                    read_params,
                )?;
            }
            IrStmt::For {
                init,
                condition,
                step,
                body,
                ..
            } => {
                collect_readonly_record_pointer_read_params_from_body(
                    init,
                    mutable_record_pointer_params,
                    read_params,
                )?;
                if let Some(condition) = condition {
                    collect_readonly_record_pointer_read_params_from_expr(
                        condition,
                        mutable_record_pointer_params,
                        read_params,
                    )?;
                }
                if let Some(step) = step {
                    collect_readonly_record_pointer_read_params_from_body(
                        std::slice::from_ref(step.as_ref()),
                        mutable_record_pointer_params,
                        read_params,
                    )?;
                }
                collect_readonly_record_pointer_read_params_from_body(
                    body,
                    mutable_record_pointer_params,
                    read_params,
                )?;
            }
            IrStmt::Return { value, .. } => {
                if let Some(value) = value {
                    collect_readonly_record_pointer_read_params_from_expr(
                        value,
                        mutable_record_pointer_params,
                        read_params,
                    )?;
                }
            }
            IrStmt::Expr { expr, .. } => collect_readonly_record_pointer_read_params_from_expr(
                expr,
                mutable_record_pointer_params,
                read_params,
            )?,
            IrStmt::RecordMemset { .. } => {}
            IrStmt::Break { .. } | IrStmt::Continue { .. } | IrStmt::Unsupported { .. } => {}
        }
    }
    Ok(())
}

fn collect_readonly_record_pointer_read_params_from_expr(
    expr: &IrExpr,
    mutable_record_pointer_params: &HashMap<&str, &IrType>,
    read_params: &mut HashSet<String>,
) -> Result<(), String> {
    if let Some(path) = record_pointer_member_path_from_expr(expr)? {
        if mutable_record_pointer_params
            .get(path.root_name)
            .is_some_and(|param_ty| record_pointer_types_match_ignoring_spelling(param_ty, path.root_ty))
        {
            read_params.insert(path.root_name.to_string());
        }
    }
    match expr {
        IrExpr::Binary { lhs, rhs, .. } => {
            collect_readonly_record_pointer_read_params_from_expr(
                lhs,
                mutable_record_pointer_params,
                read_params,
            )?;
            collect_readonly_record_pointer_read_params_from_expr(
                rhs,
                mutable_record_pointer_params,
                read_params,
            )
        }
        IrExpr::Unary { operand, .. }
        | IrExpr::Cast { expr: operand, .. }
        | IrExpr::LValueToRValue { expr: operand, .. }
        | IrExpr::ArrayToPointerDecay { expr: operand, .. }
        | IrExpr::FunctionToPointerDecay { expr: operand, .. }
        | IrExpr::IncDec {
            target: operand, ..
        }
        | IrExpr::Deref { ptr: operand, .. }
        | IrExpr::AddrOf { operand, .. }
        | IrExpr::Member { base: operand, .. } => collect_readonly_record_pointer_read_params_from_expr(
            operand,
            mutable_record_pointer_params,
            read_params,
        ),
        IrExpr::Conditional {
            condition,
            then_expr,
            else_expr,
            ..
        } => {
            collect_readonly_record_pointer_read_params_from_expr(
                condition,
                mutable_record_pointer_params,
                read_params,
            )?;
            collect_readonly_record_pointer_read_params_from_expr(
                then_expr,
                mutable_record_pointer_params,
                read_params,
            )?;
            collect_readonly_record_pointer_read_params_from_expr(
                else_expr,
                mutable_record_pointer_params,
                read_params,
            )
        }
        IrExpr::Index { base, index, .. } => {
            collect_readonly_record_pointer_read_params_from_expr(
                base,
                mutable_record_pointer_params,
                read_params,
            )?;
            collect_readonly_record_pointer_read_params_from_expr(
                index,
                mutable_record_pointer_params,
                read_params,
            )
        }
        IrExpr::ArrayLiteral { elements, .. } => {
            for element in elements {
                collect_readonly_record_pointer_read_params_from_expr(
                    element,
                    mutable_record_pointer_params,
                    read_params,
                )?;
            }
            Ok(())
        }
        IrExpr::Call { args, .. } => {
            for arg in args {
                collect_readonly_record_pointer_read_params_from_expr(
                    arg,
                    mutable_record_pointer_params,
                    read_params,
                )?;
            }
            Ok(())
        }
        IrExpr::LitInt { .. }
        | IrExpr::NullPtr { .. }
        | IrExpr::Var { .. }
        | IrExpr::Unsupported { .. } => Ok(()),
    }
}
