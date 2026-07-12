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

#[cfg(feature = "typed-ir")]
/// Lowers an accepted expression skeleton into typed IR with clang-derived type data.
///
/// The conversion preserves casts, pointer/member/index structure, and source
/// type boundaries for the emitter and validators. Unknown expression nodes are
/// rejected here rather than represented as best-effort Rust.
pub(super) fn lower_expr(expr: &ClangExprSkeleton) -> Result<IrExpr, ClangFrontendError> {
    match expr {
        ClangExprSkeleton::DeclRef { name, ty } => Ok(IrExpr::Var {
            name: name.clone(),
            ty: lower_type(ty)?,
            source_span: None,
        }),
        ClangExprSkeleton::IntegerLiteral {
            value,
            spelling,
            ty,
        } => Ok(IrExpr::LitInt {
            value: *value,
            spelling: spelling.clone(),
            ty: lower_type(ty)?,
            source_span: None,
        }),
        ClangExprSkeleton::SizeOfType {
            arg_type,
            ty,
            record_layout,
            target_abi,
        } => {
            let value = match record_layout {
                Some(layout) => {
                    record_layout_size_bytes(arg_type, target_abi.as_ref(), layout)?
                }
                None => sizeof_type_bytes(arg_type)?,
            };
            validate_sizeof_result_fits_type(value, ty)?;
            Ok(IrExpr::LitInt {
                value,
                spelling: value.to_string(),
                ty: lower_type(ty)?,
                source_span: None,
            })
        }
        ClangExprSkeleton::AlignOfType {
            arg_type,
            ty,
            alignment_bits,
            ..
        } => {
            let value = alignof_type_bytes(arg_type, *alignment_bits)?;
            validate_alignof_result_fits_type(value, ty)?;
            Ok(IrExpr::LitInt {
                value,
                spelling: value.to_string(),
                ty: lower_type(ty)?,
                source_span: None,
            })
        }
        ClangExprSkeleton::NullPtr { ty } => Ok(IrExpr::NullPtr {
            ty: lower_type(ty)?,
            source_span: None,
        }),
        ClangExprSkeleton::Binary { op, lhs, rhs, ty } => Ok(IrExpr::Binary {
            op: lower_binary_operator(op),
            lhs: Box::new(lower_expr(lhs)?),
            rhs: Box::new(lower_expr(rhs)?),
            ty: lower_type(ty)?,
            source_span: None,
        }),
        ClangExprSkeleton::Unary { op, operand, ty } => Ok(IrExpr::Unary {
            op: lower_unary_operator(op),
            operand: Box::new(lower_expr(operand)?),
            ty: lower_type(ty)?,
            source_span: None,
        }),
        ClangExprSkeleton::Conditional {
            condition,
            then_expr,
            else_expr,
            ty,
        } => Ok(IrExpr::Conditional {
            condition: Box::new(lower_expr(condition)?),
            then_expr: Box::new(lower_expr(then_expr)?),
            else_expr: Box::new(lower_expr(else_expr)?),
            ty: lower_type(ty)?,
            source_span: None,
        }),
        ClangExprSkeleton::IncDec {
            target,
            op,
            prefix,
            ty,
        } => Ok(IrExpr::IncDec {
            target: Box::new(lower_expr(target)?),
            op: lower_inc_dec_operator(op),
            prefix: *prefix,
            ty: lower_type(ty)?,
            source_span: None,
        }),
        ClangExprSkeleton::Deref { ptr, ty } => {
            if let Some(expr) = lower_array_decay_deref_expr(ptr, ty)? {
                return Ok(expr);
            }
            Ok(IrExpr::Deref {
                ptr: Box::new(lower_expr(ptr)?),
                ty: lower_type(ty)?,
                source_span: None,
            })
        }
        ClangExprSkeleton::AddrOf { operand, ty } => Ok(IrExpr::AddrOf {
            operand: Box::new(lower_expr(operand)?),
            ty: lower_type(ty)?,
            source_span: None,
        }),
        ClangExprSkeleton::MutableVoidPointerAddress {
            operand,
            source_pointer,
            target,
        } => Ok(IrExpr::MutableVoidPointerAddress {
            operand: Box::new(lower_expr(operand)?),
            source_pointer: lower_type(source_pointer)?,
            target: lower_type(target)?,
            source_span: None,
        }),
        ClangExprSkeleton::Cast {
            target,
            expr,
            implicit,
        } => Ok(IrExpr::Cast {
            target: lower_type(target)?,
            expr: Box::new(lower_expr(expr)?),
            implicit: *implicit,
            source_span: None,
        }),
        ClangExprSkeleton::LValueToRValue { target, expr } => Ok(IrExpr::LValueToRValue {
            target: lower_type(target)?,
            expr: Box::new(lower_expr(expr)?),
            source_span: None,
        }),
        ClangExprSkeleton::ArrayToPointerDecay { target, expr } => {
            Ok(IrExpr::ArrayToPointerDecay {
                target: lower_type(target)?,
                expr: Box::new(lower_expr(expr)?),
                source_span: None,
            })
        }
        ClangExprSkeleton::FunctionToPointerDecay { target, expr } => {
            Ok(IrExpr::FunctionToPointerDecay {
                target: lower_type(target)?,
                expr: Box::new(lower_expr(expr)?),
                source_span: None,
            })
        }
        ClangExprSkeleton::Index { base, index, ty } => Ok(IrExpr::Index {
            base: Box::new(lower_expr(base)?),
            index: Box::new(lower_expr(index)?),
            ty: lower_type(ty)?,
            source_span: None,
        }),
        ClangExprSkeleton::ArrayLiteral { elements, ty } => Ok(IrExpr::ArrayLiteral {
            elements: elements
                .iter()
                .map(lower_expr)
                .collect::<Result<Vec<_>, ClangFrontendError>>()?,
            ty: lower_type(ty)?,
            source_span: None,
        }),
        ClangExprSkeleton::Call { callee, args, ty } => Ok(IrExpr::Call {
            callee: callee.clone(),
            args: args
                .iter()
                .map(lower_expr)
                .collect::<Result<Vec<_>, ClangFrontendError>>()?,
            ty: lower_type(ty)?,
            source_span: None,
        }),
        ClangExprSkeleton::Member {
            base,
            field,
            ty,
            is_arrow,
        } => Ok(IrExpr::Member {
            base: Box::new(lower_expr(base)?),
            field: field.clone(),
            ty: lower_type(ty)?,
            is_arrow: *is_arrow,
            source_span: None,
        }),
        ClangExprSkeleton::Unsupported { node, reason } => Err(ClangFrontendError {
            kind: "unsupported_clang_expr".to_string(),
            message: format!("{node}: {reason}"),
        }),
    }
}

