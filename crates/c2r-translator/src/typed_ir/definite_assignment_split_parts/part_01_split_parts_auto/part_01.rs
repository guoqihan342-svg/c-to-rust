
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
