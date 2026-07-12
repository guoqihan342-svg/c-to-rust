fn collect_record_pointer_field_value_params_from_body(
    body: &[IrStmt],
    param_types: &HashMap<&str, &IrType>,
    mutable_record_pointer_write_params: &HashSet<String>,
    value_params: &mut HashSet<String>,
) -> Result<(), String> {
    for stmt in body {
        match stmt {
            IrStmt::Assign { target, value, .. } => {
                collect_record_pointer_field_value_param_from_assignment(
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
                collect_record_pointer_field_value_params_from_body(
                    then_body,
                    param_types,
                    mutable_record_pointer_write_params,
                    value_params,
                )?;
                collect_record_pointer_field_value_params_from_body(
                    else_body,
                    param_types,
                    mutable_record_pointer_write_params,
                    value_params,
                )?;
            }
            IrStmt::While { body, .. } | IrStmt::DoWhile { body, .. } => {
                collect_record_pointer_field_value_params_from_body(
                    body,
                    param_types,
                    mutable_record_pointer_write_params,
                    value_params,
                )?;
            }
            IrStmt::For {
                init, step, body, ..
            } => {
                collect_record_pointer_field_value_params_from_body(
                    init,
                    param_types,
                    mutable_record_pointer_write_params,
                    value_params,
                )?;
                if let Some(step) = step {
                    collect_record_pointer_field_value_params_from_body(
                        std::slice::from_ref(step.as_ref()),
                        param_types,
                        mutable_record_pointer_write_params,
                        value_params,
                    )?;
                }
                collect_record_pointer_field_value_params_from_body(
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
            | IrStmt::RecordMemset { .. }
            | IrStmt::Unsupported { .. } => {}
        }
    }
    Ok(())
}

fn collect_record_pointer_field_value_param_from_assignment(
    target: &IrExpr,
    value: &IrExpr,
    param_types: &HashMap<&str, &IrType>,
    mutable_record_pointer_write_params: &HashSet<String>,
    value_params: &mut HashSet<String>,
) -> Result<(), String> {
    let Some(path) = record_pointer_member_path_from_expr(target)? else {
        return Ok(());
    };
    if !mutable_record_pointer_write_params.contains(path.root_name) {
        return Ok(());
    }
    if emit_record_pointer_field_type(path.ty).is_none() {
        return Ok(());
    }
    collect_record_pointer_value_param_from_expr(value, param_types, value_params)
}

fn collect_record_pointer_value_param_from_expr(
    value: &IrExpr,
    param_types: &HashMap<&str, &IrType>,
    value_params: &mut HashSet<String>,
) -> Result<(), String> {
    match value {
        IrExpr::Var { name, ty, .. } => {
            if param_types.get(name.as_str()).is_some_and(|param_ty| {
                *param_ty == ty && emit_record_pointer_field_type(ty).is_some()
            }) {
                value_params.insert(name.clone());
            }
            Ok(())
        }
        IrExpr::Cast { expr, .. } => {
            collect_record_pointer_value_param_from_expr(expr, param_types, value_params)
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
    if write_params.len() > 1
        && !mutable_pointer_writes_noalias_proven(&write_params, params, policy)
    {
        return Err(
            "mutable pointer write requires exactly one pointer param for alias proof unless all written mutable pointer params have restrict/noalias proof".to_string(),
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
    if mutable_params.is_empty() {
        return false;
    }
    let params_by_name = params
        .iter()
        .map(|param| (param.name.as_str(), param))
        .collect::<HashMap<_, _>>();

    readonly_params.iter().all(|readonly_param| {
        mutable_params.iter().all(|mutable_param| {
            explicit_noalias_pair(policy, readonly_param, mutable_param)
                || params_have_restrict_noalias(&params_by_name, readonly_param, mutable_param)
        })
    })
}

fn mutable_pointer_writes_noalias_proven(
    write_params: &HashSet<String>,
    params: &[IrParam],
    policy: &EmitPolicy,
) -> bool {
    if write_params.len() <= 1 {
        return true;
    }
    let params_by_name = params
        .iter()
        .map(|param| (param.name.as_str(), param))
        .collect::<HashMap<_, _>>();
    let write_params = write_params.iter().collect::<Vec<_>>();

    for (index, left_param) in write_params.iter().enumerate() {
        for right_param in write_params.iter().skip(index + 1) {
            if !explicit_noalias_between(policy, left_param, right_param)
                && !params_have_restrict_noalias(&params_by_name, left_param, right_param)
            {
                return false;
            }
        }
    }
    true
}

fn explicit_noalias_pair(policy: &EmitPolicy, readonly_param: &str, mutable_param: &str) -> bool {
    policy
        .noalias_param_pairs
        .iter()
        .any(|pair| pair.readonly_param == readonly_param && pair.mutable_param == mutable_param)
}

fn explicit_noalias_between(policy: &EmitPolicy, left_param: &str, right_param: &str) -> bool {
    explicit_noalias_pair(policy, left_param, right_param)
        || explicit_noalias_pair(policy, right_param, left_param)
}
