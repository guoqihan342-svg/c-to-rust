#[derive(Default)]
struct MutablePointerIndexUses {
    read_params: HashSet<String>,
    invalid_params: HashSet<String>,
}

fn collect_readonly_mutable_pointer_index_params(
    body: &[IrStmt],
    params: &[IrParam],
    assigned_vars: &HashSet<String>,
    nullable_pointer_params: &HashSet<String>,
    mutable_pointer_write_params: &HashSet<String>,
    policy: &EmitPolicy,
) -> Result<HashSet<String>, String> {
    let candidates = params
        .iter()
        .filter(|param| {
            mutable_pointer_slice_element_type(&param.ty).is_some()
                && !assigned_vars.contains(&param.name)
                && !nullable_pointer_params.contains(&param.name)
                && !mutable_pointer_write_params.contains(&param.name)
        })
        .map(|param| (param.name.as_str(), &param.ty))
        .collect::<HashMap<_, _>>();
    if candidates.is_empty() {
        return Ok(HashSet::new());
    }

    let mut uses = MutablePointerIndexUses::default();
    collect_mutable_pointer_index_uses_from_body(body, &candidates, &mut uses)?;
    uses.read_params
        .retain(|name| !uses.invalid_params.contains(name));

    if !mutable_pointer_write_params.is_empty()
        && !uses.read_params.is_empty()
        && !readonly_mutable_pointer_noalias_proven(
            &uses.read_params,
            mutable_pointer_write_params,
            params,
            policy,
        )
    {
        return Err(
            "body-proven readonly mutable pointer index read with mutable pointer write requires noalias proof"
                .to_string(),
        );
    }
    Ok(uses.read_params)
}

fn collect_mutable_pointer_index_uses_from_body(
    body: &[IrStmt],
    candidates: &HashMap<&str, &IrType>,
    uses: &mut MutablePointerIndexUses,
) -> Result<(), String> {
    for stmt in body {
        match stmt {
            IrStmt::Decl { init, .. } => {
                if let Some(init) = init {
                    collect_mutable_pointer_index_uses_from_expr(init, candidates, uses, true)?;
                }
            }
            IrStmt::Assign { target, value, .. } => {
                collect_mutable_pointer_index_uses_from_expr(target, candidates, uses, false)?;
                collect_mutable_pointer_index_uses_from_expr(value, candidates, uses, true)?;
            }
            IrStmt::If {
                condition,
                then_body,
                else_body,
                ..
            } => {
                collect_mutable_pointer_index_uses_from_expr(condition, candidates, uses, true)?;
                collect_mutable_pointer_index_uses_from_body(then_body, candidates, uses)?;
                collect_mutable_pointer_index_uses_from_body(else_body, candidates, uses)?;
            }
            IrStmt::While {
                condition, body, ..
            } => {
                collect_mutable_pointer_index_uses_from_expr(condition, candidates, uses, true)?;
                collect_mutable_pointer_index_uses_from_body(body, candidates, uses)?;
            }
            IrStmt::DoWhile {
                body, condition, ..
            } => {
                collect_mutable_pointer_index_uses_from_body(body, candidates, uses)?;
                collect_mutable_pointer_index_uses_from_expr(condition, candidates, uses, true)?;
            }
            IrStmt::For {
                init,
                condition,
                step,
                body,
                ..
            } => {
                collect_mutable_pointer_index_uses_from_body(init, candidates, uses)?;
                if let Some(condition) = condition {
                    collect_mutable_pointer_index_uses_from_expr(
                        condition, candidates, uses, true,
                    )?;
                }
                if let Some(step) = step {
                    collect_mutable_pointer_index_uses_from_body(
                        std::slice::from_ref(step.as_ref()),
                        candidates,
                        uses,
                    )?;
                }
                collect_mutable_pointer_index_uses_from_body(body, candidates, uses)?;
            }
            IrStmt::Return { value, .. } => {
                if let Some(value) = value {
                    collect_mutable_pointer_index_uses_from_expr(value, candidates, uses, true)?;
                }
            }
            IrStmt::Expr { expr, .. } => {
                collect_mutable_pointer_index_uses_from_expr(expr, candidates, uses, true)?;
            }
            IrStmt::RecordMemset { .. } => {}
            IrStmt::Break { .. } | IrStmt::Continue { .. } | IrStmt::Unsupported { .. } => {}
        }
    }
    Ok(())
}

