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

fn validate_definite_assignment_target(
    target: &IrExpr,
    state: &mut DefiniteAssignmentState,
) -> Result<Option<String>, String> {
    match target {
        IrExpr::Var { name, ty, .. } if should_track_definite_assignment_type(ty) => {
            if !state.declared.contains(name) {
                return Err(format!("assign target {name} is not declared"));
            }
            Ok(Some(name.clone()))
        }
        IrExpr::Var { .. } => Ok(None),
        IrExpr::Index { base, index, .. } => {
            validate_definite_assignment_expr(base, state)
                .map_err(|detail| format!("assign index base {detail}"))?;
            validate_definite_assignment_expr(index, state)
                .map_err(|detail| format!("assign index operand {detail}"))?;
            Ok(None)
        }
        IrExpr::Deref { ptr, .. } => {
            validate_definite_assignment_expr(ptr, state)
                .map_err(|detail| format!("assign deref pointer {detail}"))?;
            Ok(None)
        }
        IrExpr::Member { base, .. } => {
            if let Some(path) = record_pointer_member_path_from_expr(target)? {
                if state
                    .mutable_record_pointer_write_params
                    .contains(path.root_name)
                {
                    state
                        .require_initialized(path.root_name)
                        .map_err(|detail| format!("assign member root {detail}"))?;
                    return Ok(None);
                }
            }
            validate_definite_assignment_expr(base, state)
                .map_err(|detail| format!("assign member base {detail}"))?;
            Ok(None)
        }
        _ => Err(
            "assign target must be Var, local fixed array Index, pointer Deref, or by-value record Member"
                .to_string(),
        ),
    }
}

fn validate_definite_assignment_assign_value(
    target: &IrExpr,
    value: &IrExpr,
    state: &mut DefiniteAssignmentState,
    target_key: &MutableRecordPointerFieldKey,
) -> Result<(), String> {
    if let Some(proof) = assignment_call_sibling_record_read(target, value)? {
        let IrExpr::Call { callee, args, .. } = value else {
            unreachable!("assignment-call sibling proof requires a direct call value");
        };
        if state.declared.contains(callee) {
            state
                .require_initialized(callee)
                .map_err(|detail| format!("call callee {detail}"))?;
        }
        for (index, arg) in args.iter().enumerate() {
            if index == proof.arg_index {
                state
                    .require_initialized(&proof.key.base)
                    .map_err(|detail| format!("call arg[{index}] member root {detail}"))?;
                state
                    .validated_mutable_record_pointer_read_fields
                    .insert(proof.key.clone());
            } else {
                validate_definite_assignment_expr(arg, state)
                    .map_err(|detail| format!("call arg[{index}] {detail}"))?;
            }
        }
        return Ok(());
    }
    if let IrExpr::Binary { lhs, rhs, .. } = value {
        if mutable_record_pointer_field_key_for_definite_assignment(lhs, state)?.as_ref()
            == Some(target_key)
        {
            return validate_definite_assignment_expr(rhs, state)
                .map_err(|detail| format!("binary rhs {detail}"));
        }
    }
    validate_definite_assignment_expr(value, state)
}

