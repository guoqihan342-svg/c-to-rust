fn collect_ir_post_increment_deref_vars_from_stmts(
    statements: &[typed_ir::IrStmt],
    vars: &mut Vec<String>,
) {
    for statement in statements {
        match statement {
            typed_ir::IrStmt::Decl { init, .. } => {
                if let Some(init) = init {
                    collect_ir_post_increment_deref_vars_from_expr(init, vars);
                }
            }
            typed_ir::IrStmt::Assign { target, value, .. } => {
                collect_ir_post_increment_deref_vars_from_expr(target, vars);
                collect_ir_post_increment_deref_vars_from_expr(value, vars);
            }
            typed_ir::IrStmt::If {
                condition,
                then_body,
                else_body,
                ..
            } => {
                collect_ir_post_increment_deref_vars_from_expr(condition, vars);
                collect_ir_post_increment_deref_vars_from_stmts(then_body, vars);
                collect_ir_post_increment_deref_vars_from_stmts(else_body, vars);
            }
            typed_ir::IrStmt::While {
                condition, body, ..
            } => {
                collect_ir_post_increment_deref_vars_from_expr(condition, vars);
                collect_ir_post_increment_deref_vars_from_stmts(body, vars);
            }
            typed_ir::IrStmt::DoWhile {
                body, condition, ..
            } => {
                collect_ir_post_increment_deref_vars_from_stmts(body, vars);
                collect_ir_post_increment_deref_vars_from_expr(condition, vars);
            }
            typed_ir::IrStmt::For {
                init,
                condition,
                step,
                body,
                ..
            } => {
                collect_ir_post_increment_deref_vars_from_stmts(init, vars);
                if let Some(condition) = condition {
                    collect_ir_post_increment_deref_vars_from_expr(condition, vars);
                }
                collect_ir_post_increment_deref_vars_from_stmts(body, vars);
                if let Some(step) = step.as_deref() {
                    collect_ir_post_increment_deref_vars_from_stmts(
                        std::slice::from_ref(step),
                        vars,
                    );
                }
            }
            typed_ir::IrStmt::Return { value, .. } => {
                if let Some(value) = value {
                    collect_ir_post_increment_deref_vars_from_expr(value, vars);
                }
            }
            typed_ir::IrStmt::Break { .. } | typed_ir::IrStmt::Continue { .. } => {}
            typed_ir::IrStmt::Expr { expr, .. } => {
                collect_ir_post_increment_deref_vars_from_expr(expr, vars);
            }
            typed_ir::IrStmt::RecordMemset { destination, .. } => {
                collect_ir_post_increment_deref_vars_from_expr(destination, vars);
            }
            typed_ir::IrStmt::Unsupported { .. } => {}
        }
    }
}

fn collect_ir_post_increment_deref_vars_from_expr(expr: &typed_ir::IrExpr, vars: &mut Vec<String>) {
    match expr {
        typed_ir::IrExpr::Deref { ptr, .. } => {
            if let Some(name) = ir_post_increment_var_name(ptr) {
                push_unique(vars, name);
            }
            collect_ir_post_increment_deref_vars_from_expr(ptr, vars);
        }
        typed_ir::IrExpr::Binary { lhs, rhs, .. } => {
            collect_ir_post_increment_deref_vars_from_expr(lhs, vars);
            collect_ir_post_increment_deref_vars_from_expr(rhs, vars);
        }
        typed_ir::IrExpr::Unary { operand, .. } => {
            collect_ir_post_increment_deref_vars_from_expr(operand, vars);
        }
        typed_ir::IrExpr::Conditional {
            condition,
            then_expr,
            else_expr,
            ..
        } => {
            collect_ir_post_increment_deref_vars_from_expr(condition, vars);
            collect_ir_post_increment_deref_vars_from_expr(then_expr, vars);
            collect_ir_post_increment_deref_vars_from_expr(else_expr, vars);
        }
        typed_ir::IrExpr::Cast { expr, .. } => {
            collect_ir_post_increment_deref_vars_from_expr(expr, vars);
        }
        typed_ir::IrExpr::LValueToRValue { expr, .. } => {
            collect_ir_post_increment_deref_vars_from_expr(expr, vars);
        }
        typed_ir::IrExpr::ArrayToPointerDecay { expr, .. } => {
            collect_ir_post_increment_deref_vars_from_expr(expr, vars);
        }
        typed_ir::IrExpr::FunctionToPointerDecay { expr, .. } => {
            collect_ir_post_increment_deref_vars_from_expr(expr, vars);
        }
        typed_ir::IrExpr::Index { base, index, .. } => {
            collect_ir_post_increment_deref_vars_from_expr(base, vars);
            collect_ir_post_increment_deref_vars_from_expr(index, vars);
        }
        typed_ir::IrExpr::Member { base, .. } => {
            collect_ir_post_increment_deref_vars_from_expr(base, vars);
        }
        typed_ir::IrExpr::ArrayLiteral { elements, .. } => {
            for element in elements {
                collect_ir_post_increment_deref_vars_from_expr(element, vars);
            }
        }
        typed_ir::IrExpr::Call { args, .. } => {
            for arg in args {
                collect_ir_post_increment_deref_vars_from_expr(arg, vars);
            }
        }
        typed_ir::IrExpr::IncDec { target, .. } => {
            collect_ir_post_increment_deref_vars_from_expr(target, vars);
        }
        typed_ir::IrExpr::AddrOf { operand, .. } => {
            collect_ir_post_increment_deref_vars_from_expr(operand, vars);
        }
        typed_ir::IrExpr::LitInt { .. }
        | typed_ir::IrExpr::NullPtr { .. }
        | typed_ir::IrExpr::Var { .. }
        | typed_ir::IrExpr::Unsupported { .. } => {}
    }
}

fn ir_post_increment_var_name(expr: &typed_ir::IrExpr) -> Option<&str> {
    match expr {
        typed_ir::IrExpr::IncDec {
            target,
            op: typed_ir::IrIncDecOp::Inc,
            prefix: false,
            ..
        } => ir_simple_var_name(target),
        typed_ir::IrExpr::Cast { expr, .. } => ir_post_increment_var_name(expr),
        _ => None,
    }
}

fn ir_simple_var_name(expr: &typed_ir::IrExpr) -> Option<&str> {
    match expr {
        typed_ir::IrExpr::Var { name, .. } => Some(name),
        _ => None,
    }
}

fn ir_pointer_is_const(ty: &typed_ir::IrType) -> bool {
    match &ty.kind {
        typed_ir::IrTypeKind::Pointer { pointee } => ty.is_const || pointee.is_const,
        _ => false,
    }
}

fn push_unique(values: &mut Vec<String>, value: &str) {
    if !values.iter().any(|item| item == value) {
        values.push(value.to_string());
    }
}

fn push_rule_once(rules: &mut Vec<String>, rule: &str) {
    if !rules.iter().any(|existing| existing == rule) {
        rules.push(rule.to_string());
    }
}
