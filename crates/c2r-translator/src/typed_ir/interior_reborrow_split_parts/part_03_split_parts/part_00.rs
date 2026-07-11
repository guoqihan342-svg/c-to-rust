fn validate_assignment_call_interior_reborrow_carrier(
    function: &IrFunction,
    policy: &EmitPolicy,
    plan: &InteriorReborrowPlan,
    setup: &IrStmt,
    sentinel: &IrStmt,
    loop_stmt: &IrStmt,
    observation: &IrStmt,
) -> Result<(String, Option<Vec<String>>), String> {
    if !is_c_bool_type(&function.return_type) {
        return Err("assignment-call interior reborrow carrier must return bool".to_string());
    }
    let owner = function
        .params
        .iter()
        .find(|param| param.name == plan.owner)
        .ok_or_else(|| "assignment-call interior reborrow owner is missing".to_string())?;
    let pointer_roots = function
        .params
        .iter()
        .filter(|param| matches!(param.ty.kind, IrTypeKind::Pointer { .. }))
        .collect::<Vec<_>>();
    let [first_root, second_root] = pointer_roots.as_slice() else {
        return Err(
            "assignment-call interior reborrow requires exactly two pointer roots".to_string(),
        );
    };
    let db = if first_root.name == plan.owner {
        *second_root
    } else if second_root.name == plan.owner {
        *first_root
    } else {
        return Err("assignment-call interior reborrow owner root drifted".to_string());
    };
    mutable_complete_record_root(owner, "owner")?;
    mutable_complete_record_root(db, "db")?;
    let value_params = function
        .params
        .iter()
        .filter(|param| !matches!(param.ty.kind, IrTypeKind::Pointer { .. }))
        .collect::<Vec<_>>();
    let seed_params = value_params
        .iter()
        .copied()
        .filter(|param| matches!(param.ty.kind, IrTypeKind::Record { .. }))
        .collect::<Vec<_>>();
    let offset_params = value_params
        .iter()
        .copied()
        .filter(|param| is_exact_u32_ir_type(&param.ty))
        .collect::<Vec<_>>();
    let (seed, offset) = match (seed_params.as_slice(), offset_params.as_slice()) {
        ([seed], []) if value_params.len() == 1 => (*seed, None),
        ([seed], [offset]) if value_params.len() == 2 => (*seed, Some(*offset)),
        _ => {
            return Err(
                "assignment-call interior reborrow requires one complete record seed and at most one exact-u32 offset"
                    .to_string(),
            )
        }
    };
    complete_named_record_fields(&seed.ty, "call seed")?;
    reject_qualified_reborrow_type(&seed.ty, "call seed")?;
    let (seed_local, seed_local_ty) = validate_reborrow_seed_setup(setup, seed)?;
    if policy.noalias_param_pairs.as_slice()
        != [NoAliasParamPair {
            readonly_param: db.name.clone(),
            mutable_param: plan.owner.clone(),
        }]
    {
        return Err(
            "assignment-call interior reborrow requires one exact forward db-to-owner noalias pair"
                .to_string(),
        );
    }

    let IrStmt::Decl {
        name: sentinel_name,
        ty: sentinel_ty,
        init: Some(init),
        ..
    } = sentinel
    else {
        return Err("assignment-call interior reborrow requires a bool sentinel".to_string());
    };
    if !is_c_bool_type(sentinel_ty) || !is_fixed_bool(init, true) {
        return Err("assignment-call interior reborrow sentinel must be exact bool true".to_string());
    }
    let IrStmt::While {
        condition, body, ..
    } = loop_stmt
    else {
        return Err("assignment-call interior reborrow requires one while".to_string());
    };
    if !is_direct_bool_var_read(condition, sentinel_name, sentinel_ty) {
        return Err("assignment-call interior reborrow while sentinel drifted".to_string());
    }
    let entry_initialized_field_path = match body.as_slice() {
        [clear, call_assignment, branch, miss_return] if offset.is_none() => {
            validate_bool_sentinel_clear(clear, sentinel_name, sentinel_ty)?;
            let call_path = validate_reborrow_call_assignment(
                call_assignment,
                plan,
                db,
                seed_local,
                seed_local_ty,
            )?;
            validate_reborrow_result_branch(branch, plan, db, &call_path)?;
            validate_fixed_bool_return(
                miss_return,
                false,
                "assignment-call interior reborrow miss path",
            )?;
            None
        }
        [clear, tail_loop @ IrStmt::DoWhile { .. }, miss_return] if offset.is_none() => {
            validate_bool_sentinel_clear(clear, sentinel_name, sentinel_ty)?;
            validate_reborrow_do_while_tail_assignment_call(
                tail_loop,
                plan,
                db,
                seed_local,
                seed_local_ty,
            )?;
            validate_fixed_bool_return(
                miss_return,
                false,
                "assignment-call interior reborrow do-while tail miss path",
            )?;
            None
        }
        [clear, outer_branch, miss_return] => {
            validate_bool_sentinel_clear(clear, sentinel_name, sentinel_ty)?;
            let offset = offset.ok_or_else(|| {
                "assignment-call interior reborrow zero-start branch requires one exact-u32 offset"
                    .to_string()
            })?;
            let entry_initialized_field_path = validate_reborrow_zero_start_branch(
                outer_branch,
                plan,
                db,
                seed_local,
                seed_local_ty,
                offset,
            )?;
            validate_fixed_bool_return(
                miss_return,
                false,
                "assignment-call interior reborrow zero-start miss path",
            )?;
            Some(entry_initialized_field_path)
        }
        _ => {
            return Err(
                "assignment-call interior reborrow while body must preserve the exact call branch, do-while tail, or zero-start carrier order"
                    .to_string(),
            )
        }
    };
    validate_fixed_bool_return(
        observation,
        true,
        "assignment-call interior reborrow final path",
    )?;
    Ok((db.name.clone(), entry_initialized_field_path))
}

