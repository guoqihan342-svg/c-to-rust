#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_decl_init_type_mismatch_in_generic_emitter() {
    let u32_ty = ir_u32();
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "bad_decl".to_string(),
        return_type: u32_ty.clone(),
        params: vec![],
        body: vec![
            IrStmt::Decl {
                name: "tmp".to_string(),
                ty: u32_ty.clone(),
                init: Some(ir_lit(1, "1", i32_ty)),
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("tmp", u32_ty)),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("decl init type mismatch must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("decl tmp initializer type i32"));
    assert!(error.reason.contains("expected type u32"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_bitnot_operand_type_mismatch_in_generic_emitter() {
    let u32_ty = ir_u32();
    let u8_ty = ir_u8();
    let ir = IrFunction {
        name: "bad_bitnot".to_string(),
        return_type: u32_ty.clone(),
        params: vec![IrParam {
            name: "x".to_string(),
            ty: u8_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(ir_bitnot(ir_var("x", u8_ty), u32_ty)),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("bitnot operand type mismatch must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("bitnot operand type u8"));
    assert!(error.reason.contains("expected type u32"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_unsigned_unary_minus_in_generic_emitter() {
    let u32_ty = ir_u32();
    let ir = IrFunction {
        name: "bad_unsigned_neg".to_string(),
        return_type: u32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: u32_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(ir_neg(ir_var("value", u32_ty.clone()), u32_ty)),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("unsigned unary minus must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(
        error.reason.contains("signed integer"),
        "unexpected error for unsigned unary minus: {}",
        error.reason
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_mismatched_signed_unary_minus_type_in_generic_emitter() {
    let i16_ty = ir_integer("short", "short", true, 16);
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "bad_signed_neg_width".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i16_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(ir_neg(ir_var("value", i16_ty), i32_ty)),
            source_span: None,
        }],
        source_span: None,
    };

    let error =
        emit_rust_from_ir(&ir).expect_err("signed unary minus type mismatch must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(
        error
            .reason
            .contains("unary minus operand type i16 does not match result type i32"),
        "unexpected error for signed unary minus mismatch: {}",
        error.reason
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_logical_not_return_value() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "is_zero_value".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(ir_not(ir_var("value", i32_ty.clone()), i32_ty.clone())),
            source_span: None,
        }],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit logical not return value");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub fn is_zero_value(value: i32) -> i32"));
    assert!(rust.contains("return (if value == 0i32 { 1i32 } else { 0i32 });"));
    assert_rust_snippet_compiles("typed-ir-logical-not-return-value", rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_logical_not_u8_operand_as_c_int_value() {
    let i32_ty = ir_i32();
    let u8_ty = ir_u8();
    let ir = IrFunction {
        name: "is_zero_byte".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: u8_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(ir_not(ir_var("value", u8_ty), i32_ty)),
            source_span: None,
        }],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit logical not u8 operand as C int value");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub fn is_zero_byte(value: u8) -> i32"));
    assert!(rust.contains("return (if value == 0u8 { 1i32 } else { 0i32 });"));
    assert_rust_snippet_compiles("typed-ir-logical-not-u8-operand", rust);
}
