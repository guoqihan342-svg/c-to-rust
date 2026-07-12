#[cfg(feature = "typed-ir")]
fn record_field_compound_assignment_value_rejection_reason(
    value: &ClangExprSkeleton,
) -> Option<String> {
    match value {
        ClangExprSkeleton::DeclRef { ty, .. }
        | ClangExprSkeleton::IntegerLiteral { ty, .. }
        | ClangExprSkeleton::SizeOfType { ty, .. } => {
            if compound_assignment_integer_type_supported_before_abi_binding(ty) {
                None
            } else {
                Some(format!(
                    "record field compound assignment RHS must be a simple integer variable, literal, or integral cast; got {}",
                    ty.spelled
                ))
            }
        }
        ClangExprSkeleton::Cast { target, expr, .. } => {
            if !compound_assignment_integer_type_supported_before_abi_binding(target) {
                return Some(format!(
                    "record field compound assignment RHS cast target must be an integer; got {}",
                    target.spelled
                ));
            }
            record_field_compound_assignment_value_rejection_reason(expr)
        }
        ClangExprSkeleton::LValueToRValue { target, expr } => {
            if !compound_assignment_integer_type_supported_before_abi_binding(target) {
                return Some(format!(
                    "record field compound assignment RHS lvalue-to-rvalue target must be an integer; got {}",
                    target.spelled
                ));
            }
            let ClangExprSkeleton::Member { ty, .. } = expr.as_ref() else {
                return Some(
                    "record field compound assignment RHS lvalue-to-rvalue read must be a direct record scalar field"
                        .to_string(),
                );
            };
            if !compound_assignment_integer_type_supported_before_abi_binding(ty) {
                return Some(format!(
                    "record field compound assignment RHS lvalue-to-rvalue source must be an integer; got {}",
                    ty.spelled
                ));
            }
            if !compound_assignment_types_match(target, ty) {
                return Some(format!(
                    "record field compound assignment RHS lvalue-to-rvalue target/source types must match: target={}, source={}",
                    target.canonical, ty.canonical
                ));
            }
            if record_field_compound_assignment_value_is_direct_record_scalar_member(expr) {
                None
            } else {
                Some(
                    "record field compound assignment RHS lvalue-to-rvalue read must be a direct by-value or readonly record pointer scalar field"
                        .to_string(),
                )
            }
        }
        ClangExprSkeleton::Unsupported { node, reason } => Some(format!(
            "record field compound assignment RHS uses unsupported expression {node}: {reason}"
        )),
        _ => Some(
            "record field compound assignment RHS must be a simple integer variable, literal, or integral cast"
                .to_string(),
        ),
    }
}

#[cfg(feature = "typed-ir")]
fn record_field_compound_assignment_value_is_direct_record_scalar_member(
    value: &ClangExprSkeleton,
) -> bool {
    let ClangExprSkeleton::Member {
        base, ty, is_arrow, ..
    } = value
    else {
        return false;
    };
    if !compound_assignment_integer_type_supported_before_abi_binding(ty) {
        return false;
    }
    match (is_arrow, base.as_ref()) {
        (
            false,
            ClangExprSkeleton::DeclRef {
                ty:
                    ClangTypeSkeleton {
                        kind: ClangTypeKind::Record { .. },
                        ..
                    },
                ..
            },
        ) => true,
        (true, ClangExprSkeleton::DeclRef { ty: base_ty, .. }) => matches!(
            &base_ty.kind,
            ClangTypeKind::Pointer { pointee, .. }
                if matches!(&pointee.kind, ClangTypeKind::Record { .. })
        ),
        _ => false,
    }
}

#[cfg(feature = "typed-ir")]
fn compound_assignment_type_field(
    stmt: &Value,
    field: &str,
) -> Result<ClangTypeSkeleton, ClangFrontendError> {
    stmt.get(field)
        .ok_or_else(|| ClangFrontendError {
            kind: "invalid_compound_assignment_operator".to_string(),
            message: format!("CompoundAssignOperator is missing {field}.qualType"),
        })
        .and_then(|type_object| type_from_ast_type_object(type_object, None))
}

