#[derive(Clone, Copy)]
enum AssignmentCallMemberTargetKind {
    LocalRecord,
    MutableRecordPointer,
}

impl AssignmentCallComparisonContext {
    fn target_requirement(self) -> &'static str {
        match self {
            Self::DoWhileTail => {
                "a direct non-volatile, non-atomic fixed-width integer DeclRef, a local complete-record pure dot-path integer member, or a direct mutable record-pointer arrow-rooted pure dot-path integer member"
            }
            Self::IfCondition => {
                "a direct non-volatile, non-atomic fixed-width integer DeclRef or a direct mutable record-pointer arrow-rooted pure dot-path integer member"
            }
        }
    }

    fn typed_target_requirement(self) -> &'static str {
        match self {
            Self::DoWhileTail => {
                "a direct scalar, local complete-record pure dot-path, or direct mutable record-pointer arrow-rooted pure dot-path non-volatile, non-atomic fixed-width integer"
            }
            Self::IfCondition => {
                "a direct scalar or direct mutable record-pointer arrow-rooted pure dot-path non-volatile, non-atomic fixed-width integer"
            }
        }
    }
}

fn assignment_call_member_target_kind(
    target: &Value,
    context: AssignmentCallComparisonContext,
) -> AssignmentCallMemberTargetKind {
    if matches!(context, AssignmentCallComparisonContext::IfCondition)
        || assignment_call_member_path_has_arrow(target)
    {
        AssignmentCallMemberTargetKind::MutableRecordPointer
    } else {
        AssignmentCallMemberTargetKind::LocalRecord
    }
}

fn assignment_call_member_path_has_arrow(mut member: &Value) -> bool {
    while string_field(member, "kind").as_deref() == Some("MemberExpr") {
        if member.get("isArrow").and_then(Value::as_bool) == Some(true) {
            return true;
        }
        let [base] = inner(member) else {
            return false;
        };
        member = base;
    }
    false
}

fn assignment_call_has_record_pointer_member_target(assignment: &ClangStmtSkeleton) -> bool {
    let ClangStmtSkeleton::Assign { target, .. } = assignment else {
        return false;
    };
    clang_member_path_has_arrow(target)
}

fn clang_member_path_has_arrow(expr: &ClangExprSkeleton) -> bool {
    match expr {
        ClangExprSkeleton::Member {
            is_arrow: true, ..
        } => true,
        ClangExprSkeleton::Member { base, .. } => clang_member_path_has_arrow(base),
        _ => false,
    }
}

fn assignment_call_record_pointer_member_target_rejection_reason(
    target: &Value,
    context: AssignmentCallComparisonContext,
) -> Result<Option<String>, ClangFrontendError> {
    let leaf_ty = expr_type(target)?;
    if clang_type_is_volatile(&leaf_ty) || do_while_tail_type_is_atomic(&leaf_ty) {
        return Ok(Some(format!(
            "leaf type {} is volatile or atomic",
            leaf_ty.spelled
        )));
    }
    if !matches!(leaf_ty.kind, ClangTypeKind::Integer { .. }) {
        return Ok(Some(format!(
            "leaf type {} is not a fixed-width integer",
            leaf_ty.spelled
        )));
    }
    let mut member = target;
    loop {
        if string_field(member, "kind").as_deref() != Some("MemberExpr") {
            return Ok(Some(
                "path must contain exactly one arrow rooted at a direct mutable record-pointer DeclRef"
                    .to_string(),
            ));
        }
        let children = inner(member);
        let [base] = children else {
            return Err(ClangFrontendError {
                kind: "invalid_member_expr".to_string(),
                message: "assignment-call target MemberExpr must have one base operand"
                    .to_string(),
            });
        };
        match member.get("isArrow").and_then(Value::as_bool) {
            Some(false) => {
                let base_ty = expr_type(base)?;
                if clang_type_is_volatile(&base_ty)
                    || do_while_tail_type_is_atomic(&base_ty)
                {
                    return Ok(Some(format!(
                        "dot member base type {} is volatile or atomic",
                        base_ty.spelled
                    )));
                }
                if !matches!(base_ty.kind, ClangTypeKind::Record { .. }) {
                    return Ok(Some(format!(
                        "dot member base type {} is not a by-value record",
                        base_ty.spelled
                    )));
                }
                member = base;
            }
            Some(true) => {
                let base = assignment_call_direct_record_pointer_root(base)?;
                match string_field(base, "kind").as_deref() {
                    Some("MemberExpr") => {
                        return Ok(Some(format!(
                            "{} assignment-call record-pointer target must not contain a second arrow or pointer member hop",
                            context.label()
                        )));
                    }
                    Some("DeclRefExpr") => {
                        let root_ty = expr_type(base)?;
                        if clang_type_is_volatile(&root_ty)
                            || do_while_tail_type_is_atomic(&root_ty)
                        {
                            return Ok(Some(format!(
                                "root type {} is volatile or atomic",
                                root_ty.spelled
                            )));
                        }
                        if !clang_type_is_mutable_record_pointer(&root_ty) {
                            return Ok(Some(format!(
                                "root type {} must be a non-const mutable record pointer",
                                root_ty.spelled
                            )));
                        }
                        return Ok(None);
                    }
                    Some(kind) => {
                        return Ok(Some(format!(
                            "root must be a direct non-null mutable record pointer DeclRef, found {kind}"
                        )));
                    }
                    None => {
                        return Ok(Some(
                            "member base is missing its expression kind".to_string(),
                        ));
                    }
                }
            }
            None => {
                return Ok(Some(
                    "member hop is missing its arrow/dot classification".to_string(),
                ));
            }
        }
    }
}

fn assignment_call_direct_record_pointer_root(
    expr: &Value,
) -> Result<&Value, ClangFrontendError> {
    if string_field(expr, "kind").as_deref() != Some("ImplicitCastExpr")
        || string_field(expr, "castKind").as_deref() != Some("LValueToRValue")
    {
        return Ok(expr);
    }
    let children = inner(expr);
    let [operand] = children else {
        return Err(ClangFrontendError {
            kind: "invalid_member_expr".to_string(),
            message: "record-pointer lvalue-to-rvalue root cast must have one operand".to_string(),
        });
    };
    let result_ty = expr_type(expr)?;
    let operand_ty = expr_type(operand)?;
    if result_ty != operand_ty {
        return Ok(expr);
    }
    Ok(operand)
}
