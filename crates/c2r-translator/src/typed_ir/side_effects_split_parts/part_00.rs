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
            if let Some(emitted) = emit_direct_inc_dec_comparison_value_expr(
                op,
                lhs,
                rhs,
                ty,
                symbols,
                context,
                indent_level,
                path,
            )? {
                return Ok(emitted);
            }
            if let Some(expr) = emit_comparison_value_expr(op, lhs, rhs, ty, symbols, context)
                .map_err(|detail| format!("{path} {detail}"))?
            {
                return Ok(EmittedExpr {
                    prelude: String::new(),
                    expr,
                });
            }
            validate_binary_side_effect_operand_order(lhs, rhs, path)?;
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
        IrExpr::LValueToRValue { target, expr, .. } => {
            if !is_integer_type(target) {
                return Err(format!(
                    "{path} lvalue-to-rvalue target {} is unsupported",
                    type_label(target)
                ));
            }
            let source_type = expr_type(expr)
                .ok_or_else(|| format!("{path} lvalue-to-rvalue source type is unsupported"))?;
            if !is_integer_type(source_type) {
                return Err(format!(
                    "{path} lvalue-to-rvalue source {} is unsupported",
                    type_label(source_type)
                ));
            }
            validate_expr_matches_type(expr, target, "lvalue-to-rvalue expr")
                .map_err(|detail| format!("{path} {detail}"))?;
            emit_expr_with_prelude(
                expr,
                symbols,
                context,
                indent_level,
                &format!("{path} lvalue-to-rvalue expr"),
            )
        }
        IrExpr::Unary {
            op, operand, ty, ..
        } => match op {
            IrUnOp::Neg => {
                validate_signed_unary_minus_operand(operand, ty)
                    .map_err(|detail| format!("{path} {detail}"))?;
                let emitted = emit_expr_with_prelude(
                    operand,
                    symbols,
                    context,
                    indent_level,
                    &format!("{path} unary minus operand"),
                )?;
                Ok(EmittedExpr {
                    prelude: emitted.prelude,
                    expr: format!("(-{})", emitted.expr),
                })
            }
            IrUnOp::Not => {
                let mut prelude_symbols = symbols.clone();
                let emitted = match emit_expr_with_prelude(
                    operand,
                    &mut prelude_symbols,
                    context,
                    indent_level,
                    &format!("{path} logical not operand"),
                ) {
                    Ok(emitted) => {
                        *symbols = prelude_symbols;
                        emitted
                    }
                    Err(_) => {
                        return Ok(EmittedExpr {
                            prelude: String::new(),
                            expr: emit_logical_not_value_expr(operand, ty, symbols, context)
                                .map_err(|detail| format!("{path} {detail}"))?,
                        });
                    }
                };
                if emitted.prelude.is_empty() {
                    return Ok(EmittedExpr {
                        prelude: String::new(),
                        expr: emit_logical_not_value_expr(operand, ty, symbols, context)
                            .map_err(|detail| format!("{path} {detail}"))?,
                    });
                }
                if !is_c_int_type(ty) {
                    return Err(format!(
                        "{path} logical not result type must be C int, got {}",
                        type_label(ty)
                    ));
                }
                let operand_ty = expr_type(operand).ok_or_else(|| {
                    format!("{path} logical not operand type is unsupported")
                })?;
                let operand_zero = zero_literal_for_type(operand_ty)
                    .map_err(|detail| format!("{path} logical not operand zero {detail}"))?;
                let one = emit_integer_literal(1, ty)
                    .map_err(|detail| format!("{path} logical not true literal {detail}"))?;
                let zero = emit_integer_literal(0, ty)
                    .map_err(|detail| format!("{path} logical not false literal {detail}"))?;
                Ok(EmittedExpr {
                    prelude: emitted.prelude,
                    expr: format!(
                        "(if {} == {operand_zero} {{ {one} }} else {{ {zero} }})",
                        emitted.expr
                    ),
                })
            }
            IrUnOp::BitNot => {
                validate_expr_matches_type(operand, ty, "bitnot operand")
                    .map_err(|detail| format!("{path} {detail}"))?;
                let emitted = emit_expr_with_prelude(
                    operand,
                    symbols,
                    context,
                    indent_level,
                    &format!("{path} bitnot operand"),
                )?;
                Ok(EmittedExpr {
                    prelude: emitted.prelude,
                    expr: format!("!{}", emitted.expr),
                })
            }
        },
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
        IrExpr::IncDec { .. } => emit_inc_dec_value_expr(expr, symbols, context, indent_level)
            .map_err(|detail| format!("{path} {detail}"))?
            .ok_or_else(|| format!("{path} inc/dec expression is unsupported")),
        IrExpr::Deref { ptr, ty, .. } if matches!(ptr.as_ref(), IrExpr::IncDec { .. }) => {
            emit_post_increment_byte_read_expr(ptr, ty, symbols, context, indent_level, path)
        }
        IrExpr::Deref { ptr, ty, .. } => {
            let expr = if let Some(expr) = emit_mutable_pointer_deref_expr(ptr, ty, symbols, context)
                .map_err(|detail| format!("{path} {detail}"))?
            {
                expr
            } else {
                emit_readonly_pointer_deref_expr(ptr, ty, symbols, context)
                    .map_err(|detail| format!("{path} {detail}"))?
            };
            Ok(EmittedExpr {
                prelude: String::new(),
                expr,
            })
        }
        _ => Ok(EmittedExpr {
            prelude: String::new(),
            expr: emit_expr(expr, symbols, context).map_err(|detail| format!("{path} {detail}"))?,
        }),
    }
}

