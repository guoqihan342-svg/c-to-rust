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
fn integral_to_boolean_literal_skeleton_from_cast(
    expr: &Value,
    operand: &ClangExprSkeleton,
    node: &str,
) -> Result<ClangExprSkeleton, ClangFrontendError> {
    let target = expr_type(expr)?;
    if !is_bool_type_skeleton(&target) {
        return Ok(ClangExprSkeleton::Unsupported {
            node: node.to_string(),
            reason: format!(
                "castKind IntegralToBoolean target {} is outside the current clang lowering skeleton",
                target.spelled
            ),
        });
    }
    let ClangExprSkeleton::IntegerLiteral { value, .. } = operand else {
        return Ok(ClangExprSkeleton::Unsupported {
            node: node.to_string(),
            reason:
                "castKind IntegralToBoolean with non-literal operand is outside the bounded boolean literal subset"
                    .to_string(),
        });
    };
    let value = u64::from(*value != 0);
    Ok(ClangExprSkeleton::IntegerLiteral {
        value,
        spelling: value.to_string(),
        ty: target,
    })
}

#[cfg(feature = "typed-ir")]
fn is_bool_type_skeleton(ty: &ClangTypeSkeleton) -> bool {
    ty.canonical == "_Bool"
        && matches!(
            ty.kind,
            ClangTypeKind::Integer {
                signed: false,
                width: 8
            }
        )
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
