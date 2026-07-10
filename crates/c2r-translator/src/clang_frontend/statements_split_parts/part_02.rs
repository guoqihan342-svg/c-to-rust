#[cfg(feature = "typed-ir")]
enum AssignmentCallComparisonNormalization {
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
#[derive(Clone, Copy)]
enum AssignmentCallComparisonContext {
    DoWhileTail,
    IfCondition,
}

#[cfg(feature = "typed-ir")]
impl AssignmentCallComparisonContext {
    fn label(self) -> &'static str {
        match self {
            Self::DoWhileTail => "do-while tail",
            Self::IfCondition => "if condition",
        }
    }

    fn error_kind(self) -> &'static str {
        match self {
            Self::DoWhileTail => "invalid_do_stmt",
            Self::IfCondition => "invalid_if_stmt",
        }
    }

    fn comparison_operator(self, opcode: Option<&str>) -> Option<ClangBinaryOperator> {
        match (self, opcode) {
            (Self::DoWhileTail, Some("!=")) => Some(ClangBinaryOperator::Neq),
            (Self::IfCondition, Some("==")) => Some(ClangBinaryOperator::Eq),
            (Self::IfCondition, Some("!=")) => Some(ClangBinaryOperator::Neq),
            (Self::IfCondition, Some("<")) => Some(ClangBinaryOperator::Lt),
            (Self::IfCondition, Some("<=")) => Some(ClangBinaryOperator::Le),
            (Self::IfCondition, Some(">")) => Some(ClangBinaryOperator::Gt),
            (Self::IfCondition, Some(">=")) => Some(ClangBinaryOperator::Ge),
            _ => None,
        }
    }
}

#[cfg(feature = "typed-ir")]
fn do_while_tail_call_assignment_from_ast(
    condition: &Value,
) -> Result<AssignmentCallComparisonNormalization, ClangFrontendError> {
    assignment_call_comparison_from_ast(condition, AssignmentCallComparisonContext::DoWhileTail)
}

#[cfg(feature = "typed-ir")]
fn if_assignment_call_comparison_from_ast(
    condition: &Value,
) -> Result<AssignmentCallComparisonNormalization, ClangFrontendError> {
    assignment_call_comparison_from_ast(condition, AssignmentCallComparisonContext::IfCondition)
}

