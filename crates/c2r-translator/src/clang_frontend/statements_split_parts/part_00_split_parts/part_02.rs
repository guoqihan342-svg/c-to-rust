
#[cfg(feature = "typed-ir")]
fn compound_assignment_index_rejection_reason(index: &ClangExprSkeleton) -> Option<String> {
    match index {
        ClangExprSkeleton::DeclRef { ty, .. }
        | ClangExprSkeleton::IntegerLiteral { ty, .. } => {
            if matches!(&ty.kind, ClangTypeKind::Integer { .. }) {
                None
            } else {
                Some(format!(
                    "compound assignment index must be an integer literal, variable, or integral cast; got {}",
                    ty.spelled
                ))
            }
        }
        ClangExprSkeleton::Cast { target, expr, .. }
        | ClangExprSkeleton::LValueToRValue { target, expr } => {
            if !matches!(&target.kind, ClangTypeKind::Integer { .. }) {
                return Some(format!(
                    "compound assignment index cast target must be an integer; got {}",
                    target.spelled
                ));
            }
            compound_assignment_index_rejection_reason(expr)
        }
        ClangExprSkeleton::Unsupported { node, reason } => Some(format!(
            "compound assignment index uses unsupported expression {node}: {reason}"
        )),
        _ => Some(
            "compound assignment index must be a side-effect-free integer literal, variable, or integral cast"
                .to_string(),
        ),
    }
}

#[cfg(feature = "typed-ir")]
fn compound_assignment_target_is_direct_index(target: &ClangExprSkeleton) -> bool {
    matches!(target, ClangExprSkeleton::Index { .. })
}

#[cfg(feature = "typed-ir")]
fn index_compound_assignment_value_rejection_reason(value: &ClangExprSkeleton) -> Option<String> {
    match value {
        ClangExprSkeleton::DeclRef { ty, .. }
        | ClangExprSkeleton::IntegerLiteral { ty, .. } => {
            if matches!(&ty.kind, ClangTypeKind::Integer { .. }) {
                None
            } else {
                Some(format!(
                    "index compound assignment RHS must be a side-effect-free integer expression; got {}",
                    ty.spelled
                ))
            }
        }
        ClangExprSkeleton::Cast { target, expr, .. }
        | ClangExprSkeleton::LValueToRValue { target, expr } => {
            if !matches!(&target.kind, ClangTypeKind::Integer { .. }) {
                return Some(format!(
                    "index compound assignment RHS cast target must be an integer; got {}",
                    target.spelled
                ));
            }
            index_compound_assignment_value_rejection_reason(expr)
        }
        ClangExprSkeleton::Binary {
            op,
            lhs,
            rhs,
            ty,
        } if matches!(
            op,
            ClangBinaryOperator::Add
                | ClangBinaryOperator::Sub
                | ClangBinaryOperator::Mul
                | ClangBinaryOperator::Div
                | ClangBinaryOperator::Mod
                | ClangBinaryOperator::BitAnd
                | ClangBinaryOperator::BitOr
                | ClangBinaryOperator::BitXor
                | ClangBinaryOperator::Shl
                | ClangBinaryOperator::Shr
        ) => {
            if !matches!(&ty.kind, ClangTypeKind::Integer { .. }) {
                return Some(format!(
                    "index compound assignment RHS binary result must be an integer; got {}",
                    ty.spelled
                ));
            }
            index_compound_assignment_value_rejection_reason(lhs)
                .or_else(|| index_compound_assignment_value_rejection_reason(rhs))
        }
        ClangExprSkeleton::Unary {
            op: ClangUnaryOperator::Neg | ClangUnaryOperator::BitNot,
            operand,
            ty,
        } => {
            if !matches!(&ty.kind, ClangTypeKind::Integer { .. }) {
                return Some(format!(
                    "index compound assignment RHS unary result must be an integer; got {}",
                    ty.spelled
                ));
            }
            index_compound_assignment_value_rejection_reason(operand)
        }
        ClangExprSkeleton::Unsupported { node, reason } => Some(format!(
            "index compound assignment RHS uses unsupported expression {node}: {reason}"
        )),
        _ => Some(
            "index compound assignment RHS must be built from integer literals, variables, casts, and side-effect-free arithmetic or bitwise operators"
                .to_string(),
        ),
    }
}

#[cfg(feature = "typed-ir")]
fn compound_assignment_target_is_direct_record_field(target: &ClangExprSkeleton) -> bool {
    compound_assignment_target_is_by_value_record_field(target)
        || compound_assignment_target_is_mutable_record_pointer_field(target)
}

#[cfg(feature = "typed-ir")]
fn compound_assignment_target_is_by_value_record_field(target: &ClangExprSkeleton) -> bool {
    matches!(
        target,
        ClangExprSkeleton::Member {
            base,
            is_arrow: false,
            ..
        } if matches!(
            base.as_ref(),
            ClangExprSkeleton::DeclRef {
                ty: ClangTypeSkeleton {
                    kind: ClangTypeKind::Record { .. },
                    ..
                },
                ..
            }
        )
    )
}

#[cfg(feature = "typed-ir")]
fn compound_assignment_target_is_mutable_record_pointer_field(target: &ClangExprSkeleton) -> bool {
    matches!(
        target,
        ClangExprSkeleton::Member {
            base,
            is_arrow: true,
            ..
        } if matches!(
            base.as_ref(),
            ClangExprSkeleton::DeclRef {
                ty,
                ..
            } if clang_type_is_mutable_record_pointer(ty)
        )
    )
}

#[cfg(feature = "typed-ir")]
fn clang_type_is_mutable_record_pointer(ty: &ClangTypeSkeleton) -> bool {
    matches!(
        &ty.kind,
        ClangTypeKind::Pointer { pointee, .. }
            if !clang_type_is_const(pointee)
                && matches!(&pointee.kind, ClangTypeKind::Record { .. })
    )
}
