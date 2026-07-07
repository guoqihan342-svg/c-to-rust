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
