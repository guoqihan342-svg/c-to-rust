#[cfg(feature = "typed-ir")]
enum DoWhileTailCallAssignmentNormalization {
    NotMatched,
    Rejected(String),
    Accepted {
        assignment: ClangStmtSkeleton,
        condition: ClangExprSkeleton,
    },
}

#[cfg(feature = "typed-ir")]
#[derive(Clone, Copy)]
enum DoWhileTailWrappedNode {
    Assignment,
    Call,
}

#[cfg(feature = "typed-ir")]
fn do_while_tail_call_assignment_from_ast(
    condition: &Value,
) -> Result<DoWhileTailCallAssignmentNormalization, ClangFrontendError> {
    let condition = do_while_tail_strip_parens(condition)?;
    if string_field(condition, "kind").as_deref() != Some("BinaryOperator")
        || string_field(condition, "opcode").as_deref() != Some("!=")
    {
        return Ok(DoWhileTailCallAssignmentNormalization::NotMatched);
    }
    let children = inner(condition);
    let [assignment_operand, sentinel_node] = children else {
        return Err(ClangFrontendError {
            kind: "invalid_do_stmt".to_string(),
            message: "do-while sentinel comparison must have two operands".to_string(),
        });
    };

    let mut comparison_conversions = Vec::new();
    let Some(assignment_node) = do_while_tail_wrapped_node(
        assignment_operand,
        &mut comparison_conversions,
        DoWhileTailWrappedNode::Assignment,
    )?
    else {
        return Ok(DoWhileTailCallAssignmentNormalization::NotMatched);
    };
    let assignment_children = inner(assignment_node);
    let [target_node, value_node] = assignment_children else {
        return Err(ClangFrontendError {
            kind: "invalid_assignment_operator".to_string(),
            message: "do-while tail assignment must have two operands".to_string(),
        });
    };

    if string_field(target_node, "kind").as_deref() != Some("DeclRefExpr") {
        return Ok(DoWhileTailCallAssignmentNormalization::Rejected(
            "do-while tail-call assignment target must be a direct non-volatile, non-atomic fixed-width integer DeclRef"
                .to_string(),
        ));
    }
    let target = expr_skeleton_from_ast(target_node)?;
    let ClangExprSkeleton::DeclRef { ty: target_ty, .. } = &target else {
        return Ok(DoWhileTailCallAssignmentNormalization::Rejected(
            "do-while tail-call assignment target must be a direct non-volatile, non-atomic fixed-width integer DeclRef"
                .to_string(),
        ));
    };
    if let Some(reason) = do_while_tail_fixed_integer_type_rejection_reason(target_ty) {
        return Ok(DoWhileTailCallAssignmentNormalization::Rejected(format!(
            "do-while tail-call assignment target must be a direct non-volatile, non-atomic fixed-width integer DeclRef: {reason}"
        )));
    }
    let assignment_ty = expr_type(assignment_node)?;
    if !compound_assignment_types_match(target_ty, &assignment_ty) {
        return Ok(DoWhileTailCallAssignmentNormalization::Rejected(format!(
            "do-while tail-call assignment result type {} must match target type {}",
            assignment_ty.canonical, target_ty.canonical
        )));
    }

    let mut value_conversions = Vec::new();
    let Some(call_node) = do_while_tail_wrapped_node(
        value_node,
        &mut value_conversions,
        DoWhileTailWrappedNode::Call,
    )?
    else {
        return Ok(DoWhileTailCallAssignmentNormalization::Rejected(
            "do-while tail assignment RHS must be exactly one direct call, optionally wrapped in clang-proven integer conversions"
                .to_string(),
        ));
    };
    if let Some(reason) = do_while_tail_direct_call_rejection_reason(call_node)? {
        return Ok(DoWhileTailCallAssignmentNormalization::Rejected(reason));
    }
    let call_ty = expr_type(call_node)?;
    if let Some(reason) = do_while_tail_fixed_integer_type_rejection_reason(&call_ty) {
        return Ok(DoWhileTailCallAssignmentNormalization::Rejected(format!(
            "do-while tail assignment direct call must return a fixed-width integer: {reason}"
        )));
    }
    if value_conversions.is_empty() {
        if !compound_assignment_types_match(target_ty, &call_ty) {
            return Ok(DoWhileTailCallAssignmentNormalization::Rejected(format!(
                "do-while tail assignment direct call return type {} must match target type {} or carry a clang-proven integer conversion",
                call_ty.canonical, target_ty.canonical
            )));
        }
    } else if !compound_assignment_types_match(target_ty, &expr_type(value_node)?) {
        return Ok(DoWhileTailCallAssignmentNormalization::Rejected(
            "do-while tail assignment converted RHS type must match its target type".to_string(),
        ));
    }

    if let Some(reason) = do_while_tail_additional_effect_rejection_reason(sentinel_node) {
        return Ok(DoWhileTailCallAssignmentNormalization::Rejected(format!(
            "do-while tail assignment sentinel must not contain a second side effect: {reason}"
        )));
    }
    let sentinel = condition_expr_skeleton_from_ast(sentinel_node)?;
    let Some(sentinel_ty) = clang_expr_skeleton_type(&sentinel) else {
        return Ok(DoWhileTailCallAssignmentNormalization::Rejected(
            "do-while tail assignment sentinel has no supported result type".to_string(),
        ));
    };
    if let Some(reason) = do_while_tail_fixed_integer_type_rejection_reason(sentinel_ty) {
        return Ok(DoWhileTailCallAssignmentNormalization::Rejected(format!(
            "do-while tail assignment sentinel must be a fixed-width integer expression: {reason}"
        )));
    }

    let assignment = ClangStmtSkeleton::Assign {
        target: target.clone(),
        value: value_expr_skeleton_from_ast(value_node)?,
    };
    let condition = ClangExprSkeleton::Binary {
        op: ClangBinaryOperator::Neq,
        lhs: Box::new(do_while_tail_assignment_read_skeleton(
            assignment_operand,
            &target,
            target_ty,
        )?),
        rhs: Box::new(sentinel),
        ty: expr_type(condition)?,
    };
    Ok(DoWhileTailCallAssignmentNormalization::Accepted {
        assignment,
        condition,
    })
}

