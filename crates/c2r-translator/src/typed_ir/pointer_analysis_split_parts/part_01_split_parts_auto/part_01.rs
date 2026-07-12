
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
            IrStmt::RecordMemset { .. } => {}
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
        | IrExpr::MutableVoidPointerAddress { operand, .. }
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
    policy: &EmitPolicy,
) -> Result<HashSet<String>, String> {
    let mutable_record_pointer_param_names = params
        .iter()
        .filter(|param| mutable_record_pointer_pointee_type(&param.ty).is_some())
        .map(|param| param.name.clone())
        .collect::<HashSet<_>>();
    let record_pointer_field_value_params =
        collect_record_pointer_field_value_params(body, params, &mutable_record_pointer_param_names)?;
    let readonly_pointer_uses = collect_readonly_pointer_param_uses(body, params)?;
    let active_pointer_params = params
        .iter()
        .filter(|param| {
            matches!(param.ty.kind, IrTypeKind::Pointer { .. })
                && emit_opaque_void_pointer_type(&param.ty).is_none()
                && !record_pointer_field_value_params.contains(&param.name)
                && !is_unused_readonly_8_bit_pointer_param(
                    &param.name,
                    &param.ty,
                    &readonly_pointer_uses.read_params,
                    &readonly_pointer_uses.mentioned_params,
                )
        })
        .map(|param| param.name.as_str())
        .collect::<Vec<_>>();
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
    if !write_params.is_empty()
        && active_pointer_params.len() != 1
        && !mutable_record_pointer_alias_proven(&active_pointer_params, &write_params, params, policy)
    {
        return Err(
            "mutable record pointer field assignment requires exactly one pointer param for alias proof"
                .to_string(),
        );
    }
    Ok(write_params)
}

fn mutable_record_pointer_alias_proven(
    active_pointer_params: &[&str],
    write_params: &HashSet<String>,
    params: &[IrParam],
    policy: &EmitPolicy,
) -> bool {
    let params_by_name = params
        .iter()
        .map(|param| (param.name.as_str(), param))
        .collect::<HashMap<_, _>>();
    active_pointer_params.iter().all(|pointer_param| {
        write_params.iter().all(|write_param| {
            if *pointer_param == write_param {
                return true;
            }
            if write_params.contains(*pointer_param) {
                explicit_noalias_between(policy, pointer_param, write_param)
                    || params_have_restrict_noalias(&params_by_name, pointer_param, write_param)
            } else {
                explicit_noalias_pair(policy, pointer_param, write_param)
                    || params_have_restrict_noalias(&params_by_name, pointer_param, write_param)
            }
        })
    })
}

fn collect_record_pointer_field_value_params(
    body: &[IrStmt],
    params: &[IrParam],
    mutable_record_pointer_write_params: &HashSet<String>,
) -> Result<HashSet<String>, String> {
    let param_types: HashMap<&str, &IrType> = params
        .iter()
        .map(|param| (param.name.as_str(), &param.ty))
        .collect();
    let mut value_params = HashSet::new();
    collect_record_pointer_field_value_params_from_body(
        body,
        &param_types,
        mutable_record_pointer_write_params,
        &mut value_params,
    )?;
    Ok(value_params)
}