fn validate_reborrow_seed_setup<'a>(
    setup: &'a IrStmt,
    seed: &IrParam,
) -> Result<(&'a str, &'a IrType), String> {
    let IrStmt::Decl {
        name,
        ty,
        init: Some(init),
        ..
    } = setup
    else {
        return Err(
            "assignment-call interior reborrow requires one initialized seed local".to_string(),
        );
    };
    let init = match init {
        IrExpr::LValueToRValue { target, expr, .. }
            if types_match_ignoring_spelling(target, &seed.ty) => expr.as_ref(),
        direct => direct,
    };
    let IrExpr::Var {
        name: seed_name,
        ty: seed_ty,
        ..
    } = init
    else {
        return Err(
            "assignment-call interior reborrow seed local must copy the seed parameter".to_string(),
        );
    };
    if name == &seed.name
        || seed_name != &seed.name
        || !types_match_ignoring_spelling(ty, &seed.ty)
        || !types_match_ignoring_spelling(seed_ty, &seed.ty)
    {
        return Err("assignment-call interior reborrow seed setup drifted".to_string());
    }
    complete_named_record_fields(ty, "call seed local")?;
    Ok((name, ty))
}

fn mutable_complete_record_root<'a>(
    param: &'a IrParam,
    label: &str,
) -> Result<&'a IrType, String> {
    let record = mutable_record_pointer_pointee_type(&param.ty).ok_or_else(|| {
        format!("assignment-call interior reborrow {label} must be a mutable record pointer")
    })?;
    complete_named_record_fields(record, label)?;
    reject_qualified_reborrow_type(&param.ty, label)?;
    Ok(record)
}

fn validate_reborrow_call_assignment(
    stmt: &IrStmt,
    plan: &InteriorReborrowPlan,
    db: &IrParam,
    seed_local: &str,
    seed_local_ty: &IrType,
) -> Result<Vec<String>, String> {
    let IrStmt::Assign { target, value, .. } = stmt else {
        return Err("assignment-call interior reborrow requires one call assignment".to_string());
    };
    let path = exact_nested_alias_u32_path(target, plan, "call assignment target")?;
    let IrExpr::Call {
        callee, args, ty, ..
    } = value
    else {
        return Err("assignment-call interior reborrow assignment must contain one call".to_string());
    };
    emit_identifier(callee, "assignment-call interior reborrow callee")?;
    if !is_exact_u32_ir_type(ty) {
        return Err("assignment-call interior reborrow callee must return exact u32".to_string());
    }
    let [db_arg, seed_arg, alias_arg] = args.as_slice() else {
        return Err(
            "assignment-call interior reborrow call requires db/address-seed/same-alias"
                .to_string(),
        );
    };
    validate_exact_pointer_var_arg(db_arg, &db.name, &db.ty, "db")?;
    let IrExpr::AddrOf {
        operand,
        ty: address_ty,
        ..
    } = seed_arg
    else {
        return Err("assignment-call interior reborrow second arg must be &seed".to_string());
    };
    let IrExpr::Var {
        name: seed_name,
        ty: seed_ty,
        ..
    } = operand.as_ref()
    else {
        return Err("assignment-call interior reborrow seed address must be direct".to_string());
    };
    if seed_name != seed_local
        || !types_match_ignoring_spelling(seed_ty, seed_local_ty)
        || mutable_record_pointer_pointee_type(address_ty)
            .is_none_or(|pointee| !types_match_ignoring_spelling(pointee, seed_local_ty))
    {
        return Err("assignment-call interior reborrow seed address/type drifted".to_string());
    }
    validate_exact_pointer_var_arg(alias_arg, &plan.alias, path.root_ty, "alias")?;
    Ok(path.fields.iter().map(|field| (*field).to_string()).collect())
}

fn validate_exact_pointer_var_arg(
    expr: &IrExpr,
    expected_name: &str,
    expected_ty: &IrType,
    label: &str,
) -> Result<(), String> {
    let (expr, read_ty) = match expr {
        IrExpr::LValueToRValue { target, expr, .. } => (expr.as_ref(), target),
        direct => (direct, expected_ty),
    };
    let IrExpr::Var { name, ty, .. } = expr else {
        return Err(format!("assignment-call interior reborrow {label} arg must be a direct root"));
    };
    if name != expected_name
        || !record_pointer_types_match_ignoring_spelling(ty, expected_ty)
        || !record_pointer_types_match_ignoring_spelling(read_ty, expected_ty)
    {
        return Err(format!("assignment-call interior reborrow {label} arg drifted"));
    }
    Ok(())
}
