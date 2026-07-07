/// Emits an expression and any required prelude without losing side effects.
///
/// Most expressions lower to a single Rust value, but post-increment byte reads
/// and nested expressions can require preceding statements. Keeping that split
/// explicit prevents the emitter from reordering C-side effects or pretending
/// an unsupported side-effect pattern is a pure value expression.
fn emit_expr_with_prelude(
    expr: &IrExpr,
    symbols: &mut HashSet<String>,
    context: &EmitContext,
    indent_level: usize,
    path: &str,
) -> Result<EmittedExpr, String> {
    match expr {
        IrExpr::Binary {
            op, lhs, rhs, ty, ..
        } => {
            if let Some(expr) = emit_short_circuit_value_expr(op, lhs, rhs, ty, symbols, context)
                .map_err(|detail| format!("{path} {detail}"))?
            {
                return Ok(EmittedExpr {
                    prelude: String::new(),
                    expr,
                });
            }
            if let Some(expr) = emit_comparison_value_expr(op, lhs, rhs, ty, symbols, context)
                .map_err(|detail| format!("{path} {detail}"))?
            {
                return Ok(EmittedExpr {
                    prelude: String::new(),
                    expr,
                });
            }
            let op_token = emit_binary_op(op).map_err(|detail| format!("{path} {detail}"))?;
            validate_binary_operand_types(op_token, lhs, rhs, ty)
                .map_err(|detail| format!("{path} {detail}"))?;
            validate_binary_runtime_contract(op, lhs, rhs, ty, &context.policy)
                .map_err(|detail| format!("{path} {detail}"))?;
            let lhs = emit_expr_with_prelude(
                lhs,
                symbols,
                context,
                indent_level,
                &format!("{path} binary lhs"),
            )?;
            let rhs = emit_expr_with_prelude(
                rhs,
                symbols,
                context,
                indent_level,
                &format!("{path} binary rhs"),
            )?;
            Ok(EmittedExpr {
                prelude: format!("{}{}", lhs.prelude, rhs.prelude),
                expr: emit_binary_result_expr(op, op_token, &lhs.expr, &rhs.expr, ty),
            })
        }
        IrExpr::Cast { target, expr, .. } => {
            if !is_integer_type(target) {
                return Err(format!(
                    "{path} cast target {} is unsupported",
                    type_label(target)
                ));
            }
            let source_type =
                expr_type(expr).ok_or_else(|| format!("{path} cast source type is unsupported"))?;
            if !is_integer_type(source_type) {
                return Err(format!(
                    "{path} cast source {} is unsupported",
                    type_label(source_type)
                ));
            }
            let target = emit_scalar_type(target)
                .map_err(|detail| format!("{path} cast target has {detail}"))?;
            let emitted = emit_expr_with_prelude(
                expr,
                symbols,
                context,
                indent_level,
                &format!("{path} cast expr"),
            )?;
            Ok(EmittedExpr {
                prelude: emitted.prelude,
                expr: format!("({} as {target})", emitted.expr),
            })
        }
        IrExpr::ArrayToPointerDecay { .. } => Err(format!(
            "{path} array-to-pointer decay requires explicit lowering evidence"
        )),
        IrExpr::FunctionToPointerDecay { .. } => Err(format!(
            "{path} function-to-pointer decay creates a function pointer value and requires explicit function-pointer lowering evidence"
        )),
        IrExpr::Conditional {
            condition,
            then_expr,
            else_expr,
            ty,
            ..
        } => Ok(EmittedExpr {
            prelude: String::new(),
            expr: emit_conditional_value_expr(
                condition, then_expr, else_expr, ty, symbols, context,
            )
            .map_err(|detail| format!("{path} {detail}"))?,
        }),
        IrExpr::Index {
            base, index, ty, ..
        } => {
            let index = emit_expr_with_prelude(
                index,
                symbols,
                context,
                indent_level,
                &format!("{path} index operand"),
            )?;
            let expr = emit_index_expr_with_emitted_index(base, &index.expr, ty, symbols, context)
                .map_err(|detail| format!("{path} {detail}"))?;
            Ok(EmittedExpr {
                prelude: index.prelude,
                expr,
            })
        }
        IrExpr::ArrayLiteral { .. } => Err(format!(
            "{path} array literal expression is only supported as a declaration initializer"
        )),
        IrExpr::Call {
            callee, args, ty, ..
        } => emit_call_expr_with_prelude(
            callee,
            args,
            ty,
            symbols,
            context,
            indent_level,
            path,
        ),
        IrExpr::IncDec { .. } => emit_inc_dec_value_expr(expr, symbols, indent_level)
            .map_err(|detail| format!("{path} {detail}"))?
            .ok_or_else(|| format!("{path} inc/dec expression is unsupported")),
        IrExpr::Deref { ptr, ty, .. } if matches!(ptr.as_ref(), IrExpr::IncDec { .. }) => {
            emit_post_increment_byte_read_expr(ptr, ty, symbols, context, indent_level, path)
        }
        IrExpr::Deref { ptr, ty, .. } => Ok(EmittedExpr {
            prelude: String::new(),
            expr: emit_readonly_pointer_deref_expr(ptr, ty, symbols, context)
                .map_err(|detail| format!("{path} {detail}"))?,
        }),
        _ => Ok(EmittedExpr {
            prelude: String::new(),
            expr: emit_expr(expr, symbols, context).map_err(|detail| format!("{path} {detail}"))?,
        }),
    }
}

