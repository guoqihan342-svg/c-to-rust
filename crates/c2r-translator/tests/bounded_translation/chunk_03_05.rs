#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_runs_unsigned_mul_with_wrapping_semantics() {
    let u32_ty = ir_u32();
    let ir = IrFunction {
        name: "mul_two".to_string(),
        return_type: u32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: u32_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(ir_binary(
                IrBinOp::Mul,
                ir_var("value", u32_ty.clone()),
                ir_lit(2, "2U", u32_ty.clone()),
                u32_ty,
            )),
            source_span: None,
        }],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit unsigned wrapping mul");

    assert_rust_snippet_runs(
        "typed-ir-unsigned-wrapping-mul",
        &emitted.rust,
        "assert_eq!(mul_two(u32::MAX), 0xFFFF_FFFEu32);",
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_division_by_zero_literal() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "bad_div_zero".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(ir_binary(
                IrBinOp::Div,
                ir_var("value", i32_ty.clone()),
                ir_lit(0, "0", i32_ty.clone()),
                i32_ty,
            )),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("division by zero must fail closed");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(error.reason.contains("division by zero literal"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_modulo_by_zero_literal() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "bad_mod_zero".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(ir_binary(
                IrBinOp::Mod,
                ir_var("value", i32_ty.clone()),
                ir_lit(0, "0", i32_ty.clone()),
                i32_ty,
            )),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("modulo by zero must fail closed");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(error.reason.contains("modulo by zero literal"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_shift_count_equal_to_integer_width_literal() {
    let u32_ty = ir_u32();
    let ir = IrFunction {
        name: "bad_shift_width".to_string(),
        return_type: u32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: u32_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(ir_binary(
                IrBinOp::Shl,
                ir_var("value", u32_ty.clone()),
                ir_lit(32, "32U", u32_ty.clone()),
                u32_ty,
            )),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("invalid shift count must fail closed");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(error.reason.contains("shift count literal 32"));
    assert!(error.reason.contains("width 32"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_negative_shift_count_literal() {
    let u32_ty = ir_u32();
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "bad_shift_negative".to_string(),
        return_type: u32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: u32_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(ir_binary(
                IrBinOp::Shr,
                ir_var("value", u32_ty.clone()),
                ir_neg(ir_lit(1, "1", i32_ty.clone()), i32_ty),
                u32_ty,
            )),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("negative shift count must fail closed");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(error.reason.contains("negative shift count literal"));
}
#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_signed_right_shift_without_contract() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "bad_signed_rshift".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(ir_binary(
                IrBinOp::Shr,
                ir_var("value", i32_ty.clone()),
                ir_lit(1, "1", i32_ty.clone()),
                i32_ty,
            )),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("signed right shift must fail closed");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(error.reason.contains("signed right shift"));
    assert!(error.reason.contains("implementation-defined"));
}
