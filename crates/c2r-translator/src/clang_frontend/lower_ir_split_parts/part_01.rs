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

#[cfg(feature = "typed-ir")]
fn alignof_type_bytes(
    ty: &ClangTypeSkeleton,
    alignment_bits: Option<u16>,
) -> Result<u64, ClangFrontendError> {
    match alignment_bits {
        Some(bits) if bits > 0 && bits % 8 == 0 => Ok(u64::from(bits / 8)),
        Some(bits) => Err(ClangFrontendError {
            kind: "unsupported_alignof_type".to_string(),
            message: format!(
                "_Alignof({}) has non-byte-addressable alignment {bits}; typed IR lowering requires explicit target alignment provenance",
                ty.spelled
            ),
        }),
        None => Err(ClangFrontendError {
            kind: "unsupported_alignof_type".to_string(),
            message: format!(
                "_Alignof({}) requires target ABI alignment profile before typed IR lowering",
                ty.spelled
            ),
        }),
    }
}

#[cfg(feature = "typed-ir")]
pub(super) fn compound_assignment_operator_from_opcode(
    opcode: Option<&str>,
) -> Result<ClangBinaryOperator, ClangFrontendError> {
    match opcode {
        Some("+=") => Ok(ClangBinaryOperator::Add),
        Some("-=") => Ok(ClangBinaryOperator::Sub),
        Some("*=") => Ok(ClangBinaryOperator::Mul),
        Some("/=") => Ok(ClangBinaryOperator::Div),
        Some("%=") => Ok(ClangBinaryOperator::Mod),
        Some("&=") => Ok(ClangBinaryOperator::BitAnd),
        Some("|=") => Ok(ClangBinaryOperator::BitOr),
        Some("^=") => Ok(ClangBinaryOperator::BitXor),
        Some("<<=") => Ok(ClangBinaryOperator::Shl),
        Some(">>=") => Ok(ClangBinaryOperator::Shr),
        Some(opcode) => Err(ClangFrontendError {
            kind: "unsupported_compound_assignment_operator".to_string(),
            message: format!("compound assignment opcode {opcode} is outside the current skeleton"),
        }),
        None => Err(ClangFrontendError {
            kind: "invalid_compound_assignment_operator".to_string(),
            message: "CompoundAssignOperator is missing opcode".to_string(),
        }),
    }
}

#[cfg(feature = "typed-ir")]
fn lower_binary_operator(op: &ClangBinaryOperator) -> IrBinOp {
    match op {
        ClangBinaryOperator::Add => IrBinOp::Add,
        ClangBinaryOperator::Sub => IrBinOp::Sub,
        ClangBinaryOperator::Mul => IrBinOp::Mul,
        ClangBinaryOperator::Div => IrBinOp::Div,
        ClangBinaryOperator::Mod => IrBinOp::Mod,
        ClangBinaryOperator::BitAnd => IrBinOp::BitAnd,
        ClangBinaryOperator::BitOr => IrBinOp::BitOr,
        ClangBinaryOperator::BitXor => IrBinOp::BitXor,
        ClangBinaryOperator::Shl => IrBinOp::Shl,
        ClangBinaryOperator::Shr => IrBinOp::Shr,
        ClangBinaryOperator::LogAnd => IrBinOp::LogAnd,
        ClangBinaryOperator::LogOr => IrBinOp::LogOr,
        ClangBinaryOperator::Eq => IrBinOp::Eq,
        ClangBinaryOperator::Neq => IrBinOp::Neq,
        ClangBinaryOperator::Lt => IrBinOp::Lt,
        ClangBinaryOperator::Le => IrBinOp::Le,
        ClangBinaryOperator::Gt => IrBinOp::Gt,
        ClangBinaryOperator::Ge => IrBinOp::Ge,
    }
}

#[cfg(feature = "typed-ir")]
fn lower_unary_operator(op: &ClangUnaryOperator) -> IrUnOp {
    match op {
        ClangUnaryOperator::Neg => IrUnOp::Neg,
        ClangUnaryOperator::Not => IrUnOp::Not,
        ClangUnaryOperator::BitNot => IrUnOp::BitNot,
    }
}

#[cfg(feature = "typed-ir")]
fn lower_inc_dec_operator(op: &ClangIncDecOperator) -> IrIncDecOp {
    match op {
        ClangIncDecOperator::Inc => IrIncDecOp::Inc,
        ClangIncDecOperator::Dec => IrIncDecOp::Dec,
    }
}

#[cfg(feature = "typed-ir")]
pub(super) fn lower_type(ty: &ClangTypeSkeleton) -> Result<IrType, ClangFrontendError> {
    match &ty.kind {
        ClangTypeKind::Void => Ok(IrType {
            spelled: ty.spelled.clone(),
            canonical: ty.canonical.clone(),
            kind: IrTypeKind::Void,
            is_const: clang_type_is_const(ty),
            width_bits: None,
            source_span: None,
        }),
        ClangTypeKind::Integer { signed, width } => Ok(IrType {
            spelled: ty.spelled.clone(),
            canonical: ty.canonical.clone(),
            kind: IrTypeKind::Integer {
                signed: *signed,
                width: *width,
            },
            is_const: clang_type_is_const(ty),
            width_bits: Some(*width),
            source_span: None,
        }),
        ClangTypeKind::Pointer { pointee, .. } => Ok(IrType {
            spelled: ty.spelled.clone(),
            canonical: ty.canonical.clone(),
            kind: IrTypeKind::Pointer {
                pointee: Box::new(lower_type(pointee)?),
            },
            is_const: false,
            width_bits: None,
            source_span: None,
        }),
        ClangTypeKind::Array { element, len } => Ok(IrType {
            spelled: ty.spelled.clone(),
            canonical: ty.canonical.clone(),
            kind: IrTypeKind::Array {
                element: Box::new(lower_type(element)?),
                len: *len,
            },
            is_const: clang_type_is_const(ty),
            width_bits: None,
            source_span: None,
        }),
        ClangTypeKind::Record { name } => Ok(IrType {
            spelled: ty.spelled.clone(),
            canonical: ty.canonical.clone(),
            kind: IrTypeKind::Record {
                name: name.clone(),
                fields: None,
            },
            is_const: clang_type_is_const(ty),
            width_bits: None,
            source_span: None,
        }),
        ClangTypeKind::Function => Ok(IrType {
            spelled: ty.spelled.clone(),
            canonical: ty.canonical.clone(),
            kind: IrTypeKind::Function,
            is_const: false,
            width_bits: None,
            source_span: None,
        }),
        ClangTypeKind::Unsupported { reason } => Err(ClangFrontendError {
            kind: "unsupported_clang_type".to_string(),
            message: reason.clone(),
        }),
    }
}

#[cfg(feature = "typed-ir")]
pub(super) fn clang_type_is_const(ty: &ClangTypeSkeleton) -> bool {
    ty.spelled.trim_start().starts_with("const ")
}
