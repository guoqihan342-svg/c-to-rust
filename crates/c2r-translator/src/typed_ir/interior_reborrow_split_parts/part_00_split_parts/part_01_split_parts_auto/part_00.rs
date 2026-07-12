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
