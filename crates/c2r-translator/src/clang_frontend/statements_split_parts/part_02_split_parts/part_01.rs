
#[cfg(feature = "typed-ir")]
fn do_while_tail_call_assignment_from_ast(
    condition: &Value,
) -> Result<AssignmentCallComparisonNormalization, ClangFrontendError> {
    let context = AssignmentCallComparisonContext::DoWhileTail;
    let condition = do_while_tail_strip_parens(condition, context)?;
    if string_field(condition, "kind").as_deref() != Some("BinaryOperator") {
        return assignment_call_comparison_from_ast(condition, context);
    }
    let logical_opcode = string_field(condition, "opcode");
    let Some(logical_op @ ("&&" | "||")) = logical_opcode.as_deref() else {
        return assignment_call_comparison_from_ast(condition, context);
    };
    let children = inner(condition);
    let [assignment_comparison, suffix_node] = children else {
        return Err(ClangFrontendError {
            kind: context.error_kind().to_string(),
            message: format!(
                "{} logical condition must have two operands",
                context.label()
            ),
        });
    };

    let (assignment, assignment_condition) =
        match assignment_call_comparison_from_ast(assignment_comparison, context)? {
            AssignmentCallComparisonNormalization::Accepted {
                assignment,
                condition,
            } => (assignment, condition),
            AssignmentCallComparisonNormalization::NotMatched => {
                return Ok(AssignmentCallComparisonNormalization::NotMatched);
            }
            AssignmentCallComparisonNormalization::Rejected(reason) => {
                return Ok(AssignmentCallComparisonNormalization::Rejected(reason));
            }
        };
    if assignment_call_has_record_pointer_member_target(&assignment) {
        return Ok(AssignmentCallComparisonNormalization::Rejected(format!(
            "{} record-pointer assignment-call comparison cannot be combined with a logical suffix",
            context.label()
        )));
    }
    if logical_op == "||" {
        return Ok(AssignmentCallComparisonNormalization::Rejected(format!(
            "{} assignment-call comparison only supports a pure suffix joined by &&",
            context.label()
        )));
    }
    if let Some(reason) = do_while_tail_additional_effect_rejection_reason(suffix_node) {
        return Ok(AssignmentCallComparisonNormalization::Rejected(format!(
            "{} && suffix must not contain a side effect: {reason}",
            context.label()
        )));
    }
    if let Some(reason) = do_while_tail_pure_suffix_shape_rejection_reason(suffix_node) {
        return Ok(AssignmentCallComparisonNormalization::Rejected(format!(
            "{} && suffix must be one pure scalar or comparison expression: {reason}",
            context.label()
        )));
    }
    let suffix = condition_expr_skeleton_from_ast(suffix_node)?;
    let Some(suffix_ty) = clang_expr_skeleton_type(&suffix) else {
        return Ok(AssignmentCallComparisonNormalization::Rejected(format!(
            "{} && suffix has no supported scalar result type",
            context.label()
        )));
    };
    if let Some(reason) = do_while_tail_fixed_integer_type_rejection_reason(suffix_ty) {
        return Ok(AssignmentCallComparisonNormalization::Rejected(format!(
            "{} && suffix must have a fixed-width integer result: {reason}",
            context.label()
        )));
    }

    Ok(AssignmentCallComparisonNormalization::Accepted {
        assignment,
        condition: ClangExprSkeleton::Binary {
            op: ClangBinaryOperator::LogAnd,
            lhs: Box::new(assignment_condition),
            rhs: Box::new(suffix),
            ty: expr_type(condition)?,
        },
    })
}

#[cfg(feature = "typed-ir")]
fn do_while_tail_pure_suffix_shape_rejection_reason(expr: &Value) -> Option<String> {
    if string_field(expr, "kind").as_deref() == Some("BinaryOperator") {
        match string_field(expr, "opcode").as_deref() {
            Some(
                "+" | "-" | "*" | "/" | "%" | "&" | "|" | "^" | "<<" | ">>" | "==" | "!=" | "<"
                | "<=" | ">" | ">=",
            ) => {}
            Some("&&" | "||") => {
                return Some("nested short-circuit operators are outside this slice".to_string());
            }
            Some(opcode) => {
                return Some(format!("binary operator {opcode} is outside this slice"));
            }
            None => return Some("binary operator is missing its opcode".to_string()),
        }
    } else if matches!(
        string_field(expr, "kind").as_deref(),
        Some("ConditionalOperator" | "BinaryConditionalOperator")
    ) {
        return Some("conditional operators are outside this slice".to_string());
    }

    inner(expr)
        .iter()
        .find_map(do_while_tail_pure_suffix_shape_rejection_reason)
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
            message: format!(
                "{} sentinel comparison must have two operands",
                context.label()
            ),
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

    let target_kind = string_field(target_node, "kind");
    let target_is_direct_scalar = target_kind.as_deref() == Some("DeclRefExpr");
    let target_is_member = target_kind.as_deref() == Some("MemberExpr");
    if !target_is_direct_scalar && !target_is_member {
        return Ok(AssignmentCallComparisonNormalization::Rejected(format!(
            "{} assignment-call target must be {}",
            context.label(),
            context.target_requirement(),
        )));
    }
    let target = expr_skeleton_from_ast(target_node)?;
    let Some(target_ty) = clang_expr_skeleton_type(&target) else {
        return Ok(AssignmentCallComparisonNormalization::Rejected(format!(
            "{} assignment-call target must be {}",
            context.label(),
            context.target_requirement(),
        )));
    };
    if target_is_member {
        match assignment_call_member_target_kind(target_node, context) {
            AssignmentCallMemberTargetKind::MutableRecordPointer => {
                if let Some(reason) =
                    assignment_call_record_pointer_member_target_rejection_reason(
                        target_node,
                        context,
                    )?
                {
                    return Ok(AssignmentCallComparisonNormalization::Rejected(format!(
                        "{} assignment-call record-pointer arrow member target is unsupported: {reason}",
                        context.label()
                    )));
                }
            }
            AssignmentCallMemberTargetKind::LocalRecord => {
                if let Some(reason) =
                    do_while_tail_local_record_member_target_rejection_reason(target_node)?
                {
                    return Ok(AssignmentCallComparisonNormalization::Rejected(format!(
                        "{} assignment-call local record member target is unsupported: {reason}",
                        context.label()
                    )));
                }
            }
        }
    } else if !matches!(&target, ClangExprSkeleton::DeclRef { .. }) {
        return Ok(AssignmentCallComparisonNormalization::Rejected(format!(
            "{} assignment-call target must be a direct non-volatile, non-atomic fixed-width integer DeclRef",
            context.label()
        )));
    }
    if let Some(reason) = do_while_tail_fixed_integer_type_rejection_reason(target_ty) {
        return Ok(AssignmentCallComparisonNormalization::Rejected(format!(
            "{} assignment-call target must be {}: {reason}",
            context.label(),
            context.typed_target_requirement(),
        )));
    }
    let assignment_ty = expr_type(assignment_node)?;
    if !compound_assignment_types_match(target_ty, &assignment_ty) {
        return Ok(AssignmentCallComparisonNormalization::Rejected(format!(
            "{} assignment-call result type {} must match target type {}",
            context.label(),
            assignment_ty.canonical,
            target_ty.canonical
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
