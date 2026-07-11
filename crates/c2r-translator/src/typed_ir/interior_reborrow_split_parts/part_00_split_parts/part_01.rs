fn validate_direct_owner_u32_increment(
    function: &IrFunction,
    plan: &InteriorReborrowPlan,
    stmt: &IrStmt,
) -> Result<String, String> {
    let IrStmt::Assign { target, value, .. } = stmt else {
        return Err(
            "interior reborrow stats sequence requires one normalized owner increment assignment"
                .to_string(),
        );
    };
    let target_path = record_pointer_member_path_from_expr(target)?.ok_or_else(|| {
        "interior reborrow stats sequence increment target must be a record member".to_string()
    })?;
    if target_path.root_name != plan.owner
        || target_path.fields.len() != 1
        || !is_exact_u32_ir_type(target_path.ty)
    {
        return Err(
            "interior reborrow stats sequence increment must target one direct owner u32 field"
                .to_string(),
        );
    }

    let owner_param = function
        .params
        .iter()
        .find(|param| param.name == plan.owner)
        .ok_or_else(|| "interior reborrow stats sequence owner parameter is missing".to_string())?;
    if !record_pointer_types_match_ignoring_spelling(target_path.root_ty, &owner_param.ty) {
        return Err("interior reborrow stats sequence owner type drifted".to_string());
    }
    let owner_record = mutable_record_pointer_pointee_type(&owner_param.ty)
        .ok_or_else(|| "interior reborrow stats sequence owner must remain mutable".to_string())?;
    let owner_fields = complete_named_record_fields(owner_record, "stats sequence owner")?;
    let declared_target = unique_record_field(
        owner_fields,
        &target_path.fields[0],
        "stats sequence increment",
    )?;
    if !types_match_ignoring_spelling(&declared_target.ty, target_path.ty) {
        return Err(
            "interior reborrow stats sequence increment inventory type drifted".to_string(),
        );
    }
    reject_qualified_reborrow_type(target_path.ty, "stats sequence increment")?;

    let IrExpr::Binary {
        op: IrBinOp::Add,
        lhs,
        rhs,
        ty: compute_ty,
        ..
    } = value
    else {
        return Err(
            "interior reborrow stats sequence increment must preserve normalized addition"
                .to_string(),
        );
    };
    if !is_exact_u32_ir_type(compute_ty)
        || !types_match_ignoring_spelling(compute_ty, target_path.ty)
    {
        return Err("interior reborrow stats sequence increment type drifted".to_string());
    }
    let lhs_path = record_pointer_member_path_from_expr(lhs)?.ok_or_else(|| {
        "interior reborrow stats sequence increment lhs must reread its target".to_string()
    })?;
    if lhs_path.root_name != target_path.root_name
        || lhs_path.fields != target_path.fields
        || !types_match_ignoring_spelling(lhs_path.ty, target_path.ty)
    {
        return Err("interior reborrow stats sequence increment lhs/target drifted".to_string());
    }
    if !matches!(rhs.as_ref(), IrExpr::LitInt { value: 1, ty, .. }
        if is_exact_u32_ir_type(ty) && types_match_ignoring_spelling(ty, target_path.ty))
    {
        return Err(
            "interior reborrow stats sequence increment requires exact u32 literal 1".to_string(),
        );
    }
    Ok(target_path.fields[0].to_string())
}

fn validate_owner_sibling_size_add_carrier(
    function: &IrFunction,
    terminal: Option<&IrStmt>,
) -> Result<(), String> {
    match terminal {
        None if matches!(&function.return_type.kind, IrTypeKind::Void) => Ok(()),
        None => Err(
            "interior reborrow size update two-statement carrier requires void return"
                .to_string(),
        ),
        Some(terminal) if is_c_bool_type(&function.return_type) => {
            validate_fixed_bool_return(terminal, true, "interior reborrow size update terminal")
        }
        Some(_) => Err(
            "interior reborrow size update three-statement carrier requires bool return true"
                .to_string(),
        ),
    }
}

