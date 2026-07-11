fn validate_reborrow_result_branch(
    stmt: &IrStmt,
    plan: &InteriorReborrowPlan,
    db: &IrParam,
    call_path: &[String],
) -> Result<(), String> {
    let IrStmt::If {
        condition,
        then_body,
        else_body,
        ..
    } = stmt
    else {
        return Err("assignment-call interior reborrow assignment must be followed by if".to_string());
    };
    if !else_body.is_empty() {
        return Err("assignment-call interior reborrow if must not have else".to_string());
    }
    let IrExpr::Binary {
        op: IrBinOp::Eq,
        lhs,
        rhs,
        ..
    } = condition
    else {
        return Err("assignment-call interior reborrow if must use exact equality".to_string());
    };
    let lhs = match lhs.as_ref() {
        IrExpr::LValueToRValue { target, expr, .. } if is_exact_u32_ir_type(target) => expr.as_ref(),
        direct => direct,
    };
    let compare_path = exact_nested_alias_u32_path(lhs, plan, "comparison read")?;
    if compare_path.fields != call_path.iter().map(String::as_str).collect::<Vec<_>>() {
        return Err("assignment-call interior reborrow comparison path drifted".to_string());
    }
    if !is_exact_u32_constant(rhs) {
        return Err("assignment-call interior reborrow sentinel must be exact u32 constant".to_string());
    }
    let [reset, owner_add, continue_stmt] = then_body.as_slice() else {
        return Err("assignment-call interior reborrow hit body must be reset/add/continue".to_string());
    };
    validate_alias_write(reset, plan, true)?;
    let reset_path = match reset {
        IrStmt::Assign { target, .. } => exact_nested_alias_u32_path(target, plan, "reset target")?,
        _ => unreachable!(),
    };
    if reset_path.fields != compare_path.fields {
        return Err("assignment-call interior reborrow reset path drifted".to_string());
    }
    validate_owner_db_add(owner_add, plan, db)?;
    if !matches!(continue_stmt, IrStmt::Continue { .. }) {
        return Err("assignment-call interior reborrow hit body must end in continue".to_string());
    }
    Ok(())
}

fn exact_nested_alias_u32_path<'a>(
    expr: &'a IrExpr,
    plan: &InteriorReborrowPlan,
    label: &str,
) -> Result<RecordPointerMemberPath<'a>, String> {
    let path = record_pointer_member_path_from_expr(expr)?
        .ok_or_else(|| format!("assignment-call interior reborrow {label} must be a member path"))?;
    if path.root_name != plan.alias || path.fields.len() < 2 || !is_exact_u32_ir_type(path.ty) {
        return Err(format!(
            "assignment-call interior reborrow {label} must be nested exact-u32 alias path"
        ));
    }
    Ok(path)
}

fn validate_owner_db_add(
    stmt: &IrStmt,
    plan: &InteriorReborrowPlan,
    db: &IrParam,
) -> Result<(), String> {
    let IrStmt::Assign { target, value, .. } = stmt else {
        return Err("assignment-call interior reborrow requires owner wrapping add".to_string());
    };
    let target_path = record_pointer_member_path_from_expr(target)?
        .ok_or_else(|| "assignment-call interior reborrow owner target must be direct".to_string())?;
    let IrExpr::Binary {
        op: IrBinOp::Add,
        lhs,
        rhs,
        ty,
        ..
    } = value
    else {
        return Err("assignment-call interior reborrow owner update must preserve +=".to_string());
    };
    let lhs_path = record_pointer_member_path_from_expr(lhs)?
        .ok_or_else(|| "assignment-call interior reborrow add lhs must reread target".to_string())?;
    let rhs = match rhs.as_ref() {
        IrExpr::LValueToRValue { target, expr, .. } if is_exact_u32_ir_type(target) => expr.as_ref(),
        _ => return Err("assignment-call interior reborrow add RHS must read db field".to_string()),
    };
    let rhs_path = record_pointer_member_path_from_expr(rhs)?
        .ok_or_else(|| "assignment-call interior reborrow add RHS must be direct db field".to_string())?;
    if target_path.root_name != plan.owner
        || target_path.fields.len() != 1
        || lhs_path.root_name != target_path.root_name
        || lhs_path.fields != target_path.fields
        || rhs_path.root_name != db.name
        || rhs_path.fields.len() != 1
        || !record_pointer_types_match_ignoring_spelling(rhs_path.root_ty, &db.ty)
        || !is_exact_u32_ir_type(target_path.ty)
        || !is_exact_u32_ir_type(lhs_path.ty)
        || !is_exact_u32_ir_type(rhs_path.ty)
        || !is_exact_u32_ir_type(ty)
    {
        return Err("assignment-call interior reborrow owner/db add drifted".to_string());
    }
    Ok(())
}
