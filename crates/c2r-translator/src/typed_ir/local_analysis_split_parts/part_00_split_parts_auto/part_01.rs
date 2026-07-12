
fn collect_zero_init_record_local_uses_from_expr(
    expr: &IrExpr,
    declarations: &HashSet<String>,
    allowed_address_args: &mut HashSet<String>,
    disallowed_uses: &mut HashSet<String>,
) {
    match expr {
        IrExpr::Var { name, .. } => {
            if declarations.contains(name) {
                disallowed_uses.insert(name.clone());
            }
        }
        IrExpr::Call { args, .. } => {
            for arg in args {
                if let IrExpr::AddrOf { operand, ty, .. } = arg {
                    if let Ok(name) = validate_local_record_address_call_arg(operand, ty) {
                        if declarations.contains(name) {
                            allowed_address_args.insert(name.to_string());
                            continue;
                        }
                    }
                }
                collect_zero_init_record_local_uses_from_expr(
                    arg,
                    declarations,
                    allowed_address_args,
                    disallowed_uses,
                );
            }
        }
        IrExpr::Binary { lhs, rhs, .. } => {
            collect_zero_init_record_local_uses_from_expr(
                lhs,
                declarations,
                allowed_address_args,
                disallowed_uses,
            );
            collect_zero_init_record_local_uses_from_expr(
                rhs,
                declarations,
                allowed_address_args,
                disallowed_uses,
            );
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
        | IrExpr::MutableVoidPointerAddress { operand, .. }
        | IrExpr::Member { base: operand, .. } => {
            collect_zero_init_record_local_uses_from_expr(
                operand,
                declarations,
                allowed_address_args,
                disallowed_uses,
            );
        }
        IrExpr::Conditional {
            condition,
            then_expr,
            else_expr,
            ..
        } => {
            collect_zero_init_record_local_uses_from_expr(
                condition,
                declarations,
                allowed_address_args,
                disallowed_uses,
            );
            collect_zero_init_record_local_uses_from_expr(
                then_expr,
                declarations,
                allowed_address_args,
                disallowed_uses,
            );
            collect_zero_init_record_local_uses_from_expr(
                else_expr,
                declarations,
                allowed_address_args,
                disallowed_uses,
            );
        }
        IrExpr::Index { base, index, .. } => {
            collect_zero_init_record_local_uses_from_expr(
                base,
                declarations,
                allowed_address_args,
                disallowed_uses,
            );
            collect_zero_init_record_local_uses_from_expr(
                index,
                declarations,
                allowed_address_args,
                disallowed_uses,
            );
        }
        IrExpr::ArrayLiteral { elements, .. } => {
            for element in elements {
                collect_zero_init_record_local_uses_from_expr(
                    element,
                    declarations,
                    allowed_address_args,
                    disallowed_uses,
                );
            }
        }
        IrExpr::LitInt { .. } | IrExpr::NullPtr { .. } | IrExpr::Unsupported { .. } => {}
    }
}

fn collect_byte_cursor_sources(body: &[IrStmt]) -> HashMap<String, String> {
    let mut candidates = HashMap::new();
    collect_byte_cursor_sources_from_body(body, &mut candidates);
    candidates
        .into_iter()
        .filter(|(cursor, _)| body_has_post_increment_byte_read(body, cursor))
        .collect()
}

fn collect_byte_cursor_sources_from_body(
    body: &[IrStmt],
    cursor_sources: &mut HashMap<String, String>,
) {
    for stmt in body {
        match stmt {
            IrStmt::Assign { target, value, .. } => {
                if let Some((cursor, source)) = byte_cursor_cast_assignment_parts(target, value) {
                    cursor_sources.insert(cursor.to_string(), source.to_string());
                }
            }
            IrStmt::If {
                then_body,
                else_body,
                ..
            } => {
                collect_byte_cursor_sources_from_body(then_body, cursor_sources);
                collect_byte_cursor_sources_from_body(else_body, cursor_sources);
            }
            IrStmt::While { body, .. } => {
                collect_byte_cursor_sources_from_body(body, cursor_sources);
            }
            IrStmt::DoWhile { body, .. } => {
                collect_byte_cursor_sources_from_body(body, cursor_sources);
            }
            IrStmt::For {
                init, step, body, ..
            } => {
                collect_byte_cursor_sources_from_body(init, cursor_sources);
                if let Some(step) = step {
                    collect_byte_cursor_sources_from_body(
                        std::slice::from_ref(step.as_ref()),
                        cursor_sources,
                    );
                }
                collect_byte_cursor_sources_from_body(body, cursor_sources);
            }
            _ => {}
        }
    }
}

fn byte_cursor_cast_assignment_parts<'a>(
    target: &'a IrExpr,
    value: &'a IrExpr,
) -> Option<(&'a str, &'a str)> {
    let IrExpr::Var {
        name: cursor,
        ty: cursor_ty,
        ..
    } = target
    else {
        return None;
    };
    let IrExpr::Cast {
        target,
        expr,
        implicit: false,
        ..
    } = value
    else {
        return None;
    };
    let IrExpr::Var {
        name: source,
        ty: source_ty,
        ..
    } = expr.as_ref()
    else {
        return None;
    };
    if is_u8_pointer(cursor_ty) && is_u8_pointer(target) && is_const_void_pointer(source_ty) {
        Some((cursor.as_str(), source.as_str()))
    } else {
        None
    }
}

