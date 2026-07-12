
#[cfg(feature = "typed-ir")]
fn record_layout_size_bytes(
    ty: &ClangTypeSkeleton,
    target_abi: Option<&TargetAbiProfile>,
    layout: &ClangRecordLayoutBinding,
) -> Result<u64, ClangFrontendError> {
    let ClangTypeKind::Record { name } = &ty.kind else {
        return Err(ClangFrontendError {
            kind: "invalid_record_layout_binding".to_string(),
            message: format!(
                "record layout {} cannot bind non-record sizeof({})",
                layout.record_type, ty.spelled
            ),
        });
    };
    let expected = format!("struct {name}");
    let valid_hash = |value: &str| {
        value.len() == 64
            && value
                .bytes()
                .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
    };
    if layout.record_type != expected
        || layout.size_bytes == 0
        || layout.align_bytes == 0
        || !layout.align_bytes.is_power_of_two()
        || !layout.size_bytes.is_multiple_of(layout.align_bytes)
        || !valid_hash(&layout.dump_sha256)
        || !valid_hash(&layout.diagnostics_sha256)
        || !valid_hash(&layout.compile_arguments_sha256)
        || !valid_hash(&layout.compile_database_sha256)
        || target_abi != Some(&layout.target_abi)
        || layout.target_abi.triple_or_abi.trim().is_empty()
        || layout.target_abi.char_width != 8
        || layout.target_abi.int_width == 0
        || layout.target_abi.pointer_width == 0
    {
        return Err(ClangFrontendError {
            kind: "invalid_record_layout_binding".to_string(),
            message: format!(
                "sizeof({}) record-layout provenance is incomplete or mismatched",
                ty.spelled
            ),
        });
    }
    Ok(layout.size_bytes)
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
