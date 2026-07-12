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
            implicit_cast_expr_skeleton_from_ast(expr, preserve_integral_casts)
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
        Some("CharacterLiteral") => {
            let value = integer_field(expr, "value").ok_or_else(|| ClangFrontendError {
                kind: "invalid_character_literal".to_string(),
                message: "CharacterLiteral is missing a signed JSON integer value".to_string(),
            })?;
            let ty = expr_type(expr)?;
            if ty.canonical.trim() != "int" {
                return Err(ClangFrontendError {
                    kind: "unsupported_character_literal_type".to_string(),
                    message: format!(
                        "CharacterLiteral type {} is outside the plain C int literal subset",
                        ty.canonical
                    ),
                });
            }
            let value = u64::try_from(value).map_err(|_| ClangFrontendError {
                kind: "unsupported_character_literal_value".to_string(),
                message: "CharacterLiteral value must be non-negative".to_string(),
            })?;
            if value > i32::MAX as u64 {
                return Err(ClangFrontendError {
                    kind: "unsupported_character_literal_value".to_string(),
                    message: format!(
                        "CharacterLiteral value {value} is outside the supported C int range"
                    ),
                });
            }
            Ok(ClangExprSkeleton::IntegerLiteral {
                value,
                spelling: value.to_string(),
                ty,
            })
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
        Some("StringLiteral") => string_literal_expr_skeleton_from_ast(expr),
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
            if string_field(expr, "castKind").as_deref() == Some("IntegralToBoolean") {
                let operand = inner(expr).first().ok_or_else(|| ClangFrontendError {
                    kind: "invalid_cast_expr".to_string(),
                    message: "CStyleCastExpr is missing operand".to_string(),
                })?;
                let operand = expr_skeleton_from_ast_with_options(operand, true)?;
                return integral_to_boolean_skeleton_from_cast(
                    expr,
                    &operand,
                    "CStyleCastExpr",
                );
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