fn body_has_post_increment_byte_read(body: &[IrStmt], cursor: &str) -> bool {
    body.iter()
        .any(|stmt| stmt_has_post_increment_byte_read(stmt, cursor))
}

fn stmt_has_post_increment_byte_read(stmt: &IrStmt, cursor: &str) -> bool {
    match stmt {
        IrStmt::Decl { init, .. } => init
            .as_ref()
            .is_some_and(|expr| expr_has_post_increment_byte_read(expr, cursor)),
        IrStmt::Assign { target, value, .. } => {
            expr_has_post_increment_byte_read(target, cursor)
                || expr_has_post_increment_byte_read(value, cursor)
        }
        IrStmt::Return { value, .. } => value
            .as_ref()
            .is_some_and(|expr| expr_has_post_increment_byte_read(expr, cursor)),
        IrStmt::Break { .. } | IrStmt::Continue { .. } => false,
        IrStmt::Expr { expr, .. } => expr_has_post_increment_byte_read(expr, cursor),
        IrStmt::RecordMemset { destination, .. } => {
            expr_has_post_increment_byte_read(destination, cursor)
        }
        IrStmt::If {
            condition,
            then_body,
            else_body,
            ..
        } => {
            expr_has_post_increment_byte_read(condition, cursor)
                || body_has_post_increment_byte_read(then_body, cursor)
                || body_has_post_increment_byte_read(else_body, cursor)
        }
        IrStmt::While {
            condition, body, ..
        } => {
            expr_has_post_increment_byte_read(condition, cursor)
                || body_has_post_increment_byte_read(body, cursor)
        }
        IrStmt::DoWhile {
            body, condition, ..
        } => {
            body_has_post_increment_byte_read(body, cursor)
                || expr_has_post_increment_byte_read(condition, cursor)
        }
        IrStmt::For {
            init,
            condition,
            step,
            body,
            ..
        } => {
            body_has_post_increment_byte_read(init, cursor)
                || condition
                    .as_ref()
                    .is_some_and(|expr| expr_has_post_increment_byte_read(expr, cursor))
                || step
                    .as_ref()
                    .is_some_and(|stmt| stmt_has_post_increment_byte_read(stmt, cursor))
                || body_has_post_increment_byte_read(body, cursor)
        }
        IrStmt::Unsupported { .. } => false,
    }
}
