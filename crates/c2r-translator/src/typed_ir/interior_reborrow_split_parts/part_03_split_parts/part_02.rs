fn validate_reborrow_do_while_tail_assignment_call(
    stmt: &IrStmt,
    plan: &InteriorReborrowPlan,
    db: &IrParam,
    seed_local: &str,
    seed_local_ty: &IrType,
) -> Result<(), String> {
    let IrStmt::DoWhile {
        body, condition, ..
    } = stmt
    else {
        return Err("assignment-call interior reborrow tail requires one do-while".to_string());
    };
    let (body_call, call_assignment) = match body.as_slice() {
        [call_assignment] => (None, call_assignment),
        [body_call, call_assignment] => (Some(body_call), call_assignment),
        _ => {
            return Err(
                "assignment-call interior reborrow do-while allows at most one direct-call C body statement before one normalized tail assignment"
                    .to_string(),
            )
        }
    };
    let call_path =
        validate_reborrow_call_assignment(call_assignment, plan, db, seed_local, seed_local_ty)?;
    if let Some(body_call) = body_call {
        let IrStmt::Assign { target, .. } = call_assignment else {
            return Err(
                "assignment-call interior reborrow do-while tail lost its normalized assignment"
                    .to_string(),
            );
        };
        let alias_root_ty = record_pointer_member_path_from_expr(target)?
            .ok_or_else(|| {
                "assignment-call interior reborrow do-while tail lost its alias target".to_string()
            })?
            .root_ty;
        validate_reborrow_do_while_body_call(body_call, plan, db, alias_root_ty)?;
    }
    let IrExpr::Binary {
        op: IrBinOp::Neq,
        lhs,
        rhs,
        ..
    } = condition
    else {
        return Err(
            "assignment-call interior reborrow do-while tail must use exact inequality".to_string(),
        );
    };
    let lhs = match lhs.as_ref() {
        IrExpr::LValueToRValue { target, expr, .. } if is_exact_u32_ir_type(target) => {
            expr.as_ref()
        }
        direct => direct,
    };
    let compare_path = exact_nested_alias_u32_path(lhs, plan, "do-while comparison read")?;
    if compare_path.fields != call_path.iter().map(String::as_str).collect::<Vec<_>>() {
        return Err(
            "assignment-call interior reborrow do-while comparison path drifted".to_string(),
        );
    }
    if !is_exact_u32_constant(rhs) {
        return Err(
            "assignment-call interior reborrow do-while sentinel must be an exact u32 constant"
                .to_string(),
        );
    }
    Ok(())
}

fn validate_reborrow_do_while_body_call(
    stmt: &IrStmt,
    plan: &InteriorReborrowPlan,
    db: &IrParam,
    alias_ty: &IrType,
) -> Result<(), String> {
    let IrStmt::Expr {
        expr: IrExpr::Call { callee, args, .. },
        ..
    } = stmt
    else {
        return Err(
            "assignment-call interior reborrow do-while C body must be one direct call expression"
                .to_string(),
        );
    };
    emit_identifier(
        callee,
        "assignment-call interior reborrow do-while body callee",
    )?;
    let [db_arg, alias_arg] = args.as_slice() else {
        return Err(
            "assignment-call interior reborrow do-while body call requires exact call-root/same-alias arguments"
                .to_string(),
        );
    };
    validate_exact_pointer_var_arg(db_arg, &db.name, &db.ty, "do-while body call root")?;
    validate_exact_pointer_var_arg(alias_arg, &plan.alias, alias_ty, "do-while body same-alias")
}
