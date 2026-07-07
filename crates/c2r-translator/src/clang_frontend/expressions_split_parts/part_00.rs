#[cfg(feature = "typed-ir")]
fn expr_skeleton_from_ast(expr: &Value) -> Result<ClangExprSkeleton, ClangFrontendError> {
    expr_skeleton_from_ast_with_options(expr, false)
}

#[cfg(feature = "typed-ir")]
fn value_expr_skeleton_from_ast(expr: &Value) -> Result<ClangExprSkeleton, ClangFrontendError> {
    expr_skeleton_from_ast_with_options(expr, true)
}

#[cfg(feature = "typed-ir")]
fn condition_expr_skeleton_from_ast(expr: &Value) -> Result<ClangExprSkeleton, ClangFrontendError> {
    expr_skeleton_from_ast_with_options(expr, true)
}

#[cfg(feature = "typed-ir")]
fn while_condition_expr_skeleton_from_ast(
    expr: &Value,
) -> Result<ClangExprSkeleton, ClangFrontendError> {
    if string_field(expr, "kind").as_deref() == Some("UnaryOperator")
        && string_field(expr, "opcode").as_deref() == Some("--")
        && expr.get("isPostfix").and_then(Value::as_bool) == Some(false)
    {
        let skeleton = inc_dec_expr_skeleton_from_ast(expr, true, true)?;
        let ClangExprSkeleton::IncDec {
            target,
            op: ClangIncDecOperator::Dec,
            prefix: true,
            ty,
        } = &skeleton
        else {
            return Ok(skeleton);
        };
        let ClangExprSkeleton::DeclRef { ty: target_ty, .. } = target.as_ref() else {
            return Ok(ClangExprSkeleton::Unsupported {
                node: "UnaryOperator".to_string(),
                reason: "while prefix decrement condition must target a simple integer variable"
                    .to_string(),
            });
        };
        if !matches!(&target_ty.kind, ClangTypeKind::Integer { .. })
            || !compound_assignment_types_match(target_ty, ty)
        {
            return Ok(ClangExprSkeleton::Unsupported {
                node: "UnaryOperator".to_string(),
                reason: format!(
                    "while prefix decrement target type {} is unsupported",
                    target_ty.canonical
                ),
            });
        }
        return Ok(skeleton);
    }
    condition_expr_skeleton_from_ast(expr)
}