fn validate_definite_assignment_expr(
    expr: &IrExpr,
    state: &mut DefiniteAssignmentState,
) -> Result<(), String> {
    match expr {
        IrExpr::Var { name, ty, .. } if should_track_definite_assignment_type(ty) => {
            state.require_initialized(name)
        }
        IrExpr::Var { .. } => Ok(()),
        IrExpr::Binary { lhs, rhs, .. } => {
            validate_definite_assignment_expr(lhs, state)
                .map_err(|detail| format!("binary lhs {detail}"))?;
            validate_definite_assignment_expr(rhs, state)
                .map_err(|detail| format!("binary rhs {detail}"))
        }
        IrExpr::Unary { operand, .. } => validate_definite_assignment_expr(operand, state)
            .map_err(|detail| format!("unary operand {detail}")),
        IrExpr::Conditional {
            condition,
            then_expr,
            else_expr,
            ..
        } => {
            validate_definite_assignment_expr(condition, state)
                .map_err(|detail| format!("conditional condition {detail}"))?;
            validate_definite_assignment_expr(then_expr, state)
                .map_err(|detail| format!("conditional then {detail}"))?;
            validate_definite_assignment_expr(else_expr, state)
                .map_err(|detail| format!("conditional else {detail}"))
        }
        IrExpr::Cast { expr, .. } => validate_definite_assignment_expr(expr, state)
            .map_err(|detail| format!("cast expr {detail}")),
        IrExpr::LValueToRValue { expr, .. } => validate_definite_assignment_expr(expr, state)
            .map_err(|detail| format!("lvalue-to-rvalue expr {detail}")),
        IrExpr::ArrayToPointerDecay { expr, .. } => validate_definite_assignment_expr(expr, state)
            .map_err(|detail| format!("array-to-pointer decay expr {detail}")),
        IrExpr::FunctionToPointerDecay { expr, .. } => {
            validate_definite_assignment_expr(expr, state)
                .map_err(|detail| format!("function-to-pointer decay expr {detail}"))
        }
        IrExpr::Index { base, index, .. } => {
            validate_definite_assignment_expr(base, state)
                .map_err(|detail| format!("index base {detail}"))?;
            validate_definite_assignment_expr(index, state)
                .map_err(|detail| format!("index operand {detail}"))
        }
        IrExpr::Member { base, .. } => {
            if let Some(key) =
                mutable_record_pointer_field_key_for_definite_assignment(expr, state)?
            {
                state
                    .require_initialized(&key.base)
                    .map_err(|detail| format!("member root {detail}"))?;
                state.require_mutable_record_pointer_field_initialized(&key)?;
                return Ok(());
            }
            validate_definite_assignment_expr(base, state)
                .map_err(|detail| format!("member base {detail}"))?;
            Ok(())
        }
        IrExpr::ArrayLiteral { elements, .. } => {
            for (index, element) in elements.iter().enumerate() {
                validate_definite_assignment_expr(element, state)
                    .map_err(|detail| format!("array element[{index}] {detail}"))?;
            }
            Ok(())
        }
        IrExpr::Call { callee, args, .. } => {
            if state.declared.contains(callee) {
                state
                    .require_initialized(callee)
                    .map_err(|detail| format!("call callee {detail}"))?;
            }
            for (index, arg) in args.iter().enumerate() {
                validate_definite_assignment_expr(arg, state)
                    .map_err(|detail| format!("call arg[{index}] {detail}"))?;
            }
            Ok(())
        }
        IrExpr::IncDec { target, .. } => {
            if let Some(key) =
                mutable_record_pointer_field_key_for_definite_assignment(target, state)?
            {
                validate_definite_assignment_target(target, state)
                    .map_err(|detail| format!("inc/dec target {detail}"))?;
                state.assign_mutable_record_pointer_field(key);
                return Ok(());
            }
            validate_definite_assignment_expr(target, state)
                .map_err(|detail| format!("inc/dec target {detail}"))
        }
        IrExpr::Deref { ptr, .. } => {
            validate_definite_assignment_expr(ptr, state)
                .map_err(|detail| format!("deref pointer {detail}"))?;
            if let Some(key) = mutable_pointer_slot_key_for_definite_assignment(expr, state)? {
                state.require_mutable_pointer_slot_initialized(&key)?;
            }
            Ok(())
        }
        IrExpr::AddrOf { operand, .. } => validate_definite_assignment_expr(operand, state)
            .map_err(|detail| format!("address-of operand {detail}")),
        IrExpr::MutableVoidPointerAddress { operand, .. } => {
            validate_definite_assignment_target(operand, state)
                .map(|_| ())
                .map_err(|detail| format!("mutable void pointer address operand {detail}"))
        }
        IrExpr::LitInt { .. } | IrExpr::NullPtr { .. } | IrExpr::Unsupported { .. } => Ok(()),
    }
}

fn mutable_record_pointer_field_key_for_definite_assignment(
    expr: &IrExpr,
    state: &DefiniteAssignmentState,
) -> Result<Option<MutableRecordPointerFieldKey>, String> {
    let Some(path) = record_pointer_member_path_from_expr(expr)? else {
        return Ok(None);
    };
    if !state
        .mutable_record_pointer_write_params
        .contains(path.root_name)
    {
        return Ok(None);
    }
    let field_path = record_pointer_member_path_key(&path);
    mutable_record_pointer_pointee_type(path.root_ty).ok_or_else(|| {
        format!(
            "mutable record pointer field {}.{field_path} has unsupported base type {}",
            path.root_name,
            type_label(path.root_ty)
        )
    })?;
    emit_mutable_record_pointer_field_type(path.ty).map_err(|detail| {
        format!(
            "mutable record pointer field {}.{field_path} has {detail}",
            path.root_name
        )
    })?;
    let key = if let Some(plan) = state.interior_reborrows.get(path.root_name) {
        MutableRecordPointerFieldKey {
            base: plan.owner.clone(),
            field: format!("{}.{}", plan.owner_path.join("."), field_path),
        }
    } else {
        MutableRecordPointerFieldKey {
            base: path.root_name.to_string(),
            field: field_path,
        }
    };
    Ok(Some(key))
}

fn mutable_pointer_slot_key_for_definite_assignment(
    expr: &IrExpr,
    state: &DefiniteAssignmentState,
) -> Result<Option<MutablePointerSlotKey>, String> {
    let IrExpr::Deref { ptr, ty, .. } = expr else {
        return Ok(None);
    };
    let IrExpr::Var {
        name, ty: base_ty, ..
    } = ptr.as_ref()
    else {
        return Ok(None);
    };
    if !state.mutable_pointer_write_params.contains(name) {
        return Ok(None);
    }
    let element_ty = mutable_pointer_slice_element_type(base_ty).ok_or_else(|| {
        format!(
            "mutable pointer slot {name}[0] has unsupported base type {}",
            type_label(base_ty)
        )
    })?;
    let element = emit_scalar_type(element_ty)
        .map_err(|detail| format!("mutable pointer slot {name}[0] element has {detail}"))?;
    let result = emit_scalar_type(ty)
        .map_err(|detail| format!("mutable pointer slot {name}[0] result has {detail}"))?;
    if element != result {
        return Err(format!(
            "mutable pointer slot {name}[0] result type {result} does not match element type {element}"
        ));
    }
    Ok(Some(MutablePointerSlotKey { base: name.clone() }))
}

fn should_track_definite_assignment_type(ty: &IrType) -> bool {
    emit_scalar_type(ty).is_ok() || matches!(emit_function_pointer_param_type(ty), Ok(Some(_)))
}
