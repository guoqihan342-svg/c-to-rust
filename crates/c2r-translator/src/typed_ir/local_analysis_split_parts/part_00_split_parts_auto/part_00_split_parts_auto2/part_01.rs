
fn collect_uninitialized_record_local_decls(
    body: &[IrStmt],
    declarations: &mut HashSet<String>,
) -> Result<(), String> {
    for stmt in body {
        match stmt {
            IrStmt::Decl { name, ty, init, .. } => {
                if init.is_none() && matches!(ty.kind, IrTypeKind::Record { .. }) {
                    declarations.insert(name.clone());
                }
            }
            IrStmt::If {
                then_body,
                else_body,
                ..
            } => {
                collect_uninitialized_record_local_decls(then_body, declarations)?;
                collect_uninitialized_record_local_decls(else_body, declarations)?;
            }
            IrStmt::While { body, .. } | IrStmt::DoWhile { body, .. } => {
                collect_uninitialized_record_local_decls(body, declarations)?;
            }
            IrStmt::For {
                init, step, body, ..
            } => {
                collect_uninitialized_record_local_decls(init, declarations)?;
                if let Some(step) = step.as_deref() {
                    collect_uninitialized_record_local_decls(
                        std::slice::from_ref(step),
                        declarations,
                    )?;
                }
                collect_uninitialized_record_local_decls(body, declarations)?;
            }
            IrStmt::Assign { .. }
            | IrStmt::Return { .. }
            | IrStmt::Break { .. }
            | IrStmt::Continue { .. }
            | IrStmt::Expr { .. }
            | IrStmt::RecordMemset { .. }
            | IrStmt::Unsupported { .. } => {}
        }
    }
    Ok(())
}

fn collect_zero_init_record_local_uses_from_body(
    body: &[IrStmt],
    declarations: &HashSet<String>,
    allowed_address_args: &mut HashSet<String>,
    disallowed_uses: &mut HashSet<String>,
) {
    for stmt in body {
        collect_zero_init_record_local_uses_from_stmt(
            stmt,
            declarations,
            allowed_address_args,
            disallowed_uses,
        );
    }
}

fn collect_zero_init_record_local_uses_from_stmt(
    stmt: &IrStmt,
    declarations: &HashSet<String>,
    allowed_address_args: &mut HashSet<String>,
    disallowed_uses: &mut HashSet<String>,
) {
    match stmt {
        IrStmt::Decl { init, .. } => {
            if let Some(init) = init {
                collect_zero_init_record_local_uses_from_expr(
                    init,
                    declarations,
                    allowed_address_args,
                    disallowed_uses,
                );
            }
        }
        IrStmt::Assign { target, value, .. } => {
            collect_zero_init_record_local_uses_from_expr(
                target,
                declarations,
                allowed_address_args,
                disallowed_uses,
            );
            collect_zero_init_record_local_uses_from_expr(
                value,
                declarations,
                allowed_address_args,
                disallowed_uses,
            );
        }
        IrStmt::If {
            condition,
            then_body,
            else_body,
            ..
        } => {
            collect_zero_init_record_local_uses_from_expr(
                condition,
                declarations,
                allowed_address_args,
                disallowed_uses,
            );
            collect_zero_init_record_local_uses_from_body(
                then_body,
                declarations,
                allowed_address_args,
                disallowed_uses,
            );
            collect_zero_init_record_local_uses_from_body(
                else_body,
                declarations,
                allowed_address_args,
                disallowed_uses,
            );
        }
        IrStmt::While {
            condition, body, ..
        } => {
            collect_zero_init_record_local_uses_from_expr(
                condition,
                declarations,
                allowed_address_args,
                disallowed_uses,
            );
            collect_zero_init_record_local_uses_from_body(
                body,
                declarations,
                allowed_address_args,
                disallowed_uses,
            );
        }
        IrStmt::DoWhile {
            body, condition, ..
        } => {
            collect_zero_init_record_local_uses_from_body(
                body,
                declarations,
                allowed_address_args,
                disallowed_uses,
            );
            collect_zero_init_record_local_uses_from_expr(
                condition,
                declarations,
                allowed_address_args,
                disallowed_uses,
            );
        }
        IrStmt::For {
            init,
            condition,
            step,
            body,
            ..
        } => {
            collect_zero_init_record_local_uses_from_body(
                init,
                declarations,
                allowed_address_args,
                disallowed_uses,
            );
            if let Some(condition) = condition {
                collect_zero_init_record_local_uses_from_expr(
                    condition,
                    declarations,
                    allowed_address_args,
                    disallowed_uses,
                );
            }
            if let Some(step) = step.as_deref() {
                collect_zero_init_record_local_uses_from_stmt(
                    step,
                    declarations,
                    allowed_address_args,
                    disallowed_uses,
                );
            }
            collect_zero_init_record_local_uses_from_body(
                body,
                declarations,
                allowed_address_args,
                disallowed_uses,
            );
        }
        IrStmt::Return { value, .. } => {
            if let Some(value) = value {
                collect_zero_init_record_local_uses_from_expr(
                    value,
                    declarations,
                    allowed_address_args,
                    disallowed_uses,
                );
            }
        }
        IrStmt::Expr { expr, .. } => collect_zero_init_record_local_uses_from_expr(
            expr,
            declarations,
            allowed_address_args,
            disallowed_uses,
        ),
        IrStmt::RecordMemset { destination, .. } => {
            collect_zero_init_record_local_uses_from_expr(
                destination,
                declarations,
                allowed_address_args,
                disallowed_uses,
            )
        }
        IrStmt::Break { .. } | IrStmt::Continue { .. } | IrStmt::Unsupported { .. } => {}
    }
}
