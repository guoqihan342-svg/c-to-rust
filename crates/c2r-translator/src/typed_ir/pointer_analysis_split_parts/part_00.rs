fn collect_nullable_pointer_params(
    body: &[IrStmt],
    params: &[IrParam],
) -> Result<HashSet<String>, String> {
    reject_nullable_mutable_pointer_params(body, params)?;
    let readonly_pointer_params = params
        .iter()
        .filter(|param| is_supported_nullable_pointer_type(&param.ty))
        .map(|param| (param.name.as_str(), &param.ty))
        .collect::<HashMap<_, _>>();
    let mut nullable_params = HashSet::new();
    collect_nullable_pointer_params_from_body(body, &readonly_pointer_params, &mut nullable_params);
    let mut proven_nonnull_params = HashSet::new();
    validate_nullable_pointer_param_uses_in_body(
        body,
        &nullable_params,
        &mut proven_nonnull_params,
    )?;
    Ok(nullable_params)
}

fn reject_nullable_mutable_pointer_params(
    body: &[IrStmt],
    params: &[IrParam],
) -> Result<(), String> {
    let mutable_pointer_params = params
        .iter()
        .filter(|param| mutable_pointer_slice_element_type(&param.ty).is_some())
        .map(|param| (param.name.as_str(), &param.ty))
        .collect::<HashMap<_, _>>();
    if mutable_pointer_params.is_empty() {
        return Ok(());
    }
    for stmt in body {
        reject_nullable_mutable_pointer_params_in_stmt(stmt, &mutable_pointer_params)?;
    }
    Ok(())
}

fn reject_nullable_mutable_pointer_params_in_stmt(
    stmt: &IrStmt,
    mutable_pointer_params: &HashMap<&str, &IrType>,
) -> Result<(), String> {
    match stmt {
        IrStmt::Decl { init, .. } => {
            if let Some(init) = init {
                reject_nullable_mutable_pointer_params_in_expr(init, mutable_pointer_params)?;
            }
        }
        IrStmt::Assign { target, value, .. } => {
            reject_nullable_mutable_pointer_params_in_expr(target, mutable_pointer_params)?;
            reject_nullable_mutable_pointer_params_in_expr(value, mutable_pointer_params)?;
        }
        IrStmt::If {
            condition,
            then_body,
            else_body,
            ..
        } => {
            reject_nullable_mutable_pointer_params_in_expr(condition, mutable_pointer_params)?;
            for stmt in then_body {
                reject_nullable_mutable_pointer_params_in_stmt(stmt, mutable_pointer_params)?;
            }
            for stmt in else_body {
                reject_nullable_mutable_pointer_params_in_stmt(stmt, mutable_pointer_params)?;
            }
        }
        IrStmt::While {
            condition, body, ..
        } => {
            reject_nullable_mutable_pointer_params_in_expr(condition, mutable_pointer_params)?;
            for stmt in body {
                reject_nullable_mutable_pointer_params_in_stmt(stmt, mutable_pointer_params)?;
            }
        }
        IrStmt::DoWhile {
            body, condition, ..
        } => {
            for stmt in body {
                reject_nullable_mutable_pointer_params_in_stmt(stmt, mutable_pointer_params)?;
            }
            reject_nullable_mutable_pointer_params_in_expr(condition, mutable_pointer_params)?;
        }
        IrStmt::For {
            init,
            condition,
            step,
            body,
            ..
        } => {
            for stmt in init {
                reject_nullable_mutable_pointer_params_in_stmt(stmt, mutable_pointer_params)?;
            }
            if let Some(condition) = condition {
                reject_nullable_mutable_pointer_params_in_expr(condition, mutable_pointer_params)?;
            }
            if let Some(step) = step {
                reject_nullable_mutable_pointer_params_in_stmt(step, mutable_pointer_params)?;
            }
            for stmt in body {
                reject_nullable_mutable_pointer_params_in_stmt(stmt, mutable_pointer_params)?;
            }
        }
        IrStmt::Return { value, .. } => {
            if let Some(value) = value {
                reject_nullable_mutable_pointer_params_in_expr(value, mutable_pointer_params)?;
            }
        }
        IrStmt::Expr { expr, .. } => {
            reject_nullable_mutable_pointer_params_in_expr(expr, mutable_pointer_params)?;
        }
        IrStmt::Break { .. } | IrStmt::Continue { .. } | IrStmt::Unsupported { .. } => {}
    }
    Ok(())
}

