fn collect_readonly_pointer_read_params_from_expr(
    expr: &IrExpr,
    readonly_pointer_params: &HashMap<&str, &IrType>,
    uses: &mut ReadonlyPointerParamUses,
) -> Result<(), String> {
    collect_direct_readonly_pointer_mentioned_param(expr, readonly_pointer_params, uses)?;
    match expr {
        IrExpr::Index { base, index, .. } => {
            collect_direct_readonly_pointer_read_param(base, readonly_pointer_params, uses)?;
            collect_readonly_pointer_read_params_from_expr(base, readonly_pointer_params, uses)?;
            collect_readonly_pointer_read_params_from_expr(index, readonly_pointer_params, uses)?;
        }
        IrExpr::Deref { ptr, .. } => {
            collect_direct_readonly_pointer_read_param(ptr, readonly_pointer_params, uses)?;
            if let Some((base, _)) = readonly_pointer_add_operands_from_expr(ptr.as_ref()) {
                collect_direct_readonly_pointer_read_param(base, readonly_pointer_params, uses)?;
            }
            collect_readonly_pointer_read_params_from_expr(ptr, readonly_pointer_params, uses)?;
        }
        IrExpr::Binary { lhs, rhs, .. } => {
            collect_readonly_pointer_read_params_from_expr(lhs, readonly_pointer_params, uses)?;
            collect_readonly_pointer_read_params_from_expr(rhs, readonly_pointer_params, uses)?;
        }
        IrExpr::Unary { operand, .. }
        | IrExpr::Cast { expr: operand, .. }
        | IrExpr::LValueToRValue { expr: operand, .. }
        | IrExpr::ArrayToPointerDecay { expr: operand, .. }
        | IrExpr::FunctionToPointerDecay { expr: operand, .. }
        | IrExpr::AddrOf { operand, .. }
        | IrExpr::Member { base: operand, .. }
        | IrExpr::IncDec {
            target: operand, ..
        } => {
            collect_readonly_pointer_read_params_from_expr(operand, readonly_pointer_params, uses)?;
        }
        IrExpr::Conditional {
            condition,
            then_expr,
            else_expr,
            ..
        } => {
            collect_readonly_pointer_read_params_from_expr(
                condition,
                readonly_pointer_params,
                uses,
            )?;
            collect_readonly_pointer_read_params_from_expr(
                then_expr,
                readonly_pointer_params,
                uses,
            )?;
            collect_readonly_pointer_read_params_from_expr(
                else_expr,
                readonly_pointer_params,
                uses,
            )?;
        }
        IrExpr::ArrayLiteral { elements, .. } => {
            for element in elements {
                collect_readonly_pointer_read_params_from_expr(
                    element,
                    readonly_pointer_params,
                    uses,
                )?;
            }
        }
        IrExpr::Call { callee, args, .. } => {
            if callee == "strlen" && args.len() == 1 {
                collect_direct_readonly_pointer_read_param(
                    &args[0],
                    readonly_pointer_params,
                    uses,
                )?;
            }
            if callee == "strnlen" && args.len() == 2 {
                collect_direct_readonly_pointer_read_param(
                    &args[0],
                    readonly_pointer_params,
                    uses,
                )?;
            }
            if callee == "memcmp" && args.len() == 3 {
                collect_direct_readonly_pointer_read_param(
                    &args[0],
                    readonly_pointer_params,
                    uses,
                )?;
                collect_direct_readonly_pointer_read_param(
                    &args[1],
                    readonly_pointer_params,
                    uses,
                )?;
            }
            if callee == "memcpy" && args.len() == 3 {
                collect_direct_readonly_pointer_read_param(
                    &args[1],
                    readonly_pointer_params,
                    uses,
                )?;
            }
            for arg in args {
                collect_readonly_pointer_read_params_from_expr(arg, readonly_pointer_params, uses)?;
            }
        }
        IrExpr::LitInt { .. }
        | IrExpr::NullPtr { .. }
        | IrExpr::Var { .. }
        | IrExpr::Unsupported { .. } => {}
    }
    Ok(())
}

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
        IrExpr::Var { name, ty, .. } => {
            if readonly_pointer_params
                .get(name.as_str())
                .is_some_and(|param_ty| *param_ty == ty)
            {
                uses.read_params.insert(name.to_string());
                uses.mentioned_params.insert(name.to_string());
            }
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
            IrStmt::Assign { target, .. } => {
                collect_mutable_record_pointer_write_param_from_target(
                    target,
                    mutable_record_pointer_params,
                    write_params,
                )?
            }
            IrStmt::If {
                then_body,
                else_body,
                ..
            } => {
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
            IrStmt::While { body, .. } | IrStmt::DoWhile { body, .. } => {
                collect_mutable_record_pointer_write_params_from_body(
                    body,
                    mutable_record_pointer_params,
                    write_params,
                )?;
            }
            IrStmt::For {
                init, step, body, ..
            } => {
                collect_mutable_record_pointer_write_params_from_body(
                    init,
                    mutable_record_pointer_params,
                    write_params,
                )?;
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
            IrStmt::Decl { .. }
            | IrStmt::Return { .. }
            | IrStmt::Break { .. }
            | IrStmt::Continue { .. }
            | IrStmt::Expr { .. }
            | IrStmt::Unsupported { .. } => {}
        }
    }
    Ok(())
}

fn collect_mutable_record_pointer_write_param_from_target(
    target: &IrExpr,
    mutable_record_pointer_params: &HashMap<&str, &IrType>,
    write_params: &mut HashSet<String>,
) -> Result<(), String> {
    let IrExpr::Member {
        base,
        field,
        ty,
        is_arrow: true,
        ..
    } = target
    else {
        return Ok(());
    };
    let IrExpr::Var {
        name, ty: base_ty, ..
    } = base.as_ref()
    else {
        return Ok(());
    };
    if !mutable_record_pointer_params
        .get(name.as_str())
        .is_some_and(|param_ty| *param_ty == base_ty)
    {
        return Ok(());
    }
    emit_mutable_record_pointer_field_type(ty)
        .map_err(|detail| format!("mutable record pointer arrow field {field} has {detail}"))?;
    write_params.insert(name.clone());
    Ok(())
}
