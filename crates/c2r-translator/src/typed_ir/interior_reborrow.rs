#[derive(Clone, Debug, Eq, PartialEq)]
struct InteriorReborrowPlan {
    alias: String,
    owner: String,
    owner_field: String,
}

fn analyze_interior_reborrow(
    function: &IrFunction,
) -> Result<HashMap<String, InteriorReborrowPlan>, String> {
    let candidates = function
        .body
        .iter()
        .filter(|stmt| interior_reborrow_decl_parts(stmt).is_some())
        .collect::<Vec<_>>();
    if candidates.is_empty() {
        return Ok(HashMap::new());
    }
    if candidates.len() != 1 {
        return Err("interior reborrow requires exactly one local alias declaration".to_string());
    }
    let [decl, write, observation] = function.body.as_slice() else {
        return Err(
            "interior reborrow requires one linear declaration, write, and owner observation"
                .to_string(),
        );
    };
    let (alias, alias_ty, owner, owner_ty, owner_field, field_ty) =
        interior_reborrow_decl_parts(decl).expect("candidate declaration");

    let pointer_params = function
        .params
        .iter()
        .filter(|param| matches!(param.ty.kind, IrTypeKind::Pointer { .. }))
        .collect::<Vec<_>>();
    if pointer_params.len() != 1 || pointer_params[0].name != owner {
        return Err("interior reborrow requires one direct owner pointer parameter".to_string());
    }
    if !record_pointer_types_match_ignoring_spelling(&pointer_params[0].ty, owner_ty) {
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

    let IrStmt::Assign { target, value, .. } = write else {
        return Err("interior reborrow alias must be used by one direct field write".to_string());
    };
    let write_path = record_pointer_member_path_from_expr(target)?
        .ok_or_else(|| "interior reborrow write must be a record member path".to_string())?;
    if write_path.root_name != alias || write_path.fields.len() < 2 {
        return Err(
            "interior reborrow write requires alias->nested.leaf with one arrow".to_string(),
        );
    }
    if !is_exact_u32_ir_type(write_path.ty) {
        return Err("interior reborrow write leaf must be an exact u32".to_string());
    }
    if !is_exact_u32_constant(value) {
        return Err(
            "interior reborrow write value must be a side-effect-free exact-u32 constant"
                .to_string(),
        );
    }

    let IrStmt::Return { value: Some(value), .. } = observation
    else {
        return Err("interior reborrow result must be observed through owner/current".to_string());
    };
    if !is_c_bool_type(&function.return_type) || !is_fixed_true_bool(value) {
        return Err("interior reborrow carrier must return fixed bool true".to_string());
    }

    let plan = InteriorReborrowPlan {
        alias: alias.to_string(),
        owner: owner.to_string(),
        owner_field: owner_field.to_string(),
    };
    Ok(HashMap::from([(plan.alias.clone(), plan)]))
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

fn complete_named_record_fields<'a>(
    ty: &'a IrType,
    label: &str,
) -> Result<&'a [IrRecordField], String> {
    let IrTypeKind::Record {
        name,
        fields: Some(fields),
    } = &ty.kind
    else {
        return Err(format!(
            "interior reborrow {label} requires a complete named record inventory"
        ));
    };
    emit_identifier(name, "interior reborrow record")?;
    let mut names = HashSet::new();
    if fields.is_empty() || fields.iter().any(|field| !names.insert(&field.name)) {
        return Err(format!(
            "interior reborrow {label} has an empty or conflicting field inventory"
        ));
    }
    Ok(fields)
}

fn unique_record_field<'a>(
    fields: &'a [IrRecordField],
    expected: &str,
    label: &str,
) -> Result<&'a IrRecordField, String> {
    let matches = fields
        .iter()
        .filter(|field| field.name == expected)
        .collect::<Vec<_>>();
    match matches.as_slice() {
        [field] => Ok(*field),
        _ => Err(format!(
            "interior reborrow {label} field {expected} is missing or conflicting"
        )),
    }
}

fn reject_qualified_reborrow_type(ty: &IrType, label: &str) -> Result<(), String> {
    let spellings = format!("{} {}", ty.spelled, ty.canonical).to_ascii_lowercase();
    if ty.is_const
        || spellings.split_whitespace().any(|part| part == "volatile")
        || spellings.contains("_atomic")
        || spellings.contains("atomic(")
    {
        return Err(format!(
            "interior reborrow {label} const/volatile/atomic qualification is unsupported"
        ));
    }
    Ok(())
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
    if !expr_type(expr).is_some_and(is_exact_u32_ir_type)
        || static_integer_value(expr).is_none()
    {
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

fn is_fixed_true_bool(expr: &IrExpr) -> bool {
    matches!(
        expr,
        IrExpr::LitInt { value: 1, ty, .. } if is_c_bool_type(ty)
    )
}

fn emit_interior_reborrow_decl(
    stmt: &IrStmt,
    indent_level: usize,
    symbols: &mut HashSet<String>,
    context: &EmitContext,
) -> Result<Option<String>, String> {
    let IrStmt::Decl { name, .. } = stmt else {
        return Ok(None);
    };
    let Some(plan) = context.interior_reborrow(name) else {
        return Ok(None);
    };
    if symbols.contains(name) || !symbols.contains(&plan.owner) {
        return Err("interior reborrow declaration has invalid symbol scope".to_string());
    }
    symbols.insert(name.clone());
    let alias = emit_identifier(name, "interior reborrow alias")?;
    let owner = emit_identifier(&plan.owner, "interior reborrow owner")?;
    let field = emit_identifier(&plan.owner_field, "interior reborrow field")?;
    Ok(Some(format!(
        "{}let {alias} = &mut {owner}.{field};\n",
        "    ".repeat(indent_level)
    )))
}

fn validate_interior_reborrow_definite_assignment(
    context: &EmitContext,
) -> Result<DefiniteAssignmentEvidence, String> {
    if context.interior_reborrows.len() != 1 {
        return Err("interior reborrow evidence requested without a plan".to_string());
    }
    Ok(DefiniteAssignmentEvidence {
        mutable_record_pointer_read_fields: HashSet::new(),
        mutable_pointer_read_slots: HashSet::new(),
    })
}