#[cfg(feature = "typed-ir")]
fn lower_array_decay_deref_expr(
    ptr: &ClangExprSkeleton,
    ty: &ClangTypeSkeleton,
) -> Result<Option<IrExpr>, ClangFrontendError> {
    if let ClangExprSkeleton::ArrayToPointerDecay { target, expr } = ptr {
        return lower_array_decay_deref_to_index(expr, target, ty, int_zero_literal_expr());
    }

    let ClangExprSkeleton::Binary {
        op: ClangBinaryOperator::Add,
        lhs,
        rhs,
        ty: binary_ty,
    } = ptr
    else {
        return Ok(None);
    };

    let Some((target, expr, index)) = array_decay_pointer_add_parts(lhs, rhs) else {
        return Ok(None);
    };
    let index_ty = clang_expr_skeleton_type(index).ok_or_else(|| ClangFrontendError {
        kind: "unsupported_clang_expr".to_string(),
        message: "ArrayToPointerDecay pointer-add deref requires a typed integer index expression"
            .to_string(),
    })?;
    if !matches!(index_ty.kind, ClangTypeKind::Integer { .. }) {
        return Err(ClangFrontendError {
            kind: "unsupported_clang_expr".to_string(),
            message: format!(
                "ArrayToPointerDecay pointer-add deref requires integer index, got {}",
                index_ty.spelled
            ),
        });
    }

    let ClangTypeKind::Pointer { pointee, .. } = &binary_ty.kind else {
        return Err(ClangFrontendError {
            kind: "unsupported_clang_expr".to_string(),
            message: format!(
                "ArrayToPointerDecay pointer-add result {} is not a pointer type",
                binary_ty.spelled
            ),
        });
    };
    let result_ty = lower_type(ty)?;
    let pointee_ty = lower_type(pointee)?;
    if result_ty != pointee_ty {
        return Err(ClangFrontendError {
            kind: "unsupported_clang_expr".to_string(),
            message: "ArrayToPointerDecay pointer-add deref requires matching pointer pointee and result types".to_string(),
        });
    }

    lower_array_decay_deref_to_index(expr, target, ty, lower_expr(index)?)
}

#[cfg(feature = "typed-ir")]
fn array_decay_pointer_add_parts<'a>(
    lhs: &'a ClangExprSkeleton,
    rhs: &'a ClangExprSkeleton,
) -> Option<(
    &'a ClangTypeSkeleton,
    &'a ClangExprSkeleton,
    &'a ClangExprSkeleton,
)> {
    match (lhs, rhs) {
        (ClangExprSkeleton::ArrayToPointerDecay { target, expr }, index)
        | (index, ClangExprSkeleton::ArrayToPointerDecay { target, expr }) => {
            Some((target, expr, index))
        }
        _ => None,
    }
}

#[cfg(feature = "typed-ir")]
pub(super) fn clang_expr_skeleton_type(expr: &ClangExprSkeleton) -> Option<&ClangTypeSkeleton> {
    match expr {
        ClangExprSkeleton::DeclRef { ty, .. }
        | ClangExprSkeleton::IntegerLiteral { ty, .. }
        | ClangExprSkeleton::SizeOfType { ty, .. }
        | ClangExprSkeleton::AlignOfType { ty, .. }
        | ClangExprSkeleton::NullPtr { ty }
        | ClangExprSkeleton::Binary { ty, .. }
        | ClangExprSkeleton::Unary { ty, .. }
        | ClangExprSkeleton::Conditional { ty, .. }
        | ClangExprSkeleton::IncDec { ty, .. }
        | ClangExprSkeleton::Deref { ty, .. }
        | ClangExprSkeleton::AddrOf { ty, .. }
        | ClangExprSkeleton::Index { ty, .. }
        | ClangExprSkeleton::ArrayLiteral { ty, .. }
        | ClangExprSkeleton::Call { ty, .. }
        | ClangExprSkeleton::Member { ty, .. } => Some(ty),
        ClangExprSkeleton::MutableVoidPointerAddress { target, .. } => Some(target),
        ClangExprSkeleton::Cast { target, .. }
        | ClangExprSkeleton::LValueToRValue { target, .. }
        | ClangExprSkeleton::ArrayToPointerDecay { target, .. }
        | ClangExprSkeleton::FunctionToPointerDecay { target, .. } => Some(target),
        ClangExprSkeleton::Unsupported { .. } => None,
    }
}
