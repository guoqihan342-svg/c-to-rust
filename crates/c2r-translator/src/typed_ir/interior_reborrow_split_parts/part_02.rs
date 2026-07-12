fn collect_interior_reborrow_decls<'a>(body: &'a [IrStmt], found: &mut Vec<&'a IrStmt>) {
    for stmt in body {
        if interior_reborrow_decl_parts(stmt).is_some() {
            found.push(stmt);
        }
        match stmt {
            IrStmt::If {
                then_body,
                else_body,
                ..
            } => {
                collect_interior_reborrow_decls(then_body, found);
                collect_interior_reborrow_decls(else_body, found);
            }
            IrStmt::While { body, .. } | IrStmt::DoWhile { body, .. } => {
                collect_interior_reborrow_decls(body, found)
            }
            IrStmt::For {
                init, step, body, ..
            } => {
                collect_interior_reborrow_decls(init, found);
                if let Some(step) = step {
                    collect_interior_reborrow_decls(std::slice::from_ref(step.as_ref()), found);
                }
                collect_interior_reborrow_decls(body, found);
            }
            IrStmt::Decl { .. }
            | IrStmt::Assign { .. }
            | IrStmt::Return { .. }
            | IrStmt::Break { .. }
            | IrStmt::Continue { .. }
            | IrStmt::Expr { .. }
            | IrStmt::RecordMemset { .. }
            | IrStmt::Unsupported { .. } => {}
        }
    }
}

fn validate_bounded_alias_uses(
    body: &[IrStmt],
    plan: &InteriorReborrowPlan,
) -> Result<usize, String> {
    let mut writes = 0;
    validate_bounded_alias_use_list(body, plan, &mut writes)?;
    Ok(writes)
}

fn validate_bounded_alias_use_list(
    body: &[IrStmt],
    plan: &InteriorReborrowPlan,
    writes: &mut usize,
) -> Result<(), String> {
    for stmt in body {
        match stmt {
            IrStmt::Decl { name, init, .. } if name == &plan.alias => {
                if interior_reborrow_decl_parts(stmt).is_none() {
                    return Err("interior reborrow alias redeclaration is unsupported".to_string());
                }
            }
            IrStmt::Assign { target, value, .. } => {
                let alias_write = record_pointer_member_path_from_expr(target)?
                    .is_some_and(|path| path.root_name == plan.alias);
                if alias_write {
                    *writes += 1;
                    reject_alias_expr(value, plan)?;
                } else {
                    reject_alias_expr(target, plan)?;
                    reject_alias_expr(value, plan)?;
                }
            }
            IrStmt::If {
                condition,
                then_body,
                else_body,
                ..
            } => {
                reject_alias_expr(condition, plan)?;
                validate_bounded_alias_use_list(then_body, plan, writes)?;
                validate_bounded_alias_use_list(else_body, plan, writes)?;
            }
            IrStmt::While {
                condition, body, ..
            } => {
                reject_alias_expr(condition, plan)?;
                validate_bounded_alias_use_list(body, plan, writes)?;
            }
            IrStmt::DoWhile {
                body, condition, ..
            } => {
                validate_bounded_alias_use_list(body, plan, writes)?;
                reject_alias_expr(condition, plan)?;
            }
            IrStmt::For {
                init,
                condition,
                step,
                body,
                ..
            } => {
                validate_bounded_alias_use_list(init, plan, writes)?;
                if let Some(condition) = condition {
                    reject_alias_expr(condition, plan)?;
                }
                if let Some(step) = step {
                    validate_bounded_alias_use_list(
                        std::slice::from_ref(step.as_ref()),
                        plan,
                        writes,
                    )?;
                }
                validate_bounded_alias_use_list(body, plan, writes)?;
            }
            IrStmt::Decl { init, .. } => {
                if let Some(init) = init {
                    reject_alias_expr(init, plan)?;
                }
            }
            IrStmt::Return { value, .. } => {
                if let Some(value) = value {
                    reject_alias_expr(value, plan)?;
                }
            }
            IrStmt::Expr { expr, .. } => reject_alias_expr(expr, plan)?,
            IrStmt::RecordMemset { destination, .. } => reject_alias_expr(destination, plan)?,
            IrStmt::Break { .. }
            | IrStmt::Continue { .. }
            | IrStmt::Unsupported { .. } => {}
        }
    }
    Ok(())
}

fn reject_alias_expr(expr: &IrExpr, plan: &InteriorReborrowPlan) -> Result<(), String> {
    if expr_mentions_var(expr, &plan.alias) {
        Err("interior reborrow alias escape, rebind, store, or return is unsupported".to_string())
    } else {
        Ok(())
    }
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
    let fields = plan
        .owner_path
        .iter()
        .map(|field| emit_identifier(field, "interior reborrow field"))
        .collect::<Result<Vec<_>, _>>()?
        .join(".");
    Ok(Some(format!(
        "{}let {alias} = &mut {owner}.{fields};\n",
        "    ".repeat(indent_level)
    )))
}
