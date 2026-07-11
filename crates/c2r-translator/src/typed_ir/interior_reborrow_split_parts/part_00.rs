#[derive(Clone, Debug, Eq, PartialEq)]
struct InteriorReborrowPlan {
    alias: String,
    owner: String,
    owner_path: Vec<String>,
    call_root: Option<String>,
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
    };
    match function.body.as_slice() {
        [_, write, observation] => {
            if validate_bounded_alias_uses(&function.body, &plan)? != 1 {
                return Err(
                    "interior reborrow alias requires exactly one bounded field write".to_string(),
                );
            }
            validate_legacy_interior_reborrow_carrier(function, &plan, write, observation)?
        }
        [_, sentinel, loop_stmt, observation] => validate_run_once_interior_reborrow_carrier(
            function,
            policy,
            &plan,
            sentinel,
            loop_stmt,
            observation,
        )?,
        [_, setup, sentinel, loop_stmt, observation] => {
            plan.call_root = Some(validate_assignment_call_interior_reborrow_carrier(
                function,
                policy,
                &plan,
                setup,
                sentinel,
                loop_stmt,
                observation,
            )?);
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

fn validate_interior_reborrow_types(
    function: &IrFunction,
    alias_ty: &IrType,
    owner: &str,
    owner_ty: &IrType,
    owner_field: &str,
    field_ty: &IrType,
) -> Result<(), String> {
    let owner_param = function
        .params
        .iter()
        .find(|param| param.name == owner)
        .ok_or_else(|| "interior reborrow owner must be a direct parameter".to_string())?;
    if !record_pointer_types_match_ignoring_spelling(&owner_param.ty, owner_ty) {
        return Err("interior reborrow owner parameter type drifted".to_string());
    }
    let owner_record = mutable_record_pointer_pointee_type(owner_ty).ok_or_else(|| {
        "interior reborrow owner must be a non-const mutable record pointer".to_string()
    })?;
    let owner_fields = complete_named_record_fields(owner_record, "owner")?;
    let declared_field = unique_record_field(owner_fields, owner_field, "owner")?;
    if !types_match_ignoring_spelling(&declared_field.ty, field_ty) {
        return Err("interior reborrow owner field type conflicts with inventory".to_string());
    }
    let alias_pointee = mutable_record_pointer_pointee_type(alias_ty).ok_or_else(|| {
        "interior reborrow alias must be a mutable pointer to a named record".to_string()
    })?;
    complete_named_record_fields(alias_pointee, "alias pointee")?;
    if !types_match_ignoring_spelling(alias_pointee, field_ty) {
        return Err("interior reborrow typedef pointer pointee does not match owner field".to_string());
    }
    reject_qualified_reborrow_type(alias_ty, "alias")?;
    reject_qualified_reborrow_type(owner_ty, "owner")?;
    Ok(())
}

fn validate_legacy_interior_reborrow_carrier(
    function: &IrFunction,
    plan: &InteriorReborrowPlan,
    write: &IrStmt,
    observation: &IrStmt,
) -> Result<(), String> {
    let pointer_params = function
        .params
        .iter()
        .filter(|param| matches!(param.ty.kind, IrTypeKind::Pointer { .. }))
        .collect::<Vec<_>>();
    if pointer_params.len() != 1 || pointer_params[0].name != plan.owner {
        return Err("interior reborrow requires one direct owner pointer parameter".to_string());
    }
    validate_alias_write(write, plan, false)?;
    validate_fixed_bool_return(observation, true, "interior reborrow carrier")?;
    if !is_c_bool_type(&function.return_type) {
        return Err("interior reborrow carrier must return fixed bool true".to_string());
    }
    Ok(())
}

fn validate_run_once_interior_reborrow_carrier(
    function: &IrFunction,
    policy: &EmitPolicy,
    plan: &InteriorReborrowPlan,
    sentinel: &IrStmt,
    loop_stmt: &IrStmt,
    observation: &IrStmt,
) -> Result<(), String> {
    if !is_c_bool_type(&function.return_type) || function.params.len() != 2 {
        return Err(
            "run-once interior reborrow requires bool return and exactly owner/source parameters"
                .to_string(),
        );
    }
    if validate_bounded_alias_uses(&function.body, plan)? != 1 {
        return Err("interior reborrow alias requires exactly one bounded field write".to_string());
    }
    let source = function
        .params
        .iter()
        .find(|param| param.name != plan.owner)
        .ok_or_else(|| "run-once interior reborrow readonly source is missing".to_string())?;
    let source_record = readonly_record_pointer_pointee_type(&source.ty).ok_or_else(|| {
        "run-once interior reborrow source must be one readonly record pointer root".to_string()
    })?;
    complete_named_record_fields(source_record, "readonly source")?;
    reject_qualified_reborrow_type(&source.ty, "readonly source")?;
    if !explicit_noalias_pair(policy, &source.name, &plan.owner) {
        return Err(
            "run-once interior reborrow requires exact readonly-source to mutable-owner noalias proof"
                .to_string(),
        );
    }

    let IrStmt::Decl {
        name: sentinel_name,
        ty: sentinel_ty,
        init: Some(init),
        ..
    } = sentinel
    else {
        return Err("run-once interior reborrow requires an initialized bool sentinel".to_string());
    };
    if !is_c_bool_type(sentinel_ty) || !is_fixed_bool(init, true) {
        return Err("run-once interior reborrow sentinel must be exact bool true".to_string());
    }

    let IrStmt::While {
        condition, body, ..
    } = loop_stmt
    else {
        return Err("run-once interior reborrow requires one while sentinel".to_string());
    };
    if !is_direct_bool_var_read(condition, sentinel_name, sentinel_ty) {
        return Err(
            "run-once interior reborrow while condition must directly read its bool sentinel"
                .to_string(),
        );
    }
    let [clear, alias_write, owner_add, continue_stmt, unreachable_return] = body.as_slice()
    else {
        return Err(
            "run-once interior reborrow while body shape drifted from clear/write/add/continue/return"
                .to_string(),
        );
    };
    validate_bool_sentinel_clear(clear, sentinel_name, sentinel_ty)?;
    validate_alias_write(alias_write, plan, true)?;
    validate_owner_source_add(owner_add, plan, source)?;
    if !matches!(continue_stmt, IrStmt::Continue { .. }) {
        return Err(
            "run-once interior reborrow requires a current-level while continue".to_string(),
        );
    }
    validate_fixed_bool_return(
        unreachable_return,
        false,
        "run-once interior reborrow post-continue",
    )?;
    validate_fixed_bool_return(observation, true, "run-once interior reborrow final")
}
