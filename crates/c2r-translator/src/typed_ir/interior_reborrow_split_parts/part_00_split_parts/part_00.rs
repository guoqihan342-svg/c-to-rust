#[derive(Clone, Debug, Eq, PartialEq)]
struct InteriorReborrowPlan {
    alias: String,
    owner: String,
    owner_path: Vec<String>,
    call_root: Option<String>,
    entry_initialized_field_path: Option<Vec<String>>,
    allows_owner_sibling_size_add_read: bool,
}

fn analyze_interior_reborrow(
    function: &IrFunction,
    policy: &EmitPolicy,
) -> Result<HashMap<String, InteriorReborrowPlan>, String> {
    let mut candidates = Vec::new();
    collect_interior_reborrow_decls(&function.body, &mut candidates);
    if candidates.is_empty() {
        return Ok(HashMap::new());
    }
    if candidates.len() != 1 {
        return Err("interior reborrow requires exactly one local alias declaration".to_string());
    }
    let decl = function.body.first().ok_or_else(|| {
        "interior reborrow alias declaration must be the first top-level statement".to_string()
    })?;
    if !std::ptr::eq(candidates[0], decl) {
        return Err(
            "interior reborrow alias declaration must be the first top-level statement"
                .to_string(),
        );
    }
    let (alias, alias_ty, owner, owner_ty, owner_field, field_ty) =
        interior_reborrow_decl_parts(decl).expect("candidate declaration");
    validate_interior_reborrow_types(function, alias_ty, owner, owner_ty, owner_field, field_ty)?;

    let mut plan = InteriorReborrowPlan {
        alias: alias.to_string(),
        owner: owner.to_string(),
        owner_path: vec![owner_field.to_string()],
        call_root: None,
        entry_initialized_field_path: None,
        allows_owner_sibling_size_add_read: false,
    };
    match function.body.as_slice() {
        [_, owner_add] => {
            validate_owner_sibling_size_add_from_alias(function, policy, &plan, owner_add)?;
            validate_owner_sibling_size_add_carrier(function, None)?;
            plan.allows_owner_sibling_size_add_read = true;
        }
        [_, write, observation] => {
            if matches!(write, IrStmt::If { .. }) {
                validate_guarded_owner_stats_sequence_carrier(
                    function,
                    policy,
                    &plan,
                    write,
                    observation,
                )?;
                plan.allows_owner_sibling_size_add_read = true;
            } else if is_owner_sibling_size_add_stmt(write, &plan)? {
                validate_owner_sibling_size_add_from_alias(function, policy, &plan, write)?;
                validate_owner_sibling_size_add_carrier(function, Some(observation))?;
                plan.allows_owner_sibling_size_add_read = true;
            } else {
                if validate_bounded_alias_uses(&function.body, &plan)? != 1 {
                    return Err(
                        "interior reborrow alias requires exactly one bounded field write"
                            .to_string(),
                    );
                }
                validate_legacy_interior_reborrow_carrier(function, &plan, write, observation)?
            }
        }
        [_, sentinel, loop_stmt, observation] => validate_run_once_interior_reborrow_carrier(
            function,
            policy,
            &plan,
            sentinel,
            loop_stmt,
            observation,
        )?,
        [_, first, second, third, fourth] => {
            if is_direct_owner_u32_increment_stmt(first, &plan)? {
                validate_owner_stats_sequence_carrier(
                    function, policy, &plan, first, second, third, fourth,
                )?;
                plan.allows_owner_sibling_size_add_read = true;
            } else {
                let (call_root, entry_initialized_field_path) =
                    validate_assignment_call_interior_reborrow_carrier(
                        function, policy, &plan, first, second, third, fourth,
                    )?;
                plan.call_root = Some(call_root);
                plan.entry_initialized_field_path = entry_initialized_field_path;
            }
        }
        _ => {
            return Err(
                "interior reborrow requires a bounded linear or bool run-once carrier"
                    .to_string(),
            )
        }
    }

    Ok(HashMap::from([(plan.alias.clone(), plan)]))
}

fn is_owner_sibling_size_add_stmt(
    stmt: &IrStmt,
    plan: &InteriorReborrowPlan,
) -> Result<bool, String> {
    let IrStmt::Assign { target, .. } = stmt else {
        return Ok(false);
    };
    Ok(record_pointer_member_path_from_expr(target)?
        .is_some_and(|path| path.root_name == plan.owner && path.fields.len() == 1))
}

