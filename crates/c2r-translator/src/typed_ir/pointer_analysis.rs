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
    let IrExpr::Var { name, ty, .. } = condition else {
        return;
    };
    if readonly_pointer_params
        .get(name.as_str())
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

fn collect_opaque_pointer_call_arg_params_from_stmt(
    stmt: &IrStmt,
    param_types: &HashMap<&str, &IrType>,
    call_arg_params: &mut HashSet<String>,
) {
    match stmt {
        IrStmt::Decl { init, .. } => {
            if let Some(init) = init {
                collect_opaque_pointer_call_arg_params_from_expr(
                    init,
                    param_types,
                    call_arg_params,
                );
            }
        }
        IrStmt::Assign { target, value, .. } => {
            collect_opaque_pointer_call_arg_params_from_expr(target, param_types, call_arg_params);
            collect_opaque_pointer_call_arg_params_from_expr(value, param_types, call_arg_params);
        }
        IrStmt::If {
            condition,
            then_body,
            else_body,
            ..
        } => {
            collect_opaque_pointer_call_arg_params_from_expr(
                condition,
                param_types,
                call_arg_params,
            );
            collect_opaque_pointer_call_arg_params_from_body(
                then_body,
                param_types,
                call_arg_params,
            );
            collect_opaque_pointer_call_arg_params_from_body(
                else_body,
                param_types,
                call_arg_params,
            );
        }
        IrStmt::While {
            condition, body, ..
        } => {
            collect_opaque_pointer_call_arg_params_from_expr(
                condition,
                param_types,
                call_arg_params,
            );
            collect_opaque_pointer_call_arg_params_from_body(body, param_types, call_arg_params);
        }
        IrStmt::DoWhile {
            body, condition, ..
        } => {
            collect_opaque_pointer_call_arg_params_from_body(body, param_types, call_arg_params);
            collect_opaque_pointer_call_arg_params_from_expr(
                condition,
                param_types,
                call_arg_params,
            );
        }
        IrStmt::For {
            init,
            condition,
            step,
            body,
            ..
        } => {
            collect_opaque_pointer_call_arg_params_from_body(init, param_types, call_arg_params);
            if let Some(condition) = condition {
                collect_opaque_pointer_call_arg_params_from_expr(
                    condition,
                    param_types,
                    call_arg_params,
                );
            }
            if let Some(step) = step.as_deref() {
                collect_opaque_pointer_call_arg_params_from_stmt(
                    step,
                    param_types,
                    call_arg_params,
                );
            }
            collect_opaque_pointer_call_arg_params_from_body(body, param_types, call_arg_params);
        }
        IrStmt::Return { value, .. } => {
            if let Some(value) = value {
                collect_opaque_pointer_call_arg_params_from_expr(
                    value,
                    param_types,
                    call_arg_params,
                );
            }
        }
        IrStmt::Expr { expr, .. } => {
            collect_opaque_pointer_call_arg_params_from_expr(expr, param_types, call_arg_params);
        }
        IrStmt::Break { .. } | IrStmt::Continue { .. } | IrStmt::Unsupported { .. } => {}
    }
}