fn emit_direct_inc_dec_comparison_value_expr(
    op: &IrBinOp,
    lhs: &IrExpr,
    rhs: &IrExpr,
    result_ty: &IrType,
    symbols: &mut HashSet<String>,
    context: &EmitContext,
    indent_level: usize,
    path: &str,
) -> Result<Option<EmittedExpr>, String> {
    let Some(emitted) = emit_direct_inc_dec_comparison_condition_expr(
        op,
        lhs,
        rhs,
        result_ty,
        symbols,
        context,
        indent_level,
        path,
    )?
    else {
        return Ok(None);
    };
    let one = emit_integer_literal(1, result_ty)
        .map_err(|detail| format!("{path} comparison true literal {detail}"))?;
    let zero = emit_integer_literal(0, result_ty)
        .map_err(|detail| format!("{path} comparison false literal {detail}"))?;

    Ok(Some(EmittedExpr {
        prelude: emitted.prelude,
        expr: format!("(if {} {{ {one} }} else {{ {zero} }})", emitted.expr),
    }))
}

fn emit_direct_inc_dec_comparison_condition_expr(
    op: &IrBinOp,
    lhs: &IrExpr,
    rhs: &IrExpr,
    result_ty: &IrType,
    symbols: &mut HashSet<String>,
    context: &EmitContext,
    indent_level: usize,
    path: &str,
) -> Result<Option<EmittedExpr>, String> {
    let Ok(op) = emit_comparison_op(op) else {
        return Ok(None);
    };
    let lhs_is_direct_inc_dec = matches!(lhs, IrExpr::IncDec { .. });
    let rhs_is_direct_inc_dec = matches!(rhs, IrExpr::IncDec { .. });
    let (inc_dec, other, inc_dec_is_lhs) = match (
        lhs_is_direct_inc_dec,
        rhs_is_direct_inc_dec,
    ) {
        (false, false) => return Ok(None),
        (true, true) => {
            return Err(format!(
                "{path} comparison cannot lower two direct increment/decrement operands"
            ));
        }
        (true, false) => (lhs, rhs, true),
        (false, true) => (rhs, lhs, false),
    };
    if scalar_inc_dec_assigned_var_name(inc_dec).is_none() {
        return Ok(None);
    }
    if let Some(callee) = find_call_callee(other) {
        return Err(format!(
            "{path} comparison operand call expression {callee} is unsupported"
        ));
    }
    if let Some(kind) = find_direct_inc_dec_comparison_memory_operand(other) {
        return Err(format!(
            "{path} comparison operand {kind} expression is unsupported"
        ));
    }
    if expr_has_inc_dec(other) {
        return Err(format!(
            "{path} comparison cannot lower more than one increment/decrement side effect"
        ));
    }
    validate_binary_side_effect_operand_order(lhs, rhs, path)?;
    validate_comparison_condition_types(lhs, rhs, result_ty, op)
        .map_err(|detail| format!("{path} {detail}"))?;

    let other = emit_expr(other, symbols, context).map_err(|detail| {
        format!(
            "{path} comparison {} {detail}",
            if inc_dec_is_lhs { "rhs" } else { "lhs" }
        )
    })?;
    let mut prelude_symbols = symbols.clone();
    let emitted_inc_dec = emit_expr_with_prelude(
        inc_dec,
        &mut prelude_symbols,
        context,
        indent_level,
        &format!(
            "{path} comparison {}",
            if inc_dec_is_lhs { "lhs" } else { "rhs" }
        ),
    )?;
    let (lhs, rhs) = if inc_dec_is_lhs {
        (emitted_inc_dec.expr, other)
    } else {
        (other, emitted_inc_dec.expr)
    };
    *symbols = prelude_symbols;

    Ok(Some(EmittedExpr {
        prelude: emitted_inc_dec.prelude,
        expr: format!("({lhs} {op} {rhs})"),
    }))
}

