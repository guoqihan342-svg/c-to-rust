fn collect_param_symbols(params: &[IrParam]) -> Result<HashSet<String>, String> {
    let mut symbols = HashSet::new();
    for param in params {
        if !symbols.insert(param.name.clone()) {
            return Err(format!(
                "param {} duplicates an existing symbol",
                param.name
            ));
        }
    }
    Ok(symbols)
}

fn collect_assigned_vars_from_body(body: &[IrStmt], assigned_vars: &mut HashSet<String>) {
    for stmt in body {
        match stmt {
            IrStmt::Decl { init, .. } => {
                if let Some(init) = init {
                    collect_assigned_vars_from_expr(init, assigned_vars);
                }
            }
            IrStmt::Assign { target, value, .. } => {
                if let Some(name) = assigned_var_name_from_target(target) {
                    assigned_vars.insert(name.clone());
                }
                collect_assigned_vars_from_expr(target, assigned_vars);
                collect_assigned_vars_from_expr(value, assigned_vars);
            }
            IrStmt::If {
                condition,
                then_body,
                else_body,
                ..
            } => {
                collect_assigned_vars_from_expr(condition, assigned_vars);
                collect_assigned_vars_from_body(then_body, assigned_vars);
                collect_assigned_vars_from_body(else_body, assigned_vars);
            }
            IrStmt::While {
                condition, body, ..
            } => {
                collect_assigned_vars_from_expr(condition, assigned_vars);
                if let IrExpr::IncDec {
                    target,
                    op: IrIncDecOp::Dec,
                    ..
                } = condition
                {
                    if let IrExpr::Var { name, .. } = target.as_ref() {
                        assigned_vars.insert(name.clone());
                    }
                }
                collect_assigned_vars_from_body(body, assigned_vars);
            }
            IrStmt::DoWhile {
                body, condition, ..
            } => {
                collect_assigned_vars_from_expr(condition, assigned_vars);
                if let IrExpr::IncDec {
                    target,
                    op: IrIncDecOp::Dec,
                    ..
                } = condition
                {
                    if let IrExpr::Var { name, .. } = target.as_ref() {
                        assigned_vars.insert(name.clone());
                    }
                }
                collect_assigned_vars_from_body(body, assigned_vars);
            }
            IrStmt::For {
                init,
                condition,
                step,
                body,
                ..
            } => {
                collect_assigned_vars_from_body(init, assigned_vars);
                if let Some(condition) = condition {
                    collect_assigned_vars_from_expr(condition, assigned_vars);
                }
                if let Some(step) = step {
                    collect_assigned_vars_from_body(
                        std::slice::from_ref(step.as_ref()),
                        assigned_vars,
                    );
                }
                collect_assigned_vars_from_body(body, assigned_vars);
            }
            IrStmt::Return { value, .. } => {
                if let Some(value) = value {
                    collect_assigned_vars_from_expr(value, assigned_vars);
                }
            }
            IrStmt::Expr { expr, .. } => {
                if let Some(name) =
                    c_memset_assigned_var_name(expr).or_else(|| c_memcpy_assigned_var_name(expr))
                {
                    assigned_vars.insert(name.clone());
                }
                collect_assigned_vars_from_expr(expr, assigned_vars);
                if let IrExpr::IncDec {
                    target,
                    prefix: true,
                    ..
                } = expr
                {
                    if let IrExpr::Var { name, .. } = target.as_ref() {
                        assigned_vars.insert(name.clone());
                    }
                }
            }
            _ => {}
        }
    }
}

