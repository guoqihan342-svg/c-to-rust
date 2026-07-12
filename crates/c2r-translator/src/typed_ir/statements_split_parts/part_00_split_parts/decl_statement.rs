fn emit_decl_statement(
    name: &String,
    ty: &IrType,
    init: &Option<IrExpr>,
    indent: &str,
    indent_level: usize,
    symbols: &mut HashSet<String>,
    context: &EmitContext,
) -> Result<String, String> {
            let decl_name = emit_identifier(name, "decl")?;
            if symbols.contains(name) {
                return Err(format!("decl {name} duplicates an existing symbol"));
            }
            if init.is_none() && context.byte_cursor_source(name).is_some() && is_u8_pointer(ty) {
                symbols.insert(name.clone());
                return Ok(format!("{indent}let mut {decl_name}: usize = 0;\n"));
            }
            if let Some(decl_ty) = emit_function_pointer_param_type(ty)
                .map_err(|detail| format!("decl {name} has {detail}"))?
            {
                let Some(init) = init else {
                    symbols.insert(name.clone());
                    return Ok(format!("{indent}let mut {decl_name}: {decl_ty};\n"));
                };
                let IrExpr::FunctionToPointerDecay { target, expr, .. } = init else {
                    return Err(format!(
                        "decl {name} function pointer initializer must be a direct function-to-pointer decay"
                    ));
                };
                if target != ty {
                    return Err(format!(
                        "decl {name} function pointer initializer target {} does not match declared type {}",
                        type_label(target),
                        type_label(ty)
                    ));
                }
                let init = emit_function_pointer_decay_call_arg(target, expr)
                    .map_err(|detail| format!("decl {name} initializer {detail}"))?;
                symbols.insert(name.clone());
                let mut_prefix = if context.is_assigned_var(name) {
                    "mut "
                } else {
                    ""
                };
                return Ok(format!(
                    "{indent}let {mut_prefix}{decl_name}: {decl_ty} = {init};\n"
                ));
            }
            if matches!(ty.kind, IrTypeKind::Array { .. }) {
                let decl_ty = emit_fixed_array_type(ty)
                    .map_err(|detail| format!("decl {name} has {detail}"))?;
                let Some(IrExpr::ArrayLiteral {
                    elements,
                    ty: literal_ty,
                    ..
                }) = init
                else {
                    return Err(format!(
                        "decl {name} array initializer must be an array literal"
                    ));
                };
                if literal_ty != ty {
                    return Err(format!(
                        "decl {name} array literal type {} does not match declared type {}",
                        type_label(literal_ty),
                        type_label(ty)
                    ));
                }
                let init = emit_array_literal(
                    elements,
                    ty,
                    symbols,
                    context,
                    &format!("decl {name} initializer"),
                )?;
                symbols.insert(name.clone());
                let mut_prefix = if context.is_assigned_var(name) {
                    "mut "
                } else {
                    ""
                };
                return Ok(format!(
                    "{indent}let {mut_prefix}{decl_name}: {decl_ty} = {init};\n"
                ));
            }
            if matches!(ty.kind, IrTypeKind::Record { .. }) {
                let decl_ty =
                    emit_value_type(ty).map_err(|detail| format!("decl {name} has {detail}"))?;
                let (init, zero_initialized) = if let Some(init) = init {
                    validate_expr_matches_type(init, ty, &format!("decl {name} initializer"))?;
                    let init = emit_expr(init, symbols, context)
                        .map_err(|detail| format!("decl {name} initializer {detail}"))?;
                    (init, false)
                } else if context.is_zero_initialized_record_local(name) {
                    (emit_record_zero_initializer(ty)?, true)
                } else {
                    return Err(format!("decl {name} record initializer is required"));
                };
                symbols.insert(name.clone());
                let mut_prefix = if zero_initialized || context.is_assigned_var(name) {
                    "mut "
                } else {
                    ""
                };
                return Ok(format!(
                    "{indent}let {mut_prefix}{decl_name}: {decl_ty} = {init};\n"
                ));
            }
            let decl_ty =
                emit_scalar_type(ty).map_err(|detail| format!("decl {name} has {detail}"))?;
            if let Some(init) = init {
                validate_expr_matches_type(init, ty, &format!("decl {name} initializer"))?;
                let emitted = emit_expr_with_prelude(
                    init,
                    symbols,
                    context,
                    indent_level,
                    &format!("decl {name} initializer"),
                )?;
                symbols.insert(name.clone());
                Ok(format!(
                    "{}{indent}let mut {decl_name}: {decl_ty} = {};\n",
                    emitted.prelude, emitted.expr
                ))
            } else {
                symbols.insert(name.clone());
                Ok(format!("{indent}let mut {decl_name}: {decl_ty};\n"))
            }
}
