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
        return Err(
            "assignment-call interior reborrow tail requires one do-while".to_string(),
        );
    };
    let [call_assignment] = body.as_slice() else {
        return Err(
            "assignment-call interior reborrow do-while requires an empty C body and one normalized tail assignment"
                .to_string(),
        );
    };
    let call_path = validate_reborrow_call_assignment(
        call_assignment,
        plan,
        db,
        seed_local,
        seed_local_ty,
    )?;
    let IrExpr::Binary {
        op: IrBinOp::Neq,
        lhs,
        rhs,
        ..
    } = condition
    else {
        return Err(
            "assignment-call interior reborrow do-while tail must use exact inequality"
                .to_string(),
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
