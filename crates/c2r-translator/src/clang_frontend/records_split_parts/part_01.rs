#[cfg(feature = "typed-ir")]
pub(super) fn attach_record_inventory_to_function(
    function: &mut IrFunction,
    inventory: &BTreeMap<String, Vec<IrRecordField>>,
) {
    attach_record_inventory_to_type(&mut function.return_type, inventory);
    for param in &mut function.params {
        attach_record_inventory_to_type(&mut param.ty, inventory);
    }
    for stmt in &mut function.body {
        attach_record_inventory_to_stmt(stmt, inventory);
    }
}

#[cfg(feature = "typed-ir")]
/// Recursively attaches discovered record fields to statement-local IR types.
///
/// Clang skeleton lowering may initially carry only a record name; this pass
/// enriches matching types from the translation-unit inventory before emission.
/// It does not infer missing layouts, so absent inventory remains a later
/// fail-closed type or member-access error.
fn attach_record_inventory_to_stmt(
    stmt: &mut IrStmt,
    inventory: &BTreeMap<String, Vec<IrRecordField>>,
) {
    match stmt {
        IrStmt::Decl { ty, init, .. } => {
            attach_record_inventory_to_type(ty, inventory);
            if let Some(init) = init {
                attach_record_inventory_to_expr(init, inventory);
            }
        }
        IrStmt::Assign { target, value, .. } => {
            attach_record_inventory_to_expr(target, inventory);
            attach_record_inventory_to_expr(value, inventory);
        }
        IrStmt::If {
            condition,
            then_body,
            else_body,
            ..
        } => {
            attach_record_inventory_to_expr(condition, inventory);
            for stmt in then_body {
                attach_record_inventory_to_stmt(stmt, inventory);
            }
            for stmt in else_body {
                attach_record_inventory_to_stmt(stmt, inventory);
            }
        }
        IrStmt::While {
            condition, body, ..
        }
        | IrStmt::DoWhile {
            condition, body, ..
        } => {
            attach_record_inventory_to_expr(condition, inventory);
            for stmt in body {
                attach_record_inventory_to_stmt(stmt, inventory);
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
                attach_record_inventory_to_stmt(stmt, inventory);
            }
            if let Some(condition) = condition {
                attach_record_inventory_to_expr(condition, inventory);
            }
            if let Some(step) = step {
                attach_record_inventory_to_stmt(step, inventory);
            }
            for stmt in body {
                attach_record_inventory_to_stmt(stmt, inventory);
            }
        }
        IrStmt::Return { value, .. } => {
            if let Some(value) = value {
                attach_record_inventory_to_expr(value, inventory);
            }
        }
        IrStmt::Expr { expr, .. } => attach_record_inventory_to_expr(expr, inventory),
        IrStmt::RecordMemset { destination, .. } => {
            attach_record_inventory_to_expr(destination, inventory)
        }
        IrStmt::Break { .. } | IrStmt::Continue { .. } | IrStmt::Unsupported { .. } => {}
    }
}

#[cfg(feature = "typed-ir")]
fn attach_record_inventory_to_expr(
    expr: &mut IrExpr,
    inventory: &BTreeMap<String, Vec<IrRecordField>>,
) {
    match expr {
        IrExpr::LitInt { ty, .. }
        | IrExpr::NullPtr { ty, .. }
        | IrExpr::Var { ty, .. }
        | IrExpr::Binary { ty, .. }
        | IrExpr::Unary { ty, .. }
        | IrExpr::Conditional { ty, .. }
        | IrExpr::Index { ty, .. }
        | IrExpr::ArrayLiteral { ty, .. }
        | IrExpr::Call { ty, .. }
        | IrExpr::Member { ty, .. }
        | IrExpr::IncDec { ty, .. }
        | IrExpr::Deref { ty, .. }
        | IrExpr::AddrOf { ty, .. } => attach_record_inventory_to_type(ty, inventory),
        IrExpr::MutableVoidPointerAddress {
            source_pointer,
            target,
            ..
        } => {
            attach_record_inventory_to_type(source_pointer, inventory);
            attach_record_inventory_to_type(target, inventory);
        }
        IrExpr::Cast { target, .. }
        | IrExpr::LValueToRValue { target, .. }
        | IrExpr::ArrayToPointerDecay { target, .. }
        | IrExpr::FunctionToPointerDecay { target, .. } => {
            attach_record_inventory_to_type(target, inventory)
        }
        IrExpr::Unsupported { .. } => {}
    }

    match expr {
        IrExpr::Binary { lhs, rhs, .. } => {
            attach_record_inventory_to_expr(lhs, inventory);
            attach_record_inventory_to_expr(rhs, inventory);
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
        | IrExpr::AddrOf { operand, .. }
        | IrExpr::MutableVoidPointerAddress { operand, .. } => {
            attach_record_inventory_to_expr(operand, inventory)
        }
        IrExpr::Conditional {
            condition,
            then_expr,
            else_expr,
            ..
        } => {
            attach_record_inventory_to_expr(condition, inventory);
            attach_record_inventory_to_expr(then_expr, inventory);
            attach_record_inventory_to_expr(else_expr, inventory);
        }
        IrExpr::Index { base, index, .. } => {
            attach_record_inventory_to_expr(base, inventory);
            attach_record_inventory_to_expr(index, inventory);
        }
        IrExpr::ArrayLiteral { elements, .. } => {
            for element in elements {
                attach_record_inventory_to_expr(element, inventory);
            }
        }
        IrExpr::Call { args, .. } => {
            for arg in args {
                attach_record_inventory_to_expr(arg, inventory);
            }
        }
        IrExpr::Member { base, .. } => attach_record_inventory_to_expr(base, inventory),
        IrExpr::LitInt { .. }
        | IrExpr::NullPtr { .. }
        | IrExpr::Var { .. }
        | IrExpr::Unsupported { .. } => {}
    }
}

#[cfg(feature = "typed-ir")]
fn attach_record_inventory_to_type(
    ty: &mut IrType,
    inventory: &BTreeMap<String, Vec<IrRecordField>>,
) {
    match &mut ty.kind {
        IrTypeKind::Pointer { pointee } => attach_record_inventory_to_type(pointee, inventory),
        IrTypeKind::Array { element, .. } => attach_record_inventory_to_type(element, inventory),
        IrTypeKind::Record { name, fields } => {
            if fields.is_none() {
                if let Some(record_fields) = inventory.get(name) {
                    *fields = Some(record_fields.clone());
                }
            }
        }
        IrTypeKind::Void
        | IrTypeKind::Integer { .. }
        | IrTypeKind::Function
        | IrTypeKind::Unsupported { .. } => {}
    }
}