#[cfg(feature = "typed-ir")]
fn do_while_tail_strip_parens(mut expr: &Value) -> Result<&Value, ClangFrontendError> {
    while string_field(expr, "kind").as_deref() == Some("ParenExpr") {
        let children = inner(expr);
        let [operand] = children else {
            return Err(ClangFrontendError {
                kind: "invalid_do_stmt".to_string(),
                message: "parenthesized do-while operand must have one child".to_string(),
            });
        };
        expr = operand;
    }
    Ok(expr)
}

#[cfg(feature = "typed-ir")]
fn do_while_tail_wrapped_node<'a>(
    expr: &'a Value,
    conversions: &mut Vec<&'a Value>,
    expected: DoWhileTailWrappedNode,
) -> Result<Option<&'a Value>, ClangFrontendError> {
    let expr = do_while_tail_strip_parens(expr)?;
    let is_expected = match expected {
        DoWhileTailWrappedNode::Assignment => {
            string_field(expr, "kind").as_deref() == Some("BinaryOperator")
                && string_field(expr, "opcode").as_deref() == Some("=")
        }
        DoWhileTailWrappedNode::Call => {
            string_field(expr, "kind").as_deref() == Some("CallExpr")
        }
    };
    if is_expected {
        return Ok(Some(expr));
    }
    if !matches!(
        string_field(expr, "kind").as_deref(),
        Some("ImplicitCastExpr" | "CStyleCastExpr")
    ) || !is_integral_conversion_cast_expr(expr)
    {
        return Ok(None);
    }
    conversions.push(expr);
    let children = inner(expr);
    let [operand] = children else {
        return Err(ClangFrontendError {
            kind: "invalid_do_stmt".to_string(),
            message: "integer conversion must have one operand".to_string(),
        });
    };
    do_while_tail_wrapped_node(operand, conversions, expected)
}

#[cfg(feature = "typed-ir")]
fn do_while_tail_direct_call_rejection_reason(
    call: &Value,
) -> Result<Option<String>, ClangFrontendError> {
    let children = inner(call);
    let Some((callee, args)) = children.split_first() else {
        return Err(ClangFrontendError {
            kind: "invalid_call_expr".to_string(),
            message: "do-while tail CallExpr is missing callee".to_string(),
        });
    };
    if !do_while_tail_is_direct_function_callee(callee)? {
        return Ok(Some(
            "do-while tail assignment RHS call must use a direct FunctionDecl identifier"
                .to_string(),
        ));
    }
    for arg in args {
        if let Some(reason) = do_while_tail_additional_effect_rejection_reason(arg) {
            return Ok(Some(format!(
                "do-while tail assignment RHS must contain exactly one call and no second side effect: {reason}"
            )));
        }
    }
    match call_expr_skeleton_from_ast(call)? {
        ClangExprSkeleton::Call { .. } => Ok(None),
        ClangExprSkeleton::Unsupported { node, reason } => Ok(Some(format!(
            "do-while tail assignment direct call is unsupported {node}: {reason}"
        ))),
        _ => Ok(Some(
            "do-while tail assignment RHS must lower to exactly one direct call".to_string(),
        )),
    }
}

#[cfg(feature = "typed-ir")]
fn do_while_tail_is_direct_function_callee(
    callee: &Value,
) -> Result<bool, ClangFrontendError> {
    let callee = do_while_tail_strip_parens(callee)?;
    match string_field(callee, "kind").as_deref() {
        Some("ImplicitCastExpr")
            if matches!(
                string_field(callee, "castKind").as_deref(),
                Some("FunctionToPointerDecay" | "NoOp")
            ) =>
        {
            let children = inner(callee);
            let [operand] = children else {
                return Err(ClangFrontendError {
                    kind: "invalid_call_expr".to_string(),
                    message: "direct function callee cast must have one operand".to_string(),
                });
            };
            do_while_tail_is_direct_function_callee(operand)
        }
        Some("DeclRefExpr") => Ok(callee
            .get("referencedDecl")
            .and_then(|decl| string_field(decl, "kind"))
            .as_deref()
            == Some("FunctionDecl")),
        _ => Ok(false),
    }
}