fn validate_owner_sibling_size_add_from_alias(
    function: &IrFunction,
    policy: &EmitPolicy,
    plan: &InteriorReborrowPlan,
    stmt: &IrStmt,
) -> Result<(String, String), String> {
    if policy.noalias_param_pairs.iter().any(|pair| {
        (pair.readonly_param == plan.alias && pair.mutable_param == plan.owner)
            || (pair.readonly_param == plan.owner && pair.mutable_param == plan.alias)
    }) {
        return Err(
            "interior reborrow owner and interior alias must not be modeled as noalias"
                .to_string(),
        );
    }
    let IrStmt::Assign { target, value, .. } = stmt else {
        return Err("interior reborrow size update requires one owner compound assignment".to_string());
    };
    let target_path = record_pointer_member_path_from_expr(target)?
        .ok_or_else(|| "interior reborrow size update target must be a record member".to_string())?;
    if target_path.root_name != plan.owner || target_path.fields.len() != 1 {
        return Err(
            "interior reborrow size update must target one direct owner sibling field".to_string(),
        );
    }
    if plan.owner_path.first().map(String::as_str) == target_path.fields.first().copied() {
        return Err(
            "interior reborrow size update target overlaps the aliased owner projection"
                .to_string(),
        );
    }
    validate_exact_abi_size_t(target_path.ty, "target")?;

    let owner_param = function
        .params
        .iter()
        .find(|param| param.name == plan.owner)
        .ok_or_else(|| "interior reborrow size update owner parameter is missing".to_string())?;
    if !record_pointer_types_match_ignoring_spelling(target_path.root_ty, &owner_param.ty) {
        return Err("interior reborrow size update owner type drifted".to_string());
    }
    let owner_record = mutable_record_pointer_pointee_type(&owner_param.ty)
        .ok_or_else(|| "interior reborrow size update owner must remain mutable".to_string())?;
    let owner_fields = complete_named_record_fields(owner_record, "size update owner")?;
    let declared_target = unique_record_field(
        owner_fields,
        &target_path.fields[0],
        "size update target",
    )?;
    if !types_match_ignoring_spelling(&declared_target.ty, target_path.ty) {
        return Err("interior reborrow size update target inventory type drifted".to_string());
    }
    reject_qualified_reborrow_type(target_path.ty, "size update target")?;

    let IrExpr::Binary {
        op: IrBinOp::Add,
        lhs,
        rhs,
        ty: compute_ty,
        ..
    } = value
    else {
        return Err("interior reborrow size update must preserve += addition".to_string());
    };
    if !types_match_ignoring_spelling(compute_ty, target_path.ty) {
        return Err(
            "interior reborrow size update compute/result/target type drifted".to_string(),
        );
    }
    validate_exact_abi_size_t(compute_ty, "compute result")?;

    let lhs_path = record_pointer_member_path_from_expr(lhs)?
        .ok_or_else(|| "interior reborrow size update lhs must reread its target".to_string())?;
    if lhs_path.root_name != target_path.root_name
        || lhs_path.fields != target_path.fields
        || !types_match_ignoring_spelling(lhs_path.ty, target_path.ty)
    {
        return Err("interior reborrow size update lhs/target drifted".to_string());
    }

    let IrExpr::Cast {
        target: conversion_ty,
        expr: source_read,
        ..
    } = rhs.as_ref()
    else {
        return Err(
            "interior reborrow size update RHS requires an explicit ABI-bound widening cast"
                .to_string(),
        );
    };
    if !types_match_ignoring_spelling(conversion_ty, compute_ty) {
        return Err(
            "interior reborrow size update RHS conversion/compute type drifted".to_string(),
        );
    }
    validate_exact_abi_size_t(conversion_ty, "RHS conversion")?;

    let IrExpr::LValueToRValue {
        target: source_ty,
        expr: source,
        ..
    } = source_read.as_ref()
    else {
        return Err(
            "interior reborrow size update RHS must be one direct alias field read".to_string(),
        );
    };
    if !is_exact_u32_ir_type(source_ty) {
        return Err("interior reborrow size update RHS read must be exact u32".to_string());
    }
    let source_path = record_pointer_member_path_from_expr(source)?.ok_or_else(|| {
        "interior reborrow size update RHS must be one direct alias field read".to_string()
    })?;
    if source_path.root_name != plan.alias
        || source_path.fields.len() != 1
        || !is_exact_u32_ir_type(source_path.ty)
        || !types_match_ignoring_spelling(source_path.ty, source_ty)
    {
        return Err(
            "interior reborrow size update RHS alias projection/type drifted".to_string(),
        );
    }
    let (_, alias_ty, _, _, _, _) = interior_reborrow_decl_parts(&function.body[0])
        .ok_or_else(|| "interior reborrow size update alias declaration drifted".to_string())?;
    if !record_pointer_types_match_ignoring_spelling(source_path.root_ty, alias_ty) {
        return Err("interior reborrow size update alias root type drifted".to_string());
    }
    let alias_record = mutable_record_pointer_pointee_type(alias_ty)
        .ok_or_else(|| "interior reborrow size update alias must remain mutable".to_string())?;
    let alias_fields = complete_named_record_fields(alias_record, "size update alias")?;
    let declared_source = unique_record_field(
        alias_fields,
        &source_path.fields[0],
        "size update RHS",
    )?;
    if !types_match_ignoring_spelling(&declared_source.ty, source_path.ty) {
        return Err("interior reborrow size update RHS inventory type drifted".to_string());
    }
    reject_qualified_reborrow_type(source_path.ty, "size update RHS")?;
    Ok((
        target_path.fields[0].to_string(),
        source_path.fields[0].to_string(),
    ))
}