fn collect_mutable_pointer_index_uses_from_expr(
    expr: &IrExpr,
    candidates: &HashMap<&str, &IrType>,
    uses: &mut MutablePointerIndexUses,
    allow_index_read: bool,
) -> Result<(), String> {
    match expr {
        IrExpr::Var { name, ty, .. } => {
            if candidates
                .get(name.as_str())
                .is_some_and(|param_ty| *param_ty == ty)
            {
                uses.invalid_params.insert(name.clone());
            }
        }
        IrExpr::Index { base, index, .. } => {
            let direct_candidate = match base.as_ref() {
                IrExpr::Var { name, ty, .. }
                    if candidates
                        .get(name.as_str())
                        .is_some_and(|param_ty| *param_ty == ty) =>
                {
                    if allow_index_read {
                        uses.read_params.insert(name.clone());
                    } else {
                        uses.invalid_params.insert(name.clone());
                    }
                    true
                }
                _ => false,
            };
            if !direct_candidate {
                collect_mutable_pointer_index_uses_from_expr(base, candidates, uses, false)?;
            }
            collect_mutable_pointer_index_uses_from_expr(index, candidates, uses, true)?;
        }
        IrExpr::Binary { lhs, rhs, .. } => {
            collect_mutable_pointer_index_uses_from_expr(lhs, candidates, uses, true)?;
            collect_mutable_pointer_index_uses_from_expr(rhs, candidates, uses, true)?;
        }
        IrExpr::Unary { operand, .. }
        | IrExpr::Cast { expr: operand, .. }
        | IrExpr::LValueToRValue { expr: operand, .. } => {
            collect_mutable_pointer_index_uses_from_expr(
                operand,
                candidates,
                uses,
                allow_index_read,
            )?;
        }
        IrExpr::IncDec {
            target: operand, ..
        }
        | IrExpr::Deref { ptr: operand, .. }
        | IrExpr::AddrOf { operand, .. }
        | IrExpr::MutableVoidPointerAddress { operand, .. }
        | IrExpr::ArrayToPointerDecay { expr: operand, .. }
        | IrExpr::FunctionToPointerDecay { expr: operand, .. }
        | IrExpr::Member { base: operand, .. } => {
            collect_mutable_pointer_index_uses_from_expr(operand, candidates, uses, false)?;
        }
        IrExpr::Conditional {
            condition,
            then_expr,
            else_expr,
            ..
        } => {
            collect_mutable_pointer_index_uses_from_expr(condition, candidates, uses, true)?;
            collect_mutable_pointer_index_uses_from_expr(then_expr, candidates, uses, true)?;
            collect_mutable_pointer_index_uses_from_expr(else_expr, candidates, uses, true)?;
        }
        IrExpr::ArrayLiteral { elements, .. } => {
            for element in elements {
                collect_mutable_pointer_index_uses_from_expr(element, candidates, uses, true)?;
            }
        }
        IrExpr::Call { args, .. } => {
            for arg in args {
                collect_mutable_pointer_index_uses_from_expr(arg, candidates, uses, false)?;
            }
        }
        IrExpr::LitInt { .. } | IrExpr::NullPtr { .. } | IrExpr::Unsupported { .. } => {}
    }
    Ok(())
}

#[derive(Default)]
struct RecordPointerArrayIndexUses {
    indexed_params: HashSet<String>,
    read_params: HashSet<String>,
    invalid_params: HashSet<String>,
}

fn collect_readonly_record_pointer_array_index_params(
    body: &[IrStmt],
    params: &[IrParam],
    assigned_vars: &HashSet<String>,
    nullable_pointer_params: &HashSet<String>,
    mutable_pointer_write_params: &HashSet<String>,
    mutable_record_pointer_write_params: &HashSet<String>,
    policy: &EmitPolicy,
) -> Result<HashSet<String>, String> {
    let candidates = params
        .iter()
        .filter(|param| {
            record_pointer_pointee_type(&param.ty).is_some()
                && !assigned_vars.contains(&param.name)
                && !nullable_pointer_params.contains(&param.name)
        })
        .map(|param| (param.name.as_str(), &param.ty))
        .collect::<HashMap<_, _>>();
    if candidates.is_empty() {
        return Ok(HashSet::new());
    }

    let mut uses = RecordPointerArrayIndexUses::default();
    collect_record_pointer_array_index_uses_from_body(body, &candidates, &mut uses)?;
    if uses
        .indexed_params
        .iter()
        .any(|name| uses.invalid_params.contains(name))
    {
        return Err(
            "record pointer fixed array readonly index cannot be combined with a write or address/call escape"
                .to_string(),
        );
    }

    let mut write_params = mutable_pointer_write_params.clone();
    write_params.extend(mutable_record_pointer_write_params.iter().cloned());
    if !write_params.is_empty()
        && !uses.read_params.is_empty()
        && !readonly_mutable_pointer_noalias_proven(
            &uses.read_params,
            &write_params,
            params,
            policy,
        )
    {
        return Err(
            "readonly record pointer fixed array index read with mutable pointer write requires noalias proof"
                .to_string(),
        );
    }
    Ok(uses.read_params)
}