fn is_direct_owner_u32_increment_stmt(
    stmt: &IrStmt,
    plan: &InteriorReborrowPlan,
) -> Result<bool, String> {
    let IrStmt::Assign { target, .. } = stmt else {
        return Ok(false);
    };
    Ok(
        record_pointer_member_path_from_expr(target)?.is_some_and(|path| {
            path.root_name == plan.owner && path.fields.len() == 1 && is_exact_u32_ir_type(path.ty)
        }),
    )
}

fn validate_owner_stats_sequence_carrier(
    function: &IrFunction,
    policy: &EmitPolicy,
    plan: &InteriorReborrowPlan,
    increment: &IrStmt,
    first_add: &IrStmt,
    second_add: &IrStmt,
    terminal: &IrStmt,
) -> Result<(), String> {
    if function.params.len() != 1 || function.params[0].name != plan.owner {
        return Err(
            "interior reborrow stats sequence requires exactly one mutable owner pointer root"
                .to_string(),
        );
    }
    if !is_c_bool_type(&function.return_type) {
        return Err("interior reborrow stats sequence requires bool return".to_string());
    }
    validate_fixed_bool_return(terminal, true, "interior reborrow stats sequence terminal")?;

    let counter = validate_direct_owner_u32_increment(function, plan, increment)?;
    let (first_target, first_source) =
        validate_owner_sibling_size_add_from_alias(function, policy, plan, first_add)?;
    let (second_target, second_source) =
        validate_owner_sibling_size_add_from_alias(function, policy, plan, second_add)?;
    let projection = plan
        .owner_path
        .first()
        .ok_or_else(|| "interior reborrow stats sequence projection is missing".to_string())?;

    let owner_paths = [
        counter.as_str(),
        first_target.as_str(),
        second_target.as_str(),
        projection.as_str(),
    ];
    if owner_paths
        .iter()
        .enumerate()
        .any(|(index, path)| owner_paths[index + 1..].contains(path))
    {
        return Err(
            "interior reborrow stats sequence counter, targets, and projection must not overlap"
                .to_string(),
        );
    }
    if first_source == second_source {
        return Err("interior reborrow stats sequence alias sources must be distinct".to_string());
    }
    Ok(())
}

fn validate_guarded_owner_stats_sequence_carrier(
    function: &IrFunction,
    policy: &EmitPolicy,
    plan: &InteriorReborrowPlan,
    guarded: &IrStmt,
    terminal: &IrStmt,
) -> Result<(), String> {
    let IrStmt::If {
        condition,
        then_body,
        else_body,
        ..
    } = guarded
    else {
        return Err("guarded interior stats sequence requires one if statement".to_string());
    };
    if !else_body.is_empty() {
        return Err("guarded interior stats sequence must not have an else branch".to_string());
    }
    let [increment, first_add, second_add, success_return] = then_body.as_slice() else {
        return Err(
            "guarded interior stats sequence body must contain exactly increment/add/add/true return"
                .to_string(),
        );
    };
    validate_ordered_interior_stats_guard(function, plan, condition)?;
    validate_owner_stats_sequence_carrier(
        function,
        policy,
        plan,
        increment,
        first_add,
        second_add,
        success_return,
    )?;
    validate_fixed_bool_return(
        terminal,
        false,
        "guarded interior stats sequence false-path terminal",
    )
}

fn validate_ordered_interior_stats_guard(
    function: &IrFunction,
    plan: &InteriorReborrowPlan,
    condition: &IrExpr,
) -> Result<(), String> {
    let IrExpr::Binary {
        op: IrBinOp::LogAnd,
        lhs: first,
        rhs: second,
        ty,
        ..
    } = condition
    else {
        return Err(
            "guarded interior stats sequence requires two ordered equalities joined by &&"
                .to_string(),
        );
    };
    if !is_c_int_type(ty) {
        return Err("guarded interior stats sequence && result must be C int".to_string());
    }
    let first_field = validate_guard_c_int_equality(function, plan, first)?;
    let second_field = validate_guard_bool_equality(function, plan, second)?;
    if first_field == second_field {
        return Err(
            "guarded interior stats sequence comparison fields must be distinct".to_string(),
        );
    }
    Ok(())
}