fn collect_assigned_vars_from_expr(expr: &IrExpr, assigned_vars: &mut HashSet<String>) {
    match expr {
        IrExpr::Binary { lhs, rhs, .. } => {
            collect_assigned_vars_from_expr(lhs, assigned_vars);
            collect_assigned_vars_from_expr(rhs, assigned_vars);
        }
        IrExpr::Unary { operand, .. }
        | IrExpr::Cast { expr: operand, .. }
        | IrExpr::LValueToRValue { expr: operand, .. }
        | IrExpr::ArrayToPointerDecay { expr: operand, .. }
        | IrExpr::FunctionToPointerDecay { expr: operand, .. }
        | IrExpr::AddrOf { operand, .. } => {
            collect_assigned_vars_from_expr(operand, assigned_vars);
        }
        IrExpr::Conditional {
            condition,
            then_expr,
            else_expr,
            ..
        } => {
            collect_assigned_vars_from_expr(condition, assigned_vars);
            collect_assigned_vars_from_expr(then_expr, assigned_vars);
            collect_assigned_vars_from_expr(else_expr, assigned_vars);
        }
        IrExpr::Index { base, index, .. } => {
            collect_assigned_vars_from_expr(base, assigned_vars);
            collect_assigned_vars_from_expr(index, assigned_vars);
        }
        IrExpr::Member { base, .. } => {
            collect_assigned_vars_from_expr(base, assigned_vars);
        }
        IrExpr::ArrayLiteral { elements, .. } => {
            for element in elements {
                collect_assigned_vars_from_expr(element, assigned_vars);
            }
        }
        IrExpr::Call { args, .. } => {
            for arg in args {
                collect_assigned_vars_from_expr(arg, assigned_vars);
            }
        }
        IrExpr::IncDec { target, .. } => {
            if let Some(name) = scalar_inc_dec_assigned_var_name(expr) {
                assigned_vars.insert(name.clone());
            }
            collect_assigned_vars_from_expr(target, assigned_vars);
        }
        IrExpr::Deref { ptr, .. } => {
            collect_assigned_vars_from_expr(ptr, assigned_vars);
        }
        IrExpr::LitInt { .. }
        | IrExpr::NullPtr { .. }
        | IrExpr::Var { .. }
        | IrExpr::Unsupported { .. } => {}
    }
}

fn scalar_inc_dec_assigned_var_name(expr: &IrExpr) -> Option<&String> {
    let IrExpr::IncDec { target, ty, .. } = expr else {
        return None;
    };
    let IrExpr::Var {
        name,
        ty: target_ty,
        ..
    } = target.as_ref()
    else {
        return None;
    };
    (target_ty == ty && is_integer_type(target_ty)).then_some(name)
}

fn c_memset_assigned_var_name(expr: &IrExpr) -> Option<&String> {
    let IrExpr::Call { callee, args, .. } = expr else {
        return None;
    };
    if callee != "memset" || args.len() != 3 {
        return None;
    }
    match &args[0] {
        IrExpr::Var { name, .. } => Some(name),
        _ => None,
    }
}

fn c_memcpy_assigned_var_name(expr: &IrExpr) -> Option<&String> {
    let IrExpr::Call { callee, args, .. } = expr else {
        return None;
    };
    if callee != "memcpy" || args.len() != 3 {
        return None;
    }
    match &args[0] {
        IrExpr::Var { name, .. } => Some(name),
        _ => None,
    }
}

fn assigned_var_name_from_target(target: &IrExpr) -> Option<&String> {
    match target {
        IrExpr::Var { name, .. } => Some(name),
        IrExpr::Index { base, .. } => match base.as_ref() {
            IrExpr::Var { name, .. } => Some(name),
            _ => None,
        },
        IrExpr::Deref { ptr, .. } => pointer_write_base_name_from_ptr(ptr),
        IrExpr::Member { base, .. } => match base.as_ref() {
            IrExpr::Var { name, .. } => Some(name),
            _ => None,
        },
        _ => None,
    }
}

fn pointer_write_base_name_from_ptr(ptr: &IrExpr) -> Option<&String> {
    match ptr {
        IrExpr::Var { name, .. } => Some(name),
        IrExpr::Binary {
            op: IrBinOp::Add,
            lhs,
            rhs,
            ..
        } => mutable_pointer_add_operands(lhs, rhs).and_then(|(base, _)| match base {
            IrExpr::Var { name, .. } => Some(name),
            _ => None,
        }),
        _ => None,
    }
}