#[cfg(feature = "typed-ir")]
fn assignment_call_comparison_from_ast(
    condition: &Value,
    context: AssignmentCallComparisonContext,
) -> Result<AssignmentCallComparisonNormalization, ClangFrontendError> {
    let condition = do_while_tail_strip_parens(condition, context)?;
    if string_field(condition, "kind").as_deref() != Some("BinaryOperator") {
        return Ok(AssignmentCallComparisonNormalization::NotMatched);
    }
    let Some(comparison_op) =
        context.comparison_operator(string_field(condition, "opcode").as_deref())
    else {
        return Ok(AssignmentCallComparisonNormalization::NotMatched);
    };
    let children = inner(condition);
    let [assignment_operand, sentinel_node] = children else {
        return Err(ClangFrontendError {
            kind: context.error_kind().to_string(),
            message: format!("{} sentinel comparison must have two operands", context.label()),
        });
    };

    let mut comparison_conversions = Vec::new();
    let Some(assignment_node) = do_while_tail_wrapped_node(
        assignment_operand,
        &mut comparison_conversions,
        DoWhileTailWrappedNode::Assignment,
        context,
    )?
    else {
        return Ok(AssignmentCallComparisonNormalization::NotMatched);
    };
    let assignment_children = inner(assignment_node);
    let [target_node, value_node] = assignment_children else {
        return Err(ClangFrontendError {
            kind: "invalid_assignment_operator".to_string(),
            message: format!("{} assignment must have two operands", context.label()),
        });
    };

    if string_field(target_node, "kind").as_deref() != Some("DeclRefExpr") {
        return Ok(AssignmentCallComparisonNormalization::Rejected(format!(
            "{} assignment-call target must be a direct non-volatile, non-atomic fixed-width integer DeclRef",
            context.label()
        )));
    }
    let target = expr_skeleton_from_ast(target_node)?;
    let ClangExprSkeleton::DeclRef { ty: target_ty, .. } = &target else {
        return Ok(AssignmentCallComparisonNormalization::Rejected(format!(
            "{} assignment-call target must be a direct non-volatile, non-atomic fixed-width integer DeclRef",
            context.label()
        )));
    };
    if let Some(reason) = do_while_tail_fixed_integer_type_rejection_reason(target_ty) {
        return Ok(AssignmentCallComparisonNormalization::Rejected(format!(
            "{} assignment-call target must be a direct non-volatile, non-atomic fixed-width integer DeclRef: {reason}",
            context.label()
        )));
    }
    let assignment_ty = expr_type(assignment_node)?;
    if !compound_assignment_types_match(target_ty, &assignment_ty) {
        return Ok(AssignmentCallComparisonNormalization::Rejected(format!(
            "{} assignment-call result type {} must match target type {}",
            context.label(),
            assignment_ty.canonical, target_ty.canonical
        )));
    }

    let mut value_conversions = Vec::new();
    let Some(call_node) = do_while_tail_wrapped_node(
        value_node,
        &mut value_conversions,
        DoWhileTailWrappedNode::Call,
        context,
    )?
    else {
        return Ok(AssignmentCallComparisonNormalization::Rejected(format!(
            "{} assignment RHS must be exactly one direct call, optionally wrapped in clang-proven integer conversions",
            context.label()
        )));
    };
    if let Some(reason) = do_while_tail_direct_call_rejection_reason(call_node, context)? {
        return Ok(AssignmentCallComparisonNormalization::Rejected(reason));
    }
    let call_ty = expr_type(call_node)?;
    if let Some(reason) = do_while_tail_fixed_integer_type_rejection_reason(&call_ty) {
        return Ok(AssignmentCallComparisonNormalization::Rejected(format!(
            "{} assignment direct call must return a fixed-width integer: {reason}",
            context.label()
        )));
    }
    if value_conversions.is_empty() {
        if !compound_assignment_types_match(target_ty, &call_ty) {
            return Ok(AssignmentCallComparisonNormalization::Rejected(format!(
                "{} assignment direct call return type {} must match target type {} or carry a clang-proven integer conversion",
                context.label(),
                call_ty.canonical, target_ty.canonical
            )));
        }
    } else if !compound_assignment_types_match(target_ty, &expr_type(value_node)?) {
        return Ok(AssignmentCallComparisonNormalization::Rejected(format!(
            "{} assignment converted RHS type must match its target type",
            context.label()
        )));
    }

    if let Some(reason) = do_while_tail_additional_effect_rejection_reason(sentinel_node) {
        return Ok(AssignmentCallComparisonNormalization::Rejected(format!(
            "{} assignment sentinel must not contain a second side effect: {reason}",
            context.label()
        )));
    }
    let sentinel = condition_expr_skeleton_from_ast(sentinel_node)?;
    let Some(sentinel_ty) = clang_expr_skeleton_type(&sentinel) else {
        return Ok(AssignmentCallComparisonNormalization::Rejected(format!(
            "{} assignment sentinel has no supported result type",
            context.label()
        )));
    };
    if let Some(reason) = do_while_tail_fixed_integer_type_rejection_reason(sentinel_ty) {
        return Ok(AssignmentCallComparisonNormalization::Rejected(format!(
            "{} assignment sentinel must be a fixed-width integer expression: {reason}",
            context.label()
        )));
    }

    let assignment = ClangStmtSkeleton::Assign {
        target: target.clone(),
        value: value_expr_skeleton_from_ast(value_node)?,
    };
    let condition = ClangExprSkeleton::Binary {
        op: comparison_op,
        lhs: Box::new(do_while_tail_assignment_read_skeleton(
            assignment_operand,
            &target,
            target_ty,
            context,
        )?),
        rhs: Box::new(sentinel),
        ty: expr_type(condition)?,
    };
    Ok(AssignmentCallComparisonNormalization::Accepted {
        assignment,
        condition,
    })
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
                message: format!("parenthesized {} operand must have one child", context.label()),
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
            kind: context.error_kind().to_string(),
            message: format!("{} integer conversion must have one operand", context.label()),
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