#[cfg(feature = "typed-ir")]
fn do_while_tail_additional_effect_rejection_reason(expr: &Value) -> Option<String> {
    match string_field(expr, "kind").as_deref() {
        Some("CallExpr") => return Some("contains a second call".to_string()),
        Some("BinaryOperator") if string_field(expr, "opcode").as_deref() == Some("=") => {
            return Some("contains a second assignment or memory write".to_string());
        }
        Some("CompoundAssignOperator") => {
            return Some("contains a second compound assignment or memory write".to_string());
        }
        Some("UnaryOperator")
            if matches!(
                string_field(expr, "opcode").as_deref(),
                Some("++" | "--")
            ) =>
        {
            return Some("contains a second increment/decrement side effect".to_string());
        }
        Some("DeclRefExpr") => {
            if let Ok(ty) = expr_type(expr) {
                if clang_type_is_volatile(&ty) || do_while_tail_type_is_atomic(&ty) {
                    return Some(format!(
                        "reads volatile or atomic argument type {}",
                        ty.spelled
                    ));
                }
            }
        }
        _ => {}
    }
    inner(expr)
        .iter()
        .find_map(do_while_tail_additional_effect_rejection_reason)
}

#[cfg(feature = "typed-ir")]
fn do_while_tail_assignment_read_skeleton(
    expr: &Value,
    target: &ClangExprSkeleton,
    target_ty: &ClangTypeSkeleton,
) -> Result<ClangExprSkeleton, ClangFrontendError> {
    let expr = do_while_tail_strip_parens(expr)?;
    match string_field(expr, "kind").as_deref() {
        Some("BinaryOperator") if string_field(expr, "opcode").as_deref() == Some("=") => {
            Ok(ClangExprSkeleton::LValueToRValue {
                target: target_ty.clone(),
                expr: Box::new(target.clone()),
            })
        }
        Some(kind @ ("ImplicitCastExpr" | "CStyleCastExpr"))
            if is_integral_conversion_cast_expr(expr) =>
        {
            let children = inner(expr);
            let [operand] = children else {
                return Err(ClangFrontendError {
                    kind: "invalid_do_stmt".to_string(),
                    message: "assignment result integer conversion must have one operand"
                        .to_string(),
                });
            };
            Ok(ClangExprSkeleton::Cast {
                target: expr_type(expr)?,
                expr: Box::new(do_while_tail_assignment_read_skeleton(
                    operand, target, target_ty,
                )?),
                implicit: kind == "ImplicitCastExpr",
            })
        }
        _ => Err(ClangFrontendError {
            kind: "invalid_do_stmt".to_string(),
            message: "do-while tail assignment result has an unexpected AST wrapper".to_string(),
        }),
    }
}

#[cfg(feature = "typed-ir")]
fn do_while_tail_fixed_integer_type_rejection_reason(
    ty: &ClangTypeSkeleton,
) -> Option<String> {
    if clang_type_is_volatile(ty) {
        return Some(format!("type {} is volatile", ty.spelled));
    }
    if do_while_tail_type_is_atomic(ty) {
        return Some(format!("type {} is atomic", ty.spelled));
    }
    match &ty.kind {
        ClangTypeKind::Integer { width, .. }
            if matches!(*width, 8 | 16 | 32 | 64 | 128) =>
        {
            None
        }
        ClangTypeKind::Integer { width, .. } => Some(format!(
            "type {} has unsupported integer width {width}",
            ty.spelled
        )),
        _ => Some(format!("type {} is not a fixed-width integer", ty.spelled)),
    }
}

#[cfg(feature = "typed-ir")]
fn do_while_tail_type_is_atomic(ty: &ClangTypeSkeleton) -> bool {
    [ty.spelled.as_str(), ty.canonical.as_str()]
        .into_iter()
        .any(|spelling| {
            spelling
                .split(|ch: char| !ch.is_ascii_alphanumeric() && ch != '_')
                .any(|part| part == "_Atomic" || part == "atomic" || part.starts_with("atomic_"))
        })
}

#[cfg(feature = "typed-ir")]
fn do_while_body_has_current_level_continue(body: &[ClangStmtSkeleton]) -> bool {
    body.iter().any(|stmt| match stmt {
        ClangStmtSkeleton::Continue => true,
        ClangStmtSkeleton::If {
            then_body,
            else_body,
            ..
        } => {
            do_while_body_has_current_level_continue(then_body)
                || do_while_body_has_current_level_continue(else_body)
        }
        ClangStmtSkeleton::While { .. }
        | ClangStmtSkeleton::DoWhile { .. }
        | ClangStmtSkeleton::For { .. } => false,
        _ => false,
    })
}
