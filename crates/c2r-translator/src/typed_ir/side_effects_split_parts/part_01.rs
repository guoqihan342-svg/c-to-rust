fn emit_post_increment_byte_read_expr(
    ptr: &IrExpr,
    ty: &IrType,
    symbols: &mut HashSet<String>,
    context: &EmitContext,
    indent_level: usize,
    path: &str,
) -> Result<EmittedExpr, String> {
    let IrExpr::IncDec {
        target,
        op: IrIncDecOp::Inc,
        prefix: false,
        ..
    } = ptr
    else {
        return Err(format!("{path} deref expression is unsupported"));
    };
    let IrExpr::Var {
        name: cursor,
        ty: cursor_ty,
        ..
    } = target.as_ref()
    else {
        return Err(format!("{path} post-increment target is unsupported"));
    };
    if !symbols.contains(cursor) {
        return Err(format!(
            "{path} post-increment cursor {cursor} is not declared"
        ));
    }
    let element_ty = readonly_pointer_slice_element_type(cursor_ty)
        .filter(|element_ty| is_u8(element_ty))
        .ok_or_else(|| {
            format!(
                "{path} post-increment cursor {cursor} has unsupported type {}",
                type_label(cursor_ty)
            )
        })?;
    let element_ty = emit_scalar_type(element_ty)
        .map_err(|detail| format!("{path} post-increment element has {detail}"))?;
    let deref_ty = emit_scalar_type(ty).map_err(|detail| format!("{path} deref has {detail}"))?;
    if deref_ty != element_ty {
        return Err(format!(
            "{path} deref type {deref_ty} does not match cursor element type {element_ty}"
        ));
    }
    let (source, cursor, declare_cursor) = if let Some(source) = context.byte_cursor_source(cursor)
    {
        if !symbols.contains(source) {
            return Err(format!("{path} byte source {source} is not declared"));
        }
        (
            emit_identifier(source, "byte source")?,
            emit_identifier(cursor, "byte cursor")?,
            false,
        )
    } else {
        let source = emit_identifier(cursor, "byte source")?;
        let cursor = first_available_named_temp(&format!("{source}_index"), symbols);
        (source, emit_identifier(&cursor, "byte cursor")?, true)
    };
    let temp = first_available_temp_name("byte", symbols);
    let indent = "    ".repeat(indent_level);
    let mut prelude = String::new();
    if declare_cursor {
        prelude.push_str(&format!("{indent}let mut {cursor}: usize = 0;\n"));
    }
    prelude.push_str(&format!(
        "{indent}let {temp}: {element_ty} = {source}[{cursor}];\n\
         {indent}{cursor} += 1;\n"
    ));
    Ok(EmittedExpr {
        prelude,
        expr: temp,
    })
}

