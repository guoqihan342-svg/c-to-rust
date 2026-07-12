
#[cfg(feature = "typed-ir")]
fn for_init_comma_assignment_rhs_rejection_reason(value: &ClangExprSkeleton) -> Option<String> {
    match value {
        ClangExprSkeleton::DeclRef { ty, .. }
        | ClangExprSkeleton::IntegerLiteral { ty, .. } => {
            for_init_comma_integer_type_rejection_reason(ty)
        }
        ClangExprSkeleton::SizeOfType { arg_type, ty, .. }
        | ClangExprSkeleton::AlignOfType { arg_type, ty, .. } => {
            for_init_comma_integer_type_rejection_reason(ty).or_else(|| {
                clang_type_contains_pointer(arg_type).then(|| {
                    "ForStmt init comma-chain assignment RHS cannot inspect a pointer type"
                        .to_string()
                })
            })
        }
        ClangExprSkeleton::Binary { lhs, rhs, ty, .. } => {
            for_init_comma_integer_type_rejection_reason(ty)
                .or_else(|| for_init_comma_assignment_rhs_rejection_reason(lhs))
                .or_else(|| for_init_comma_assignment_rhs_rejection_reason(rhs))
        }
        ClangExprSkeleton::Unary { operand, ty, .. } => {
            for_init_comma_integer_type_rejection_reason(ty)
                .or_else(|| for_init_comma_assignment_rhs_rejection_reason(operand))
        }
        ClangExprSkeleton::Conditional {
            condition,
            then_expr,
            else_expr,
            ty,
        } => for_init_comma_integer_type_rejection_reason(ty)
            .or_else(|| for_init_comma_assignment_rhs_rejection_reason(condition))
            .or_else(|| for_init_comma_assignment_rhs_rejection_reason(then_expr))
            .or_else(|| for_init_comma_assignment_rhs_rejection_reason(else_expr)),
        ClangExprSkeleton::Cast { target, expr, .. }
        | ClangExprSkeleton::LValueToRValue { target, expr } => {
            for_init_comma_integer_type_rejection_reason(target)
                .or_else(|| for_init_comma_assignment_rhs_rejection_reason(expr))
        }
        ClangExprSkeleton::Call { .. } => Some(
            "ForStmt init comma-chain assignment RHS cannot contain a call".to_string(),
        ),
        ClangExprSkeleton::Deref { .. } => Some(
            "ForStmt init comma-chain assignment RHS cannot contain a dereference".to_string(),
        ),
        ClangExprSkeleton::AddrOf { .. }
        | ClangExprSkeleton::MutableVoidPointerAddress { .. } => Some(
            "ForStmt init comma-chain assignment RHS cannot contain address-of".to_string(),
        ),
        ClangExprSkeleton::IncDec { .. } => Some(
            "ForStmt init comma-chain assignment RHS cannot contain increment/decrement"
                .to_string(),
        ),
        ClangExprSkeleton::Member { .. } | ClangExprSkeleton::Index { .. } => Some(
            "ForStmt init comma-chain assignment RHS cannot contain a memory access".to_string(),
        ),
        ClangExprSkeleton::NullPtr { .. }
        | ClangExprSkeleton::ArrayToPointerDecay { .. }
        | ClangExprSkeleton::FunctionToPointerDecay { .. } => Some(
            "ForStmt init comma-chain assignment RHS cannot contain a pointer expression"
                .to_string(),
        ),
        ClangExprSkeleton::ArrayLiteral { .. } => Some(
            "ForStmt init comma-chain assignment RHS must be a pure integer scalar expression"
                .to_string(),
        ),
        ClangExprSkeleton::Unsupported { node, reason } => Some(format!(
            "ForStmt init comma-chain assignment RHS uses unsupported expression {node}: {reason}"
        )),
    }
}

#[cfg(feature = "typed-ir")]
fn for_init_comma_integer_type_rejection_reason(ty: &ClangTypeSkeleton) -> Option<String> {
    if clang_type_is_volatile(ty) {
        return Some(format!(
            "ForStmt init comma-chain assignment RHS cannot read volatile type {}",
            ty.spelled
        ));
    }
    if !matches!(&ty.kind, ClangTypeKind::Integer { .. }) {
        return Some(format!(
            "ForStmt init comma-chain assignment RHS must be an integer scalar, got {}",
            ty.spelled
        ));
    }
    None
}

#[cfg(feature = "typed-ir")]
fn clang_type_is_volatile(ty: &ClangTypeSkeleton) -> bool {
    [ty.spelled.as_str(), ty.canonical.as_str()]
        .into_iter()
        .any(|spelling| {
            spelling
                .split(|ch: char| !ch.is_ascii_alphanumeric() && ch != '_')
                .any(|part| part == "volatile")
        })
}

#[cfg(feature = "typed-ir")]
fn clang_type_contains_pointer(ty: &ClangTypeSkeleton) -> bool {
    match &ty.kind {
        ClangTypeKind::Pointer { .. } => true,
        ClangTypeKind::Array { element, .. } => clang_type_contains_pointer(element),
        _ => false,
    }
}