fn find_direct_inc_dec_comparison_memory_operand(expr: &IrExpr) -> Option<&'static str> {
    match expr {
        IrExpr::Deref { .. } => Some("deref"),
        IrExpr::Member { .. } => Some("member"),
        IrExpr::Binary { lhs, rhs, .. } => find_direct_inc_dec_comparison_memory_operand(lhs)
            .or_else(|| find_direct_inc_dec_comparison_memory_operand(rhs)),
        IrExpr::Unary { operand, .. }
        | IrExpr::Cast { expr: operand, .. }
        | IrExpr::LValueToRValue { expr: operand, .. }
        | IrExpr::ArrayToPointerDecay { expr: operand, .. }
        | IrExpr::FunctionToPointerDecay { expr: operand, .. }
        | IrExpr::AddrOf { operand, .. }
        | IrExpr::IncDec {
            target: operand, ..
        } => find_direct_inc_dec_comparison_memory_operand(operand),
        IrExpr::Conditional {
            condition,
            then_expr,
            else_expr,
            ..
        } => find_direct_inc_dec_comparison_memory_operand(condition)
            .or_else(|| find_direct_inc_dec_comparison_memory_operand(then_expr))
            .or_else(|| find_direct_inc_dec_comparison_memory_operand(else_expr)),
        IrExpr::Index { .. } => Some("index"),
        IrExpr::ArrayLiteral { elements, .. } => elements
            .iter()
            .find_map(find_direct_inc_dec_comparison_memory_operand),
        IrExpr::Call { args, .. } => args
            .iter()
            .find_map(find_direct_inc_dec_comparison_memory_operand),
        IrExpr::LitInt { .. }
        | IrExpr::NullPtr { .. }
        | IrExpr::Var { .. }
        | IrExpr::Unsupported { .. } => None,
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
    let side_effect_args = side_effect_call_args(args)?;
    if side_effect_args.is_empty() {
        return Ok(None);
    }
    validate_bounded_call_args(args, context).map_err(|detail| format!("{path} {detail}"))?;

    let callee = emit_side_effect_call_callee(callee, ty, path)?;
    let mut prelude = String::new();
    let mut emitted_args = Vec::with_capacity(args.len());
    for (index, arg) in args.iter().enumerate() {
        if side_effect_args
            .iter()
            .any(|(side_effect_index, _)| *side_effect_index == index)
        {
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

fn validate_binary_side_effect_operand_order(
    lhs: &IrExpr,
    rhs: &IrExpr,
    path: &str,
) -> Result<(), String> {
    if let Some(assigned_var) = side_effect_expr_assigned_var_name(lhs)? {
        if expr_mentions_var(rhs, assigned_var) {
            return Err(format!(
                "{path} binary rhs reads variable {assigned_var} modified by lhs side-effect expression"
            ));
        }
    }
    if let Some(assigned_var) = side_effect_expr_assigned_var_name(rhs)? {
        if expr_mentions_var(lhs, assigned_var) {
            return Err(format!(
                "{path} binary lhs reads variable {assigned_var} modified by rhs side-effect expression"
            ));
        }
    }
    Ok(())
}

fn side_effect_call_args(args: &[IrExpr]) -> Result<Vec<(usize, &str)>, String> {
    let mut found = Vec::new();
    for (index, arg) in args.iter().enumerate() {
        let Some(assigned_var) = side_effect_expr_assigned_var_name(arg)? else {
            continue;
        };
        if found
            .iter()
            .any(|(_, existing_var)| *existing_var == assigned_var)
        {
            return Err(format!(
                "call arguments cannot modify variable {assigned_var} more than once"
            ));
        }
        found.push((index, assigned_var));
    }
    Ok(found)
}

fn side_effect_expr_assigned_var_name(expr: &IrExpr) -> Result<Option<&str>, String> {
    if let Some(name) = scalar_inc_dec_assigned_var_name(expr) {
        return Ok(Some(name.as_str()));
    }
    if let Some(name) = member_inc_dec_assigned_base_var_name(expr) {
        return Ok(Some(name.as_str()));
    }
    let IrExpr::Call { args, .. } = expr else {
        return Ok(None);
    };
    let found = side_effect_call_args(args)?;
    match found.as_slice() {
        [] => Ok(None),
        [(_, name)] => Ok(Some(*name)),
        _ => Err(
            "nested call argument cannot use increment/decrement value semantics for more than one variable"
                .to_string(),
        ),
    }
}

fn member_inc_dec_assigned_base_var_name(expr: &IrExpr) -> Option<&String> {
    let IrExpr::IncDec { target, ty, .. } = expr else {
        return None;
    };
    let IrExpr::Member {
        base,
        ty: target_ty,
        is_arrow: true,
        ..
    } = target.as_ref()
    else {
        return None;
    };
    let IrExpr::Var { name, .. } = base.as_ref() else {
        return None;
    };
    (target_ty == ty && is_integer_type(target_ty)).then_some(name)
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
    if side_effect_call_args(args)?.is_empty() {
        return Ok(None);
    }
    emit_call_expr_with_prelude(callee, args, ty, symbols, context, indent_level, path).map(Some)
}

fn emit_prefix_inc_dec_value_expr(
    expr: &IrExpr,
    symbols: &HashSet<String>,
    context: &EmitContext,
    indent_level: usize,
) -> Result<Option<EmittedExpr>, String> {
    let IrExpr::IncDec {
        target,
        op,
        prefix: true,
        ty,
        ..
    } = expr
    else {
        return Ok(None);
    };
    let indent = "    ".repeat(indent_level);

    if let Some(line) = emit_prefix_inc_dec_statement(expr, symbols)? {
        let IrExpr::Var { name, .. } = target.as_ref() else {
            return Ok(None);
        };
        let name = emit_identifier(name, "prefix inc/dec value target")?;
        return Ok(Some(EmittedExpr {
            prelude: format!("{indent}{line}\n"),
            expr: name,
        }));
    }

    let Some((target_name, target_ty)) =
        emit_member_inc_dec_value_target(target, ty, symbols, context, "prefix inc/dec target")?
    else {
        return Ok(None);
    };
    let one = emit_integer_literal(1, target_ty)
        .map_err(|detail| format!("prefix inc/dec step {detail}"))?;
    let rhs = emit_inc_dec_assignment_rhs(&target_name, target_ty, op, &one).ok_or_else(|| {
        format!(
            "prefix inc/dec target {target_name} has unsupported type {}",
            type_label(target_ty)
        )
    })?;
    Ok(Some(EmittedExpr {
        prelude: format!("{indent}{target_name} = {rhs};\n"),
        expr: target_name,
    }))
}

fn emit_postfix_inc_dec_value_expr(
    expr: &IrExpr,
    symbols: &mut HashSet<String>,
    context: &EmitContext,
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
    let (name, target_ty) = if let IrExpr::Var {
        name,
        ty: target_ty,
        ..
    } = target.as_ref()
    {
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
        (emit_identifier(name, "postfix inc/dec target")?, target_ty)
    } else if let Some((target_name, target_ty)) =
        emit_member_inc_dec_value_target(target, ty, symbols, context, "postfix inc/dec target")?
    {
        (target_name, target_ty)
    } else {
        return Ok(None);
    };
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
    context: &EmitContext,
    indent_level: usize,
) -> Result<Option<EmittedExpr>, String> {
    if let Some(emitted) = emit_prefix_inc_dec_value_expr(expr, symbols, context, indent_level)? {
        return Ok(Some(emitted));
    }
    emit_postfix_inc_dec_value_expr(expr, symbols, context, indent_level)
}

fn emit_member_inc_dec_value_target<'a>(
    target: &'a IrExpr,
    result_ty: &IrType,
    symbols: &HashSet<String>,
    context: &EmitContext,
    path: &str,
) -> Result<Option<(String, &'a IrType)>, String> {
    let IrExpr::Member {
        field,
        ty: target_ty,
        is_arrow,
        ..
    } = target
    else {
        return Ok(None);
    };
    if !*is_arrow {
        return Ok(None);
    }
    if target_ty != result_ty {
        return Err(format!(
            "{path} field {field} type {} does not match result type {}",
            type_label(target_ty),
            type_label(result_ty)
        ));
    }
    if !is_integer_type(target_ty) {
        return Err(format!(
            "{path} field {field} has unsupported type {}",
            type_label(target_ty)
        ));
    }
    let Some(target_name) = emit_mutable_record_pointer_member_assignment_target(
        target, symbols, context,
    )
    .map_err(|detail| format!("{path} {detail}"))?
    else {
        return Ok(None);
    };
    Ok(Some((target_name, target_ty)))
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