fn validate_guard_c_int_equality(
    function: &IrFunction,
    plan: &InteriorReborrowPlan,
    comparison: &IrExpr,
) -> Result<String, String> {
    let IrExpr::Binary {
        op: IrBinOp::Eq,
        lhs,
        rhs,
        ty,
        ..
    } = comparison
    else {
        return Err(
            "guarded interior stats sequence first comparison must be exact equality".to_string(),
        );
    };
    if !is_c_int_type(ty) {
        return Err(
            "guarded interior stats sequence first equality result must be C int".to_string(),
        );
    }
    let IrExpr::LValueToRValue {
        target: read_ty,
        expr: read,
        ..
    } = lhs.as_ref()
    else {
        return Err(
            "guarded interior stats sequence first equality must directly read alias C int"
                .to_string(),
        );
    };
    let literal_matches = matches!(
        rhs.as_ref(),
        IrExpr::LitInt { ty, .. } if is_c_int_type(read_ty) && is_c_int_type(ty)
    ) || (is_exact_u32_ir_type(read_ty)
        && is_exact_u32_constant(rhs)
        && static_integer_value(rhs).is_some_and(|value| u32::try_from(value).is_ok()));
    if !literal_matches {
        return Err(
            "guarded interior stats sequence first equality must compare C int or u32 with a losslessly converted non-negative literal"
                .to_string(),
        );
    }
    validate_direct_guard_alias_field(function, plan, read, read_ty, "first equality")
}

fn validate_guard_bool_equality(
    function: &IrFunction,
    plan: &InteriorReborrowPlan,
    comparison: &IrExpr,
) -> Result<String, String> {
    let IrExpr::Binary {
        op: IrBinOp::Eq,
        lhs,
        rhs,
        ty,
        ..
    } = comparison
    else {
        return Err(
            "guarded interior stats sequence second comparison must be exact equality".to_string(),
        );
    };
    if !is_c_int_type(ty) {
        return Err(
            "guarded interior stats sequence second equality result must be C int".to_string(),
        );
    }
    let IrExpr::Cast {
        target: promoted_ty,
        expr: promoted,
        implicit: true,
        ..
    } = lhs.as_ref()
    else {
        return Err(
            "guarded interior stats sequence second equality must promote one alias bool read"
                .to_string(),
        );
    };
    let IrExpr::LValueToRValue {
        target: read_ty,
        expr: read,
        ..
    } = promoted.as_ref()
    else {
        return Err(
            "guarded interior stats sequence second equality must directly read alias bool"
                .to_string(),
        );
    };
    if !is_c_int_type(promoted_ty)
        || !is_c_bool_type(read_ty)
        || !matches!(rhs.as_ref(), IrExpr::LitInt { value: 1, ty, .. } if is_c_int_type(ty))
    {
        return Err(
            "guarded interior stats sequence second equality must compare promoted bool with true"
                .to_string(),
        );
    }
    validate_direct_guard_alias_field(function, plan, read, read_ty, "second equality")
}

fn validate_direct_guard_alias_field(
    function: &IrFunction,
    plan: &InteriorReborrowPlan,
    read: &IrExpr,
    read_ty: &IrType,
    label: &str,
) -> Result<String, String> {
    let path = record_pointer_member_path_from_expr(read)?.ok_or_else(|| {
        format!("guarded interior stats sequence {label} must read one alias field")
    })?;
    if path.root_name != plan.alias
        || path.fields.len() != 1
        || !types_match_ignoring_spelling(path.ty, read_ty)
    {
        return Err(format!(
            "guarded interior stats sequence {label} alias projection/type drifted"
        ));
    }
    let (_, alias_ty, _, _, _, _) = interior_reborrow_decl_parts(&function.body[0])
        .ok_or_else(|| "guarded interior stats sequence alias declaration drifted".to_string())?;
    if !record_pointer_types_match_ignoring_spelling(path.root_ty, alias_ty) {
        return Err(format!(
            "guarded interior stats sequence {label} alias root type drifted"
        ));
    }
    let alias_record = mutable_record_pointer_pointee_type(alias_ty)
        .ok_or_else(|| "guarded interior stats sequence alias must remain mutable".to_string())?;
    let alias_fields = complete_named_record_fields(alias_record, "guard alias")?;
    let declared = unique_record_field(alias_fields, path.fields[0], label)?;
    if !types_match_ignoring_spelling(&declared.ty, path.ty) {
        return Err(format!(
            "guarded interior stats sequence {label} inventory type drifted"
        ));
    }
    reject_qualified_reborrow_type(path.ty, label)?;
    Ok(path.fields[0].to_string())
}
