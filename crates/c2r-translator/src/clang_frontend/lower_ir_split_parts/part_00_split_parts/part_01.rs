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
