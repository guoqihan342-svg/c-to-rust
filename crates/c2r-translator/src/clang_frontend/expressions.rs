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
            let operand = expr_skeleton_from_ast_with_options(operand, preserve_integral_casts)?;
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
            if preserve_integral_casts && is_integral_conversion_cast_expr(expr) {
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
                index: Box::new(expr_skeleton_from_ast_with_options(
                    index,
                    preserve_integral_casts,
                )?),
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
                operand: Box::new(expr_skeleton_from_ast_with_options(
                    operand,
                    preserve_integral_casts,
                )?),
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
            Ok(ClangExprSkeleton::Cast {
                target,
                expr: Box::new(expr_skeleton_from_ast_with_options(
                    operand,
                    preserve_integral_casts,
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
        })
    } else {
        Ok(ClangExprSkeleton::SizeOfType { arg_type, ty })
    }
}

#[cfg(feature = "typed-ir")]
fn is_enum_qual_type_spelling(qual_type: &str) -> bool {
    let mut trimmed = qual_type.trim();
    while let Some(unqualified) = trimmed.strip_prefix("const ") {
        trimmed = unqualified.trim();
    }
    trimmed
        .strip_prefix("enum ")
        .map(|name| is_simple_c_identifier(name.trim()))
        .unwrap_or(false)
}

#[cfg(feature = "typed-ir")]
fn null_pointer_skeleton_from_cast(
    expr: &Value,
    operand: &ClangExprSkeleton,
    node: &str,
) -> Result<ClangExprSkeleton, ClangFrontendError> {
    let target = expr_type(expr)?;
    if !matches!(target.kind, ClangTypeKind::Pointer { .. }) {
        return Ok(ClangExprSkeleton::Unsupported {
            node: node.to_string(),
            reason: format!(
                "castKind NullToPointer target {} is outside the current clang lowering skeleton",
                target.spelled
            ),
        });
    }
    if !matches!(operand, ClangExprSkeleton::IntegerLiteral { value: 0, .. }) {
        return Ok(ClangExprSkeleton::Unsupported {
            node: node.to_string(),
            reason: "castKind NullToPointer without integer zero operand is outside the current clang lowering skeleton".to_string(),
        });
    }
    Ok(ClangExprSkeleton::NullPtr { ty: target })
}

#[cfg(feature = "typed-ir")]
fn array_subscript_base_skeleton_from_ast(
    base: &Value,
    preserve_integral_casts: bool,
) -> Result<ClangExprSkeleton, ClangFrontendError> {
    if string_field(base, "kind").as_deref() == Some("ImplicitCastExpr")
        && string_field(base, "castKind").as_deref() == Some("ArrayToPointerDecay")
    {
        let operand = inner(base).first().ok_or_else(|| ClangFrontendError {
            kind: "invalid_clang_expr".to_string(),
            message: "ArrayToPointerDecay in ArraySubscriptExpr base is missing operand"
                .to_string(),
        })?;
        return expr_skeleton_from_ast_with_options(operand, preserve_integral_casts);
    }
    expr_skeleton_from_ast_with_options(base, preserve_integral_casts)
}

#[cfg(feature = "typed-ir")]
fn init_list_expr_skeleton_from_ast(expr: &Value) -> Result<ClangExprSkeleton, ClangFrontendError> {
    let ty = expr_type(expr)?;
    let ClangTypeKind::Array { element, len } = &ty.kind else {
        return Ok(ClangExprSkeleton::Unsupported {
            node: "InitListExpr".to_string(),
            reason: format!(
                "initializer list type {} is outside the current clang lowering skeleton",
                ty.spelled
            ),
        });
    };
    let Some(len) = len else {
        return Ok(ClangExprSkeleton::Unsupported {
            node: "InitListExpr".to_string(),
            reason:
                "incomplete array initializer list is outside the current clang lowering skeleton"
                    .to_string(),
        });
    };
    if !matches!(&element.kind, ClangTypeKind::Integer { .. }) {
        return Ok(ClangExprSkeleton::Unsupported {
            node: "InitListExpr".to_string(),
            reason: format!(
                "array element type {} is outside the current clang lowering skeleton",
                element.spelled
            ),
        });
    }
    let init_children = inner(expr);
    if init_children
        .iter()
        .any(|child| string_field(child, "kind").as_deref() == Some("DesignatedInitExpr"))
    {
        return Ok(ClangExprSkeleton::Unsupported {
            node: "InitListExpr".to_string(),
            reason: "unexpanded DesignatedInitExpr is outside the bounded fixed-array initializer subset".to_string(),
        });
    }
    let elements = if init_children.is_empty() {
        match materialized_array_filler_elements(expr, *len)? {
            Some(elements) => elements,
            None => {
                return Ok(ClangExprSkeleton::Unsupported {
                    node: "InitListExpr".to_string(),
                    reason: format!(
                        "initializer element count 0 does not match array length {len}"
                    ),
                });
            }
        }
    } else {
        if init_children.len() != *len {
            return Ok(ClangExprSkeleton::Unsupported {
                node: "InitListExpr".to_string(),
                reason: format!(
                    "initializer element count {} does not match array length {len}",
                    init_children.len()
                ),
            });
        }
        init_children
            .iter()
            .map(|element| expr_skeleton_from_ast_with_options(element, true))
            .collect::<Result<Vec<_>, ClangFrontendError>>()?
    };
    for (index, element) in elements.iter().enumerate() {
        if let Some(reason) = array_literal_element_rejection_reason(element) {
            return Ok(ClangExprSkeleton::Unsupported {
                node: "InitListExpr".to_string(),
                reason: format!("initializer element {index} {reason}"),
            });
        }
    }

    Ok(ClangExprSkeleton::ArrayLiteral { elements, ty })
}

#[cfg(feature = "typed-ir")]
fn materialized_array_filler_elements(
    expr: &Value,
    len: usize,
) -> Result<Option<Vec<ClangExprSkeleton>>, ClangFrontendError> {
    let Some(filler_entries) = array_filler(expr) else {
        return Ok(None);
    };
    let Some(filler) = filler_entries.first() else {
        return Ok(Some(vec![ClangExprSkeleton::Unsupported {
            node: "InitListExpr".to_string(),
            reason: "array_filler is empty".to_string(),
        }]));
    };
    if string_field(filler, "kind").as_deref() != Some("ImplicitValueInitExpr") {
        return Ok(Some(vec![ClangExprSkeleton::Unsupported {
            node: "InitListExpr".to_string(),
            reason: "array_filler first entry is not ImplicitValueInitExpr".to_string(),
        }]));
    }
    if filler_entries.len().saturating_sub(1) > len {
        return Ok(Some(vec![ClangExprSkeleton::Unsupported {
            node: "InitListExpr".to_string(),
            reason: format!(
                "array_filler materializes {} elements for array length {len}",
                filler_entries.len().saturating_sub(1)
            ),
        }]));
    }

    let mut elements = filler_entries[1..]
        .iter()
        .map(|element| expr_skeleton_from_ast_with_options(element, true))
        .collect::<Result<Vec<_>, ClangFrontendError>>()?;
    while elements.len() < len {
        elements.push(expr_skeleton_from_ast_with_options(filler, true)?);
    }
    Ok(Some(elements))
}

#[cfg(feature = "typed-ir")]
fn implicit_value_init_expr_skeleton_from_ast(
    expr: &Value,
) -> Result<ClangExprSkeleton, ClangFrontendError> {
    let ty = expr_type(expr)?;
    if !matches!(ty.kind, ClangTypeKind::Integer { .. }) {
        return Ok(ClangExprSkeleton::Unsupported {
            node: "ImplicitValueInitExpr".to_string(),
            reason: format!(
                "zero initializer type {} is outside the bounded integer array subset",
                ty.spelled
            ),
        });
    }
    Ok(ClangExprSkeleton::IntegerLiteral {
        value: 0,
        spelling: "0".to_string(),
        ty,
    })
}

#[cfg(feature = "typed-ir")]
fn array_literal_element_rejection_reason(expr: &ClangExprSkeleton) -> Option<String> {
    match expr {
        ClangExprSkeleton::IntegerLiteral { .. } => None,
        ClangExprSkeleton::Cast { target, expr, .. } => {
            if !matches!(target.kind, ClangTypeKind::Integer { .. }) {
                return Some(format!(
                    "cast target {} is not an integer; only pure integer literal elements are supported",
                    target.spelled
                ));
            }
            array_literal_element_rejection_reason(expr)
        }
        ClangExprSkeleton::Unsupported { node, reason } => Some(format!(
            "is unsupported {node}: {reason}; only pure integer literal elements are supported"
        )),
        _ => Some(
            "uses a non-literal or side-effecting expression; only pure integer literal elements are supported"
                .to_string(),
        ),
    }
}

#[cfg(feature = "typed-ir")]
fn inc_dec_expr_skeleton_from_ast(
    expr: &Value,
    allow_prefix: bool,
    preserve_integral_casts: bool,
) -> Result<ClangExprSkeleton, ClangFrontendError> {
    let opcode = string_field(expr, "opcode").ok_or_else(|| ClangFrontendError {
        kind: "invalid_unary_operator".to_string(),
        message: "UnaryOperator is missing opcode".to_string(),
    })?;
    let op = match opcode.as_str() {
        "++" => ClangIncDecOperator::Inc,
        "--" => ClangIncDecOperator::Dec,
        _ => {
            return Ok(ClangExprSkeleton::Unsupported {
                node: "UnaryOperator".to_string(),
                reason: format!("opcode {opcode} is outside the current inc/dec skeleton"),
            })
        }
    };
    let Some(is_postfix) = expr.get("isPostfix").and_then(Value::as_bool) else {
        return Ok(ClangExprSkeleton::Unsupported {
            node: "UnaryOperator".to_string(),
            reason: "inc/dec UnaryOperator is missing an explicit isPostfix flag".to_string(),
        });
    };
    if !is_postfix && !allow_prefix {
        return Ok(ClangExprSkeleton::Unsupported {
            node: "UnaryOperator".to_string(),
            reason: format!("prefix opcode {opcode} is outside the current skeleton"),
        });
    }
    let target = inner(expr).first().ok_or_else(|| ClangFrontendError {
        kind: "invalid_unary_operator".to_string(),
        message: "UnaryOperator is missing operand".to_string(),
    })?;
    Ok(ClangExprSkeleton::IncDec {
        target: Box::new(expr_skeleton_from_ast_with_options(
            target,
            preserve_integral_casts,
        )?),
        op,
        prefix: !is_postfix,
        ty: expr_type(expr)?,
    })
}
