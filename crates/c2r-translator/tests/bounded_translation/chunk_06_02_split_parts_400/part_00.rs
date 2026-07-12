#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_conditional_return_value() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "select_value".to_string(),
        return_type: i32_ty.clone(),
        params: vec![
            IrParam {
                name: "flag".to_string(),
                ty: i32_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "left".to_string(),
                ty: i32_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "right".to_string(),
                ty: i32_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![IrStmt::Return {
            value: Some(ir_conditional(
                ir_var("flag", i32_ty.clone()),
                ir_var("left", i32_ty.clone()),
                ir_var("right", i32_ty.clone()),
                i32_ty.clone(),
            )),
            source_span: None,
        }],
        source_span: None,
    };

    let rust = emit_rust_from_ir(&ir).expect("emit conditional return value");

    assert!(rust.contains("pub fn select_value(flag: i32, left: i32, right: i32) -> i32"));
    assert!(rust.contains("return (if flag != 0i32 { left } else { right });"));
    assert_rust_snippet_compiles("typed-ir-conditional-return-value", &rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_conditional_assignment_value() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "select_into_value".to_string(),
        return_type: i32_ty.clone(),
        params: vec![
            IrParam {
                name: "flag".to_string(),
                ty: i32_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "value".to_string(),
                ty: i32_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "fallback".to_string(),
                ty: i32_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![
            IrStmt::Assign {
                target: ir_var("value", i32_ty.clone()),
                value: ir_conditional(
                    ir_var("flag", i32_ty.clone()),
                    ir_var("value", i32_ty.clone()),
                    ir_var("fallback", i32_ty.clone()),
                    i32_ty.clone(),
                ),
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("value", i32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let rust = emit_rust_from_ir(&ir).expect("emit conditional assignment value");

    assert!(
        rust.contains("pub fn select_into_value(flag: i32, mut value: i32, fallback: i32) -> i32")
    );
    assert!(rust.contains("value = (if flag != 0i32 { value } else { fallback });"));
    assert!(rust.contains("return value;"));
    assert_rust_snippet_compiles("typed-ir-conditional-assignment-value", &rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_conditional_decl_initializer() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "select_init".to_string(),
        return_type: i32_ty.clone(),
        params: vec![
            IrParam {
                name: "flag".to_string(),
                ty: i32_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "left".to_string(),
                ty: i32_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "right".to_string(),
                ty: i32_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![
            IrStmt::Decl {
                name: "out".to_string(),
                ty: i32_ty.clone(),
                init: Some(ir_conditional(
                    ir_var("flag", i32_ty.clone()),
                    ir_var("left", i32_ty.clone()),
                    ir_var("right", i32_ty.clone()),
                    i32_ty.clone(),
                )),
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("out", i32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let rust = emit_rust_from_ir(&ir).expect("emit conditional decl initializer");

    assert!(rust.contains("pub fn select_init(flag: i32, left: i32, right: i32) -> i32"));
    assert!(rust.contains("let mut out: i32 = (if flag != 0i32 { left } else { right });"));
    assert!(rust.contains("return out;"));
    assert_rust_snippet_compiles("typed-ir-conditional-decl-initializer", &rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_conditional_value_with_mismatched_arm_types() {
    let i32_ty = ir_i32();
    let u32_ty = ir_u32();
    let ir = IrFunction {
        name: "bad_conditional_arm_types".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "flag".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(ir_conditional(
                ir_var("flag", i32_ty.clone()),
                ir_lit(1, "1", i32_ty.clone()),
                ir_lit(2, "2U", u32_ty),
                i32_ty.clone(),
            )),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("mismatched conditional arms must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("return expr"));
    assert!(error
        .reason
        .contains("conditional else expression type u32 does not match expected type i32"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_conditional_value_with_call_arm() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "bad_conditional_call_arm".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "flag".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(ir_conditional(
                ir_var("flag", i32_ty.clone()),
                IrExpr::Call {
                    callee: "helper".to_string(),
                    args: vec![],
                    ty: i32_ty.clone(),
                    source_span: None,
                },
                ir_lit(0, "0", i32_ty.clone()),
                i32_ty.clone(),
            )),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("conditional call arm must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("return expr"));
    assert!(error
        .reason
        .contains("conditional then expression call expression helper is unsupported"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_conditional_value_with_post_increment_byte_read_arm() {
    let i32_ty = ir_i32();
    let u8_ty = ir_u8();
    let const_u8_ptr = ir_pointer(
        "const uint8_t *",
        "const unsigned char *",
        ir_const(u8_ty.clone()),
        false,
    );
    let byte_read = ir_deref(
        IrExpr::IncDec {
            target: Box::new(ir_var("p", const_u8_ptr.clone())),
            op: IrIncDecOp::Inc,
            prefix: false,
            ty: const_u8_ptr.clone(),
            source_span: None,
        },
        u8_ty.clone(),
    );
    let ir = IrFunction {
        name: "bad_conditional_byte_read_arm".to_string(),
        return_type: i32_ty.clone(),
        params: vec![
            IrParam {
                name: "flag".to_string(),
                ty: i32_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "p".to_string(),
                ty: const_u8_ptr,
                source_span: None,
            },
        ],
        body: vec![IrStmt::Return {
            value: Some(ir_conditional(
                ir_var("flag", i32_ty.clone()),
                IrExpr::Cast {
                    target: i32_ty.clone(),
                    expr: Box::new(byte_read),
                    implicit: true,
                    source_span: None,
                },
                ir_lit(0, "0", i32_ty.clone()),
                i32_ty.clone(),
            )),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir)
        .expect_err("conditional post-increment byte read arm must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("return expr"));
    assert!(error
        .reason
        .contains("conditional then expression cannot use increment/decrement value semantics"));
}
