use super::{
    clang_mutable_record_pointer_record_name,
    compound_assignment_target_is_direct_index, compound_assignment_target_is_direct_record_field,
    compound_assignment_target_type, index_compound_assignment_value_rejection_reason,
    record_field_compound_assignment_value_rejection_reason, ClangBinaryOperator,
    ClangExprSkeleton, ClangFrontendError, ClangIncDecOperator, ClangRecordLayoutBinding,
    ClangStmtSkeleton, ClangTypeKind, ClangTypeSkeleton, ClangUnaryOperator, TargetAbiProfile,
};
use crate::typed_ir::{
    IrBinOp, IrExpr, IrIncDecOp, IrRecordLayoutBinding, IrStmt, IrType, IrTypeKind, IrUnOp,
};

#[cfg(feature = "typed-ir")]
/// Lowers an accepted statement skeleton into typed IR without choosing Rust.
///
/// Unsupported skeletons become `unsupported_clang_stmt` errors, and every
/// nested expression or body is lowered through the same fail-closed path. This
/// keeps frontend semantics separate from the later Rust emitter.
pub(super) fn lower_stmt(stmt: &ClangStmtSkeleton) -> Result<IrStmt, ClangFrontendError> {
    match stmt {
        ClangStmtSkeleton::Decl { name, ty, init } => Ok(IrStmt::Decl {
            name: name.clone(),
            ty: lower_type(ty)?,
            init: init.as_ref().map(lower_expr).transpose()?,
            source_span: None,
        }),
        ClangStmtSkeleton::Assign { target, value } => Ok(IrStmt::Assign {
            target: lower_expr(target)?,
            value: lower_expr(value)?,
            source_span: None,
        }),
        ClangStmtSkeleton::CompoundAssign {
            target,
            op,
            value,
            result_ty,
            compute_lhs_ty,
            compute_result_ty,
        } => lower_compound_assign_stmt(
            target,
            op,
            value,
            result_ty,
            compute_lhs_ty,
            compute_result_ty,
        ),
        ClangStmtSkeleton::If {
            condition,
            then_body,
            else_body,
        } => Ok(IrStmt::If {
            condition: lower_expr(condition)?,
            then_body: then_body
                .iter()
                .map(lower_stmt)
                .collect::<Result<Vec<_>, ClangFrontendError>>()?,
            else_body: else_body
                .iter()
                .map(lower_stmt)
                .collect::<Result<Vec<_>, ClangFrontendError>>()?,
            source_span: None,
        }),
        ClangStmtSkeleton::While { condition, body } => Ok(IrStmt::While {
            condition: lower_expr(condition)?,
            body: body
                .iter()
                .map(lower_stmt)
                .collect::<Result<Vec<_>, ClangFrontendError>>()?,
            source_span: None,
        }),
        ClangStmtSkeleton::DoWhile { body, condition } => Ok(IrStmt::DoWhile {
            body: body
                .iter()
                .map(lower_stmt)
                .collect::<Result<Vec<_>, ClangFrontendError>>()?,
            condition: lower_expr(condition)?,
            source_span: None,
        }),
        ClangStmtSkeleton::For {
            init,
            condition,
            step,
            body,
        } => Ok(IrStmt::For {
            init: init
                .iter()
                .map(lower_stmt)
                .collect::<Result<Vec<_>, ClangFrontendError>>()?,
            condition: condition.as_ref().map(lower_expr).transpose()?,
            step: step.as_deref().map(lower_stmt).transpose()?.map(Box::new),
            body: body
                .iter()
                .map(lower_stmt)
                .collect::<Result<Vec<_>, ClangFrontendError>>()?,
            source_span: None,
        }),
        ClangStmtSkeleton::Return { value } => Ok(IrStmt::Return {
            value: value.as_ref().map(lower_expr).transpose()?,
            source_span: None,
        }),
        ClangStmtSkeleton::Break => Ok(IrStmt::Break { source_span: None }),
        ClangStmtSkeleton::Continue => Ok(IrStmt::Continue { source_span: None }),
        ClangStmtSkeleton::Expr { expr } => match lower_record_memset_statement(expr)? {
            Some(stmt) => Ok(stmt),
            None => Ok(IrStmt::Expr {
                expr: lower_expr(expr)?,
                source_span: None,
            }),
        },
        ClangStmtSkeleton::Unsupported { reason } => Err(ClangFrontendError {
            kind: "unsupported_clang_stmt".to_string(),
            message: reason.clone(),
        }),
    }
}

