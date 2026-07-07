#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_mismatched_binary_operand_types_in_generic_emitter() {
    let u32_ty = ir_u32();
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "mask".to_string(),
        return_type: u32_ty.clone(),
        params: vec![IrParam {
            name: "x".to_string(),
            ty: u32_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(ir_binary(
                IrBinOp::BitAnd,
                ir_var("x", u32_ty.clone()),
                ir_lit(0xFF, "0xFF", i32_ty),
                u32_ty.clone(),
            )),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("mismatched binary types must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("binary operand types must match"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_mismatched_mul_div_mod_operand_types_in_generic_emitter() {
    for (op, symbol, name) in [
        (IrBinOp::Mul, "*", "bad_multiplicative_mul"),
        (IrBinOp::Div, "/", "bad_multiplicative_div"),
        (IrBinOp::Mod, "%", "bad_multiplicative_mod"),
    ] {
        let u32_ty = ir_u32();
        let i32_ty = ir_i32();
        let ir = IrFunction {
            name: name.to_string(),
            return_type: u32_ty.clone(),
            params: vec![IrParam {
                name: "x".to_string(),
                ty: u32_ty.clone(),
                source_span: None,
            }],
            body: vec![IrStmt::Return {
                value: Some(ir_binary(
                    op,
                    ir_var("x", u32_ty.clone()),
                    ir_lit(2, "2", i32_ty),
                    u32_ty.clone(),
                )),
                source_span: None,
            }],
            source_span: None,
        };

        let error = emit_rust_from_ir(&ir).expect_err("mismatched binary types must fail closed");

        assert!(
            error
                .reason
                .contains("outside the current typed IR emitter subset"),
            "{symbol} produced unexpected error: {}",
            error.reason
        );
        assert!(
            error.reason.contains(&format!(
                "binary operand types must match result type for {symbol}"
            )),
            "{symbol} produced unexpected error: {}",
            error.reason
        );
    }
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_return_type_mismatch_in_generic_emitter() {
    let u32_ty = ir_u32();
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "bad_return".to_string(),
        return_type: u32_ty,
        params: vec![],
        body: vec![IrStmt::Return {
            value: Some(ir_lit(1, "1", i32_ty)),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("return type mismatch must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("return expr type i32"));
    assert!(error.reason.contains("expected type u32"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_assign_type_mismatch_in_generic_emitter() {
    let u32_ty = ir_u32();
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "bad_assign".to_string(),
        return_type: u32_ty.clone(),
        params: vec![IrParam {
            name: "x".to_string(),
            ty: u32_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::Assign {
                target: ir_var("x", u32_ty.clone()),
                value: ir_lit(1, "1", i32_ty),
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("x", u32_ty)),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("assign type mismatch must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("assign value type i32"));
    assert!(error.reason.contains("expected type u32"));
}

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

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_logical_not_assignment_value() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "normalize_zero".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::Assign {
                target: ir_var("value", i32_ty.clone()),
                value: ir_not(ir_var("value", i32_ty.clone()), i32_ty.clone()),
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("value", i32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let rust = emit_rust_from_ir(&ir).expect("emit logical not assignment value");

    assert!(rust.contains("pub fn normalize_zero(mut value: i32) -> i32"));
    assert!(rust.contains("value = (if value == 0i32 { 1i32 } else { 0i32 });"));
    assert!(rust.contains("return value;"));
    assert_rust_snippet_compiles("typed-ir-logical-not-assignment-value", &rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_logical_not_decl_initializer() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "init_is_zero".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::Decl {
                name: "out".to_string(),
                ty: i32_ty.clone(),
                init: Some(ir_not(ir_var("value", i32_ty.clone()), i32_ty.clone())),
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("out", i32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let rust = emit_rust_from_ir(&ir).expect("emit logical not decl initializer");

    assert!(rust.contains("pub fn init_is_zero(value: i32) -> i32"));
    assert!(rust.contains("let mut out: i32 = (if value == 0i32 { 1i32 } else { 0i32 });"));
    assert!(rust.contains("return out;"));
    assert_rust_snippet_compiles("typed-ir-logical-not-decl-initializer", &rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_logical_not_comparison_return_value() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "not_positive".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(ir_not(
                ir_binary(
                    IrBinOp::Gt,
                    ir_var("value", i32_ty.clone()),
                    ir_lit(0, "0", i32_ty.clone()),
                    i32_ty.clone(),
                ),
                i32_ty.clone(),
            )),
            source_span: None,
        }],
        source_span: None,
    };

    let rust = emit_rust_from_ir(&ir).expect("emit logical not comparison return value");

    assert!(rust.contains("pub fn not_positive(value: i32) -> i32"));
    assert!(rust.contains("return (if (value <= 0i32) { 1i32 } else { 0i32 });"));
    assert!(!rust.contains("(value > 0i32) == 0i32"));
    assert_rust_snippet_compiles("typed-ir-logical-not-comparison-return-value", &rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_logical_not_as_comparison_condition_operand() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "is_zero_by_compare".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::If {
                condition: ir_binary(
                    IrBinOp::Eq,
                    ir_not(ir_var("value", i32_ty.clone()), i32_ty.clone()),
                    ir_lit(1, "1", i32_ty.clone()),
                    i32_ty.clone(),
                ),
                then_body: vec![IrStmt::Return {
                    value: Some(ir_lit(1, "1", i32_ty.clone())),
                    source_span: None,
                }],
                else_body: vec![],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_lit(0, "0", i32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let rust = emit_rust_from_ir(&ir).expect("emit logical not as comparison condition operand");

    assert!(rust.contains("pub fn is_zero_by_compare(value: i32) -> i32"));
    assert!(rust.contains("if ((if value == 0i32 { 1i32 } else { 0i32 }) == 1i32) {"));
    assert!(rust.contains("return 1i32;"));
    assert!(rust.contains("return 0i32;"));
    assert_rust_snippet_compiles("typed-ir-logical-not-comparison-condition-operand", &rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_value_comparison_with_logical_not_operand_as_c_int() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "logical_not_value_comparison".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(ir_binary(
                IrBinOp::Eq,
                ir_not(ir_var("value", i32_ty.clone()), i32_ty.clone()),
                ir_lit(1, "1", i32_ty.clone()),
                i32_ty.clone(),
            )),
            source_span: None,
        }],
        source_span: None,
    };

    let rust =
        emit_rust_from_ir(&ir).expect("emit value comparison with logical not operand as C int");

    assert!(rust.contains("pub fn logical_not_value_comparison(value: i32) -> i32"));
    assert!(rust.contains(
        "return (if ((if value == 0i32 { 1i32 } else { 0i32 }) == 1i32) { 1i32 } else { 0i32 });"
    ));
    assert_rust_snippet_compiles("typed-ir-logical-not-value-comparison", &rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_logical_not_value_with_call_operand() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "bad_logical_not_call".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(ir_not(
                IrExpr::Call {
                    callee: "helper".to_string(),
                    args: vec![ir_var("value", i32_ty.clone())],
                    ty: i32_ty.clone(),
                    source_span: None,
                },
                i32_ty,
            )),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("logical not call operand must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("return expr"));
    assert!(error
        .reason
        .contains("logical not operand call expression helper is unsupported"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_logical_not_value_with_incdec_operand() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "bad_logical_not_incdec".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(ir_not(
                IrExpr::IncDec {
                    target: Box::new(ir_var("value", i32_ty.clone())),
                    op: IrIncDecOp::Inc,
                    prefix: false,
                    ty: i32_ty.clone(),
                    source_span: None,
                },
                i32_ty,
            )),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("logical not incdec operand must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("return expr"));
    assert!(error.reason.contains("logical not operand"));
    assert!(error.reason.contains("inc/dec expression is unsupported"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_logical_not_value_with_deref_operand() {
    let i32_ty = ir_i32();
    let ptr_ty = ir_pointer("int *", "int *", i32_ty.clone(), false);
    let ir = IrFunction {
        name: "bad_logical_not_deref".to_string(),
        return_type: i32_ty.clone(),
        params: vec![],
        body: vec![IrStmt::Return {
            value: Some(ir_not(
                IrExpr::Deref {
                    ptr: Box::new(ir_var("ptr", ptr_ty)),
                    ty: i32_ty.clone(),
                    source_span: None,
                },
                i32_ty,
            )),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("logical not deref operand must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("return expr"));
    assert!(error
        .reason
        .contains("logical not operand deref pointer ptr is not declared"));
}
