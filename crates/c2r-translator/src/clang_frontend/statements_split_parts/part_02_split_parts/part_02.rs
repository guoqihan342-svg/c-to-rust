
#[cfg(feature = "typed-ir")]
fn do_while_tail_local_record_member_target_rejection_reason(
    target: &Value,
) -> Result<Option<String>, ClangFrontendError> {
    let mut member = target;
    let mut member_count = 0usize;
    loop {
        if string_field(member, "kind").as_deref() != Some("MemberExpr") {
            return Ok(Some(
                "path contains an expression other than a direct DeclRef root and dot members"
                    .to_string(),
            ));
        }
        if member.get("isArrow").and_then(Value::as_bool) != Some(false) {
            return Ok(Some(
                "path contains an arrow or unknown member hop".to_string(),
            ));
        }
        let children = inner(member);
        let [base] = children else {
            return Err(ClangFrontendError {
                kind: "invalid_member_expr".to_string(),
                message: "assignment-call target MemberExpr must have one base operand".to_string(),
            });
        };
        let base_ty = expr_type(base)?;
        if clang_type_is_volatile(&base_ty) || do_while_tail_type_is_atomic(&base_ty) {
            return Ok(Some(format!(
                "member base type {} is volatile or atomic",
                base_ty.spelled
            )));
        }
        if !matches!(base_ty.kind, ClangTypeKind::Record { .. }) {
            return Ok(Some(format!(
                "member base type {} is not a complete by-value record",
                base_ty.spelled
            )));
        }
        member_count += 1;

        match string_field(base, "kind").as_deref() {
            Some("MemberExpr") => member = base,
            Some("DeclRefExpr") => {
                if member_count == 0
                    || base
                        .get("referencedDecl")
                        .and_then(|decl| string_field(decl, "kind"))
                        .as_deref()
                        != Some("VarDecl")
                {
                    return Ok(Some(
                        "root must be a direct local by-value record variable".to_string(),
                    ));
                }
                return Ok(None);
            }
            Some(kind) => {
                return Ok(Some(format!(
                    "path contains unsupported {kind} before its root"
                )));
            }
            None => return Ok(Some("path base is missing its expression kind".to_string())),
        }
    }
}