#[cfg(feature = "typed-ir")]
/// Converts one clang JSON expression into the conservative skeleton layer.
///
/// This is the AST semantic boundary before typed IR. It accepts only node
/// shapes whose C meaning is explicitly modeled, preserves integral casts when
/// value contexts need them, and returns `Unsupported` skeletons or structured
/// errors instead of guessing through unfamiliar clang nodes.
fn expr_skeleton_from_ast_with_options(
    expr: &Value,
    preserve_integral_casts: bool,
) -> Result<ClangExprSkeleton, ClangFrontendError> {
    match string_field(expr, "kind").as_deref() {
        Some("ImplicitCastExpr") => {
            let cast_kind = string_field(expr, "castKind");
            let operand = inner(expr).first().ok_or_else(|| ClangFrontendError {
                kind: "invalid_clang_expr".to_string(),
                message: "ImplicitCastExpr is missing operand".to_string(),
            })?;
            let preserve_integral_conversion =
                (preserve_integral_casts || cast_kind.as_deref() == Some("NoOp"))
                    && is_integral_conversion_cast_expr(expr);
            let operand = expr_skeleton_from_ast_with_options(
                operand,
                preserve_integral_casts || preserve_integral_conversion,
            )?;
            if cast_kind.as_deref() == Some("FunctionToPointerDecay") {
                return Ok(ClangExprSkeleton::FunctionToPointerDecay {
                    target: expr_type(expr)?,
                    expr: Box::new(operand),
                });
            }
            if cast_kind.as_deref() == Some("NullToPointer") {
                return null_pointer_skeleton_from_cast(expr, &operand, "ImplicitCastExpr");
            }
            if cast_kind.as_deref() == Some("ArrayToPointerDecay") {
                return Ok(ClangExprSkeleton::ArrayToPointerDecay {
                    target: expr_type(expr)?,
                    expr: Box::new(operand),
                });
            }
            if preserve_integral_conversion {
                return Ok(ClangExprSkeleton::Cast {
                    target: expr_type(expr)?,
                    expr: Box::new(operand),
                    implicit: true,
                });
            }
            if preserve_integral_casts && is_integer_lvalue_to_rvalue_cast_expr(expr) {
                return Ok(ClangExprSkeleton::LValueToRValue {
                    target: expr_type(expr)?,
                    expr: Box::new(operand),
                });
            }
            match cast_kind.as_deref() {
                Some("LValueToRValue" | "NoOp") => Ok(operand),
                Some(cast_kind) => Ok(ClangExprSkeleton::Unsupported {
                    node: "ImplicitCastExpr".to_string(),
                    reason: format!(
                        "castKind {cast_kind} is outside the current clang lowering skeleton"
                    ),
                }),
                None => Ok(ClangExprSkeleton::Unsupported {
                    node: "ImplicitCastExpr".to_string(),
                    reason: "missing castKind is outside the current clang lowering skeleton"
                        .to_string(),
                }),
            }
        }
        Some("ParenExpr") => inner(expr)
            .first()
            .ok_or_else(|| ClangFrontendError {
                kind: "invalid_clang_expr".to_string(),
                message: "ParenExpr is missing operand".to_string(),
            })
            .and_then(|operand| {
                expr_skeleton_from_ast_with_options(operand, preserve_integral_casts)
            }),
        Some("DeclRefExpr") => {
            let name = expr
                .get("referencedDecl")
                .and_then(|value| string_field(value, "name"))
                .ok_or_else(|| ClangFrontendError {
                    kind: "invalid_decl_ref_expr".to_string(),
                    message: "DeclRefExpr is missing referencedDecl.name".to_string(),
                })?;
            let ty = expr_type(expr)?;
            Ok(ClangExprSkeleton::DeclRef { name, ty })
        }
        Some("IntegerLiteral") => {
            let spelling = string_field(expr, "value").ok_or_else(|| ClangFrontendError {
                kind: "invalid_integer_literal".to_string(),
                message: "IntegerLiteral is missing value".to_string(),
            })?;
            let value = spelling
                .parse::<u64>()
                .map_err(|error| ClangFrontendError {
                    kind: "invalid_integer_literal".to_string(),
                    message: format!("IntegerLiteral value is not u64: {error}"),
                })?;
            let ty = expr_type(expr)?;
            Ok(ClangExprSkeleton::IntegerLiteral {
                value,
                spelling,
                ty,
            })
        }
        Some("UnaryExprOrTypeTraitExpr") => unary_expr_or_type_trait_skeleton_from_ast(expr),
        Some("BinaryOperator") => {
            let op = match string_field(expr, "opcode").as_deref() {
                Some("+") => ClangBinaryOperator::Add,
                Some("-") => ClangBinaryOperator::Sub,
                Some("*") => ClangBinaryOperator::Mul,
                Some("/") => ClangBinaryOperator::Div,
                Some("%") => ClangBinaryOperator::Mod,
                Some("&") => ClangBinaryOperator::BitAnd,
                Some("|") => ClangBinaryOperator::BitOr,
                Some("^") => ClangBinaryOperator::BitXor,
                Some("<<") => ClangBinaryOperator::Shl,
                Some(">>") => ClangBinaryOperator::Shr,
                Some("&&") => ClangBinaryOperator::LogAnd,
                Some("||") => ClangBinaryOperator::LogOr,
                Some("==") => ClangBinaryOperator::Eq,
                Some("!=") => ClangBinaryOperator::Neq,
                Some("<") => ClangBinaryOperator::Lt,
                Some("<=") => ClangBinaryOperator::Le,
                Some(">") => ClangBinaryOperator::Gt,
                Some(">=") => ClangBinaryOperator::Ge,
                Some(opcode) => {
                    return Ok(ClangExprSkeleton::Unsupported {
                        node: "BinaryOperator".to_string(),
                        reason: format!("opcode {opcode} is outside the current skeleton"),
                    });
                }
                None => {
                    return Err(ClangFrontendError {
                        kind: "invalid_binary_operator".to_string(),
                        message: "BinaryOperator is missing opcode".to_string(),
                    });
                }
            };
            let children = inner(expr);
            let [lhs, rhs] = children else {
                return Err(ClangFrontendError {
                    kind: "invalid_binary_operator".to_string(),
                    message: "BinaryOperator must have two operands".to_string(),
                });
            };
            let preserve_operand_integral_casts =
                preserve_integral_casts || preserves_integral_operand_casts(&op);
            Ok(ClangExprSkeleton::Binary {
                op,
                lhs: Box::new(expr_skeleton_from_ast_with_options(
                    lhs,
                    preserve_operand_integral_casts,
                )?),
                rhs: Box::new(expr_skeleton_from_ast_with_options(
                    rhs,
                    preserve_operand_integral_casts,
                )?),
                ty: expr_type(expr)?,
            })
        }
        Some("ConditionalOperator") => {
            let children = inner(expr);
            let [condition, then_expr, else_expr] = children else {
                return Err(ClangFrontendError {
                    kind: "invalid_conditional_operator".to_string(),
                    message: "ConditionalOperator must have condition, then, and else operands"
                        .to_string(),
                });
            };
            Ok(ClangExprSkeleton::Conditional {
                condition: Box::new(condition_expr_skeleton_from_ast(condition)?),
                then_expr: Box::new(expr_skeleton_from_ast_with_options(then_expr, true)?),
                else_expr: Box::new(expr_skeleton_from_ast_with_options(else_expr, true)?),
                ty: expr_type(expr)?,
            })
        }
        Some("BinaryConditionalOperator") => Ok(ClangExprSkeleton::Unsupported {
            node: "BinaryConditionalOperator".to_string(),
            reason: "GNU omitted-middle conditional operator is outside the current skeleton"
                .to_string(),
        }),
        Some("ArraySubscriptExpr") => {
            let children = inner(expr);
            let [base, index] = children else {
                return Err(ClangFrontendError {
                    kind: "invalid_array_subscript_expr".to_string(),
                    message: "ArraySubscriptExpr must have base and index operands".to_string(),
                });
            };
            Ok(ClangExprSkeleton::Index {
                base: Box::new(array_subscript_base_skeleton_from_ast(
                    base,
                    preserve_integral_casts,
                )?),
                index: Box::new(expr_skeleton_from_ast_with_options(index, true)?),
                ty: expr_type(expr)?,
            })
        }
        Some("MemberExpr") => {
            let base = inner(expr).first().ok_or_else(|| ClangFrontendError {
                kind: "invalid_member_expr".to_string(),
                message: "MemberExpr is missing base operand".to_string(),
            })?;
            let field = string_field(expr, "name").ok_or_else(|| ClangFrontendError {
                kind: "invalid_member_expr".to_string(),
                message: "MemberExpr is missing name".to_string(),
            })?;
            let is_arrow = expr
                .get("isArrow")
                .and_then(Value::as_bool)
                .unwrap_or(false);
            Ok(ClangExprSkeleton::Member {
                base: Box::new(expr_skeleton_from_ast_with_options(
                    base,
                    preserve_integral_casts,
                )?),
                field,
                ty: expr_type(expr)?,
                is_arrow,
            })
        }
        Some("InitListExpr") => init_list_expr_skeleton_from_ast(expr),
        Some("ImplicitValueInitExpr") => implicit_value_init_expr_skeleton_from_ast(expr),
        Some("CallExpr") => call_expr_skeleton_from_ast(expr),
        Some("UnaryOperator") => {
            let opcode = string_field(expr, "opcode").ok_or_else(|| ClangFrontendError {
                kind: "invalid_unary_operator".to_string(),
                message: "UnaryOperator is missing opcode".to_string(),
            })?;
            if opcode == "++" || opcode == "--" {
                return inc_dec_expr_skeleton_from_ast(expr, true, preserve_integral_casts);
            }
            if opcode == "*" {
                let ptr = inner(expr).first().ok_or_else(|| ClangFrontendError {
                    kind: "invalid_unary_operator".to_string(),
                    message: "UnaryOperator is missing operand".to_string(),
                })?;
                let ptr = expr_skeleton_from_ast_with_options(ptr, preserve_integral_casts)?;
                if matches!(ptr, ClangExprSkeleton::IncDec { prefix: true, .. }) {
                    return Ok(ClangExprSkeleton::Unsupported {
                        node: "UnaryOperator".to_string(),
                        reason:
                            "deref pointer cannot use prefix increment/decrement value semantics"
                                .to_string(),
                    });
                }
                return Ok(ClangExprSkeleton::Deref {
                    ptr: Box::new(ptr),
                    ty: expr_type(expr)?,
                });
            }
            if opcode == "&" {
                let operand = inner(expr).first().ok_or_else(|| ClangFrontendError {
                    kind: "invalid_unary_operator".to_string(),
                    message: "UnaryOperator is missing operand".to_string(),
                })?;
                return Ok(ClangExprSkeleton::AddrOf {
                    operand: Box::new(expr_skeleton_from_ast_with_options(
                        operand,
                        preserve_integral_casts,
                    )?),
                    ty: expr_type(expr)?,
                });
            }
            if opcode == "+" {
                let result_ty = expr_type(expr)?;
                if !matches!(&result_ty.kind, ClangTypeKind::Integer { .. }) {
                    return Ok(ClangExprSkeleton::Unsupported {
                        node: "UnaryOperator".to_string(),
                        reason: format!(
                            "unary plus result type {} is outside the integer promotion subset",
                            result_ty.spelled
                        ),
                    });
                }
                let operand = inner(expr).first().ok_or_else(|| ClangFrontendError {
                    kind: "invalid_unary_operator".to_string(),
                    message: "UnaryOperator is missing operand".to_string(),
                })?;
                let operand = expr_skeleton_from_ast_with_options(operand, true)?;
                if let Some(operand_ty) = clang_expr_skeleton_type(&operand) {
                    if !compound_assignment_types_match(operand_ty, &result_ty) {
                        return Ok(ClangExprSkeleton::Unsupported {
                            node: "UnaryOperator".to_string(),
                            reason: format!(
                                "unary plus operand type {} must match result type {} after clang-proven integer promotion",
                                operand_ty.spelled, result_ty.spelled
                            ),
                        });
                    }
                }
                return Ok(operand);
            }

            let op = match opcode.as_str() {
                "-" => ClangUnaryOperator::Neg,
                "!" => ClangUnaryOperator::Not,
                "~" => ClangUnaryOperator::BitNot,
                opcode => {
                    return Ok(ClangExprSkeleton::Unsupported {
                        node: "UnaryOperator".to_string(),
                        reason: format!("opcode {opcode} is outside the current skeleton"),
                    });
                }
            };
            let operand = inner(expr).first().ok_or_else(|| ClangFrontendError {
                kind: "invalid_unary_operator".to_string(),
                message: "UnaryOperator is missing operand".to_string(),
            })?;
            Ok(ClangExprSkeleton::Unary {
                op,
                operand: Box::new(expr_skeleton_from_ast_with_options(operand, true)?),
                ty: expr_type(expr)?,
            })
        }
        Some("CStyleCastExpr") => {
            if string_field(expr, "castKind").as_deref() == Some("NullToPointer") {
                let operand = inner(expr).first().ok_or_else(|| ClangFrontendError {
                    kind: "invalid_cast_expr".to_string(),
                    message: "CStyleCastExpr is missing operand".to_string(),
                })?;
                let operand =
                    expr_skeleton_from_ast_with_options(operand, preserve_integral_casts)?;
                return null_pointer_skeleton_from_cast(expr, &operand, "CStyleCastExpr");
            }
            if !matches!(
                string_field(expr, "castKind").as_deref(),
                Some("BitCast" | "IntegralCast" | "IntegralPromotion" | "NoOp")
            ) {
                return Ok(ClangExprSkeleton::Unsupported {
                    node: "CStyleCastExpr".to_string(),
                    reason: match string_field(expr, "castKind") {
                        Some(cast_kind) => format!(
                            "castKind {cast_kind} is outside the current clang lowering skeleton"
                        ),
                        None => "missing castKind is outside the current clang lowering skeleton"
                            .to_string(),
                    },
                });
            }
            let target = expr_type(expr)?;
            let operand = inner(expr).first().ok_or_else(|| ClangFrontendError {
                kind: "invalid_cast_expr".to_string(),
                message: "CStyleCastExpr is missing operand".to_string(),
            })?;
            let preserve_operand_integral_casts =
                preserve_integral_casts || is_integral_conversion_cast_expr(expr);
            Ok(ClangExprSkeleton::Cast {
                target,
                expr: Box::new(expr_skeleton_from_ast_with_options(
                    operand,
                    preserve_operand_integral_casts,
                )?),
                implicit: false,
            })
        }
        Some(kind) => Ok(ClangExprSkeleton::Unsupported {
            node: kind.to_string(),
            reason: format!("{kind} is outside the current clang lowering skeleton"),
        }),
        None => Err(ClangFrontendError {
            kind: "invalid_clang_expr".to_string(),
            message: "clang expression node is missing kind".to_string(),
        }),
    }
}