fn reject_nullable_mutable_pointer_params_in_expr(
    expr: &IrExpr,
    mutable_pointer_params: &HashMap<&str, &IrType>,
) -> Result<(), String> {
    if let IrExpr::Binary {
        op: IrBinOp::Eq | IrBinOp::Neq,
        lhs,
        rhs,
        ..
    } = expr
    {
        if let Some((name, pointer_ty)) = null_pointer_comparison_var(lhs, rhs) {
            if mutable_pointer_params
                .get(name)
                .is_some_and(|param_ty| *param_ty == pointer_ty)
            {
                return Err(format!(
                    "nullable mutable pointer param {name} cannot be lowered to &mut [T]"
                ));
            }
        }
    }
    match expr {
        IrExpr::Binary { lhs, rhs, .. } => {
            reject_nullable_mutable_pointer_params_in_expr(lhs, mutable_pointer_params)?;
            reject_nullable_mutable_pointer_params_in_expr(rhs, mutable_pointer_params)?;
        }
        IrExpr::Unary { operand, .. }
        | IrExpr::Cast { expr: operand, .. }
        | IrExpr::LValueToRValue { expr: operand, .. }
        | IrExpr::ArrayToPointerDecay { expr: operand, .. }
        | IrExpr::FunctionToPointerDecay { expr: operand, .. }
        | IrExpr::AddrOf { operand, .. }
        | IrExpr::Deref { ptr: operand, .. }
        | IrExpr::Member { base: operand, .. }
        | IrExpr::IncDec {
            target: operand, ..
        } => {
            reject_nullable_mutable_pointer_params_in_expr(operand, mutable_pointer_params)?;
        }
        IrExpr::Conditional {
            condition,
            then_expr,
            else_expr,
            ..
        } => {
            reject_nullable_mutable_pointer_params_in_expr(condition, mutable_pointer_params)?;
            reject_nullable_mutable_pointer_params_in_expr(then_expr, mutable_pointer_params)?;
            reject_nullable_mutable_pointer_params_in_expr(else_expr, mutable_pointer_params)?;
        }
        IrExpr::Index { base, index, .. } => {
            reject_nullable_mutable_pointer_params_in_expr(base, mutable_pointer_params)?;
            reject_nullable_mutable_pointer_params_in_expr(index, mutable_pointer_params)?;
        }
        IrExpr::ArrayLiteral { elements, .. } => {
            for element in elements {
                reject_nullable_mutable_pointer_params_in_expr(element, mutable_pointer_params)?;
            }
        }
        IrExpr::Call { args, .. } => {
            for arg in args {
                reject_nullable_mutable_pointer_params_in_expr(arg, mutable_pointer_params)?;
            }
        }
        IrExpr::LitInt { .. }
        | IrExpr::NullPtr { .. }
        | IrExpr::Var { .. }
        | IrExpr::Unsupported { .. } => {}
    }
    Ok(())
}

fn collect_nullable_pointer_params_from_body(
    body: &[IrStmt],
    readonly_pointer_params: &HashMap<&str, &IrType>,
    nullable_params: &mut HashSet<String>,
) {
    for stmt in body {
        match stmt {
            IrStmt::Decl { init, .. } => {
                if let Some(init) = init {
                    collect_nullable_pointer_params_from_expr(
                        init,
                        readonly_pointer_params,
                        nullable_params,
                    );
                }
            }
            IrStmt::Assign { target, value, .. } => {
                collect_nullable_pointer_params_from_expr(
                    target,
                    readonly_pointer_params,
                    nullable_params,
                );
                collect_nullable_pointer_params_from_expr(
                    value,
                    readonly_pointer_params,
                    nullable_params,
                );
            }
            IrStmt::If {
                condition,
                then_body,
                else_body,
                ..
            } => {
                collect_nullable_pointer_condition_param(
                    condition,
                    readonly_pointer_params,
                    nullable_params,
                );
                collect_nullable_pointer_params_from_expr(
                    condition,
                    readonly_pointer_params,
                    nullable_params,
                );
                collect_nullable_pointer_params_from_body(
                    then_body,
                    readonly_pointer_params,
                    nullable_params,
                );
                collect_nullable_pointer_params_from_body(
                    else_body,
                    readonly_pointer_params,
                    nullable_params,
                );
            }
            IrStmt::While {
                condition, body, ..
            } => {
                collect_nullable_pointer_params_from_expr(
                    condition,
                    readonly_pointer_params,
                    nullable_params,
                );
                collect_nullable_pointer_params_from_body(
                    body,
                    readonly_pointer_params,
                    nullable_params,
                );
            }
            IrStmt::DoWhile {
                body, condition, ..
            } => {
                collect_nullable_pointer_params_from_body(
                    body,
                    readonly_pointer_params,
                    nullable_params,
                );
                collect_nullable_pointer_params_from_expr(
                    condition,
                    readonly_pointer_params,
                    nullable_params,
                );
            }
            IrStmt::For {
                init,
                condition,
                step,
                body,
                ..
            } => {
                collect_nullable_pointer_params_from_body(
                    init,
                    readonly_pointer_params,
                    nullable_params,
                );
                if let Some(condition) = condition {
                    collect_nullable_pointer_params_from_expr(
                        condition,
                        readonly_pointer_params,
                        nullable_params,
                    );
                }
                if let Some(step) = step {
                    collect_nullable_pointer_params_from_body(
                        std::slice::from_ref(step.as_ref()),
                        readonly_pointer_params,
                        nullable_params,
                    );
                }
                collect_nullable_pointer_params_from_body(
                    body,
                    readonly_pointer_params,
                    nullable_params,
                );
            }
            IrStmt::Return { value, .. } => {
                if let Some(value) = value {
                    collect_nullable_pointer_params_from_expr(
                        value,
                        readonly_pointer_params,
                        nullable_params,
                    );
                }
            }
            IrStmt::Break { .. } | IrStmt::Continue { .. } => {}
            IrStmt::Expr { expr, .. } => {
                collect_nullable_pointer_params_from_expr(
                    expr,
                    readonly_pointer_params,
                    nullable_params,
                );
            }
            IrStmt::Unsupported { .. } => {}
        }
    }
}

