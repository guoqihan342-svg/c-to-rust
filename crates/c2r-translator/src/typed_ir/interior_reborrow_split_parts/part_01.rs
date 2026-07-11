fn validate_bool_sentinel_clear(
    stmt: &IrStmt,
    sentinel: &str,
    sentinel_ty: &IrType,
) -> Result<(), String> {
    let IrStmt::Assign {
        target: IrExpr::Var { name, ty, .. },
        value,
        ..
    } = stmt
    else {
        return Err("run-once interior reborrow must clear its bool sentinel first".to_string());
    };
    if name != sentinel
        || !types_match_ignoring_spelling(ty, sentinel_ty)
        || !is_fixed_bool(value, false)
    {
        return Err("run-once interior reborrow sentinel clear drifted".to_string());
    }
    Ok(())
}

fn validate_alias_write(
    stmt: &IrStmt,
    plan: &InteriorReborrowPlan,
    require_zero: bool,
) -> Result<(), String> {
    let IrStmt::Assign { target, value, .. } = stmt else {
        return Err("interior reborrow alias must be used by one direct field write".to_string());
    };
    let write_path = record_pointer_member_path_from_expr(target)?
        .ok_or_else(|| "interior reborrow write must be a record member path".to_string())?;
    if write_path.root_name != plan.alias || write_path.fields.len() < 2 {
        return Err(
            "interior reborrow write requires alias->nested.leaf with one arrow".to_string(),
        );
    }
    if !is_exact_u32_ir_type(write_path.ty) {
        return Err("interior reborrow write leaf must be an exact u32".to_string());
    }
    if !is_exact_u32_constant(value)
        || (require_zero && static_integer_value(value) != Some(0))
    {
        return Err(if require_zero {
            "run-once interior reborrow write value must be side-effect-free exact-u32 zero"
                .to_string()
        } else {
            "interior reborrow write value must be a side-effect-free exact-u32 constant"
                .to_string()
        });
    }
    Ok(())
}

fn validate_owner_source_add(
    stmt: &IrStmt,
    plan: &InteriorReborrowPlan,
    source: &IrParam,
) -> Result<(), String> {
    let IrStmt::Assign { target, value, .. } = stmt else {
        return Err("run-once interior reborrow requires one owner += source field".to_string());
    };
    let target_path = record_pointer_member_path_from_expr(target)?.ok_or_else(|| {
        "run-once interior reborrow owner update must target a direct record field".to_string()
    })?;
    if target_path.root_name != plan.owner
        || target_path.fields.len() != 1
        || !is_exact_u32_ir_type(target_path.ty)
    {
        return Err(
            "run-once interior reborrow owner update must target one exact-u32 owner field"
                .to_string(),
        );
    }
    let IrExpr::Binary {
        op: IrBinOp::Add,
        lhs,
        rhs,
        ty,
        ..
    } = value
    else {
        return Err("run-once interior reborrow owner update must preserve += semantics".to_string());
    };
    let lhs_path = record_pointer_member_path_from_expr(lhs)?
        .ok_or_else(|| "run-once interior reborrow owner add lhs must reread its target".to_string())?;
    if lhs_path.root_name != target_path.root_name
        || lhs_path.fields != target_path.fields
        || !types_match_ignoring_spelling(lhs_path.ty, target_path.ty)
        || !is_exact_u32_ir_type(ty)
    {
        return Err("run-once interior reborrow owner add lhs/type drifted".to_string());
    }

    let source_expr = match rhs.as_ref() {
        IrExpr::LValueToRValue { target, expr, .. } if is_exact_u32_ir_type(target) => expr.as_ref(),
        _ => {
            return Err(
                "run-once interior reborrow owner add RHS must be a direct readonly field read"
                    .to_string(),
            )
        }
    };
    let source_path = record_pointer_member_path_from_expr(source_expr)?.ok_or_else(|| {
        "run-once interior reborrow owner add RHS must be a readonly record field".to_string()
    })?;
    if source_path.root_name != source.name
        || source_path.fields.len() != 1
        || !record_pointer_types_match_ignoring_spelling(source_path.root_ty, &source.ty)
        || !is_exact_u32_ir_type(source_path.ty)
    {
        return Err("run-once interior reborrow readonly source field/type drifted".to_string());
    }
    Ok(())
}

fn is_direct_bool_var_read(expr: &IrExpr, name: &str, ty: &IrType) -> bool {
    let direct = match expr {
        IrExpr::LValueToRValue { target, expr, .. }
            if is_c_bool_type(target) && types_match_ignoring_spelling(target, ty) =>
        {
            expr.as_ref()
        }
        direct => direct,
    };
    matches!(direct, IrExpr::Var { name: actual, ty: actual_ty, .. }
        if actual == name && is_c_bool_type(actual_ty)
            && types_match_ignoring_spelling(actual_ty, ty))
}

fn validate_fixed_bool_return(
    stmt: &IrStmt,
    expected: bool,
    label: &str,
) -> Result<(), String> {
    let IrStmt::Return {
        value: Some(value), ..
    } = stmt
    else {
        return Err(format!("{label} must be a fixed bool return"));
    };
    if !is_fixed_bool(value, expected) {
        return Err(format!("{label} must return fixed bool {expected}"));
    }
    Ok(())
}

fn is_fixed_bool(expr: &IrExpr, expected: bool) -> bool {
    matches!(expr, IrExpr::LitInt { value, ty, .. }
        if *value == u64::from(expected) && is_c_bool_type(ty))
}

fn interior_reborrow_decl_parts(
    stmt: &IrStmt,
) -> Option<(&str, &IrType, &str, &IrType, &str, &IrType)> {
    let IrStmt::Decl {
        name,
        ty,
        init: Some(IrExpr::AddrOf { operand, ty: addr_ty, .. }),
        ..
    } = stmt
    else {
        return None;
    };
    if !record_pointer_types_match_ignoring_spelling(ty, addr_ty) {
        return None;
    }
    let IrExpr::Member {
        base,
        field,
        ty: field_ty,
        is_arrow: true,
        ..
    } = operand.as_ref()
    else {
        return None;
    };
    let IrExpr::Var {
        name: owner,
        ty: owner_ty,
        ..
    } = base.as_ref()
    else {
        return None;
    };
    Some((name, ty, owner, owner_ty, field, field_ty))
}

fn is_exact_u32_ir_type(ty: &IrType) -> bool {
    matches!(
        ty.kind,
        IrTypeKind::Integer {
            signed: false,
            width: 32
        }
    )
}

fn is_exact_u32_constant(expr: &IrExpr) -> bool {
    if !expr_type(expr).is_some_and(is_exact_u32_ir_type) || static_integer_value(expr).is_none() {
        return false;
    }
    match expr {
        IrExpr::LitInt { .. } => true,
        IrExpr::Cast {
            implicit: true,
            expr,
            ..
        } => matches!(expr.as_ref(), IrExpr::LitInt { .. }),
        _ => false,
    }
}