fn emit_call_expr_with_prelude(
    callee: &str,
    args: &[IrExpr],
    ty: &IrType,
    symbols: &mut HashSet<String>,
    context: &EmitContext,
    indent_level: usize,
    path: &str,
) -> Result<EmittedExpr, String> {
    if let Some(emitted) =
        emit_nested_single_inc_dec_call_expr(callee, args, ty, symbols, context, indent_level, path)?
    {
        return Ok(emitted);
    }
    if args.len() != 1 || scalar_inc_dec_assigned_var_name(&args[0]).is_none() {
        return Ok(EmittedExpr {
            prelude: String::new(),
            expr: emit_call_expr(callee, args, ty, symbols, context)
                .map_err(|detail| format!("{path} {detail}"))?,
        });
    }

    let callee = emit_side_effect_call_callee(callee, ty, path)?;
    let arg = emit_inc_dec_value_expr(&args[0], symbols, indent_level)
        .map_err(|detail| format!("{path} call arg[0] {detail}"))?
        .ok_or_else(|| format!("{path} call arg[0] inc/dec expression is unsupported"))?;
    Ok(EmittedExpr {
        prelude: arg.prelude,
        expr: format!("{callee}({})", arg.expr),
    })
}

fn emit_side_effect_call_callee(callee: &str, ty: &IrType, path: &str) -> Result<String, String> {
    let callee =
        emit_identifier(callee, "call callee").map_err(|detail| format!("{path} {detail}"))?;
    if matches!(
        callee.as_str(),
        "assert" | "abs" | "strlen" | "strnlen" | "memcmp"
    ) {
        return Err(format!(
            "{path} call callee {callee} cannot use increment/decrement value arguments"
        ));
    }
    if reserved_c_macro_or_stdlib_callee(&callee) {
        return Err(format!(
            "{path} call callee \"{callee}\" is reserved C macro/stdlib/extern surface and requires explicit lowering or extern binding"
        ));
    }
    if matches!(ty.kind, IrTypeKind::Pointer { .. }) {
        return Err(format!(
            "{path} call result has pointer value return {} requires explicit ownership/lifetime/ABI lowering",
            type_label(ty)
        ));
    }
    if !is_void_type(ty) {
        emit_scalar_type(ty).map_err(|detail| format!("{path} call result has {detail}"))?;
    }

    Ok(callee)
}

fn emit_nested_single_inc_dec_call_expr(
    callee: &str,
    args: &[IrExpr],
    ty: &IrType,
    symbols: &mut HashSet<String>,
    context: &EmitContext,
    indent_level: usize,
    path: &str,
) -> Result<Option<EmittedExpr>, String> {
    let [IrExpr::Call {
        callee: inner_callee,
        args: inner_args,
        ty: inner_ty,
        ..
    }] = args
    else {
        return Ok(None);
    };
    if !side_effect_single_chain_nested_call_with_scalar_inc_dec_leaf(args) {
        return Ok(None);
    }

    let callee = emit_side_effect_call_callee(callee, ty, path)?;
    let inner = emit_call_expr_with_prelude(
        inner_callee,
        inner_args,
        inner_ty,
        symbols,
        context,
        indent_level,
        &format!("{path} call arg[0]"),
    )?;
    Ok(Some(EmittedExpr {
        prelude: inner.prelude,
        expr: format!("{callee}({})", inner.expr),
    }))
}

fn side_effect_single_chain_nested_call_with_scalar_inc_dec_leaf(args: &[IrExpr]) -> bool {
    let [arg] = args else {
        return false;
    };
    side_effect_single_chain_nested_call_expr_with_scalar_inc_dec_leaf(arg)
}

fn side_effect_single_chain_nested_call_expr_with_scalar_inc_dec_leaf(expr: &IrExpr) -> bool {
    let IrExpr::Call { args, .. } = expr else {
        return false;
    };
    let [arg] = args.as_slice() else {
        return false;
    };
    scalar_inc_dec_assigned_var_name(arg).is_some()
        || side_effect_single_chain_nested_call_expr_with_scalar_inc_dec_leaf(arg)
}