fn collect_record_pointer_array_index_uses_from_body(
    body: &[IrStmt],
    candidates: &HashMap<&str, &IrType>,
    uses: &mut RecordPointerArrayIndexUses,
) -> Result<(), String> {
    for stmt in body {
        match stmt {
            IrStmt::Decl { init, .. } => {
                if let Some(init) = init {
                    collect_record_pointer_array_index_uses_from_expr(
                        init, candidates, uses, true,
                    )?;
                }
            }
            IrStmt::Assign { target, value, .. } => {
                collect_record_pointer_array_index_uses_from_expr(target, candidates, uses, false)?;
                collect_record_pointer_array_index_uses_from_expr(value, candidates, uses, true)?;
            }
            IrStmt::If {
                condition,
                then_body,
                else_body,
                ..
            } => {
                collect_record_pointer_array_index_uses_from_expr(
                    condition, candidates, uses, true,
                )?;
                collect_record_pointer_array_index_uses_from_body(then_body, candidates, uses)?;
                collect_record_pointer_array_index_uses_from_body(else_body, candidates, uses)?;
            }
            IrStmt::While {
                condition, body, ..
            } => {
                collect_record_pointer_array_index_uses_from_expr(
                    condition, candidates, uses, true,
                )?;
                collect_record_pointer_array_index_uses_from_body(body, candidates, uses)?;
            }
            IrStmt::DoWhile {
                body, condition, ..
            } => {
                collect_record_pointer_array_index_uses_from_body(body, candidates, uses)?;
                collect_record_pointer_array_index_uses_from_expr(
                    condition, candidates, uses, true,
                )?;
            }
            IrStmt::For {
                init,
                condition,
                step,
                body,
                ..
            } => {
                collect_record_pointer_array_index_uses_from_body(init, candidates, uses)?;
                if let Some(condition) = condition {
                    collect_record_pointer_array_index_uses_from_expr(
                        condition, candidates, uses, true,
                    )?;
                }
                if let Some(step) = step {
                    collect_record_pointer_array_index_uses_from_body(
                        std::slice::from_ref(step.as_ref()),
                        candidates,
                        uses,
                    )?;
                }
                collect_record_pointer_array_index_uses_from_body(body, candidates, uses)?;
            }
            IrStmt::Return { value, .. } => {
                if let Some(value) = value {
                    collect_record_pointer_array_index_uses_from_expr(
                        value, candidates, uses, true,
                    )?;
                }
            }
            IrStmt::Expr { expr, .. } => {
                collect_record_pointer_array_index_uses_from_expr(expr, candidates, uses, true)?;
            }
            IrStmt::RecordMemset { .. } => {}
            IrStmt::Break { .. } | IrStmt::Continue { .. } | IrStmt::Unsupported { .. } => {}
        }
    }
    Ok(())
}

fn collect_record_pointer_array_index_uses_from_expr(
    expr: &IrExpr,
    candidates: &HashMap<&str, &IrType>,
    uses: &mut RecordPointerArrayIndexUses,
    allow_read: bool,
) -> Result<(), String> {
    match expr {
        IrExpr::Var { name, ty, .. } => {
            if candidates
                .get(name.as_str())
                .is_some_and(|param_ty| record_pointer_types_match_ignoring_spelling(param_ty, ty))
            {
                uses.invalid_params.insert(name.clone());
            }
        }
        IrExpr::Index {
            base, index, ty, ..
        } => {
            if let Some((name, element_ty)) =
                direct_record_pointer_fixed_array_member(base, candidates)?
            {
                uses.indexed_params.insert(name.clone());
                validate_side_effect_free_integer_index(index)?;
                let element_label = emit_scalar_type(element_ty)
                    .map_err(|detail| format!("record pointer array element has {detail}"))?;
                let result_label = emit_scalar_type(ty)
                    .map_err(|detail| format!("record pointer array index result has {detail}"))?;
                if element_label != result_label {
                    return Err(format!(
                        "record pointer array index result type {result_label} does not match element type {element_label}"
                    ));
                }
                if allow_read {
                    uses.read_params.insert(name);
                } else {
                    uses.invalid_params.insert(name);
                }
                return Ok(());
            }
            collect_record_pointer_array_index_uses_from_expr(base, candidates, uses, false)?;
            collect_record_pointer_array_index_uses_from_expr(index, candidates, uses, false)?;
        }
        IrExpr::Member { base, .. } => {
            if let Some((name, _)) = direct_record_pointer_fixed_array_member(expr, candidates)? {
                uses.indexed_params.insert(name.clone());
                uses.invalid_params.insert(name);
                return Ok(());
            }
            collect_record_pointer_array_index_uses_from_expr(base, candidates, uses, false)?;
        }
        IrExpr::Binary { lhs, rhs, .. } => {
            collect_record_pointer_array_index_uses_from_expr(lhs, candidates, uses, allow_read)?;
            collect_record_pointer_array_index_uses_from_expr(rhs, candidates, uses, allow_read)?;
        }
        IrExpr::Unary { operand, .. }
        | IrExpr::Cast { expr: operand, .. }
        | IrExpr::LValueToRValue { expr: operand, .. } => {
            collect_record_pointer_array_index_uses_from_expr(
                operand, candidates, uses, allow_read,
            )?;
        }
        IrExpr::IncDec {
            target: operand, ..
        }
        | IrExpr::Deref { ptr: operand, .. }
        | IrExpr::AddrOf { operand, .. }
        | IrExpr::MutableVoidPointerAddress { operand, .. }
        | IrExpr::ArrayToPointerDecay { expr: operand, .. }
        | IrExpr::FunctionToPointerDecay { expr: operand, .. } => {
            collect_record_pointer_array_index_uses_from_expr(operand, candidates, uses, false)?;
        }
        IrExpr::Conditional {
            condition,
            then_expr,
            else_expr,
            ..
        } => {
            collect_record_pointer_array_index_uses_from_expr(
                condition, candidates, uses, allow_read,
            )?;
            collect_record_pointer_array_index_uses_from_expr(
                then_expr, candidates, uses, allow_read,
            )?;
            collect_record_pointer_array_index_uses_from_expr(
                else_expr, candidates, uses, allow_read,
            )?;
        }
        IrExpr::ArrayLiteral { elements, .. } => {
            for element in elements {
                collect_record_pointer_array_index_uses_from_expr(
                    element, candidates, uses, allow_read,
                )?;
            }
        }
        IrExpr::Call { args, .. } => {
            for arg in args {
                collect_record_pointer_array_index_uses_from_expr(arg, candidates, uses, false)?;
            }
        }
        IrExpr::LitInt { .. } | IrExpr::NullPtr { .. } | IrExpr::Unsupported { .. } => {}
    }
    Ok(())
}

