fn collect_assigned_vars(body: &[IrStmt]) -> HashSet<String> {
    let mut assigned_vars = HashSet::new();
    collect_assigned_vars_from_body(body, &mut assigned_vars);
    collect_nested_local_record_assigned_vars(body, &mut assigned_vars);
    collect_address_taken_vars_from_body(body, &mut assigned_vars);
    assigned_vars
}

fn collect_address_taken_vars_from_body(body: &[IrStmt], vars: &mut HashSet<String>) {
    for stmt in body {
        collect_address_taken_vars_from_stmt(stmt, vars);
    }
}

fn collect_address_taken_vars_from_stmt(stmt: &IrStmt, vars: &mut HashSet<String>) {
    match stmt {
        IrStmt::Decl { init, .. } => {
            if let Some(init) = init {
                collect_address_taken_vars_from_expr(init, vars);
            }
        }
        IrStmt::Assign { target, value, .. } => {
            collect_address_taken_vars_from_expr(target, vars);
            collect_address_taken_vars_from_expr(value, vars);
        }
        IrStmt::If {
            condition,
            then_body,
            else_body,
            ..
        } => {
            collect_address_taken_vars_from_expr(condition, vars);
            collect_address_taken_vars_from_body(then_body, vars);
            collect_address_taken_vars_from_body(else_body, vars);
        }
        IrStmt::While {
            condition, body, ..
        }
        | IrStmt::DoWhile {
            condition, body, ..
        } => {
            collect_address_taken_vars_from_expr(condition, vars);
            collect_address_taken_vars_from_body(body, vars);
        }
        IrStmt::For {
            init,
            condition,
            step,
            body,
            ..
        } => {
            collect_address_taken_vars_from_body(init, vars);
            if let Some(condition) = condition {
                collect_address_taken_vars_from_expr(condition, vars);
            }
            if let Some(step) = step {
                collect_address_taken_vars_from_stmt(step, vars);
            }
            collect_address_taken_vars_from_body(body, vars);
        }
        IrStmt::Return { value, .. } => {
            if let Some(value) = value {
                collect_address_taken_vars_from_expr(value, vars);
            }
        }
        IrStmt::Expr { expr, .. } => collect_address_taken_vars_from_expr(expr, vars),
        IrStmt::RecordMemset { destination, .. } => {
            collect_address_taken_vars_from_expr(destination, vars)
        }
        IrStmt::Break { .. } | IrStmt::Continue { .. } | IrStmt::Unsupported { .. } => {}
    }
}

fn collect_address_taken_vars_from_expr(expr: &IrExpr, vars: &mut HashSet<String>) {
    match expr {
        IrExpr::AddrOf { operand, .. } => {
            if let IrExpr::Var { name, .. } = operand.as_ref() {
                vars.insert(name.clone());
            }
            collect_address_taken_vars_from_expr(operand, vars);
        }
        IrExpr::MutableVoidPointerAddress { operand, .. } => {
            collect_address_taken_vars_from_expr(operand, vars);
        }
        IrExpr::Binary { lhs, rhs, .. } => {
            collect_address_taken_vars_from_expr(lhs, vars);
            collect_address_taken_vars_from_expr(rhs, vars);
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
        | IrExpr::Member { base: operand, .. } => {
            collect_address_taken_vars_from_expr(operand, vars);
        }
        IrExpr::Conditional {
            condition,
            then_expr,
            else_expr,
            ..
        } => {
            collect_address_taken_vars_from_expr(condition, vars);
            collect_address_taken_vars_from_expr(then_expr, vars);
            collect_address_taken_vars_from_expr(else_expr, vars);
        }
        IrExpr::Index { base, index, .. } => {
            collect_address_taken_vars_from_expr(base, vars);
            collect_address_taken_vars_from_expr(index, vars);
        }
        IrExpr::ArrayLiteral { elements, .. } => {
            for element in elements {
                collect_address_taken_vars_from_expr(element, vars);
            }
        }
        IrExpr::Call { args, .. } => {
            for arg in args {
                collect_address_taken_vars_from_expr(arg, vars);
            }
        }
        IrExpr::LitInt { .. }
        | IrExpr::NullPtr { .. }
        | IrExpr::Var { .. }
        | IrExpr::Unsupported { .. } => {}
    }
}

fn collect_nested_local_record_assigned_vars(body: &[IrStmt], assigned_vars: &mut HashSet<String>) {
    for stmt in body {
        match stmt {
            IrStmt::Assign { target, .. } => {
                if let Ok(Some(path)) = local_record_member_path_from_expr(target) {
                    assigned_vars.insert(path.root_name.to_string());
                }
            }
            IrStmt::If {
                then_body,
                else_body,
                ..
            } => {
                collect_nested_local_record_assigned_vars(then_body, assigned_vars);
                collect_nested_local_record_assigned_vars(else_body, assigned_vars);
            }
            IrStmt::While { body, .. } | IrStmt::DoWhile { body, .. } => {
                collect_nested_local_record_assigned_vars(body, assigned_vars);
            }
            IrStmt::For {
                init, step, body, ..
            } => {
                collect_nested_local_record_assigned_vars(init, assigned_vars);
                if let Some(step) = step.as_deref() {
                    collect_nested_local_record_assigned_vars(
                        std::slice::from_ref(step),
                        assigned_vars,
                    );
                }
                collect_nested_local_record_assigned_vars(body, assigned_vars);
            }
            IrStmt::Decl { .. }
            | IrStmt::Return { .. }
            | IrStmt::Break { .. }
            | IrStmt::Continue { .. }
            | IrStmt::Expr { .. }
            | IrStmt::RecordMemset { .. }
            | IrStmt::Unsupported { .. } => {}
        }
    }
}

fn collect_zero_initialized_record_locals(body: &[IrStmt]) -> Result<HashSet<String>, String> {
    let mut declarations = HashSet::new();
    collect_uninitialized_record_local_decls(body, &mut declarations)?;
    if declarations.is_empty() {
        return Ok(HashSet::new());
    }

    let mut allowed_address_args = HashSet::new();
    let mut disallowed_uses = HashSet::new();
    collect_zero_init_record_local_uses_from_body(
        body,
        &declarations,
        &mut allowed_address_args,
        &mut disallowed_uses,
    );

    Ok(allowed_address_args
        .difference(&disallowed_uses)
        .cloned()
        .collect())
}