#[cfg(feature = "typed-ir")]
fn do_while_tail_strip_parens(
    mut expr: &Value,
    context: AssignmentCallComparisonContext,
) -> Result<&Value, ClangFrontendError> {
    while string_field(expr, "kind").as_deref() == Some("ParenExpr") {
        let children = inner(expr);
        let [operand] = children else {
            return Err(ClangFrontendError {
                kind: context.error_kind().to_string(),
                message: format!(
                    "parenthesized {} operand must have one child",
                    context.label()
                ),
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
    context: AssignmentCallComparisonContext,
) -> Result<Option<&'a Value>, ClangFrontendError> {
    let expr = do_while_tail_strip_parens(expr, context)?;
    let is_expected = match expected {
        DoWhileTailWrappedNode::Assignment => {
            string_field(expr, "kind").as_deref() == Some("BinaryOperator")
                && string_field(expr, "opcode").as_deref() == Some("=")
        }
        DoWhileTailWrappedNode::Call => string_field(expr, "kind").as_deref() == Some("CallExpr"),
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
            kind: context.error_kind().to_string(),
            message: format!(
                "{} integer conversion must have one operand",
                context.label()
            ),
        });
    };
    do_while_tail_wrapped_node(operand, conversions, expected, context)
}

#[cfg(feature = "typed-ir")]
fn do_while_tail_direct_call_rejection_reason(
    call: &Value,
    context: AssignmentCallComparisonContext,
) -> Result<Option<String>, ClangFrontendError> {
    let children = inner(call);
    let Some((callee, args)) = children.split_first() else {
        return Err(ClangFrontendError {
            kind: "invalid_call_expr".to_string(),
            message: format!("{} assignment CallExpr is missing callee", context.label()),
        });
    };
    if !do_while_tail_is_direct_function_callee(callee, context)? {
        return Ok(Some(format!(
            "{} assignment RHS call must use a direct FunctionDecl identifier",
            context.label()
        )));
    }
    for arg in args {
        if let Some(reason) = do_while_tail_additional_effect_rejection_reason(arg) {
            return Ok(Some(format!(
                "{} assignment RHS must contain exactly one call and no second side effect: {reason}",
                context.label()
            )));
        }
    }
    match call_expr_skeleton_from_ast(call)? {
        ClangExprSkeleton::Call { .. } => Ok(None),
        ClangExprSkeleton::Unsupported { node, reason } => Ok(Some(format!(
            "{} assignment direct call is unsupported {node}: {reason}",
            context.label()
        ))),
        _ => Ok(Some(format!(
            "{} assignment RHS must lower to exactly one direct call",
            context.label()
        ))),
    }
}

#[cfg(feature = "typed-ir")]
fn do_while_tail_is_direct_function_callee(
    callee: &Value,
    context: AssignmentCallComparisonContext,
) -> Result<bool, ClangFrontendError> {
    let callee = do_while_tail_strip_parens(callee, context)?;
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
            do_while_tail_is_direct_function_callee(operand, context)
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
            if matches!(string_field(expr, "opcode").as_deref(), Some("++" | "--")) =>
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
    context: AssignmentCallComparisonContext,
) -> Result<ClangExprSkeleton, ClangFrontendError> {
    let expr = do_while_tail_strip_parens(expr, context)?;
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
                    kind: context.error_kind().to_string(),
                    message: format!(
                        "{} assignment result integer conversion must have one operand",
                        context.label()
                    ),
                });
            };
            Ok(ClangExprSkeleton::Cast {
                target: expr_type(expr)?,
                expr: Box::new(do_while_tail_assignment_read_skeleton(
                    operand, target, target_ty, context,
                )?),
                implicit: kind == "ImplicitCastExpr",
            })
        }
        _ => Err(ClangFrontendError {
            kind: context.error_kind().to_string(),
            message: format!(
                "{} assignment result has an unexpected AST wrapper",
                context.label()
            ),
        }),
    }
}

#[cfg(feature = "typed-ir")]
fn do_while_tail_fixed_integer_type_rejection_reason(ty: &ClangTypeSkeleton) -> Option<String> {
    if clang_type_is_volatile(ty) {
        return Some(format!("type {} is volatile", ty.spelled));
    }
    if do_while_tail_type_is_atomic(ty) {
        return Some(format!("type {} is atomic", ty.spelled));
    }
    match &ty.kind {
        ClangTypeKind::Integer { width, .. } if matches!(*width, 8 | 16 | 32 | 64 | 128) => None,
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
fn do_while_body_insert_tail_assignment_before_current_level_continue(
    body: &mut Vec<ClangStmtSkeleton>,
    assignment: &ClangStmtSkeleton,
) {
    let original = std::mem::take(body);
    let mut rewritten = Vec::with_capacity(original.len());
    for stmt in original {
        match stmt {
            ClangStmtSkeleton::Continue => {
                rewritten.push(assignment.clone());
                rewritten.push(ClangStmtSkeleton::Continue);
            }
            ClangStmtSkeleton::If {
                condition,
                mut then_body,
                mut else_body,
            } => {
                do_while_body_insert_tail_assignment_before_current_level_continue(
                    &mut then_body,
                    assignment,
                );
                do_while_body_insert_tail_assignment_before_current_level_continue(
                    &mut else_body,
                    assignment,
                );
                rewritten.push(ClangStmtSkeleton::If {
                    condition,
                    then_body,
                    else_body,
                });
            }
            nested_or_plain => rewritten.push(nested_or_plain),
        }
    }
    *body = rewritten;
}