fn direct_record_pointer_fixed_array_member<'a>(
    expr: &'a IrExpr,
    candidates: &HashMap<&str, &IrType>,
) -> Result<Option<(String, &'a IrType)>, String> {
    let IrExpr::Member {
        base,
        field,
        ty,
        is_arrow: true,
        ..
    } = expr
    else {
        return Ok(None);
    };
    let IrExpr::Var {
        name, ty: root_ty, ..
    } = base.as_ref()
    else {
        return Ok(None);
    };
    if !candidates
        .get(name.as_str())
        .is_some_and(|param_ty| record_pointer_types_match_ignoring_spelling(param_ty, root_ty))
    {
        return Ok(None);
    }
    let IrTypeKind::Array { element, len } = &ty.kind else {
        return Ok(None);
    };
    if len.is_none() {
        return Err(format!(
            "record pointer array field {field} has unknown length"
        ));
    }
    if !is_integer_type(element) {
        return Err(format!(
            "record pointer array field {field} requires a scalar element, got {}",
            type_label(element)
        ));
    }
    Ok(Some((name.clone(), element.as_ref())))
}

fn validate_side_effect_free_integer_index(expr: &IrExpr) -> Result<(), String> {
    let ty = expr_type(expr)
        .ok_or_else(|| "record pointer array index type is unsupported".to_string())?;
    if !is_integer_type(ty) {
        return Err(format!(
            "record pointer array index requires an integer type, got {}",
            type_label(ty)
        ));
    }
    match expr {
        IrExpr::LitInt { .. } | IrExpr::Var { .. } => Ok(()),
        IrExpr::Binary { lhs, rhs, .. } => {
            validate_side_effect_free_integer_index(lhs)?;
            validate_side_effect_free_integer_index(rhs)
        }
        IrExpr::Unary { operand, .. }
        | IrExpr::Cast { expr: operand, .. }
        | IrExpr::LValueToRValue { expr: operand, .. } => {
            validate_side_effect_free_integer_index(operand)
        }
        IrExpr::Conditional {
            condition,
            then_expr,
            else_expr,
            ..
        } => {
            validate_side_effect_free_integer_index(condition)?;
            validate_side_effect_free_integer_index(then_expr)?;
            validate_side_effect_free_integer_index(else_expr)
        }
        IrExpr::NullPtr { .. }
        | IrExpr::ArrayToPointerDecay { .. }
        | IrExpr::FunctionToPointerDecay { .. }
        | IrExpr::Index { .. }
        | IrExpr::ArrayLiteral { .. }
        | IrExpr::Call { .. }
        | IrExpr::Member { .. }
        | IrExpr::IncDec { .. }
        | IrExpr::Deref { .. }
        | IrExpr::AddrOf { .. }
        | IrExpr::MutableVoidPointerAddress { .. }
        | IrExpr::Unsupported { .. } => Err(
            "record pointer array index must be a side-effect-free integer expression".to_string(),
        ),
    }
}