#[cfg(feature = "typed-ir")]
fn for_step_stmt_skeleton_from_ast(stmt: &Value) -> Result<ClangStmtSkeleton, ClangFrontendError> {
    match string_field(stmt, "kind").as_deref() {
        Some("BinaryOperator") if string_field(stmt, "opcode").as_deref() == Some("=") => {
            assign_stmt_skeleton_from_ast(stmt)
        }
        Some("CompoundAssignOperator") => compound_assign_stmt_skeleton_from_ast(stmt),
        Some("UnaryOperator") => inc_dec_for_step_skeleton_from_ast(stmt),
        Some(kind) => Ok(ClangStmtSkeleton::Unsupported {
            reason: format!("ForStmt step {kind} is outside the current clang lowering skeleton"),
        }),
        None => Err(ClangFrontendError {
            kind: "invalid_for_stmt".to_string(),
            message: "ForStmt step slot is missing kind".to_string(),
        }),
    }
}

#[cfg(feature = "typed-ir")]
fn inc_dec_for_step_skeleton_from_ast(
    stmt: &Value,
) -> Result<ClangStmtSkeleton, ClangFrontendError> {
    inc_dec_stmt_skeleton_from_ast(stmt, "ForStmt step")
}

#[cfg(feature = "typed-ir")]
fn inc_dec_stmt_skeleton_from_ast(
    stmt: &Value,
    context: &str,
) -> Result<ClangStmtSkeleton, ClangFrontendError> {
    let step = inc_dec_expr_skeleton_from_ast(stmt, true, false)?;
    let ClangExprSkeleton::IncDec { target, op, ty, .. } = step else {
        let reason = match step {
            ClangExprSkeleton::Unsupported { reason, .. } => reason,
            _ => format!("{context} must be an increment/decrement expression"),
        };
        return Ok(ClangStmtSkeleton::Unsupported { reason });
    };
    let target_ty = match inc_dec_assignment_target_type(target.as_ref(), context) {
        Ok(target_ty) => target_ty,
        Err(reason) => {
            return Ok(ClangStmtSkeleton::Unsupported { reason });
        }
    }
    .clone();
    if !is_integer_or_target_dependent_integer_type(&target_ty)
        || !is_same_lvalue_to_rvalue_integer_type(&target_ty, &ty)
    {
        return Ok(ClangStmtSkeleton::Unsupported {
            reason: format!(
                "{context} inc/dec target type {} is unsupported; parsed target {:?} does not match result type {} ({:?})",
                target_ty.canonical, target_ty.kind, ty.canonical, ty.kind
            ),
        });
    }
    let bin_op = match op {
        ClangIncDecOperator::Inc => ClangBinaryOperator::Add,
        ClangIncDecOperator::Dec => ClangBinaryOperator::Sub,
    };
    Ok(ClangStmtSkeleton::Assign {
        target: target.as_ref().clone(),
        value: ClangExprSkeleton::Binary {
            op: bin_op,
            lhs: target,
            rhs: Box::new(ClangExprSkeleton::IntegerLiteral {
                value: 1,
                spelling: "1".to_string(),
                ty: target_ty.clone(),
            }),
            ty: target_ty.clone(),
        },
    })
}

#[cfg(feature = "typed-ir")]
fn inc_dec_assignment_target_type<'a>(
    target: &'a ClangExprSkeleton,
    context: &str,
) -> Result<&'a ClangTypeSkeleton, String> {
    match target {
        ClangExprSkeleton::DeclRef { ty, .. } => Ok(ty),
        ClangExprSkeleton::Member {
            base,
            ty,
            is_arrow: true,
            ..
        } => {
            if context != "statement" && context != "ForStmt step" {
                return Err(format!(
                    "{context} inc/dec record pointer field targets are unsupported outside standalone statements or for-loop steps"
                ));
            }
            match base.as_ref() {
                ClangExprSkeleton::DeclRef { ty: base_ty, .. }
                    if clang_type_is_mutable_record_pointer(base_ty) =>
                {
                    Ok(ty)
                }
                ClangExprSkeleton::DeclRef { .. } => Err(format!(
                    "{context} inc/dec record pointer field target base must be a non-const record pointer variable"
                )),
                _ => Err(format!(
                    "{context} inc/dec record pointer field target must have a direct record pointer variable base"
                )),
            }
        }
        ClangExprSkeleton::Member {
            base,
            ty,
            is_arrow: false,
            ..
        } => {
            if context != "statement" && context != "ForStmt step" {
                return Err(format!(
                    "{context} inc/dec record field targets are unsupported outside standalone statements"
                ));
            }
            match base.as_ref() {
                ClangExprSkeleton::DeclRef { ty: base_ty, .. }
                    if matches!(&base_ty.kind, ClangTypeKind::Record { .. }) =>
                {
                    Ok(ty)
                }
                ClangExprSkeleton::DeclRef { .. } => Err(format!(
                    "{context} inc/dec record field target base must be a record variable"
                )),
                _ => Err(format!(
                    "{context} inc/dec record field target must have a direct record variable base"
                )),
            }
        }
        _ => Err(format!(
            "{context} inc/dec target must be a simple variable, by-value record field, or direct mutable record pointer field"
        )),
    }
}
