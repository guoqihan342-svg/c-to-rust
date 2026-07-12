
#[cfg(feature = "clang-lowering-report")]
fn collect_binary_runtime_preconditions(
    op: &typed_ir::IrBinOp,
    ty: &typed_ir::IrType,
    source_span: &Option<typed_ir::SourceSpan>,
    preconditions: &mut Vec<serde_json::Value>,
) {
    if !is_integer_type(ty) {
        return;
    }
    let signed = is_signed_integer_type(ty);
    match op {
        typed_ir::IrBinOp::Add if signed => preconditions.push(runtime_precondition(
            "signed_add_no_overflow",
            "C signed addition must not overflow unless the slice contract declares a wrapping profile",
            op,
            ty,
            source_span,
        )),
        typed_ir::IrBinOp::Sub if signed => preconditions.push(runtime_precondition(
            "signed_sub_no_overflow",
            "C signed subtraction must not overflow unless the slice contract declares a wrapping profile",
            op,
            ty,
            source_span,
        )),
        typed_ir::IrBinOp::Mul if signed => preconditions.push(runtime_precondition(
            "signed_mul_no_overflow",
            "C signed multiplication must not overflow unless the slice contract declares a wrapping profile",
            op,
            ty,
            source_span,
        )),
        typed_ir::IrBinOp::Div => {
            preconditions.push(runtime_precondition(
                "division_divisor_nonzero",
                "C division requires a non-zero divisor",
                op,
                ty,
                source_span,
            ));
            if signed {
                preconditions.push(runtime_precondition(
                    "signed_division_no_overflow",
                    "C signed division must not evaluate MIN / -1 unless the slice contract models that UB boundary",
                    op,
                    ty,
                    source_span,
                ));
            }
        }
        typed_ir::IrBinOp::Mod => {
            preconditions.push(runtime_precondition(
                "modulo_divisor_nonzero",
                "C modulo requires a non-zero divisor",
                op,
                ty,
                source_span,
            ));
            if signed {
                preconditions.push(runtime_precondition(
                    "signed_modulo_no_overflow",
                    "C signed modulo must not evaluate MIN % -1 unless the slice contract models that UB boundary",
                    op,
                    ty,
                    source_span,
                ));
            }
        }
        typed_ir::IrBinOp::Shl | typed_ir::IrBinOp::Shr => {
            preconditions.push(runtime_precondition(
                "shift_count_in_range",
                "C shift count must be nonnegative and smaller than the shifted integer width",
                op,
                ty,
                source_span,
            ));
            if matches!(op, typed_ir::IrBinOp::Shl) && signed {
                preconditions.push(runtime_precondition(
                    "signed_left_shift_no_overflow",
                    "C signed left shift must not shift a negative value or overflow the result type (C11 6.5.7p4) unless the slice contract declares a wrapping profile",
                    op,
                    ty,
                    source_span,
                ));
            }
            if matches!(op, typed_ir::IrBinOp::Shr) && signed {
                preconditions.push(runtime_precondition(
                    "signed_right_shift_implementation_defined",
                    "C signed right shift is implementation-defined and requires an explicit slice/platform contract",
                    op,
                    ty,
                    source_span,
                ));
            }
        }
        _ => {}
    }
}

#[cfg(feature = "clang-lowering-report")]
fn collect_unary_runtime_preconditions(
    op: &typed_ir::IrUnOp,
    ty: &typed_ir::IrType,
    source_span: &Option<typed_ir::SourceSpan>,
    preconditions: &mut Vec<serde_json::Value>,
) {
    if !is_signed_integer_type(ty) {
        return;
    }
    if matches!(op, typed_ir::IrUnOp::Neg) {
        preconditions.push(unary_runtime_precondition(
            "signed_negation_no_overflow",
            "C signed negation must not evaluate -MIN (C11 6.5) unless the slice contract models that UB boundary",
            op,
            ty,
            source_span,
        ));
    }
}

#[cfg(feature = "clang-lowering-report")]
fn runtime_precondition(
    code: &str,
    detail: &str,
    op: &typed_ir::IrBinOp,
    ty: &typed_ir::IrType,
    source_span: &Option<typed_ir::SourceSpan>,
) -> serde_json::Value {
    runtime_precondition_for_node(
        code,
        detail,
        format!("IrExpr::Binary.{op:?}"),
        ty,
        source_span,
    )
}

#[cfg(feature = "clang-lowering-report")]
fn unary_runtime_precondition(
    code: &str,
    detail: &str,
    op: &typed_ir::IrUnOp,
    ty: &typed_ir::IrType,
    source_span: &Option<typed_ir::SourceSpan>,
) -> serde_json::Value {
    runtime_precondition_for_node(
        code,
        detail,
        format!("IrExpr::Unary.{op:?}"),
        ty,
        source_span,
    )
}

#[cfg(feature = "clang-lowering-report")]
fn runtime_precondition_for_node(
    code: &str,
    detail: &str,
    ir_node: String,
    ty: &typed_ir::IrType,
    source_span: &Option<typed_ir::SourceSpan>,
) -> serde_json::Value {
    json!({
        "code": code,
        "detail": detail,
        "ir_node": ir_node,
        "type": type_summary(ty),
        "source_span": source_span,
    })
}

#[cfg(feature = "clang-lowering-report")]
fn type_summary(ty: &typed_ir::IrType) -> serde_json::Value {
    match &ty.kind {
        typed_ir::IrTypeKind::Integer { signed, width } => json!({
            "spelled": ty.spelled,
            "canonical": ty.canonical,
            "kind": "integer",
            "signed": signed,
            "width": width,
        }),
        _ => json!({
            "spelled": ty.spelled,
            "canonical": ty.canonical,
            "kind": "unsupported",
        }),
    }
}

#[cfg(feature = "clang-lowering-report")]
fn is_integer_type(ty: &typed_ir::IrType) -> bool {
    matches!(ty.kind, typed_ir::IrTypeKind::Integer { .. })
}

#[cfg(feature = "clang-lowering-report")]
fn is_signed_integer_type(ty: &typed_ir::IrType) -> bool {
    matches!(ty.kind, typed_ir::IrTypeKind::Integer { signed: true, .. })
}

#[cfg(feature = "clang-lowering-report")]
fn readonly_global_summary(global: &typed_ir::IrGlobal) -> serde_json::Value {
    let array_len = match &global.ty.kind {
        typed_ir::IrTypeKind::Array { len, .. } => *len,
        _ => None,
    };
    let (init_kind, value_count) = match &global.init {
        typed_ir::IrGlobalInit::Zeroed => ("zeroed", array_len.unwrap_or(0)),
        typed_ir::IrGlobalInit::IntegerArray(values) => ("integer_array", values.len()),
    };
    json!({
        "name": global.name,
        "spelled_type": global.ty.spelled,
        "canonical_type": global.ty.canonical,
        "array_len": array_len,
        "init_kind": init_kind,
        "value_count": value_count,
    })
}