fn collect_opaque_pointer_call_arg_params_from_expr(
    expr: &IrExpr,
    param_types: &HashMap<&str, &IrType>,
    call_arg_params: &mut HashSet<String>,
) {
    match expr {
        IrExpr::Call { args, .. } => {
            for arg in args {
                if let IrExpr::Var { name, ty, .. } = arg {
                    if let Some(param_ty) = param_types.get(name.as_str()) {
                        if *param_ty == ty && emit_opaque_void_pointer_type(ty).is_some() {
                            call_arg_params.insert(name.clone());
                        }
                    }
                }
                collect_opaque_pointer_call_arg_params_from_expr(arg, param_types, call_arg_params);
            }
        }
        IrExpr::Binary { lhs, rhs, .. } => {
            collect_opaque_pointer_call_arg_params_from_expr(lhs, param_types, call_arg_params);
            collect_opaque_pointer_call_arg_params_from_expr(rhs, param_types, call_arg_params);
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
        | IrExpr::Member { base: operand, .. } => {
            collect_opaque_pointer_call_arg_params_from_expr(operand, param_types, call_arg_params);
        }
        IrExpr::Conditional {
            condition,
            then_expr,
            else_expr,
            ..
        } => {
            collect_opaque_pointer_call_arg_params_from_expr(
                condition,
                param_types,
                call_arg_params,
            );
            collect_opaque_pointer_call_arg_params_from_expr(
                then_expr,
                param_types,
                call_arg_params,
            );
            collect_opaque_pointer_call_arg_params_from_expr(
                else_expr,
                param_types,
                call_arg_params,
            );
        }
        IrExpr::Index { base, index, .. } => {
            collect_opaque_pointer_call_arg_params_from_expr(base, param_types, call_arg_params);
            collect_opaque_pointer_call_arg_params_from_expr(index, param_types, call_arg_params);
        }
        IrExpr::ArrayLiteral { elements, .. } => {
            for element in elements {
                collect_opaque_pointer_call_arg_params_from_expr(
                    element,
                    param_types,
                    call_arg_params,
                );
            }
        }
        IrExpr::LitInt { .. }
        | IrExpr::NullPtr { .. }
        | IrExpr::Var { .. }
        | IrExpr::Unsupported { .. } => {}
    }
}

fn collect_raw_direct_call_pointer_params(body: &[IrStmt], params: &[IrParam]) -> HashSet<String> {
    let param_types: HashMap<&str, &IrType> = params
        .iter()
        .map(|param| (param.name.as_str(), &param.ty))
        .collect();
    let mut call_arg_params = HashSet::new();
    collect_raw_direct_call_pointer_params_from_body(body, &param_types, &mut call_arg_params);
    call_arg_params
}

fn collect_raw_direct_call_pointer_params_from_body(
    body: &[IrStmt],
    param_types: &HashMap<&str, &IrType>,
    call_arg_params: &mut HashSet<String>,
) {
    for stmt in body {
        match stmt {
            IrStmt::Decl { init, .. } => {
                if let Some(init) = init {
                    collect_raw_direct_call_pointer_params_from_expr(
                        init,
                        param_types,
                        call_arg_params,
                    );
                }
            }
            IrStmt::Assign { target, value, .. } => {
                collect_raw_direct_call_pointer_params_from_expr(
                    target,
                    param_types,
                    call_arg_params,
                );
                collect_raw_direct_call_pointer_params_from_expr(
                    value,
                    param_types,
                    call_arg_params,
                );
            }
            IrStmt::If {
                condition,
                then_body,
                else_body,
                ..
            } => {
                collect_raw_direct_call_pointer_params_from_expr(
                    condition,
                    param_types,
                    call_arg_params,
                );
                collect_raw_direct_call_pointer_params_from_body(
                    then_body,
                    param_types,
                    call_arg_params,
                );
                collect_raw_direct_call_pointer_params_from_body(
                    else_body,
                    param_types,
                    call_arg_params,
                );
            }
            IrStmt::While {
                condition, body, ..
            } => {
                collect_raw_direct_call_pointer_params_from_expr(
                    condition,
                    param_types,
                    call_arg_params,
                );
                collect_raw_direct_call_pointer_params_from_body(
                    body,
                    param_types,
                    call_arg_params,
                );
            }
            IrStmt::DoWhile {
                body, condition, ..
            } => {
                collect_raw_direct_call_pointer_params_from_body(
                    body,
                    param_types,
                    call_arg_params,
                );
                collect_raw_direct_call_pointer_params_from_expr(
                    condition,
                    param_types,
                    call_arg_params,
                );
            }
            IrStmt::For {
                init,
                condition,
                step,
                body,
                ..
            } => {
                collect_raw_direct_call_pointer_params_from_body(
                    init,
                    param_types,
                    call_arg_params,
                );
                if let Some(condition) = condition {
                    collect_raw_direct_call_pointer_params_from_expr(
                        condition,
                        param_types,
                        call_arg_params,
                    );
                }
                if let Some(step) = step.as_deref() {
                    collect_raw_direct_call_pointer_params_from_stmt(
                        step,
                        param_types,
                        call_arg_params,
                    );
                }
                collect_raw_direct_call_pointer_params_from_body(
                    body,
                    param_types,
                    call_arg_params,
                );
            }
            IrStmt::Return { value, .. } => {
                if let Some(value) = value {
                    collect_raw_direct_call_pointer_params_from_expr(
                        value,
                        param_types,
                        call_arg_params,
                    );
                }
            }
            IrStmt::Expr { expr, .. } => {
                collect_raw_direct_call_pointer_params_from_expr(
                    expr,
                    param_types,
                    call_arg_params,
                );
            }
            IrStmt::Break { .. } | IrStmt::Continue { .. } | IrStmt::Unsupported { .. } => {}
        }
    }
}

fn collect_raw_direct_call_pointer_params_from_stmt(
    stmt: &IrStmt,
    param_types: &HashMap<&str, &IrType>,
    call_arg_params: &mut HashSet<String>,
) {
    collect_raw_direct_call_pointer_params_from_body(
        std::slice::from_ref(stmt),
        param_types,
        call_arg_params,
    );
}

fn collect_raw_direct_call_pointer_params_from_expr(
    expr: &IrExpr,
    param_types: &HashMap<&str, &IrType>,
    call_arg_params: &mut HashSet<String>,
) {
    match expr {
        IrExpr::Call { args, .. } => {
            for arg in args {
                if let IrExpr::Var { name, ty, .. } = arg {
                    if param_types
                        .get(name.as_str())
                        .is_some_and(|param_ty| *param_ty == ty)
                        && emit_raw_direct_call_pointer_param_type(ty).is_some()
                    {
                        call_arg_params.insert(name.clone());
                    }
                }
                collect_raw_direct_call_pointer_params_from_expr(arg, param_types, call_arg_params);
            }
        }
        IrExpr::Binary { lhs, rhs, .. } => {
            collect_raw_direct_call_pointer_params_from_expr(lhs, param_types, call_arg_params);
            collect_raw_direct_call_pointer_params_from_expr(rhs, param_types, call_arg_params);
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
        | IrExpr::Member { base: operand, .. } => {
            collect_raw_direct_call_pointer_params_from_expr(operand, param_types, call_arg_params);
        }
        IrExpr::Conditional {
            condition,
            then_expr,
            else_expr,
            ..
        } => {
            collect_raw_direct_call_pointer_params_from_expr(
                condition,
                param_types,
                call_arg_params,
            );
            collect_raw_direct_call_pointer_params_from_expr(
                then_expr,
                param_types,
                call_arg_params,
            );
            collect_raw_direct_call_pointer_params_from_expr(
                else_expr,
                param_types,
                call_arg_params,
            );
        }
        IrExpr::Index { base, index, .. } => {
            collect_raw_direct_call_pointer_params_from_expr(base, param_types, call_arg_params);
            collect_raw_direct_call_pointer_params_from_expr(index, param_types, call_arg_params);
        }
        IrExpr::ArrayLiteral { elements, .. } => {
            for element in elements {
                collect_raw_direct_call_pointer_params_from_expr(
                    element,
                    param_types,
                    call_arg_params,
                );
            }
        }
        IrExpr::LitInt { .. }
        | IrExpr::NullPtr { .. }
        | IrExpr::Var { .. }
        | IrExpr::Unsupported { .. } => {}
    }
}

fn collect_mutable_record_pointer_write_params(
    body: &[IrStmt],
    params: &[IrParam],
) -> Result<HashSet<String>, String> {
    let pointer_param_count = params
        .iter()
        .filter(|param| {
            matches!(param.ty.kind, IrTypeKind::Pointer { .. })
                && emit_opaque_void_pointer_type(&param.ty).is_none()
        })
        .count();
    let mutable_record_pointer_params = params
        .iter()
        .filter(|param| mutable_record_pointer_pointee_type(&param.ty).is_some())
        .map(|param| (param.name.as_str(), &param.ty))
        .collect::<HashMap<_, _>>();
    let mut write_params = HashSet::new();
    collect_mutable_record_pointer_write_params_from_body(
        body,
        &mutable_record_pointer_params,
        &mut write_params,
    )?;
    if !write_params.is_empty() && pointer_param_count != 1 {
        return Err(
            "mutable record pointer field assignment requires exactly one pointer param for alias proof"
                .to_string(),
        );
    }
    Ok(write_params)
}

fn collect_opaque_record_pointer_field_value_params(
    body: &[IrStmt],
    params: &[IrParam],
    mutable_record_pointer_write_params: &HashSet<String>,
) -> Result<HashSet<String>, String> {
    let param_types: HashMap<&str, &IrType> = params
        .iter()
        .map(|param| (param.name.as_str(), &param.ty))
        .collect();
    let mut value_params = HashSet::new();
    collect_opaque_record_pointer_field_value_params_from_body(
        body,
        &param_types,
        mutable_record_pointer_write_params,
        &mut value_params,
    )?;
    Ok(value_params)
}

fn collect_opaque_record_pointer_field_value_params_from_body(
    body: &[IrStmt],
    param_types: &HashMap<&str, &IrType>,
    mutable_record_pointer_write_params: &HashSet<String>,
    value_params: &mut HashSet<String>,
) -> Result<(), String> {
    for stmt in body {
        match stmt {
            IrStmt::Assign { target, value, .. } => {
                collect_opaque_record_pointer_field_value_param_from_assignment(
                    target,
                    value,
                    param_types,
                    mutable_record_pointer_write_params,
                    value_params,
                )?;
            }
            IrStmt::If {
                then_body,
                else_body,
                ..
            } => {
                collect_opaque_record_pointer_field_value_params_from_body(
                    then_body,
                    param_types,
                    mutable_record_pointer_write_params,
                    value_params,
                )?;
                collect_opaque_record_pointer_field_value_params_from_body(
                    else_body,
                    param_types,
                    mutable_record_pointer_write_params,
                    value_params,
                )?;
            }
            IrStmt::While { body, .. } | IrStmt::DoWhile { body, .. } => {
                collect_opaque_record_pointer_field_value_params_from_body(
                    body,
                    param_types,
                    mutable_record_pointer_write_params,
                    value_params,
                )?;
            }
            IrStmt::For {
                init, step, body, ..
            } => {
                collect_opaque_record_pointer_field_value_params_from_body(
                    init,
                    param_types,
                    mutable_record_pointer_write_params,
                    value_params,
                )?;
                if let Some(step) = step {
                    collect_opaque_record_pointer_field_value_params_from_body(
                        std::slice::from_ref(step.as_ref()),
                        param_types,
                        mutable_record_pointer_write_params,
                        value_params,
                    )?;
                }
                collect_opaque_record_pointer_field_value_params_from_body(
                    body,
                    param_types,
                    mutable_record_pointer_write_params,
                    value_params,
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

fn collect_opaque_record_pointer_field_value_param_from_assignment(
    target: &IrExpr,
    value: &IrExpr,
    param_types: &HashMap<&str, &IrType>,
    mutable_record_pointer_write_params: &HashSet<String>,
    value_params: &mut HashSet<String>,
) -> Result<(), String> {
    let IrExpr::Member {
        base,
        ty,
        is_arrow: true,
        ..
    } = target
    else {
        return Ok(());
    };
    let IrExpr::Var {
        name: base_name, ..
    } = base.as_ref()
    else {
        return Ok(());
    };
    if !mutable_record_pointer_write_params.contains(base_name) {
        return Ok(());
    }
    if emit_opaque_void_pointer_type(ty).is_none() {
        return Ok(());
    }
    collect_opaque_record_pointer_value_param_from_expr(value, param_types, value_params)
}

fn collect_opaque_record_pointer_value_param_from_expr(
    value: &IrExpr,
    param_types: &HashMap<&str, &IrType>,
    value_params: &mut HashSet<String>,
) -> Result<(), String> {
    match value {
        IrExpr::Var { name, ty, .. } => {
            if param_types.get(name.as_str()).is_some_and(|param_ty| {
                *param_ty == ty && emit_opaque_void_pointer_type(ty).is_some()
            }) {
                value_params.insert(name.clone());
            }
            Ok(())
        }
        IrExpr::Cast { expr, .. } => {
            collect_opaque_record_pointer_value_param_from_expr(expr, param_types, value_params)
        }
        _ => Ok(()),
    }
}

fn validate_mutable_pointer_write_alias_boundary(
    body: &[IrStmt],
    params: &[IrParam],
    policy: &EmitPolicy,
) -> Result<(), String> {
    let mutable_pointer_params = params
        .iter()
        .filter(|param| mutable_pointer_slice_element_type(&param.ty).is_some())
        .map(|param| (param.name.as_str(), &param.ty))
        .collect::<HashMap<_, _>>();
    let readonly_pointer_params = params
        .iter()
        .filter(|param| readonly_pointer_slice_element_type(&param.ty).is_some())
        .map(|param| (param.name.as_str(), &param.ty))
        .collect::<HashMap<_, _>>();
    let mut write_params = HashSet::new();
    collect_mutable_pointer_write_params_from_body(
        body,
        &mutable_pointer_params,
        &mut write_params,
    )?;
    if write_params.len() > 1 {
        return Err(
            "mutable pointer write requires exactly one pointer param for alias proof".to_string(),
        );
    }
    // Safe Rust cannot express a potentially aliased `&[T]` read beside an
    // `&mut [T]` write without an explicit noalias fact.
    if !write_params.is_empty() {
        let mut readonly_pointer_uses = ReadonlyPointerParamUses::default();
        collect_readonly_pointer_read_params_from_body(
            body,
            &readonly_pointer_params,
            &mut readonly_pointer_uses,
        )?;
        if !readonly_pointer_uses.read_params.is_empty()
            && !readonly_mutable_pointer_noalias_proven(
                &readonly_pointer_uses.read_params,
                &write_params,
                params,
                policy,
            )
        {
            return Err(
                "mutable pointer write with readonly pointer read requires noalias proof"
                    .to_string(),
            );
        }
    }
    Ok(())
}

fn readonly_mutable_pointer_noalias_proven(
    readonly_params: &HashSet<String>,
    mutable_params: &HashSet<String>,
    params: &[IrParam],
    policy: &EmitPolicy,
) -> bool {
    let Some(mutable_param) = mutable_params.iter().next() else {
        return false;
    };
    let params_by_name = params
        .iter()
        .map(|param| (param.name.as_str(), param))
        .collect::<HashMap<_, _>>();

    readonly_params.iter().all(|readonly_param| {
        explicit_noalias_pair(policy, readonly_param, mutable_param)
            || params_have_restrict_noalias(&params_by_name, readonly_param, mutable_param)
    })
}

fn explicit_noalias_pair(policy: &EmitPolicy, readonly_param: &str, mutable_param: &str) -> bool {
    policy
        .noalias_param_pairs
        .iter()
        .any(|pair| pair.readonly_param == readonly_param && pair.mutable_param == mutable_param)
}

fn params_have_restrict_noalias(
    params_by_name: &HashMap<&str, &IrParam>,
    readonly_param: &str,
    mutable_param: &str,
) -> bool {
    params_by_name
        .get(readonly_param)
        .is_some_and(|param| type_has_restrict_qualifier(&param.ty))
        && params_by_name
            .get(mutable_param)
            .is_some_and(|param| type_has_restrict_qualifier(&param.ty))
}

fn type_has_restrict_qualifier(ty: &IrType) -> bool {
    [ty.spelled.as_str(), ty.canonical.as_str()]
        .iter()
        .any(|spelling| spelling_has_restrict_qualifier(spelling))
}

fn spelling_has_restrict_qualifier(spelling: &str) -> bool {
    spelling
        .split(|ch: char| {
            ch.is_whitespace() || matches!(ch, '*' | '(' | ')' | '[' | ']' | ',' | ';')
        })
        .any(|token| matches!(token, "restrict" | "__restrict" | "__restrict__"))
}

fn collect_readonly_pointer_param_uses(
    body: &[IrStmt],
    params: &[IrParam],
) -> Result<ReadonlyPointerParamUses, String> {
    let readonly_pointer_params = params
        .iter()
        .filter(|param| readonly_pointer_slice_element_type(&param.ty).is_some())
        .map(|param| (param.name.as_str(), &param.ty))
        .collect::<HashMap<_, _>>();
    let mut uses = ReadonlyPointerParamUses::default();
    collect_readonly_pointer_read_params_from_body(body, &readonly_pointer_params, &mut uses)?;
    Ok(uses)
}

fn validate_readonly_pointer_slice_lowering_evidence(
    params: &[IrParam],
    byte_slice_params: &HashSet<String>,
    nullable_pointer_params: &HashSet<String>,
    readonly_pointer_read_params: &HashSet<String>,
    readonly_pointer_mentioned_params: &HashSet<String>,
) -> Result<(), String> {
    for param in params {
        if readonly_pointer_slice_element_type(&param.ty).is_some()
            && !byte_slice_params.contains(&param.name)
            && !nullable_pointer_params.contains(&param.name)
            && !readonly_pointer_read_params.contains(&param.name)
            && !readonly_pointer_mentioned_params.contains(&param.name)
        {
            return Err(format!(
                "readonly pointer param {} requires pointer-to-slice lowering evidence before lowering {} to &[T]",
                param.name,
                type_label(&param.ty)
            ));
        }
    }
    Ok(())
}

fn collect_mutable_pointer_write_params_from_body(
    body: &[IrStmt],
    mutable_pointer_params: &HashMap<&str, &IrType>,
    write_params: &mut HashSet<String>,
) -> Result<(), String> {
    for stmt in body {
        match stmt {
            IrStmt::Assign { target, .. } => {
                collect_mutable_pointer_write_param_from_target(
                    target,
                    mutable_pointer_params,
                    write_params,
                )?;
            }
            IrStmt::If {
                then_body,
                else_body,
                ..
            } => {
                collect_mutable_pointer_write_params_from_body(
                    then_body,
                    mutable_pointer_params,
                    write_params,
                )?;
                collect_mutable_pointer_write_params_from_body(
                    else_body,
                    mutable_pointer_params,
                    write_params,
                )?;
            }
            IrStmt::While { body, .. } | IrStmt::DoWhile { body, .. } => {
                collect_mutable_pointer_write_params_from_body(
                    body,
                    mutable_pointer_params,
                    write_params,
                )?;
            }
            IrStmt::For {
                init, step, body, ..
            } => {
                collect_mutable_pointer_write_params_from_body(
                    init,
                    mutable_pointer_params,
                    write_params,
                )?;
                if let Some(step) = step {
                    collect_mutable_pointer_write_params_from_body(
                        std::slice::from_ref(step.as_ref()),
                        mutable_pointer_params,
                        write_params,
                    )?;
                }
                collect_mutable_pointer_write_params_from_body(
                    body,
                    mutable_pointer_params,
                    write_params,
                )?;
            }
            IrStmt::Expr { expr, .. } => {
                collect_c_memset_mutable_pointer_write_param(
                    expr,
                    mutable_pointer_params,
                    write_params,
                )?;
                collect_c_memcpy_mutable_pointer_write_param(
                    expr,
                    mutable_pointer_params,
                    write_params,
                )?;
            }
            IrStmt::Decl { .. }
            | IrStmt::Return { .. }
            | IrStmt::Break { .. }
            | IrStmt::Continue { .. }
            | IrStmt::Unsupported { .. } => {}
        }
    }
    Ok(())
}

fn collect_c_memset_mutable_pointer_write_param(
    expr: &IrExpr,
    mutable_pointer_params: &HashMap<&str, &IrType>,
    write_params: &mut HashSet<String>,
) -> Result<(), String> {
    let IrExpr::Call { callee, args, .. } = expr else {
        return Ok(());
    };
    if callee == "memset" && args.len() == 3 {
        collect_direct_mutable_pointer_write_param(&args[0], mutable_pointer_params, write_params)?;
    }
    Ok(())
}

fn collect_c_memcpy_mutable_pointer_write_param(
    expr: &IrExpr,
    mutable_pointer_params: &HashMap<&str, &IrType>,
    write_params: &mut HashSet<String>,
) -> Result<(), String> {
    let IrExpr::Call { callee, args, .. } = expr else {
        return Ok(());
    };
    if callee == "memcpy" && args.len() == 3 {
        collect_direct_mutable_pointer_write_param(&args[0], mutable_pointer_params, write_params)?;
    }
    Ok(())
}

fn collect_mutable_pointer_write_param_from_target(
    target: &IrExpr,
    mutable_pointer_params: &HashMap<&str, &IrType>,
    write_params: &mut HashSet<String>,
) -> Result<(), String> {
    match target {
        IrExpr::Index { base, .. } => {
            collect_direct_mutable_pointer_write_param(base, mutable_pointer_params, write_params)
        }
        IrExpr::Deref { ptr, .. } => match ptr.as_ref() {
            IrExpr::Binary { .. } => {
                if let Some((base, _)) = mutable_pointer_add_operands_from_expr(ptr.as_ref()) {
                    collect_direct_mutable_pointer_write_param(
                        base,
                        mutable_pointer_params,
                        write_params,
                    )?;
                }
                Ok(())
            }
            expr => collect_direct_mutable_pointer_write_param(
                expr,
                mutable_pointer_params,
                write_params,
            ),
        },
        _ => Ok(()),
    }
}

fn mutable_pointer_add_operands_from_expr(expr: &IrExpr) -> Option<(&IrExpr, &IrExpr)> {
    let IrExpr::Binary { lhs, rhs, .. } = expr else {
        return None;
    };
    mutable_pointer_add_operands(lhs, rhs)
}

fn collect_direct_mutable_pointer_write_param(
    expr: &IrExpr,
    mutable_pointer_params: &HashMap<&str, &IrType>,
    write_params: &mut HashSet<String>,
) -> Result<(), String> {
    let IrExpr::Var { name, ty, .. } = expr else {
        return Ok(());
    };
    if mutable_pointer_params
        .get(name.as_str())
        .is_some_and(|param_ty| *param_ty == ty)
    {
        write_params.insert(name.to_string());
    }
    Ok(())
}

fn collect_readonly_pointer_read_params_from_body(
    body: &[IrStmt],
    readonly_pointer_params: &HashMap<&str, &IrType>,
    uses: &mut ReadonlyPointerParamUses,
) -> Result<(), String> {
    for stmt in body {
        match stmt {
            IrStmt::Decl { init, .. } => {
                if let Some(init) = init {
                    collect_readonly_pointer_read_params_from_expr(
                        init,
                        readonly_pointer_params,
                        uses,
                    )?;
                }
            }
            IrStmt::Assign { target, value, .. } => {
                collect_readonly_pointer_read_params_from_expr(
                    target,
                    readonly_pointer_params,
                    uses,
                )?;
                collect_readonly_pointer_read_params_from_expr(
                    value,
                    readonly_pointer_params,
                    uses,
                )?;
            }
            IrStmt::If {
                condition,
                then_body,
                else_body,
                ..
            } => {
                collect_readonly_pointer_read_params_from_expr(
                    condition,
                    readonly_pointer_params,
                    uses,
                )?;
                collect_readonly_pointer_read_params_from_body(
                    then_body,
                    readonly_pointer_params,
                    uses,
                )?;
                collect_readonly_pointer_read_params_from_body(
                    else_body,
                    readonly_pointer_params,
                    uses,
                )?;
            }
            IrStmt::While {
                condition, body, ..
            } => {
                collect_readonly_pointer_read_params_from_expr(
                    condition,
                    readonly_pointer_params,
                    uses,
                )?;
                collect_readonly_pointer_read_params_from_body(
                    body,
                    readonly_pointer_params,
                    uses,
                )?;
            }
            IrStmt::DoWhile {
                body, condition, ..
            } => {
                collect_readonly_pointer_read_params_from_body(
                    body,
                    readonly_pointer_params,
                    uses,
                )?;
                collect_readonly_pointer_read_params_from_expr(
                    condition,
                    readonly_pointer_params,
                    uses,
                )?;
            }
            IrStmt::For {
                init,
                condition,
                step,
                body,
                ..
            } => {
                collect_readonly_pointer_read_params_from_body(
                    init,
                    readonly_pointer_params,
                    uses,
                )?;
                if let Some(condition) = condition {
                    collect_readonly_pointer_read_params_from_expr(
                        condition,
                        readonly_pointer_params,
                        uses,
                    )?;
                }
                if let Some(step) = step {
                    collect_readonly_pointer_read_params_from_body(
                        std::slice::from_ref(step.as_ref()),
                        readonly_pointer_params,
                        uses,
                    )?;
                }
                collect_readonly_pointer_read_params_from_body(
                    body,
                    readonly_pointer_params,
                    uses,
                )?;
            }
            IrStmt::Return { value, .. } => {
                if let Some(value) = value {
                    collect_readonly_pointer_read_params_from_expr(
                        value,
                        readonly_pointer_params,
                        uses,
                    )?;
                }
            }
            IrStmt::Expr { expr, .. } => {
                collect_readonly_pointer_read_params_from_expr(
                    expr,
                    readonly_pointer_params,
                    uses,
                )?;
            }
            IrStmt::Break { .. } | IrStmt::Continue { .. } | IrStmt::Unsupported { .. } => {}
        }
    }
    Ok(())
}

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