fn validate_exact_abi_size_t(ty: &IrType, label: &str) -> Result<(), String> {
    let IrTypeKind::Integer {
        signed: false,
        width,
    } = &ty.kind
    else {
        return Err(format!(
            "interior reborrow size update {label} must be unsigned ABI size_t"
        ));
    };
    if !is_size_t_type(ty) || *width < 32 || ty.width_bits != Some(*width) {
        return Err(format!(
            "interior reborrow size update {label} lacks lossless target-ABI size_t provenance"
        ));
    }
    Ok(())
}

fn validate_interior_reborrow_types(
    function: &IrFunction,
    alias_ty: &IrType,
    owner: &str,
    owner_ty: &IrType,
    owner_field: &str,
    field_ty: &IrType,
) -> Result<(), String> {
    let owner_param = function
        .params
        .iter()
        .find(|param| param.name == owner)
        .ok_or_else(|| "interior reborrow owner must be a direct parameter".to_string())?;
    if !record_pointer_types_match_ignoring_spelling(&owner_param.ty, owner_ty) {
        return Err("interior reborrow owner parameter type drifted".to_string());
    }
    let owner_record = mutable_record_pointer_pointee_type(owner_ty).ok_or_else(|| {
        "interior reborrow owner must be a non-const mutable record pointer".to_string()
    })?;
    let owner_fields = complete_named_record_fields(owner_record, "owner")?;
    let declared_field = unique_record_field(owner_fields, owner_field, "owner")?;
    if !types_match_ignoring_spelling(&declared_field.ty, field_ty) {
        return Err("interior reborrow owner field type conflicts with inventory".to_string());
    }
    let alias_pointee = mutable_record_pointer_pointee_type(alias_ty).ok_or_else(|| {
        "interior reborrow alias must be a mutable pointer to a named record".to_string()
    })?;
    complete_named_record_fields(alias_pointee, "alias pointee")?;
    if !types_match_ignoring_spelling(alias_pointee, field_ty) {
        return Err("interior reborrow typedef pointer pointee does not match owner field".to_string());
    }
    reject_qualified_reborrow_type(alias_ty, "alias")?;
    reject_qualified_reborrow_type(owner_ty, "owner")?;
    Ok(())
}

