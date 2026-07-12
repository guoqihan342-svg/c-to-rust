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
