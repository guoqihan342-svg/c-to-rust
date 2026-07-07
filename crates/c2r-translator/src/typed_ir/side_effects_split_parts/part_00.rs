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
        emit_side_effect_call_expr(callee, args, ty, symbols, context, indent_level, path)?
    {
        return Ok(emitted);
    }
    Ok(EmittedExpr {
        prelude: String::new(),
        expr: emit_call_expr(callee, args, ty, symbols, context)
            .map_err(|detail| format!("{path} {detail}"))?,
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

fn emit_side_effect_call_expr(
    callee: &str,
    args: &[IrExpr],
    ty: &IrType,
    symbols: &mut HashSet<String>,
    context: &EmitContext,
    indent_level: usize,
    path: &str,
) -> Result<Option<EmittedExpr>, String> {
    let Some((side_effect_index, _)) = single_side_effect_call_arg(args)? else {
        return Ok(None);
    };
    validate_bounded_call_args(args, context).map_err(|detail| format!("{path} {detail}"))?;

    let callee = emit_side_effect_call_callee(callee, ty, path)?;
    let mut prelude = String::new();
    let mut emitted_args = Vec::with_capacity(args.len());
    for (index, arg) in args.iter().enumerate() {
        if index == side_effect_index {
            let emitted = emit_expr_with_prelude(
                arg,
                symbols,
                context,
                indent_level,
                &format!("{path} call arg[{index}]"),
            )?;
            prelude.push_str(&emitted.prelude);
            emitted_args.push(emitted.expr);
        } else {
            emitted_args.push(
                emit_call_arg_expr(arg, symbols, context)
                    .map_err(|detail| format!("{path} call arg[{index}] {detail}"))?,
            );
        }
    }
    Ok(Some(EmittedExpr {
        prelude,
        expr: format!("{callee}({})", emitted_args.join(", ")),
    }))
}

fn single_side_effect_call_arg(args: &[IrExpr]) -> Result<Option<(usize, &str)>, String> {
    let mut found = None;
    for (index, arg) in args.iter().enumerate() {
        let Some(assigned_var) = side_effect_expr_assigned_var_name(arg)? else {
            continue;
        };
        if found.is_some() {
            return Err(
                "call arguments cannot use increment/decrement value semantics more than once"
                    .to_string(),
            );
        }
        found = Some((index, assigned_var));
    }
    Ok(found)
}

fn side_effect_expr_assigned_var_name(expr: &IrExpr) -> Result<Option<&str>, String> {
    if let Some(name) = scalar_inc_dec_assigned_var_name(expr) {
        return Ok(Some(name.as_str()));
    }
    let IrExpr::Call { args, .. } = expr else {
        return Ok(None);
    };
    single_side_effect_call_arg(args).map(|found| found.map(|(_, name)| name))
}

fn expr_mentions_var(expr: &IrExpr, expected: &str) -> bool {
    match expr {
        IrExpr::Var { name, .. } => name == expected,
        IrExpr::Binary { lhs, rhs, .. } => {
            expr_mentions_var(lhs, expected) || expr_mentions_var(rhs, expected)
        }
        IrExpr::Unary { operand, .. }
        | IrExpr::Cast { expr: operand, .. }
        | IrExpr::LValueToRValue { expr: operand, .. }
        | IrExpr::ArrayToPointerDecay { expr: operand, .. }
        | IrExpr::FunctionToPointerDecay { expr: operand, .. }
        | IrExpr::AddrOf { operand, .. } => expr_mentions_var(operand, expected),
        IrExpr::Conditional {
            condition,
            then_expr,
            else_expr,
            ..
        } => {
            expr_mentions_var(condition, expected)
                || expr_mentions_var(then_expr, expected)
                || expr_mentions_var(else_expr, expected)
        }
        IrExpr::Index { base, index, .. } => {
            expr_mentions_var(base, expected) || expr_mentions_var(index, expected)
        }
        IrExpr::Member { base, .. } => expr_mentions_var(base, expected),
        IrExpr::ArrayLiteral { elements, .. } => {
            elements.iter().any(|element| expr_mentions_var(element, expected))
        }
        IrExpr::Call { args, .. } => args.iter().any(|arg| expr_mentions_var(arg, expected)),
        IrExpr::IncDec { target, .. } => expr_mentions_var(target, expected),
        IrExpr::Deref { ptr, .. } => expr_mentions_var(ptr, expected),
        IrExpr::LitInt { .. }
        | IrExpr::NullPtr { .. }
        | IrExpr::Unsupported { .. } => false,
    }
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
    if single_side_effect_call_arg(args)?.is_none() {
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