#[cfg(feature = "typed-ir")]
fn unary_expr_or_type_trait_skeleton_from_ast(
    expr: &Value,
) -> Result<ClangExprSkeleton, ClangFrontendError> {
    let name = string_field(expr, "name").ok_or_else(|| ClangFrontendError {
        kind: "invalid_unary_expr_or_type_trait_expr".to_string(),
        message: "UnaryExprOrTypeTraitExpr is missing name".to_string(),
    })?;
    if name != "sizeof" && name != "_Alignof" {
        return Ok(ClangExprSkeleton::Unsupported {
            node: "UnaryExprOrTypeTraitExpr".to_string(),
            reason: format!("{name} requires explicit alignment/lowering support"),
        });
    }
    let arg_type_object = expr.get("argType").ok_or_else(|| ClangFrontendError {
        kind: if expr.get("inner").is_some() {
            format!("unsupported_{name}_operand")
        } else {
            "invalid_unary_expr_or_type_trait_expr".to_string()
        },
        message: if expr.get("inner").is_some() {
            format!("{name} expression operand requires clang argType.qualType before typed IR lowering")
        } else {
            format!("{name} type operand is missing argType.qualType")
        },
    })?;
    if clang_type_candidate_spellings(arg_type_object)
        .iter()
        .any(|spelling| is_enum_qual_type_spelling(spelling))
    {
        let spelled = string_field(arg_type_object, "qualType")
            .or_else(|| string_field(arg_type_object, "desugaredQualType"))
            .or_else(|| string_field(arg_type_object, "canonicalQualType"))
            .unwrap_or_else(|| "enum".to_string());
        return Err(ClangFrontendError {
            kind: format!("unsupported_{name}_type"),
            message: format!(
                "{name}({spelled}) requires explicit C layout/ABI provenance before typed IR lowering"
            ),
        });
    }
    let arg_type = type_from_ast_type_object(arg_type_object, None)?;
    if !matches!(
        arg_type.kind,
        ClangTypeKind::Integer { .. }
            | ClangTypeKind::Array { .. }
            | ClangTypeKind::Pointer { .. }
            | ClangTypeKind::Unsupported { .. }
    ) {
        return Err(ClangFrontendError {
            kind: format!("unsupported_{name}_type"),
            message: format!(
                "{name}({}) requires explicit C layout/ABI provenance before typed IR lowering",
                arg_type.spelled
            ),
        });
    }
    let ty = expr_type(expr)?;
    if name == "_Alignof" {
        Ok(ClangExprSkeleton::AlignOfType {
            arg_type,
            ty,
            alignment_bits: None,
            alignment_type_spellings: clang_type_candidate_spellings(arg_type_object),
        })
    } else {
        Ok(ClangExprSkeleton::SizeOfType { arg_type, ty })
    }
}
