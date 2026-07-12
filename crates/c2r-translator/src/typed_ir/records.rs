fn emit_record_definitions(
    function: &IrFunction,
    context: &EmitContext,
) -> Result<Vec<String>, String> {
    let mut records: Vec<(&str, Vec<RecordFieldUse<'_>>)> = Vec::new();
    add_record_type_inventory(&mut records, &function.return_type)?;
    for param in &function.params {
        if context.is_raw_direct_call_pointer_param(&param.name)
            && is_incomplete_record_pointer_type(&param.ty)
        {
            continue;
        }
        if let IrTypeKind::Record { name, .. } = &param.ty.kind {
            ensure_record_entry(&mut records, name);
        }
        if let Some(pointee) = readonly_record_pointer_pointee_type(&param.ty) {
            add_record_type_inventory(&mut records, pointee)?;
            if let IrTypeKind::Record { name, .. } = &pointee.kind {
                ensure_record_entry(&mut records, name);
            }
        }
        if let Some(pointee) = mutable_record_pointer_pointee_type(&param.ty) {
            add_record_type_inventory(&mut records, pointee)?;
            if let IrTypeKind::Record { name, .. } = &pointee.kind {
                ensure_record_entry(&mut records, name);
            }
        }
    }
    for stmt in &function.body {
        collect_record_field_uses_from_stmt(stmt, &mut records)?;
    }

    records
        .into_iter()
        .map(|(name, fields)| emit_record_definition(name, &fields))
        .collect()
}

fn ensure_record_entry<'a>(records: &mut Vec<(&'a str, Vec<RecordFieldUse<'a>>)>, name: &'a str) {
    if records.iter().any(|(record_name, _)| *record_name == name) {
        return;
    }
    records.push((name, Vec::new()));
}

fn add_record_type_inventory<'a>(
    records: &mut Vec<(&'a str, Vec<RecordFieldUse<'a>>)>,
    ty: &'a IrType,
) -> Result<(), String> {
    let IrTypeKind::Record {
        name,
        fields: Some(fields),
    } = &ty.kind
    else {
        return Ok(());
    };
    for field in fields {
        add_record_field_use(records, name, &field.name, &field.ty)?;
        add_record_type_inventory(records, &field.ty)?;
    }
    Ok(())
}

fn add_record_field_use<'a>(
    records: &mut Vec<(&'a str, Vec<RecordFieldUse<'a>>)>,
    record_name: &'a str,
    field_name: &'a str,
    field_ty: &'a IrType,
) -> Result<(), String> {
    ensure_record_entry(records, record_name);
    let Some((_, fields)) = records.iter_mut().find(|(name, _)| *name == record_name) else {
        return Err(format!("record {record_name} was not registered"));
    };
    if let Some(existing) = fields.iter().find(|field| field.name == field_name) {
        if record_field_types_match(existing.ty, field_ty) {
            return Ok(());
        }
        return Err(format!(
            "record {record_name} field {field_name} has inconsistent types {} and {}",
            type_label(existing.ty),
            type_label(field_ty)
        ));
    }
    fields.push(RecordFieldUse {
        name: field_name,
        ty: field_ty,
    });
    Ok(())
}

fn record_field_types_match(lhs: &IrType, rhs: &IrType) -> bool {
    lhs == rhs
        || types_match_ignoring_spelling(lhs, rhs)
        || (is_integer_type(lhs)
            && is_integer_type(rhs)
            && lhs.canonical == rhs.canonical
            && lhs.kind == rhs.kind
            && lhs.width_bits == rhs.width_bits)
}