fn collect_nullable_pointer_condition_param(
    condition: &IrExpr,
    readonly_pointer_params: &HashMap<&str, &IrType>,
    nullable_params: &mut HashSet<String>,
) {
    let Some((name, ty)) = nullable_pointer_truthiness_var_parts(condition) else {
        return;
    };
    if readonly_pointer_params
        .get(name)
        .is_some_and(|param_ty| *param_ty == ty)
    {
        nullable_params.insert(name.to_string());
    }
}

fn collect_nullable_pointer_params_from_expr(
    expr: &IrExpr,
    readonly_pointer_params: &HashMap<&str, &IrType>,
    nullable_params: &mut HashSet<String>,
) {
    if let IrExpr::Binary {
        op: IrBinOp::Eq | IrBinOp::Neq,
        lhs,
        rhs,
        ..
    } = expr
    {
        if let Some((name, pointer_ty)) = null_pointer_comparison_var(lhs, rhs) {
            if readonly_pointer_params
                .get(name)
                .is_some_and(|param_ty| *param_ty == pointer_ty)
            {
                nullable_params.insert(name.to_string());
            }
        }
    }
    match expr {
        IrExpr::Binary { lhs, rhs, .. } => {
            collect_nullable_pointer_params_from_expr(
                lhs,
                readonly_pointer_params,
                nullable_params,
            );
            collect_nullable_pointer_params_from_expr(
                rhs,
                readonly_pointer_params,
                nullable_params,
            );
        }
        IrExpr::Unary { operand, .. }
        | IrExpr::Cast { expr: operand, .. }
        | IrExpr::LValueToRValue { expr: operand, .. }
        | IrExpr::ArrayToPointerDecay { expr: operand, .. }
        | IrExpr::FunctionToPointerDecay { expr: operand, .. }
        | IrExpr::AddrOf { operand, .. } => collect_nullable_pointer_params_from_expr(
            operand,
            readonly_pointer_params,
            nullable_params,
        ),
        IrExpr::Conditional {
            condition,
            then_expr,
            else_expr,
            ..
        } => {
            collect_nullable_pointer_params_from_expr(
                condition,
                readonly_pointer_params,
                nullable_params,
            );
            collect_nullable_pointer_params_from_expr(
                then_expr,
                readonly_pointer_params,
                nullable_params,
            );
            collect_nullable_pointer_params_from_expr(
                else_expr,
                readonly_pointer_params,
                nullable_params,
            );
        }
        IrExpr::Index { base, index, .. } => {
            collect_nullable_pointer_params_from_expr(
                base,
                readonly_pointer_params,
                nullable_params,
            );
            collect_nullable_pointer_params_from_expr(
                index,
                readonly_pointer_params,
                nullable_params,
            );
        }
        IrExpr::Member { base, .. } => collect_nullable_pointer_params_from_expr(
            base,
            readonly_pointer_params,
            nullable_params,
        ),
        IrExpr::ArrayLiteral { elements, .. } => {
            for element in elements {
                collect_nullable_pointer_params_from_expr(
                    element,
                    readonly_pointer_params,
                    nullable_params,
                );
            }
        }
        IrExpr::Call { args, .. } => {
            for arg in args {
                collect_nullable_pointer_params_from_expr(
                    arg,
                    readonly_pointer_params,
                    nullable_params,
                );
            }
        }
        IrExpr::IncDec { target, .. } => collect_nullable_pointer_params_from_expr(
            target,
            readonly_pointer_params,
            nullable_params,
        ),
        IrExpr::Deref { ptr, .. } => {
            collect_nullable_pointer_params_from_expr(ptr, readonly_pointer_params, nullable_params)
        }
        IrExpr::LitInt { .. }
        | IrExpr::NullPtr { .. }
        | IrExpr::Var { .. }
        | IrExpr::Unsupported { .. } => {}
    }
}

fn collect_opaque_pointer_call_arg_params(body: &[IrStmt], params: &[IrParam]) -> HashSet<String> {
    let param_types: HashMap<&str, &IrType> = params
        .iter()
        .map(|param| (param.name.as_str(), &param.ty))
        .collect();
    let mut call_arg_params = HashSet::new();
    collect_opaque_pointer_call_arg_params_from_body(body, &param_types, &mut call_arg_params);
    call_arg_params
}

fn collect_opaque_pointer_call_arg_params_from_body(
    body: &[IrStmt],
    param_types: &HashMap<&str, &IrType>,
    call_arg_params: &mut HashSet<String>,
) {
    for stmt in body {
        collect_opaque_pointer_call_arg_params_from_stmt(stmt, param_types, call_arg_params);
    }
}