fn validate_legacy_interior_reborrow_carrier(
    function: &IrFunction,
    plan: &InteriorReborrowPlan,
    write: &IrStmt,
    observation: &IrStmt,
) -> Result<(), String> {
    let pointer_params = function
        .params
        .iter()
        .filter(|param| matches!(param.ty.kind, IrTypeKind::Pointer { .. }))
        .collect::<Vec<_>>();
    if pointer_params.len() != 1 || pointer_params[0].name != plan.owner {
        return Err("interior reborrow requires one direct owner pointer parameter".to_string());
    }
    validate_alias_write(write, plan, false)?;
    validate_fixed_bool_return(observation, true, "interior reborrow carrier")?;
    if !is_c_bool_type(&function.return_type) {
        return Err("interior reborrow carrier must return fixed bool true".to_string());
    }
    Ok(())
}

fn validate_run_once_interior_reborrow_carrier(
    function: &IrFunction,
    policy: &EmitPolicy,
    plan: &InteriorReborrowPlan,
    sentinel: &IrStmt,
    loop_stmt: &IrStmt,
    observation: &IrStmt,
) -> Result<(), String> {
    if !is_c_bool_type(&function.return_type) || function.params.len() != 2 {
        return Err(
            "run-once interior reborrow requires bool return and exactly owner/source parameters"
                .to_string(),
        );
    }
    if validate_bounded_alias_uses(&function.body, plan)? != 1 {
        return Err("interior reborrow alias requires exactly one bounded field write".to_string());
    }
    let source = function
        .params
        .iter()
        .find(|param| param.name != plan.owner)
        .ok_or_else(|| "run-once interior reborrow readonly source is missing".to_string())?;
    let source_record = readonly_record_pointer_pointee_type(&source.ty).ok_or_else(|| {
        "run-once interior reborrow source must be one readonly record pointer root".to_string()
    })?;
    complete_named_record_fields(source_record, "readonly source")?;
    reject_qualified_reborrow_type(&source.ty, "readonly source")?;
    if !explicit_noalias_pair(policy, &source.name, &plan.owner) {
        return Err(
            "run-once interior reborrow requires exact readonly-source to mutable-owner noalias proof"
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
        return Err("run-once interior reborrow requires an initialized bool sentinel".to_string());
    };
    if !is_c_bool_type(sentinel_ty) || !is_fixed_bool(init, true) {
        return Err("run-once interior reborrow sentinel must be exact bool true".to_string());
    }

    let IrStmt::While {
        condition, body, ..
    } = loop_stmt
    else {
        return Err("run-once interior reborrow requires one while sentinel".to_string());
    };
    if !is_direct_bool_var_read(condition, sentinel_name, sentinel_ty) {
        return Err(
            "run-once interior reborrow while condition must directly read its bool sentinel"
                .to_string(),
        );
    }
    let [clear, alias_write, owner_add, continue_stmt, unreachable_return] = body.as_slice()
    else {
        return Err(
            "run-once interior reborrow while body shape drifted from clear/write/add/continue/return"
                .to_string(),
        );
    };
    validate_bool_sentinel_clear(clear, sentinel_name, sentinel_ty)?;
    validate_alias_write(alias_write, plan, true)?;
    validate_owner_source_add(owner_add, plan, source)?;
    if !matches!(continue_stmt, IrStmt::Continue { .. }) {
        return Err(
            "run-once interior reborrow requires a current-level while continue".to_string(),
        );
    }
    validate_fixed_bool_return(
        unreachable_return,
        false,
        "run-once interior reborrow post-continue",
    )?;
    validate_fixed_bool_return(observation, true, "run-once interior reborrow final")
}