fn emit_single_inc_dec_call_statement_expr(
    expr: &IrExpr,
    symbols: &mut HashSet<String>,
    context: &EmitContext,
    indent_level: usize,
    path: &str,
) -> Result<Option<EmittedExpr>, String> {
    let IrExpr::Call {
        callee, args, ty, ..
    } = expr
    else {
        return Ok(None);
    };
    if args.len() != 1 || scalar_inc_dec_assigned_var_name(&args[0]).is_none() {
        return Ok(None);
    }
    emit_call_expr_with_prelude(callee, args, ty, symbols, context, indent_level, path).map(Some)
}

fn emit_prefix_inc_dec_value_expr(
    expr: &IrExpr,
    symbols: &HashSet<String>,
    indent_level: usize,
) -> Result<Option<EmittedExpr>, String> {
    let IrExpr::IncDec {
        target,
        prefix: true,
        ..
    } = expr
    else {
        return Ok(None);
    };
    let Some(line) = emit_prefix_inc_dec_statement(expr, symbols)? else {
        return Ok(None);
    };
    let IrExpr::Var { name, .. } = target.as_ref() else {
        return Ok(None);
    };

    let indent = "    ".repeat(indent_level);
    let name = emit_identifier(name, "prefix inc/dec value target")?;
    Ok(Some(EmittedExpr {
        prelude: format!("{indent}{line}\n"),
        expr: name,
    }))
}

fn emit_postfix_inc_dec_value_expr(
    expr: &IrExpr,
    symbols: &mut HashSet<String>,
    indent_level: usize,
) -> Result<Option<EmittedExpr>, String> {
    let IrExpr::IncDec {
        target,
        op,
        prefix: false,
        ty,
        ..
    } = expr
    else {
        return Ok(None);
    };
    let IrExpr::Var {
        name,
        ty: target_ty,
        ..
    } = target.as_ref()
    else {
        return Ok(None);
    };
    if !symbols.contains(name) {
        return Err(format!("postfix inc/dec target {name} is not declared"));
    }
    if target_ty != ty {
        return Err(format!(
            "postfix inc/dec target {name} type {} does not match result type {}",
            type_label(target_ty),
            type_label(ty)
        ));
    }
    if !is_integer_type(target_ty) {
        return Err(format!(
            "postfix inc/dec target {name} has unsupported type {}",
            type_label(target_ty)
        ));
    }

    let name = emit_identifier(name, "postfix inc/dec target")?;
    let one = emit_integer_literal(1, target_ty)
        .map_err(|detail| format!("postfix inc/dec step {detail}"))?;
    let rhs = emit_inc_dec_assignment_rhs(&name, target_ty, op, &one).ok_or_else(|| {
        format!(
            "postfix inc/dec target {name} has unsupported type {}",
            type_label(target_ty)
        )
    })?;
    let temp_prefix = match op {
        IrIncDecOp::Inc => "post_inc_value",
        IrIncDecOp::Dec => "post_dec_value",
    };
    let temp = first_available_named_temp(temp_prefix, symbols);
    symbols.insert(temp.clone());
    let temp = emit_identifier(&temp, "postfix inc/dec value snapshot")?;
    let snapshot_ty = emit_scalar_type(target_ty)
        .map_err(|detail| format!("postfix inc/dec snapshot has {detail}"))?;
    let indent = "    ".repeat(indent_level);

    Ok(Some(EmittedExpr {
        prelude: format!("{indent}let {temp}: {snapshot_ty} = {name};\n{indent}{name} = {rhs};\n"),
        expr: temp,
    }))
}

fn emit_inc_dec_value_expr(
    expr: &IrExpr,
    symbols: &mut HashSet<String>,
    indent_level: usize,
) -> Result<Option<EmittedExpr>, String> {
    if let Some(emitted) = emit_prefix_inc_dec_value_expr(expr, symbols, indent_level)? {
        return Ok(Some(emitted));
    }
    emit_postfix_inc_dec_value_expr(expr, symbols, indent_level)
}

fn emit_inc_dec_assignment_rhs(
    name: &str,
    target_ty: &IrType,
    op: &IrIncDecOp,
    one: &str,
) -> Option<String> {
    let bin_op = match op {
        IrIncDecOp::Inc => IrBinOp::Add,
        IrIncDecOp::Dec => IrBinOp::Sub,
    };
    if let Some(method) = unsigned_wrapping_method(&bin_op, target_ty) {
        Some(format!("{name}.{method}({one})"))
    } else if let Some((method, message)) = signed_checked_method(&bin_op, target_ty) {
        Some(format!("{name}.{method}({one}).expect(\"{message}\")"))
    } else {
        None
    }
}

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