fn emit_record_definition(name: &str, fields: &[RecordFieldUse<'_>]) -> Result<String, String> {
    if fields.is_empty() {
        return Err(format!("record {name} has no modeled fields"));
    }
    let rust_name = emit_record_type_name(name)?;
    let mut definition = String::new();
    definition.push_str("#[derive(Clone, Copy, Debug, Eq, PartialEq)]\n");
    definition.push_str(&format!("pub struct {rust_name} {{\n"));
    for field in fields {
        let field_name = emit_identifier(field.name, "record field")?;
        let field_ty = emit_record_field_type(field.ty)
            .map_err(|detail| format!("record {name} field {} has {detail}", field.name))?;
        definition.push_str(&format!("    pub {field_name}: {field_ty},\n"));
    }
    definition.push_str("}\n");
    Ok(definition)
}

fn collect_record_field_uses_from_stmt<'a>(
    stmt: &'a IrStmt,
    records: &mut Vec<(&'a str, Vec<RecordFieldUse<'a>>)>,
) -> Result<(), String> {
    match stmt {
        IrStmt::Decl { ty, init, .. } => {
            add_record_type_inventory(records, ty)?;
            if let Some(init) = init {
                collect_record_field_uses_from_expr(init, records)?;
            }
        }
        IrStmt::Assign { target, value, .. } => {
            collect_record_field_uses_from_expr(target, records)?;
            collect_record_field_uses_from_expr(value, records)?;
        }
        IrStmt::If {
            condition,
            then_body,
            else_body,
            ..
        } => {
            collect_record_field_uses_from_expr(condition, records)?;
            for stmt in then_body {
                collect_record_field_uses_from_stmt(stmt, records)?;
            }
            for stmt in else_body {
                collect_record_field_uses_from_stmt(stmt, records)?;
            }
        }
        IrStmt::While {
            condition, body, ..
        }
        | IrStmt::DoWhile {
            condition, body, ..
        } => {
            collect_record_field_uses_from_expr(condition, records)?;
            for stmt in body {
                collect_record_field_uses_from_stmt(stmt, records)?;
            }
        }
        IrStmt::For {
            init,
            condition,
            step,
            body,
            ..
        } => {
            for stmt in init {
                collect_record_field_uses_from_stmt(stmt, records)?;
            }
            if let Some(condition) = condition {
                collect_record_field_uses_from_expr(condition, records)?;
            }
            if let Some(step) = step {
                collect_record_field_uses_from_stmt(step, records)?;
            }
            for stmt in body {
                collect_record_field_uses_from_stmt(stmt, records)?;
            }
        }
        IrStmt::Return { value, .. } => {
            if let Some(value) = value {
                collect_record_field_uses_from_expr(value, records)?;
            }
        }
        IrStmt::Expr { expr, .. } => collect_record_field_uses_from_expr(expr, records)?,
        IrStmt::RecordMemset { destination, .. } => {
            collect_record_field_uses_from_expr(destination, records)?
        }
        IrStmt::Break { .. } | IrStmt::Continue { .. } | IrStmt::Unsupported { .. } => {}
    }
    Ok(())
}

fn collect_record_field_uses_from_expr<'a>(
    expr: &'a IrExpr,
    records: &mut Vec<(&'a str, Vec<RecordFieldUse<'a>>)>,
) -> Result<(), String> {
    match expr {
        IrExpr::Member {
            base,
            field,
            ty,
            is_arrow,
            ..
        } => {
            let base_ty = expr_type(base).ok_or_else(|| {
                "member expression base type is unsupported for record collection".to_string()
            })?;
            let record_ty = if *is_arrow {
                record_pointer_pointee_type(base_ty).ok_or_else(|| {
                    format!(
                        "arrow member expression base has unsupported type {}",
                        type_label(base_ty)
                    )
                })?
            } else {
                base_ty
            };
            let IrTypeKind::Record { name, .. } = &record_ty.kind else {
                return Err(format!(
                    "member expression base has unsupported type {}",
                    type_label(record_ty)
                ));
            };
            add_record_field_use(records, name, field, ty)?;
            collect_record_field_uses_from_expr(base, records)?;
        }
        IrExpr::Binary { lhs, rhs, .. } => {
            collect_record_field_uses_from_expr(lhs, records)?;
            collect_record_field_uses_from_expr(rhs, records)?;
        }
        IrExpr::Unary { operand, .. }
        | IrExpr::Cast { expr: operand, .. }
        | IrExpr::LValueToRValue { expr: operand, .. }
        | IrExpr::ArrayToPointerDecay { expr: operand, .. }
        | IrExpr::FunctionToPointerDecay { expr: operand, .. }
        | IrExpr::IncDec {
            target: operand, ..
        }
        | IrExpr::Deref { ptr: operand, .. }
        | IrExpr::AddrOf { operand, .. } => {
            collect_record_field_uses_from_expr(operand, records)?;
        }
        IrExpr::Conditional {
            condition,
            then_expr,
            else_expr,
            ..
        } => {
            collect_record_field_uses_from_expr(condition, records)?;
            collect_record_field_uses_from_expr(then_expr, records)?;
            collect_record_field_uses_from_expr(else_expr, records)?;
        }
        IrExpr::Index { base, index, .. } => {
            collect_record_field_uses_from_expr(base, records)?;
            collect_record_field_uses_from_expr(index, records)?;
        }
        IrExpr::ArrayLiteral { elements, .. } => {
            for element in elements {
                collect_record_field_uses_from_expr(element, records)?;
            }
        }
        IrExpr::Call { args, .. } => {
            for arg in args {
                collect_record_field_uses_from_expr(arg, records)?;
            }
        }
        IrExpr::LitInt { .. }
        | IrExpr::NullPtr { .. }
        | IrExpr::Var { .. }
        | IrExpr::Unsupported { .. } => {}
    }
    Ok(())
}
