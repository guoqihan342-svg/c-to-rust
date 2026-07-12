/// Checks one statement against the emitter's conservative initialization model.
///
/// This pass is intentionally narrower than full C data-flow analysis. It only
/// carries facts that are definitely true on all non-returning paths, avoids
/// assuming loops execute, and treats mutable record-pointer fields as separate
/// facts so reads cannot be emitted before an observed write.
fn validate_definite_assignment_stmt(
    stmt: &IrStmt,
    state: &mut DefiniteAssignmentState,
) -> Result<(), String> {
    match stmt {
        IrStmt::Decl { name, init, .. } => {
            if let Some(plan) = state.interior_reborrows.get(name).cloned() {
                if interior_reborrow_decl_parts(stmt).is_none() {
                    return Err(format!("decl {name} interior reborrow shape drifted"));
                }
                state
                    .require_initialized(&plan.owner)
                    .map_err(|detail| format!("decl {name} owner {detail}"))?;
                return state.declare(name, true);
            }
            if let Some(init) = init {
                validate_definite_assignment_expr(init, state)
                    .map_err(|detail| format!("decl {name} initializer {detail}"))?;
            }
            state.declare(name, init.is_some())
        }
        IrStmt::Assign { target, value, .. } => {
            let mutable_pointer_target =
                mutable_pointer_slot_key_for_definite_assignment(target, state)?;
            let mutable_record_pointer_target =
                mutable_record_pointer_field_key_for_definite_assignment(target, state)?;
            let assigned_var = validate_definite_assignment_target(target, state)?;
            match &mutable_record_pointer_target {
                Some(target_key) => {
                    validate_definite_assignment_assign_value(target, value, state, target_key)
                        .map_err(|detail| format!("assign value {detail}"))?
                }
                None => validate_definite_assignment_expr(value, state)
                    .map_err(|detail| format!("assign value {detail}"))?,
            }
            if let Some(name) = assigned_var {
                state.assign(&name)?;
            }
            if let Some(key) = mutable_pointer_target {
                state.assign_mutable_pointer_slot(key);
            }
            if let Some(key) = mutable_record_pointer_target {
                state.assign_mutable_record_pointer_field(key);
            }
            Ok(())
        }
        IrStmt::Return { value, .. } => {
            if let Some(value) = value {
                validate_definite_assignment_expr(value, state)
                    .map_err(|detail| format!("return expr {detail}"))?;
            }
            Ok(())
        }
        IrStmt::Break { .. } | IrStmt::Continue { .. } => Ok(()),
        IrStmt::Expr { expr, .. } => validate_definite_assignment_expr(expr, state)
            .map_err(|detail| format!("expr {detail}")),
        IrStmt::RecordMemset { destination, .. } => {
            validate_definite_assignment_expr(destination, state)
                .map_err(|detail| format!("record memset destination {detail}"))?;
            let IrExpr::Var { name, ty, .. } = destination else {
                return Err("record memset destination must be a direct parameter".to_string());
            };
            let pointee = mutable_record_pointer_pointee_type(ty).ok_or_else(|| {
                "record memset destination must be a mutable record pointer".to_string()
            })?;
            mark_record_memset_fields_initialized(state, name, pointee, "")
        }
        IrStmt::If {
            condition,
            then_body,
            else_body,
            ..
        } => {
            validate_definite_assignment_expr(condition, state)
                .map_err(|detail| format!("if condition {detail}"))?;
            let before = state.clone();
            let mut then_state = before.clone();
            validate_definite_assignment_labeled_body(then_body, &mut then_state, "if then")?;
            let mut else_state = before.clone();
            validate_definite_assignment_labeled_body(else_body, &mut else_state, "if else")?;
            let then_returns = body_definitely_returns(then_body);
            let else_returns = body_definitely_returns(else_body);

            state.initialized = merge_definite_branch_set(
                &before.initialized,
                &then_state.initialized,
                then_returns,
                &else_state.initialized,
                else_returns,
            );
            state
                .initialized
                .retain(|name| before.declared.contains(name));
            state.mutable_record_pointer_fields = merge_definite_branch_set(
                &before.mutable_record_pointer_fields,
                &then_state.mutable_record_pointer_fields,
                then_returns,
                &else_state.mutable_record_pointer_fields,
                else_returns,
            );
            state.mutable_pointer_slots = merge_definite_branch_set(
                &before.mutable_pointer_slots,
                &then_state.mutable_pointer_slots,
                then_returns,
                &else_state.mutable_pointer_slots,
                else_returns,
            );
            state
                .validated_mutable_record_pointer_read_fields
                .extend(then_state.validated_mutable_record_pointer_read_fields);
            state
                .validated_mutable_record_pointer_read_fields
                .extend(else_state.validated_mutable_record_pointer_read_fields);
            state
                .validated_mutable_pointer_read_slots
                .extend(then_state.validated_mutable_pointer_read_slots);
            state
                .validated_mutable_pointer_read_slots
                .extend(else_state.validated_mutable_pointer_read_slots);
            Ok(())
        }
        IrStmt::While {
            condition, body, ..
        } => {
            validate_definite_assignment_expr(condition, state)
                .map_err(|detail| format!("while condition {detail}"))?;
            let mut body_state = state.clone();
            validate_definite_assignment_labeled_body(body, &mut body_state, "while body")?;
            state
                .validated_mutable_record_pointer_read_fields
                .extend(body_state.validated_mutable_record_pointer_read_fields);
            state
                .validated_mutable_pointer_read_slots
                .extend(body_state.validated_mutable_pointer_read_slots);
            Ok(())
        }
        IrStmt::DoWhile {
            body, condition, ..
        } => {
            let mut body_state = state.clone();
            validate_definite_assignment_labeled_body(body, &mut body_state, "do while body")?;
            validate_definite_assignment_expr(condition, &mut body_state)
                .map_err(|detail| format!("do while condition {detail}"))?;
            state
                .validated_mutable_record_pointer_read_fields
                .extend(body_state.validated_mutable_record_pointer_read_fields);
            state
                .validated_mutable_pointer_read_slots
                .extend(body_state.validated_mutable_pointer_read_slots);
            Ok(())
        }
        IrStmt::For {
            init,
            condition,
            step,
            body,
            ..
        } => {
            let mut loop_state = state.clone();
            for (index, init) in init.iter().enumerate() {
                validate_definite_assignment_stmt(init, &mut loop_state)
                    .map_err(|detail| format!("for init[{index}] {detail}"))?;
            }
            if let Some(condition) = condition {
                validate_definite_assignment_expr(condition, &mut loop_state)
                    .map_err(|detail| format!("for condition {detail}"))?;
            }
            let loop_reads = loop_state
                .validated_mutable_record_pointer_read_fields
                .clone();
            let loop_pointer_reads = loop_state.validated_mutable_pointer_read_slots.clone();
            let mut body_state = loop_state.clone();
            validate_definite_assignment_labeled_body(body, &mut body_state, "for body")?;
            state
                .validated_mutable_record_pointer_read_fields
                .extend(loop_reads);
            state
                .validated_mutable_pointer_read_slots
                .extend(loop_pointer_reads);
            state
                .validated_mutable_record_pointer_read_fields
                .extend(body_state.validated_mutable_record_pointer_read_fields);
            state
                .validated_mutable_pointer_read_slots
                .extend(body_state.validated_mutable_pointer_read_slots);
            if let Some(step) = step {
                let mut step_state = loop_state;
                validate_definite_assignment_stmt(step, &mut step_state)
                    .map_err(|detail| format!("for step {detail}"))?;
                state
                    .validated_mutable_record_pointer_read_fields
                    .extend(step_state.validated_mutable_record_pointer_read_fields);
                state
                    .validated_mutable_pointer_read_slots
                    .extend(step_state.validated_mutable_pointer_read_slots);
            }
            Ok(())
        }
        IrStmt::Unsupported { .. } => Ok(()),
    }
}

fn mark_record_memset_fields_initialized(
    state: &mut DefiniteAssignmentState,
    base: &str,
    record: &IrType,
    prefix: &str,
) -> Result<(), String> {
    let IrTypeKind::Record {
        fields: Some(fields),
        ..
    } = &record.kind
    else {
        return Err("record memset destination lacks complete field inventory".to_string());
    };
    for field in fields {
        let path = if prefix.is_empty() {
            field.name.clone()
        } else {
            format!("{prefix}.{}", field.name)
        };
        state.assign_mutable_record_pointer_field(MutableRecordPointerFieldKey {
            base: base.to_string(),
            field: path.clone(),
        });
        if matches!(field.ty.kind, IrTypeKind::Record { .. }) {
            mark_record_memset_fields_initialized(state, base, &field.ty, &path)?;
        }
    }
    Ok(())
}
