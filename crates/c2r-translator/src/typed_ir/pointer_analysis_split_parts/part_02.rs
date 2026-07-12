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
            if is_unused_readonly_8_bit_pointer_param(
                &param.name,
                &param.ty,
                readonly_pointer_read_params,
                readonly_pointer_mentioned_params,
            ) {
                continue;
            }
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
            IrStmt::RecordMemset { .. } => {}
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
