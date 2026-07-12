#[cfg(feature = "typed-ir")]
fn lower_array_decay_deref_to_index(
    expr: &ClangExprSkeleton,
    target: &ClangTypeSkeleton,
    ty: &ClangTypeSkeleton,
    index: IrExpr,
) -> Result<Option<IrExpr>, ClangFrontendError> {
    let ClangTypeKind::Pointer { pointee, .. } = &target.kind else {
        return Err(ClangFrontendError {
            kind: "unsupported_clang_expr".to_string(),
            message: format!(
                "ArrayToPointerDecay target {} is not a pointer type",
                target.spelled
            ),
        });
    };
    let ClangExprSkeleton::DeclRef { ty: array_ty, .. } = expr else {
        return Err(ClangFrontendError {
            kind: "unsupported_clang_expr".to_string(),
            message: "ArrayToPointerDecay deref currently requires a direct fixed array DeclRef"
                .to_string(),
        });
    };
    let ClangTypeKind::Array {
        element,
        len: Some(_),
    } = &array_ty.kind
    else {
        return Err(ClangFrontendError {
            kind: "unsupported_clang_expr".to_string(),
            message: format!(
                "ArrayToPointerDecay deref source {} is not a complete fixed array",
                array_ty.spelled
            ),
        });
    };
    let element_ty = lower_type(element)?;
    let pointer_pointee_ty = lower_type(pointee)?;
    let result_ty = lower_type(ty)?;
    if element_ty != pointer_pointee_ty || element_ty != result_ty {
        return Err(ClangFrontendError {
            kind: "unsupported_clang_expr".to_string(),
            message: "ArrayToPointerDecay deref requires matching array element, pointer pointee, and result types".to_string(),
        });
    }
    Ok(Some(IrExpr::Index {
        base: Box::new(lower_expr(expr)?),
        index: Box::new(index),
        ty: result_ty,
        source_span: None,
    }))
}

#[cfg(feature = "typed-ir")]
fn int_zero_literal_expr() -> IrExpr {
    IrExpr::LitInt {
        value: 0,
        spelling: "0".to_string(),
        ty: IrType {
            spelled: "int".to_string(),
            canonical: "int".to_string(),
            kind: IrTypeKind::Integer {
                signed: true,
                width: 32,
            },
            is_const: false,
            width_bits: Some(32),
            source_span: None,
        },
        source_span: None,
    }
}

#[cfg(feature = "typed-ir")]
fn validate_sizeof_result_fits_type(
    value: u64,
    ty: &ClangTypeSkeleton,
) -> Result<(), ClangFrontendError> {
    let ClangTypeKind::Integer {
        signed: false,
        width,
    } = ty.kind
    else {
        return Err(ClangFrontendError {
            kind: "unsupported_sizeof_type".to_string(),
            message: format!(
                "sizeof result type {} must be an ABI-bound unsigned integer before typed IR lowering",
                ty.spelled
            ),
        });
    };
    if width >= 64 || value < (1u64 << width) {
        Ok(())
    } else {
        Err(ClangFrontendError {
            kind: "unsupported_sizeof_type".to_string(),
            message: format!(
                "sizeof result {value} does not fit target result type {} width {width}",
                ty.spelled
            ),
        })
    }
}

#[cfg(feature = "typed-ir")]
fn validate_alignof_result_fits_type(
    value: u64,
    ty: &ClangTypeSkeleton,
) -> Result<(), ClangFrontendError> {
    let ClangTypeKind::Integer {
        signed: false,
        width,
    } = ty.kind
    else {
        return Err(ClangFrontendError {
            kind: "unsupported_alignof_type".to_string(),
            message: format!(
                "_Alignof result type {} must be an ABI-bound unsigned integer before typed IR lowering",
                ty.spelled
            ),
        });
    };
    if width >= 64 || value < (1u64 << width) {
        Ok(())
    } else {
        Err(ClangFrontendError {
            kind: "unsupported_alignof_type".to_string(),
            message: format!(
                "_Alignof result {value} does not fit target result type {} width {width}",
                ty.spelled
            ),
        })
    }
}

#[cfg(feature = "typed-ir")]
fn sizeof_type_bytes(ty: &ClangTypeSkeleton) -> Result<u64, ClangFrontendError> {
    match &ty.kind {
        ClangTypeKind::Integer { width, .. } if *width > 0 && *width % 8 == 0 => {
            Ok(u64::from(*width / 8))
        }
        ClangTypeKind::Integer { width, .. } => Err(ClangFrontendError {
            kind: "unsupported_sizeof_type".to_string(),
            message: format!(
                "sizeof({}) has non-byte-addressable width {width}; typed IR lowering requires explicit target ABI provenance",
                ty.spelled
            ),
        }),
        ClangTypeKind::Array { element, len } => {
            let len = len.ok_or_else(|| ClangFrontendError {
                kind: "unsupported_sizeof_type".to_string(),
                message: format!(
                    "sizeof({}) requires a complete array bound before typed IR lowering",
                    ty.spelled
                ),
            })?;
            let len = u64::try_from(len).map_err(|_| ClangFrontendError {
                kind: "unsupported_sizeof_type".to_string(),
                message: format!(
                    "sizeof({}) array bound exceeds the current typed IR byte-size representation",
                    ty.spelled
                ),
            })?;
            let element_size = sizeof_type_bytes(element)?;
            element_size
                .checked_mul(len)
                .ok_or_else(|| ClangFrontendError {
                    kind: "unsupported_sizeof_type".to_string(),
                    message: format!(
                        "sizeof({}) overflows the current typed IR byte-size representation",
                        ty.spelled
                    ),
                })
        }
        ClangTypeKind::Pointer {
            width: Some(width), ..
        } if *width > 0 && *width % 8 == 0 => Ok(u64::from(*width / 8)),
        ClangTypeKind::Pointer {
            width: Some(width), ..
        } => Err(ClangFrontendError {
            kind: "unsupported_sizeof_type".to_string(),
            message: format!(
                "sizeof({}) has non-byte-addressable pointer width {width}; typed IR lowering requires explicit target ABI provenance",
                ty.spelled
            ),
        }),
        ClangTypeKind::Pointer { width: None, .. } => Err(ClangFrontendError {
            kind: "unsupported_sizeof_type".to_string(),
            message: format!(
                "sizeof({}) requires target ABI pointer-width provenance before typed IR lowering",
                ty.spelled
            ),
        }),
        ClangTypeKind::Unsupported { reason } => Err(ClangFrontendError {
            kind: "unsupported_sizeof_type".to_string(),
            message: format!(
                "sizeof({}) requires target ABI width provenance before typed IR lowering: {reason}",
                ty.spelled
            ),
        }),
        _ => Err(ClangFrontendError {
            kind: "unsupported_sizeof_type".to_string(),
            message: format!(
                "sizeof({}) requires explicit C layout/ABI provenance before typed IR lowering",
                ty.spelled
            ),
        }),
    }
}