fn emit_index_expr(
    base: &IrExpr,
    index: &IrExpr,
    ty: &IrType,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<String, String> {
    let IrExpr::Var {
        name: base_name,
        ty: base_ty,
        ..
    } = base
    else {
        return Err("index base must be Var".to_string());
    };
    let (element_ty, emitted_base) = if let Some(global) = context.readonly_global(base_name) {
        validate_global_expr_type(global, base_ty)?;
        (
            readonly_global_array_element_type(global)?,
            context.global_rust_name(base_name)?,
        )
    } else {
        if !symbols.contains(base_name) {
            return Err(format!("index base {base_name} is not declared"));
        }
        let element_ty = fixed_integer_array_element_type(base_ty)
            .or_else(|| readonly_pointer_slice_element_type(base_ty))
            .or_else(|| {
                context
                    .is_readonly_mutable_pointer_index_param(base_name)
                    .then(|| mutable_pointer_slice_element_type(base_ty))
                    .flatten()
            })
            .ok_or_else(|| {
                format!(
                    "index base {base_name} has unsupported type {}",
                    type_label(base_ty)
                )
            })?;
        (element_ty, emit_identifier(base_name, "index base")?)
    };
    let element_ty =
        emit_scalar_type(element_ty).map_err(|detail| format!("index element has {detail}"))?;
    let result_ty = emit_scalar_type(ty).map_err(|detail| format!("index result has {detail}"))?;
    if result_ty != element_ty {
        return Err(format!(
            "index result type {result_ty} does not match element type {element_ty}"
        ));
    }
    let index_ty =
        expr_type(index).ok_or_else(|| "index operand type is unsupported".to_string())?;
    if !is_integer_type(index_ty) {
        return Err(format!(
            "index operand type {} is unsupported",
            type_label(index_ty)
        ));
    }
    let index =
        emit_expr(index, symbols, context).map_err(|detail| format!("index operand {detail}"))?;
    Ok(format!("{emitted_base}[{index} as usize]"))
}

fn emit_index_expr_with_emitted_index(
    base: &IrExpr,
    emitted_index: &str,
    ty: &IrType,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<String, String> {
    let IrExpr::Var {
        name: base_name,
        ty: base_ty,
        ..
    } = base
    else {
        return Err("index base must be Var".to_string());
    };
    let (element_ty, emitted_base) = if let Some(global) = context.readonly_global(base_name) {
        validate_global_expr_type(global, base_ty)?;
        (
            readonly_global_array_element_type(global)?,
            context.global_rust_name(base_name)?,
        )
    } else {
        if !symbols.contains(base_name) {
            return Err(format!("index base {base_name} is not declared"));
        }
        let element_ty = fixed_integer_array_element_type(base_ty)
            .or_else(|| readonly_pointer_slice_element_type(base_ty))
            .or_else(|| {
                context
                    .is_readonly_mutable_pointer_index_param(base_name)
                    .then(|| mutable_pointer_slice_element_type(base_ty))
                    .flatten()
            })
            .ok_or_else(|| {
                format!(
                    "index base {base_name} has unsupported type {}",
                    type_label(base_ty)
                )
            })?;
        (element_ty, emit_identifier(base_name, "index base")?)
    };
    let element_ty =
        emit_scalar_type(element_ty).map_err(|detail| format!("index element has {detail}"))?;
    let result_ty = emit_scalar_type(ty).map_err(|detail| format!("index result has {detail}"))?;
    if result_ty != element_ty {
        return Err(format!(
            "index result type {result_ty} does not match element type {element_ty}"
        ));
    }
    Ok(format!("{emitted_base}[{emitted_index} as usize]"))
}

fn is_byte_cursor_cast_assignment(
    target: &IrExpr,
    value: &IrExpr,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<bool, String> {
    let IrExpr::Var {
        name: cursor,
        ty: cursor_ty,
        ..
    } = target
    else {
        return Ok(false);
    };
    let Some(source) = context.byte_cursor_source(cursor) else {
        return Ok(false);
    };
    let IrExpr::Cast {
        target,
        expr,
        implicit: false,
        ..
    } = value
    else {
        return Ok(false);
    };
    let IrExpr::Var {
        name: source_name,
        ty: source_ty,
        ..
    } = expr.as_ref()
    else {
        return Ok(false);
    };
    if source_name != source || !is_u8_pointer(cursor_ty) || !is_u8_pointer(target) {
        return Ok(false);
    }
    if !is_const_void_pointer(source_ty) {
        return Ok(false);
    }
    if !symbols.contains(cursor) {
        return Err(format!("byte cursor {cursor} is not declared"));
    }
    if !symbols.contains(source_name) {
        return Err(format!("byte cursor source {source_name} is not declared"));
    }
    Ok(true)
}

fn emit_post_increment_deref_return(
    value: &IrExpr,
    return_type: &IrType,
    indent_level: usize,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<Option<String>, String> {
    let IrExpr::Deref { ptr, ty, .. } = value else {
        return Ok(None);
    };
    let IrExpr::IncDec {
        target,
        op: IrIncDecOp::Inc,
        prefix: false,
        ..
    } = ptr.as_ref()
    else {
        return Ok(None);
    };
    let IrExpr::Var {
        name: base_name,
        ty: base_ty,
        ..
    } = target.as_ref()
    else {
        return Ok(None);
    };
    if !symbols.contains(base_name) {
        return Err(format!("post-increment cursor {base_name} is not declared"));
    }
    let element_ty = readonly_pointer_slice_element_type(base_ty)
        .filter(|element_ty| is_u8(element_ty))
        .ok_or_else(|| {
            format!(
                "post-increment cursor {base_name} has unsupported type {}",
                type_label(base_ty)
            )
        })?;
    let element_ty = emit_scalar_type(element_ty)
        .map_err(|detail| format!("post-increment element has {detail}"))?;
    let deref_ty = emit_scalar_type(ty).map_err(|detail| format!("deref result has {detail}"))?;
    let return_ty =
        emit_scalar_type(return_type).map_err(|detail| format!("return type has {detail}"))?;
    if deref_ty != element_ty || return_ty != element_ty {
        return Err(format!(
            "post-increment deref type must match element and return type: element={element_ty}, deref={deref_ty}, return={return_ty}"
        ));
    }
    let (slice_name, cursor_name, declare_cursor) =
        if let Some(source_name) = context.byte_cursor_source(base_name) {
            if !symbols.contains(source_name) {
                return Err(format!(
                    "post-increment source {source_name} is not declared"
                ));
            }
            (
                emit_identifier(source_name, "post-increment source")?,
                emit_identifier(base_name, "post-increment cursor")?,
                false,
            )
        } else {
            let slice_name = emit_identifier(base_name, "post-increment base")?;
            let cursor_name = emit_identifier(
                &first_available_named_temp(&format!("{slice_name}_index"), symbols),
                "post-increment cursor",
            )?;
            (slice_name, cursor_name, true)
        };
    let temp_name = first_available_temp_name("byte", symbols);
    let indent = "    ".repeat(indent_level);
    let mut rust = String::new();
    if declare_cursor {
        rust.push_str(&format!("{indent}let mut {cursor_name}: usize = 0;\n"));
    }
    rust.push_str(&format!(
        "{indent}let {temp_name}: {element_ty} = {slice_name}[{cursor_name}];\n\
         {indent}{cursor_name} += 1;\n\
         {indent}return {temp_name};\n"
    ));
    Ok(Some(rust))
}

fn first_available_temp_name(prefix: &str, symbols: &HashSet<String>) -> String {
    let mut index = 0usize;
    loop {
        let candidate = format!("{prefix}{index}");
        if !symbols.contains(&candidate) {
            return candidate;
        }
        index += 1;
    }
}

fn first_available_named_temp(preferred: &str, symbols: &HashSet<String>) -> String {
    if !symbols.contains(preferred) {
        return preferred.to_string();
    }
    let mut index = 1usize;
    loop {
        let candidate = format!("{preferred}{index}");
        if !symbols.contains(&candidate) {
            return candidate;
        }
        index += 1;
    }
}
