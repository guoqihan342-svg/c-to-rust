
fn params_have_restrict_noalias(
    params_by_name: &HashMap<&str, &IrParam>,
    readonly_param: &str,
    mutable_param: &str,
) -> bool {
    params_by_name
        .get(readonly_param)
        .is_some_and(|param| type_has_restrict_qualifier(&param.ty))
        && params_by_name
            .get(mutable_param)
            .is_some_and(|param| type_has_restrict_qualifier(&param.ty))
}

fn type_has_restrict_qualifier(ty: &IrType) -> bool {
    [ty.spelled.as_str(), ty.canonical.as_str()]
        .iter()
        .any(|spelling| spelling_has_restrict_qualifier(spelling))
}

fn spelling_has_restrict_qualifier(spelling: &str) -> bool {
    spelling
        .split(|ch: char| {
            ch.is_whitespace() || matches!(ch, '*' | '(' | ')' | '[' | ']' | ',' | ';')
        })
        .any(|token| matches!(token, "restrict" | "__restrict" | "__restrict__"))
}

fn collect_readonly_pointer_param_uses(
    body: &[IrStmt],
    params: &[IrParam],
) -> Result<ReadonlyPointerParamUses, String> {
    let readonly_pointer_params = params
        .iter()
        .filter(|param| readonly_pointer_slice_element_type(&param.ty).is_some())
        .map(|param| (param.name.as_str(), &param.ty))
        .collect::<HashMap<_, _>>();
    let mut uses = ReadonlyPointerParamUses::default();
    collect_readonly_pointer_read_params_from_body(body, &readonly_pointer_params, &mut uses)?;
    Ok(uses)
}

fn validate_readonly_pointer_slice_lowering_evidence(
    params: &[IrParam],
    byte_slice_params: &HashSet<String>,
    nullable_pointer_params: &HashSet<String>,
    readonly_pointer_read_params: &HashSet<String>,
    readonly_pointer_mentioned_params: &HashSet<String>,
) -> Result<(), String> {
    for param in params {
        if readonly_pointer_slice_element_type(&param.ty).is_some()
            && !byte_slice_params.contains(&param.name)
            && !nullable_pointer_params.contains(&param.name)
            && !readonly_pointer_read_params.contains(&param.name)
            && !readonly_pointer_mentioned_params.contains(&param.name)
        {
            if is_unused_readonly_8_bit_pointer_param(
                &param.name,
                &param.ty,
                readonly_pointer_read_params,
                readonly_pointer_mentioned_params,
            ) {
                continue;
            }
            return Err(format!(
                "readonly pointer param {} requires pointer-to-slice lowering evidence before lowering {} to &[T]",
                param.name,
                type_label(&param.ty)
            ));
        }
    }
    Ok(())
}

fn collect_mutable_pointer_write_params_from_body(
    body: &[IrStmt],
    mutable_pointer_params: &HashMap<&str, &IrType>,
    write_params: &mut HashSet<String>,
) -> Result<(), String> {
    for stmt in body {
        match stmt {
            IrStmt::Assign { target, .. } => {
                collect_mutable_pointer_write_param_from_target(
                    target,
                    mutable_pointer_params,
                    write_params,
                )?;
            }
            IrStmt::If {
                then_body,
                else_body,
                ..
            } => {
                collect_mutable_pointer_write_params_from_body(
                    then_body,
                    mutable_pointer_params,
                    write_params,
                )?;
                collect_mutable_pointer_write_params_from_body(
                    else_body,
                    mutable_pointer_params,
                    write_params,
                )?;
            }
            IrStmt::While { body, .. } | IrStmt::DoWhile { body, .. } => {
                collect_mutable_pointer_write_params_from_body(
                    body,
                    mutable_pointer_params,
                    write_params,
                )?;
            }
            IrStmt::For {
                init, step, body, ..
            } => {
                collect_mutable_pointer_write_params_from_body(
                    init,
                    mutable_pointer_params,
                    write_params,
                )?;
                if let Some(step) = step {
                    collect_mutable_pointer_write_params_from_body(
                        std::slice::from_ref(step.as_ref()),
                        mutable_pointer_params,
                        write_params,
                    )?;
                }
                collect_mutable_pointer_write_params_from_body(
                    body,
                    mutable_pointer_params,
                    write_params,
                )?;
            }
            IrStmt::Expr { expr, .. } => {
                collect_c_memset_mutable_pointer_write_param(
                    expr,
                    mutable_pointer_params,
                    write_params,
                )?;
                collect_c_memcpy_mutable_pointer_write_param(
                    expr,
                    mutable_pointer_params,
                    write_params,
                )?;
            }
            IrStmt::RecordMemset { .. } => {}
            IrStmt::Decl { .. }
            | IrStmt::Return { .. }
            | IrStmt::Break { .. }
            | IrStmt::Continue { .. }
            | IrStmt::Unsupported { .. } => {}
        }
    }
    Ok(())
}

fn collect_c_memset_mutable_pointer_write_param(
    expr: &IrExpr,
    mutable_pointer_params: &HashMap<&str, &IrType>,
    write_params: &mut HashSet<String>,
) -> Result<(), String> {
    let IrExpr::Call { callee, args, .. } = expr else {
        return Ok(());
    };
    if callee == "memset" && args.len() == 3 {
        collect_direct_mutable_pointer_write_param(&args[0], mutable_pointer_params, write_params)?;
    }
    Ok(())
}

fn collect_c_memcpy_mutable_pointer_write_param(
    expr: &IrExpr,
    mutable_pointer_params: &HashMap<&str, &IrType>,
    write_params: &mut HashSet<String>,
) -> Result<(), String> {
    let IrExpr::Call { callee, args, .. } = expr else {
        return Ok(());
    };
    if callee == "memcpy" && args.len() == 3 {
        collect_direct_mutable_pointer_write_param(&args[0], mutable_pointer_params, write_params)?;
    }
    Ok(())
}

fn collect_mutable_pointer_write_param_from_target(
    target: &IrExpr,
    mutable_pointer_params: &HashMap<&str, &IrType>,
    write_params: &mut HashSet<String>,
) -> Result<(), String> {
    match target {
        IrExpr::Index { base, .. } => {
            collect_direct_mutable_pointer_write_param(base, mutable_pointer_params, write_params)
        }
        IrExpr::Deref { ptr, .. } => match ptr.as_ref() {
            IrExpr::Binary { .. } => {
                if let Some((base, _)) = mutable_pointer_add_operands_from_expr(ptr.as_ref()) {
                    collect_direct_mutable_pointer_write_param(
                        base,
                        mutable_pointer_params,
                        write_params,
                    )?;
                }
                Ok(())
            }
            expr => collect_direct_mutable_pointer_write_param(
                expr,
                mutable_pointer_params,
                write_params,
            ),
        },
        _ => Ok(()),
    }
}

fn mutable_pointer_add_operands_from_expr(expr: &IrExpr) -> Option<(&IrExpr, &IrExpr)> {
    let IrExpr::Binary { lhs, rhs, .. } = expr else {
        return None;
    };
    mutable_pointer_add_operands(lhs, rhs)
}

fn collect_direct_mutable_pointer_write_param(
    expr: &IrExpr,
    mutable_pointer_params: &HashMap<&str, &IrType>,
    write_params: &mut HashSet<String>,
) -> Result<(), String> {
    let IrExpr::Var { name, ty, .. } = expr else {
        return Ok(());
    };
    if mutable_pointer_params
        .get(name.as_str())
        .is_some_and(|param_ty| *param_ty == ty)
    {
        write_params.insert(name.to_string());
    }
    Ok(())
}