#[cfg(feature = "typed-ir")]
fn lower_compound_assign_stmt(
    target: &ClangExprSkeleton,
    op: &ClangBinaryOperator,
    value: &ClangExprSkeleton,
    result_ty: &ClangTypeSkeleton,
    compute_lhs_ty: &ClangTypeSkeleton,
    compute_result_ty: &ClangTypeSkeleton,
) -> Result<IrStmt, ClangFrontendError> {
    let target_ty = compound_assignment_target_type(target)
        .map_err(|reason| ClangFrontendError {
            kind: "unsupported_compound_assignment_target".to_string(),
            message: reason,
        })
        .and_then(lower_type)?;
    let result_ty = lower_type(result_ty)?;
    let compute_lhs_ty = lower_type(compute_lhs_ty)?;
    let compute_result_ty = lower_type(compute_result_ty)?;
    if !ir_types_match_for_clang(&target_ty, &result_ty) {
        return Err(ClangFrontendError {
            kind: "unsupported_compound_assignment_type".to_string(),
            message: format!(
                "compound assignment result type must match target type: target={}, result={}",
                target_ty.canonical, result_ty.canonical
            ),
        });
    }
    if !ir_types_match_for_clang(&compute_lhs_ty, &compute_result_ty) {
        return Err(ClangFrontendError {
            kind: "unsupported_compound_assignment_type".to_string(),
            message: format!(
                "compound assignment compute lhs/result types must match: compute_lhs={}, compute_result={}",
                compute_lhs_ty.canonical, compute_result_ty.canonical
            ),
        });
    }
    if compound_assignment_target_is_direct_record_field(target) {
        if let Some(reason) = record_field_compound_assignment_value_rejection_reason(value) {
            return Err(ClangFrontendError {
                kind: "unsupported_compound_assignment_value".to_string(),
                message: reason,
            });
        }
    }
    if compound_assignment_target_is_direct_index(target) {
        if let Some(reason) = index_compound_assignment_value_rejection_reason(value) {
            return Err(ClangFrontendError {
                kind: "unsupported_compound_assignment_value".to_string(),
                message: reason,
            });
        }
    }
    let target = lower_expr(target)?;
    let lhs =
        cast_ir_expr_to_type_if_needed(compound_assignment_read_target(&target), &compute_lhs_ty);
    let rhs = cast_ir_expr_to_type_if_needed(lower_expr(value)?, &compute_lhs_ty);
    let binary = IrExpr::Binary {
        op: lower_binary_operator(op),
        lhs: Box::new(lhs),
        rhs: Box::new(rhs),
        ty: compute_lhs_ty,
        source_span: None,
    };
    let value = cast_ir_expr_to_type_if_needed(binary, &target_ty);

    Ok(IrStmt::Assign {
        target,
        value,
        source_span: None,
    })
}

#[cfg(feature = "typed-ir")]
fn compound_assignment_read_target(target: &IrExpr) -> IrExpr {
    let mut read_target = target.clone();
    let IrExpr::Index { base, .. } = &mut read_target else {
        return read_target;
    };
    let IrExpr::Var { ty, .. } = base.as_mut() else {
        return read_target;
    };
    let IrTypeKind::Pointer { pointee } = &mut ty.kind else {
        return read_target;
    };

    // The compound read is a readonly reborrow of the mutable slice target.
    pointee.is_const = true;
    read_target
}

#[cfg(feature = "typed-ir")]
fn cast_ir_expr_to_type_if_needed(expr: IrExpr, target: &IrType) -> IrExpr {
    if ir_expr_type_matches(&expr, target) {
        expr
    } else {
        IrExpr::Cast {
            target: target.clone(),
            expr: Box::new(expr),
            implicit: true,
            source_span: None,
        }
    }
}

#[cfg(feature = "typed-ir")]
fn ir_types_match_for_clang(lhs: &IrType, rhs: &IrType) -> bool {
    lhs.canonical == rhs.canonical && lhs.kind == rhs.kind && lhs.is_const == rhs.is_const
}

#[cfg(feature = "typed-ir")]
fn ir_expr_type_matches(expr: &IrExpr, expected: &IrType) -> bool {
    match expr {
        IrExpr::Var { ty, .. }
        | IrExpr::LitInt { ty, .. }
        | IrExpr::NullPtr { ty, .. }
        | IrExpr::Binary { ty, .. }
        | IrExpr::Unary { ty, .. }
        | IrExpr::Conditional { ty, .. }
        | IrExpr::IncDec { ty, .. }
        | IrExpr::Deref { ty, .. }
        | IrExpr::Index { ty, .. }
        | IrExpr::ArrayLiteral { ty, .. }
        | IrExpr::Call { ty, .. }
        | IrExpr::Member { ty, .. }
        | IrExpr::AddrOf { ty, .. } => ir_types_match_for_clang(ty, expected),
        IrExpr::MutableVoidPointerAddress { target, .. } => {
            ir_types_match_for_clang(target, expected)
        }
        IrExpr::Cast { target, .. }
        | IrExpr::LValueToRValue { target, .. }
        | IrExpr::ArrayToPointerDecay { target, .. }
        | IrExpr::FunctionToPointerDecay { target, .. } => {
            ir_types_match_for_clang(target, expected)
        }
        IrExpr::Unsupported { .. } => false,
    }
}