#[cfg(feature = "typed-ir")]
fn compound_assignment_types_match(lhs: &ClangTypeSkeleton, rhs: &ClangTypeSkeleton) -> bool {
    lhs.canonical == rhs.canonical && lhs.kind == rhs.kind
}

#[cfg(feature = "typed-ir")]
fn compound_assignment_integer_types_supported(
    target_ty: &ClangTypeSkeleton,
    compute_lhs_ty: &ClangTypeSkeleton,
    compute_result_ty: &ClangTypeSkeleton,
) -> bool {
    compound_assignment_integer_type_supported_before_abi_binding(target_ty)
        && compound_assignment_integer_type_supported_before_abi_binding(compute_lhs_ty)
        && compound_assignment_types_match(compute_lhs_ty, compute_result_ty)
}

#[cfg(feature = "typed-ir")]
fn compound_assignment_integer_type_supported_before_abi_binding(
    ty: &ClangTypeSkeleton,
) -> bool {
    matches!(&ty.kind, ClangTypeKind::Integer { .. })
        || matches!(
            &ty.kind,
            ClangTypeKind::Unsupported { reason }
                if reason.contains("requires target ABI width provenance")
        )
}

#[cfg(feature = "typed-ir")]
fn if_stmt_skeleton_from_ast(stmt: &Value) -> Result<ClangStmtSkeleton, ClangFrontendError> {
    let children = inner(stmt);
    let (condition, then_body, else_body) = if_stmt_parts_from_children(children)?;
    if_stmt_skeleton_from_parts(
        condition_expr_skeleton_from_ast(condition)?,
        then_body,
        else_body,
    )
}

#[cfg(feature = "typed-ir")]
fn if_stmt_skeletons_from_ast(
    stmt: &Value,
) -> Result<Vec<ClangStmtSkeleton>, ClangFrontendError> {
    let children = inner(stmt);
    let (condition, then_body, else_body) = if_stmt_parts_from_children(children)?;
    match if_assignment_call_comparison_from_ast(condition)? {
        AssignmentCallComparisonNormalization::NotMatched => {
            let condition = condition_expr_skeleton_from_ast(condition)?;
            let then_skeletons = stmt_body_skeleton_from_ast(then_body)?;
            if matches!(condition, ClangExprSkeleton::IntegerLiteral { value: 0, .. })
                && then_skeletons.is_empty()
                && else_body.is_some_and(|body| {
                    string_field(body, "kind").as_deref() == Some("IfStmt")
                })
            {
                return if_stmt_skeletons_from_ast(else_body.expect("checked above"));
            }
            Ok(vec![ClangStmtSkeleton::If {
                condition,
                then_body: then_skeletons,
                else_body: match else_body {
                    Some(body) => stmt_body_skeleton_from_ast(body)?,
                    None => Vec::new(),
                },
            }])
        }
        AssignmentCallComparisonNormalization::Rejected(reason) => {
            Ok(vec![ClangStmtSkeleton::Unsupported { reason }])
        }
        AssignmentCallComparisonNormalization::Accepted {
            assignment,
            condition,
        } => Ok(vec![
            assignment,
            if_stmt_skeleton_from_parts(condition, then_body, else_body)?,
        ]),
    }
}

#[cfg(feature = "typed-ir")]
fn if_stmt_parts_from_children<'a>(
    children: &'a [Value],
) -> Result<(&'a Value, &'a Value, Option<&'a Value>), ClangFrontendError> {
    Ok(match children {
        [condition, then_body] => (condition, then_body, None),
        [condition, then_body, else_body] => (condition, then_body, Some(else_body)),
        _ => {
            return Err(ClangFrontendError {
                kind: "invalid_if_stmt".to_string(),
                message: "IfStmt must have condition and then body".to_string(),
            })
        }
    })
}
