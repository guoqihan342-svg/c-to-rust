#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_for_rejects_loop_init_decl_scope_leak() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "bad_for_scope_leak".to_string(),
        return_type: i32_ty.clone(),
        params: vec![],
        body: vec![
            IrStmt::For {
                init: vec![IrStmt::Decl {
                    name: "i".to_string(),
                    ty: i32_ty.clone(),
                    init: Some(ir_lit(0, "0", i32_ty.clone())),
                    source_span: None,
                }],
                condition: Some(ir_binary(
                    IrBinOp::Lt,
                    ir_var("i", i32_ty.clone()),
                    ir_lit(3, "3", i32_ty.clone()),
                    i32_ty.clone(),
                )),
                step: Some(Box::new(IrStmt::Assign {
                    target: ir_var("i", i32_ty.clone()),
                    value: ir_binary(
                        IrBinOp::Add,
                        ir_var("i", i32_ty.clone()),
                        ir_lit(1, "1", i32_ty.clone()),
                        i32_ty.clone(),
                    ),
                    source_span: None,
                })),
                body: vec![],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("i", i32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("for init decl must not leak");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("stmt[1].return expr"));
    assert!(error.reason.contains("var i is not declared"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_for_rejects_body_decl_scope_leak_into_step() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "bad_for_body_scope_leak".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "keep_going".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::For {
                init: vec![],
                condition: Some(ir_var("keep_going", i32_ty.clone())),
                step: Some(Box::new(IrStmt::Assign {
                    target: ir_var("tmp", i32_ty.clone()),
                    value: ir_binary(
                        IrBinOp::Add,
                        ir_var("tmp", i32_ty.clone()),
                        ir_lit(1, "1", i32_ty.clone()),
                        i32_ty.clone(),
                    ),
                    source_span: None,
                })),
                body: vec![IrStmt::Decl {
                    name: "tmp".to_string(),
                    ty: i32_ty.clone(),
                    init: Some(ir_lit(0, "0", i32_ty.clone())),
                    source_span: None,
                }],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_lit(0, "0", i32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("for body decl must not leak into step");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("stmt[0].for step"));
    assert!(error.reason.contains("assign target tmp is not declared"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_for_rejects_decl_step() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "bad_for_decl_step".to_string(),
        return_type: i32_ty.clone(),
        params: vec![],
        body: vec![
            IrStmt::For {
                init: vec![],
                condition: None,
                step: Some(Box::new(IrStmt::Decl {
                    name: "i".to_string(),
                    ty: i32_ty.clone(),
                    init: Some(ir_lit(0, "0", i32_ty.clone())),
                    source_span: None,
                })),
                body: vec![],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_lit(0, "0", i32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("for step decl must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error
        .reason
        .contains("stmt[0].for step must be an Assign statement"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_for_rejects_non_c_int_condition_result() {
    let i32_ty = ir_i32();
    let u32_ty = ir_u32();
    let ir = IrFunction {
        name: "bad_for_condition_result".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::For {
                init: vec![],
                condition: Some(ir_binary(
                    IrBinOp::LogAnd,
                    ir_var("value", i32_ty.clone()),
                    ir_var("value", i32_ty.clone()),
                    u32_ty,
                )),
                step: None,
                body: vec![],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_lit(0, "0", i32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("for condition result must be C int");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("stmt[0].for condition"));
    assert!(error
        .reason
        .contains("short-circuit result type must be C int"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_short_circuit_condition_with_non_int_result_type() {
    let i32_ty = ir_i32();
    let u32_ty = ir_u32();
    let ir = IrFunction {
        name: "bad_short_circuit_result".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::If {
                condition: ir_binary(
                    IrBinOp::LogAnd,
                    ir_var("value", i32_ty.clone()),
                    ir_var("value", i32_ty.clone()),
                    u32_ty,
                ),
                then_body: vec![],
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

    let error = emit_rust_from_ir(&ir).expect_err("short-circuit condition result must be C int");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("stmt[0].if condition"));
    assert!(error
        .reason
        .contains("short-circuit result type must be C int"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_comparison_condition_with_incdec_operand() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "bad_cmp_incdec".to_string(),
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
                    IrExpr::IncDec {
                        target: Box::new(ir_var("value", i32_ty.clone())),
                        op: IrIncDecOp::Inc,
                        prefix: false,
                        ty: i32_ty.clone(),
                        source_span: None,
                    },
                    ir_lit(0, "0", i32_ty.clone()),
                    i32_ty.clone(),
                ),
                then_body: vec![IrStmt::Assign {
                    target: ir_var("value", i32_ty.clone()),
                    value: ir_var("value", i32_ty.clone()),
                    source_span: None,
                }],
                else_body: vec![],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("value", i32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("comparison incdec operand must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("stmt[0].if condition"));
    assert!(error.reason.contains("comparison lhs"));
    assert!(error.reason.contains("inc/dec expression is unsupported"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_if_with_unsupported_condition_expr() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "bad_if_call".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::If {
                condition: IrExpr::Call {
                    callee: "helper".to_string(),
                    args: vec![],
                    ty: i32_ty.clone(),
                    source_span: None,
                },
                then_body: vec![IrStmt::Assign {
                    target: ir_var("value", i32_ty.clone()),
                    value: ir_var("value", i32_ty.clone()),
                    source_span: None,
                }],
                else_body: vec![],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("value", i32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("if call condition must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("stmt[0].if condition"));
    assert!(error
        .reason
        .contains("call expression helper is unsupported"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_if_with_call_in_comparison_condition() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "bad_if_call_comparison".to_string(),
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
                    IrExpr::Call {
                        callee: "helper".to_string(),
                        args: vec![ir_var("value", i32_ty.clone())],
                        ty: i32_ty.clone(),
                        source_span: None,
                    },
                    ir_lit(0, "0", i32_ty.clone()),
                    i32_ty.clone(),
                ),
                then_body: vec![IrStmt::Assign {
                    target: ir_var("value", i32_ty.clone()),
                    value: ir_var("value", i32_ty.clone()),
                    source_span: None,
                }],
                else_body: vec![],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("value", i32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("if comparison call condition must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("stmt[0].if condition"));
    assert!(error
        .reason
        .contains("call expression helper is unsupported"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_if_with_incdec_condition_expr() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "bad_if_incdec".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::If {
                condition: IrExpr::IncDec {
                    target: Box::new(ir_var("value", i32_ty.clone())),
                    op: IrIncDecOp::Inc,
                    prefix: false,
                    ty: i32_ty.clone(),
                    source_span: None,
                },
                then_body: vec![IrStmt::Assign {
                    target: ir_var("value", i32_ty.clone()),
                    value: ir_var("value", i32_ty.clone()),
                    source_span: None,
                }],
                else_body: vec![],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("value", i32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("if incdec condition must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("stmt[0].if condition"));
    assert!(error.reason.contains("inc/dec expression is unsupported"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_logical_not_condition_with_incdec_operand() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "bad_if_not_incdec".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::If {
                condition: ir_not(
                    IrExpr::IncDec {
                        target: Box::new(ir_var("value", i32_ty.clone())),
                        op: IrIncDecOp::Inc,
                        prefix: false,
                        ty: i32_ty.clone(),
                        source_span: None,
                    },
                    i32_ty.clone(),
                ),
                then_body: vec![IrStmt::Assign {
                    target: ir_var("value", i32_ty.clone()),
                    value: ir_var("value", i32_ty.clone()),
                    source_span: None,
                }],
                else_body: vec![],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("value", i32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("logical not incdec operand must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("stmt[0].if condition"));
    assert!(error.reason.contains("logical not operand"));
    assert!(error.reason.contains("inc/dec expression is unsupported"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_logical_not_condition_with_non_int_result_type() {
    let i32_ty = ir_i32();
    let u32_ty = ir_u32();
    let ir = IrFunction {
        name: "bad_if_not_result_type".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::If {
                condition: ir_not(ir_var("value", i32_ty.clone()), u32_ty),
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

    let error = emit_rust_from_ir(&ir).expect_err("logical not result type must be C int");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("stmt[0].if condition"));
    assert!(error
        .reason
        .contains("logical not result type must be C int"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_if_with_non_var_assignment_target() {
    let i32_ty = ir_i32();
    let pointer_ty = ir_pointer("int *", "int *", i32_ty.clone(), false);
    let ir = IrFunction {
        name: "bad_if_target".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::If {
                condition: ir_var("value", i32_ty.clone()),
                then_body: vec![],
                else_body: vec![IrStmt::Assign {
                    target: IrExpr::Deref {
                        ptr: Box::new(ir_var("ptr", pointer_ty)),
                        ty: i32_ty.clone(),
                        source_span: None,
                    },
                    value: ir_lit(1, "1", i32_ty.clone()),
                    source_span: None,
                }],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("value", i32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("if non-var assignment must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("stmt[0].if else[0]"));
    assert!(error
        .reason
        .contains("deref assignment pointer ptr is not declared"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_if_body_decl_scope_leak() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "bad_if_scope".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "flag".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::If {
                condition: ir_var("flag", i32_ty.clone()),
                then_body: vec![IrStmt::Decl {
                    name: "tmp".to_string(),
                    ty: i32_ty.clone(),
                    init: Some(ir_lit(1, "1", i32_ty.clone())),
                    source_span: None,
                }],
                else_body: vec![],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("tmp", i32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("if body decl must not leak");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("var tmp is not declared"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_pointer_param_in_generic_emitter() {
    let u32_ty = ir_u32();
    let const_void_ptr = ir_pointer(
        "const void *",
        "const void *",
        IrType {
            spelled: "void".to_string(),
            canonical: "void".to_string(),
            kind: IrTypeKind::Void,
            is_const: true,
            width_bits: None,
            source_span: None,
        },
        true,
    );
    let ir = IrFunction {
        name: "read_byte".to_string(),
        return_type: u32_ty.clone(),
        params: vec![IrParam {
            name: "buf".to_string(),
            ty: const_void_ptr,
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(ir_lit(0, "0U", u32_ty.clone())),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("pointer param must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error
        .reason
        .contains("param buf has pointer type const void * is unsupported"));
}

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

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_logical_not_value_with_readonly_pointer_deref_operand() {
    let i32_ty = ir_i32();
    let u8_ty = ir_u8();
    let const_u8_ty = ir_const(u8_ty.clone());
    let const_u8_ptr_ty = ir_pointer("const uint8_t *", "uint8_t *", const_u8_ty, false);
    let ir = IrFunction {
        name: "first_is_zero_not".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "p".to_string(),
            ty: const_u8_ptr_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(ir_not(
                ir_deref(ir_var("p", const_u8_ptr_ty), u8_ty),
                i32_ty,
            )),
            source_span: None,
        }],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit logical not deref value");
    let rust = &emitted.rust;

    assert!(rust.contains("pub fn first_is_zero_not(p: &[u8]) -> i32"));
    assert!(rust.contains("if p[0usize] == 0u8 { 1i32 } else { 0i32 }"));
    assert_rust_snippet_compiles("typed-ir-logical-not-deref-value", rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_logical_not_value_with_readonly_pointer_add_index_deref_operand() {
    let i32_ty = ir_i32();
    let usize_ty = ir_usize();
    let u8_ty = ir_u8();
    let const_u8_ty = ir_const(u8_ty.clone());
    let const_u8_ptr_ty = ir_pointer("const uint8_t *", "uint8_t *", const_u8_ty, false);
    let ptr_plus_index = ir_binary(
        IrBinOp::Add,
        ir_var("p", const_u8_ptr_ty.clone()),
        ir_var("i", usize_ty.clone()),
        const_u8_ptr_ty.clone(),
    );
    let ir = IrFunction {
        name: "offset_is_zero_not".to_string(),
        return_type: i32_ty.clone(),
        params: vec![
            IrParam {
                name: "p".to_string(),
                ty: const_u8_ptr_ty,
                source_span: None,
            },
            IrParam {
                name: "i".to_string(),
                ty: usize_ty,
                source_span: None,
            },
        ],
        body: vec![IrStmt::Return {
            value: Some(ir_not(ir_deref(ptr_plus_index, u8_ty), i32_ty)),
            source_span: None,
        }],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit logical not offset deref value");
    let rust = &emitted.rust;

    assert!(rust.contains("pub fn offset_is_zero_not(p: &[u8], i: usize) -> i32"));
    assert!(rust.contains("if p[i as usize] == 0u8 { 1i32 } else { 0i32 }"));
    assert_rust_snippet_compiles("typed-ir-logical-not-offset-deref-value", rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_logical_not_value_with_pointer_operand() {
    let i32_ty = ir_i32();
    let ptr_ty = ir_pointer("int *", "int *", i32_ty.clone(), false);
    let ir = IrFunction {
        name: "bad_logical_not_pointer".to_string(),
        return_type: i32_ty.clone(),
        params: vec![],
        body: vec![IrStmt::Return {
            value: Some(ir_not(ir_var("ptr", ptr_ty), i32_ty)),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("logical not pointer operand must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("return expr"));
    assert!(error.reason.contains("logical not operand zero"));
    assert!(error.reason.contains("pointer type int * is unsupported"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_logical_not_value_with_unsupported_operand_type() {
    let i32_ty = ir_i32();
    let unsupported_ty = IrType {
        spelled: "float".to_string(),
        canonical: "float".to_string(),
        kind: IrTypeKind::Unsupported {
            reason: "floating type is outside typed IR subset".to_string(),
        },
        is_const: false,
        width_bits: None,
        source_span: None,
    };
    let ir = IrFunction {
        name: "bad_logical_not_float".to_string(),
        return_type: i32_ty.clone(),
        params: vec![],
        body: vec![IrStmt::Return {
            value: Some(ir_not(ir_var("value", unsupported_ty), i32_ty)),
            source_span: None,
        }],
        source_span: None,
    };

    let error =
        emit_rust_from_ir(&ir).expect_err("logical not unsupported operand type must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("return expr"));
    assert!(error.reason.contains("logical not operand zero"));
    assert!(error
        .reason
        .contains("unsupported type float: floating type is outside typed IR subset"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_logical_not_value_with_non_int_result_type() {
    let i32_ty = ir_i32();
    let u32_ty = ir_u32();
    let ir = IrFunction {
        name: "bad_logical_not_result_type".to_string(),
        return_type: u32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(ir_not(ir_var("value", i32_ty), u32_ty)),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("logical not result type must be C int");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("return expr"));
    assert!(error
        .reason
        .contains("logical not result type must be C int"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_non_void_function_without_return_value_in_generic_emitter() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "missing_return".to_string(),
        return_type: i32_ty.clone(),
        params: vec![],
        body: vec![IrStmt::Expr {
            expr: ir_lit(1, "1", i32_ty),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("non-void function must return");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error
        .reason
        .contains("non-void function must end with a return value"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_accepts_final_if_when_both_branches_return_values() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "return_from_if_else".to_string(),
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
        ],
        body: vec![IrStmt::If {
            condition: ir_var("flag", i32_ty.clone()),
            then_body: vec![IrStmt::Return {
                value: Some(IrExpr::Call {
                    callee: "helper".to_string(),
                    args: vec![ir_var("value", i32_ty.clone())],
                    ty: i32_ty.clone(),
                    source_span: None,
                }),
                source_span: None,
            }],
            else_body: vec![IrStmt::Return {
                value: Some(IrExpr::Call {
                    callee: "other".to_string(),
                    args: vec![ir_var("value", i32_ty.clone())],
                    ty: i32_ty.clone(),
                    source_span: None,
                }),
                source_span: None,
            }],
            source_span: None,
        }],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir)
        .expect("final if with returning branches should satisfy return gate");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub fn return_from_if_else(flag: i32, value: i32) -> i32"));
    assert!(rust.contains("if flag != 0i32 {"));
    assert!(rust.contains("return helper(value);"));
    assert!(rust.contains("} else {"));
    assert!(rust.contains("return other(value);"));
    assert_rust_snippet_compiles(
        "typed-ir-final-if-both-branches-return",
        &format!(
            "fn helper(value: i32) -> i32 {{ value + 1 }}\nfn other(value: i32) -> i32 {{ value - 1 }}\n{rust}"
        ),
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_uninitialized_local_decl_assigned_before_read() {
    let u32_ty = ir_u32();
    let ir = IrFunction {
        name: "assign_after_decl".to_string(),
        return_type: u32_ty.clone(),
        params: vec![],
        body: vec![
            IrStmt::Decl {
                name: "tmp".to_string(),
                ty: u32_ty.clone(),
                init: None,
                source_span: None,
            },
            IrStmt::Assign {
                target: ir_var("tmp", u32_ty.clone()),
                value: ir_lit(7, "7", u32_ty.clone()),
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("tmp", u32_ty)),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit assigned uninitialized local declaration");
    let rust = &emitted.rust;

    assert!(rust.contains("let mut tmp: u32;"), "{rust}");
    assert!(rust.contains("tmp = 7u32;"), "{rust}");
    assert!(rust.contains("return tmp;"), "{rust}");
    assert_rust_snippet_compiles("typed-ir-uninitialized-local-assigned-before-read", rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_uninitialized_local_decl_read_before_assignment() {
    let u32_ty = ir_u32();
    let ir = IrFunction {
        name: "bad_uninit_decl".to_string(),
        return_type: u32_ty.clone(),
        params: vec![],
        body: vec![
            IrStmt::Decl {
                name: "tmp".to_string(),
                ty: u32_ty.clone(),
                init: None,
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("tmp", u32_ty)),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir)
        .expect_err("uninitialized local read before assignment must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("tmp"), "{:?}", error);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_rust_keyword_identifier_in_generic_emitter() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "type".to_string(),
        return_type: i32_ty.clone(),
        params: vec![],
        body: vec![IrStmt::Return {
            value: Some(ir_lit(1, "1", i32_ty)),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("rust keyword function name must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error
        .reason
        .contains("function identifier \"type\" is unsupported"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_underscore_identifier_in_generic_emitter() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "_".to_string(),
        return_type: i32_ty.clone(),
        params: vec![],
        body: vec![IrStmt::Return {
            value: Some(ir_lit(1, "1", i32_ty)),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("underscore function name must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error
        .reason
        .contains("function identifier \"_\" is unsupported"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_undeclared_var_in_generic_emitter() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "bad_var".to_string(),
        return_type: i32_ty.clone(),
        params: vec![],
        body: vec![IrStmt::Return {
            value: Some(ir_var("x", i32_ty)),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("undeclared var must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("var x is not declared"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_assign_to_undeclared_var_in_generic_emitter() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "bad_assign_target".to_string(),
        return_type: i32_ty.clone(),
        params: vec![],
        body: vec![
            IrStmt::Assign {
                target: ir_var("x", i32_ty.clone()),
                value: ir_lit(1, "1", i32_ty.clone()),
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_lit(1, "1", i32_ty)),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("undeclared assign target must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("assign target x is not declared"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_out_of_range_integer_literal_in_generic_emitter() {
    let u8_ty = ir_u8();
    let ir = IrFunction {
        name: "bad_literal".to_string(),
        return_type: u8_ty.clone(),
        params: vec![],
        body: vec![IrStmt::Return {
            value: Some(ir_lit(256, "256", u8_ty)),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("out-of-range literal must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error
        .reason
        .contains("literal value 256 does not fit type u8"));
}

#[test]
fn slice_spec_deserializes_real_tu_metadata_without_changing_translation() {
    let spec: SliceSpec = serde_json::from_value(serde_json::json!({
        "target_id": "demo",
        "slice_id": "add-one",
        "source_commit": "1234567",
        "function_name": "add_one",
        "c_source": "int add_one(int value) { return value + 1; }",
        "fixture_hash": "fixture-sha",
        "source_root": "C:/src/project",
        "source_file": "src/add_one.c",
        "source_files": [
            {
                "path": "src/add_one.c",
                "role": "source",
                "sha256": "source-file-sha"
            }
        ],
        "source_file_hashes": {
            "src/add_one.c": "source-file-sha"
        },
        "function_source_span": {
            "file": "src/add_one.c",
            "line_start": 10,
            "line_end": 12,
            "byte_start": 100,
            "byte_end": 160,
            "sha256": "function-span-sha"
        },
        "compile_commands": "build/compile_commands.json",
        "build_profile": {
            "include_paths": [],
            "defines": [],
            "target_triple": "x86_64-unknown-linux-gnu",
            "abi": "linux-gnu",
            "compiler_command_source": "compile_commands.json",
            "clang_available": true
        }
    }))
    .unwrap();

    assert_eq!(spec.source_root.as_deref(), Some("C:/src/project"));
    assert_eq!(spec.source_file.as_deref(), Some("src/add_one.c"));
    assert_eq!(spec.source_files[0].path, "src/add_one.c");
    assert_eq!(
        spec.source_file_hashes
            .get("src/add_one.c")
            .map(String::as_str),
        Some("source-file-sha")
    );
    assert_eq!(
        spec.function_source_span
            .as_ref()
            .map(|span| span.sha256.as_str()),
        Some("function-span-sha")
    );
    assert_eq!(
        spec.compile_commands.as_deref(),
        Some("build/compile_commands.json")
    );

    let out_dir = unique_out_dir("real-tu-metadata");

    write_translation_artifacts(&spec, &out_dir).unwrap();

    let plan = json_file(out_dir.join("l3-add-one-auto-translation-plan.json"));
    let plan_errors = plan["errors"].as_array().expect("plan errors");
    assert!(
        plan_errors.iter().all(|error| {
            let kind = error["kind"].as_str().unwrap_or_default();
            kind.starts_with("legacy_") && kind.ends_with("_retired")
        }),
        "expected only retired-legacy diagnostics, got {plan_errors:?}"
    );
    let rust_draft = fs::read_to_string(out_dir.join("l3-add-one-rust-draft.rs")).unwrap();
    assert!(
        rust_draft.contains("pub fn add_one(value: i32) -> i32"),
        "{rust_draft}"
    );
}

#[cfg(feature = "clang-frontend")]
#[test]
fn clang_parse_spec_dry_run_uses_real_tu_metadata_without_libclang() {
    let spec: SliceSpec = serde_json::from_value(serde_json::json!({
        "target_id": "flashdb",
        "slice_id": "real-fdb-calc-crc32",
        "source_commit": "93d1755",
        "function_name": "fdb_calc_crc32",
        "c_source": "uint32_t fdb_calc_crc32(uint32_t crc, const void *buf, size_t size) { return crc; }",
        "fixture_hash": "fixture-sha",
        "source_root": "C:/src/FlashDB",
        "source_file": "src/fdb_utils.c",
        "source_files": [
            {
                "path": "src/fdb_utils.c",
                "role": "source",
                "sha256": "source-file-sha"
            }
        ],
        "source_file_hashes": {
            "src/fdb_utils.c": "source-file-sha"
        },
        "function_source_span": {
            "file": "src/fdb_utils.c",
            "line_start": 77,
            "line_end": 89,
            "byte_start": 3818,
            "byte_end": 4075,
            "sha256": "function-span-sha"
        },
        "build_profile": {
            "include_paths": ["inc", "tests"],
            "defines": ["FDB_USING_FILE_POSIX_MODE"],
            "target_triple": "x86_64-unknown-linux-gnu",
            "abi": "linux-gnu",
            "compiler_command_source": "C:/src/FlashDB/CMakeLists.txt",
            "clang_available": false
        }
    }))
    .unwrap();

    let parse_spec = ClangParseSpec::from_slice_spec(&spec).expect("clang parse spec");
    let dry_run = parse_spec.dry_run();

    assert_eq!(parse_spec.source_root, PathBuf::from("C:/src/FlashDB"));
    assert_eq!(parse_spec.source_file, PathBuf::from("src/fdb_utils.c"));
    assert_eq!(parse_spec.function_name, "fdb_calc_crc32");
    assert_eq!(
        parse_spec.source_file_hashes["src/fdb_utils.c"],
        "source-file-sha"
    );
    assert_eq!(
        parse_spec
            .function_source_span
            .as_ref()
            .map(|span| span.sha256.as_str()),
        Some("function-span-sha")
    );
    assert!(parse_spec.compile_commands.is_none());
    assert_eq!(dry_run.status, "diagnostic_only");
    assert_eq!(dry_run.claim_boundary.role, "diagnostic_only");
    assert_eq!(dry_run.active_frontend.kind, "clang_ast_dump_json");
    assert_eq!(
        dry_run.active_frontend.command,
        "clang -Xclang -ast-dump=json -fsyntax-only"
    );
    assert_eq!(dry_run.active_frontend.required_env, vec!["CLANG_PATH"]);
    assert!(!dry_run.active_frontend.uses_libclang);
    assert_eq!(
        dry_run.arguments,
        vec![
            "-IC:/src/FlashDB/inc".to_string(),
            "-IC:/src/FlashDB/tests".to_string(),
            "-DFDB_USING_FILE_POSIX_MODE".to_string(),
        ]
    );
    assert!(dry_run
        .diagnostics
        .contains(&"LIBCLANG_PATH is observed only as ignored legacy metadata; active lowering uses clang AST dump JSON via CLANG_PATH".to_string()));
}

#[cfg(feature = "clang-frontend")]
#[test]
fn clang_parse_spec_preserves_target_abi_profile() {
    let spec: SliceSpec = serde_json::from_value(serde_json::json!({
        "target_id": "demo",
        "slice_id": "target-abi-width",
        "source_commit": "1234567",
        "function_name": "identity_size",
        "c_source": "size_t identity_size(size_t value) { return value; }",
        "fixture_hash": "fixture-sha",
        "source_root": "C:/src/project",
        "source_file": "src/size.c",
        "source_file_hashes": {
            "src/size.c": "source-file-sha"
        },
        "function_source_span": {
            "file": "src/size.c",
            "line_start": 1,
            "line_end": 1,
            "byte_start": 0,
            "byte_end": 48,
            "sha256": "function-span-sha"
        },
        "build_profile": {
            "include_paths": [],
            "defines": [],
            "target": {
                "triple_or_abi": "x86_64-unknown-linux-gnu",
                "endianness": "little",
                "int_width": 32,
                "int_align": 32,
                "char_width": 8,
                "char_align": 8,
                "plain_char_signed": true,
                "short_width": 16,
                "short_align": 16,
                "long_width": 64,
                "long_align": 64,
                "long_long_width": 64,
                "long_long_align": 64,
                "pointer_width": 64,
                "pointer_align": 64
            },
            "target_triple": "x86_64-unknown-linux-gnu",
            "abi": "x86_64-unknown-linux-gnu",
            "compiler_command_source": "unit-test",
            "clang_available": true
        }
    }))
    .unwrap();

    let parse_spec = ClangParseSpec::from_slice_spec(&spec).expect("clang parse spec");
    let target_abi = parse_spec.target_abi.expect("target ABI profile");

    assert_eq!(target_abi.triple_or_abi, "x86_64-unknown-linux-gnu");
    assert_eq!(target_abi.int_width, 32);
    assert_eq!(target_abi.int_align, 32);
    assert_eq!(target_abi.char_width, 8);
    assert_eq!(target_abi.char_align, 8);
    assert_eq!(target_abi.plain_char_signed, Some(true));
    assert_eq!(target_abi.short_width, 16);
    assert_eq!(target_abi.short_align, 16);
    assert_eq!(target_abi.long_width, 64);
    assert_eq!(target_abi.long_align, 64);
    assert_eq!(target_abi.long_long_width, 64);
    assert_eq!(target_abi.long_long_align, 64);
    assert_eq!(target_abi.pointer_width, 64);
    assert_eq!(target_abi.pointer_align, 64);
}

#[cfg(feature = "clang-frontend")]
#[test]
fn clang_dry_run_records_missing_libclang_environment_without_parsing() {
    let spec: SliceSpec = serde_json::from_value(serde_json::json!({
        "target_id": "flashdb",
        "slice_id": "real-fdb-calc-crc32",
        "source_commit": "93d1755",
        "function_name": "fdb_calc_crc32",
        "c_source": "uint32_t fdb_calc_crc32(uint32_t crc, const void *buf, size_t size) { return crc; }",
        "fixture_hash": "fixture-sha",
        "source_root": "C:/src/FlashDB",
        "source_file": "src/fdb_utils.c",
        "source_file_hashes": {
            "src/fdb_utils.c": "source-file-sha"
        },
        "function_source_span": {
            "file": "src/fdb_utils.c",
            "line_start": 77,
            "line_end": 89,
            "byte_start": 3818,
            "byte_end": 4075,
            "sha256": "function-span-sha"
        },
        "build_profile": {
            "include_paths": ["inc"],
            "defines": ["FDB_USING_FILE_POSIX_MODE"],
            "target_triple": "x86_64-unknown-linux-gnu",
            "abi": "linux-gnu",
            "compiler_command_source": "C:/src/FlashDB/CMakeLists.txt",
            "clang_available": false
        }
    }))
    .unwrap();
    let environment = std::collections::BTreeMap::new();

    let dry_run = ClangParseSpec::from_slice_spec(&spec)
        .expect("clang parse spec")
        .dry_run_with_environment(&environment);

    assert_eq!(dry_run.status, "diagnostic_only");
    assert_eq!(dry_run.claim_boundary.role, "diagnostic_only");
    assert_eq!(dry_run.active_frontend.kind, "clang_ast_dump_json");
    assert_eq!(dry_run.environment.status, "not_configured");
    assert_eq!(dry_run.environment.source.as_deref(), None);
    assert_eq!(dry_run.environment.observed_libclang_path.as_deref(), None);
    assert_eq!(dry_run.environment.role, "diagnostic_only");
    assert!(dry_run.environment.diagnostics.iter().any(|diagnostic| {
        diagnostic.contains("LIBCLANG_PATH is not set and is ignored for clang AST dump lowering")
    }));
    assert!(dry_run
        .diagnostics
        .contains(&"LIBCLANG_PATH is observed only as ignored legacy metadata; active lowering uses clang AST dump JSON via CLANG_PATH".to_string()));
}

#[cfg(feature = "clang-frontend")]
#[test]
fn clang_dry_run_records_configured_libclang_path_without_enabling_parse() {
    let spec: SliceSpec = serde_json::from_value(serde_json::json!({
        "target_id": "flashdb",
        "slice_id": "real-fdb-calc-crc32",
        "source_commit": "93d1755",
        "function_name": "fdb_calc_crc32",
        "c_source": "uint32_t fdb_calc_crc32(uint32_t crc, const void *buf, size_t size) { return crc; }",
        "fixture_hash": "fixture-sha",
        "source_root": "C:/src/FlashDB",
        "source_file": "src/fdb_utils.c",
        "source_file_hashes": {
            "src/fdb_utils.c": "source-file-sha"
        },
        "function_source_span": {
            "file": "src/fdb_utils.c",
            "line_start": 77,
            "line_end": 89,
            "byte_start": 3818,
            "byte_end": 4075,
            "sha256": "function-span-sha"
        },
        "build_profile": {
            "include_paths": ["inc"],
            "defines": ["FDB_USING_FILE_POSIX_MODE"],
            "target_triple": "x86_64-unknown-linux-gnu",
            "abi": "linux-gnu",
            "compiler_command_source": "C:/src/FlashDB/CMakeLists.txt",
            "clang_available": false
        }
    }))
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "LIBCLANG_PATH".to_string(),
        "C:/LLVM/bin/libclang.dll".to_string(),
    )]);

    let dry_run = ClangParseSpec::from_slice_spec(&spec)
        .expect("clang parse spec")
        .dry_run_with_environment(&environment);

    assert_eq!(dry_run.status, "diagnostic_only");
    assert_eq!(dry_run.active_frontend.kind, "clang_ast_dump_json");
    assert_eq!(dry_run.environment.status, "ignored_for_ast_dump");
    assert_eq!(dry_run.environment.source.as_deref(), Some("LIBCLANG_PATH"));
    assert_eq!(
        dry_run.environment.observed_libclang_path.as_deref(),
        Some("C:/LLVM/bin/libclang.dll")
    );
    assert!(dry_run.environment.diagnostics.iter().any(|diagnostic| {
        diagnostic.contains("LIBCLANG_PATH is configured but ignored for clang AST dump lowering")
    }));
    assert!(dry_run
        .diagnostics
        .contains(&"LIBCLANG_PATH is observed only as ignored legacy metadata; active lowering uses clang AST dump JSON via CLANG_PATH".to_string()));
}

#[cfg(feature = "clang-frontend")]
#[test]
fn clang_parse_spec_dry_run_prefers_compile_commands_over_synthesized_args() {
    let spec: SliceSpec = serde_json::from_value(serde_json::json!({
        "target_id": "flashdb",
        "slice_id": "real-fdb-calc-crc32",
        "source_commit": "93d1755",
        "function_name": "fdb_calc_crc32",
        "c_source": "uint32_t fdb_calc_crc32(uint32_t crc, const void *buf, size_t size) { return crc; }",
        "fixture_hash": "fixture-sha",
        "source_root": "C:/src/FlashDB",
        "source_file": "src/fdb_utils.c",
        "source_file_hashes": {
            "src/fdb_utils.c": "source-file-sha"
        },
        "function_source_span": {
            "file": "src/fdb_utils.c",
            "line_start": 77,
            "line_end": 89,
            "byte_start": 3818,
            "byte_end": 4075,
            "sha256": "function-span-sha"
        },
        "compile_commands": "build/compile_commands.json",
        "build_profile": {
            "include_paths": ["inc"],
            "defines": ["FDB_USING_FILE_POSIX_MODE"],
            "target_triple": "x86_64-unknown-linux-gnu",
            "abi": "linux-gnu",
            "compiler_command_source": "compile_commands.json",
            "clang_available": false
        }
    }))
    .unwrap();

    let dry_run = ClangParseSpec::from_slice_spec(&spec)
        .expect("clang parse spec")
        .dry_run();

    assert_eq!(dry_run.arguments, Vec::<String>::new());
    assert_eq!(
        dry_run.compile_commands.as_deref(),
        Some("build/compile_commands.json")
    );
}

#[cfg(feature = "clang-frontend")]
#[test]
fn clang_parse_spec_rejects_missing_source_hash_and_function_span() {
    let spec: SliceSpec = serde_json::from_value(serde_json::json!({
        "target_id": "flashdb",
        "slice_id": "real-fdb-calc-crc32",
        "source_commit": "93d1755",
        "function_name": "fdb_calc_crc32",
        "c_source": "uint32_t fdb_calc_crc32(uint32_t crc, const void *buf, size_t size) { return crc; }",
        "fixture_hash": "fixture-sha",
        "source_root": "C:/src/FlashDB",
        "source_file": "src/fdb_utils.c",
        "build_profile": {
            "include_paths": ["inc"],
            "defines": [],
            "target_triple": "x86_64-unknown-linux-gnu",
            "abi": "linux-gnu",
            "compiler_command_source": "C:/src/FlashDB/CMakeLists.txt",
            "clang_available": false
        }
    }))
    .unwrap();

    let error = ClangParseSpec::from_slice_spec(&spec)
        .expect_err("clang frontend must require source file hash coverage");

    assert_eq!(error.kind, "missing_source_file_hash");
    assert_eq!(
        error.to_string(),
        "clang frontend dry-run requires source_file_hashes entry for source_file"
    );
}

#[cfg(feature = "clang-frontend")]
#[test]
fn clang_parse_spec_rejects_function_span_for_a_different_source_file() {
    let spec: SliceSpec = serde_json::from_value(serde_json::json!({
        "target_id": "flashdb",
        "slice_id": "real-fdb-calc-crc32",
        "source_commit": "93d1755",
        "function_name": "fdb_calc_crc32",
        "c_source": "uint32_t fdb_calc_crc32(uint32_t crc, const void *buf, size_t size) { return crc; }",
        "fixture_hash": "fixture-sha",
        "source_root": "C:/src/FlashDB",
        "source_file": "src/fdb_utils.c",
        "source_file_hashes": {
            "src/fdb_utils.c": "source-file-sha"
        },
        "function_source_span": {
            "file": "src/other.c",
            "line_start": 77,
            "line_end": 89,
            "byte_start": 3818,
            "byte_end": 4075,
            "sha256": "function-span-sha"
        },
        "build_profile": {
            "include_paths": ["inc"],
            "defines": [],
            "target_triple": "x86_64-unknown-linux-gnu",
            "abi": "linux-gnu",
            "compiler_command_source": "C:/src/FlashDB/CMakeLists.txt",
            "clang_available": false
        }
    }))
    .unwrap();

    let error = ClangParseSpec::from_slice_spec(&spec)
        .expect_err("clang frontend must bind the span to source_file");

    assert_eq!(error.kind, "function_span_source_file_mismatch");
    assert!(error
        .to_string()
        .contains("function_source_span.file must match source_file"));
}

#[cfg(feature = "clang-frontend")]
#[test]
fn clang_parse_spec_rejects_missing_real_tu_metadata() {
    let spec = SliceSpec {
        target_id: "flashdb".to_string(),
        slice_id: "real-fdb-calc-crc32".to_string(),
        source_commit: "93d1755".to_string(),
        function_name: "fdb_calc_crc32".to_string(),
        c_source:
            "uint32_t fdb_calc_crc32(uint32_t crc, const void *buf, size_t size) { return crc; }"
                .to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(true),
        ..SliceSpec::default()
    };

    let error = ClangParseSpec::from_slice_spec(&spec)
        .expect_err("clang frontend must require real TU metadata");

    assert_eq!(error.kind, "missing_source_root");
    assert_eq!(
        error.to_string(),
        "clang frontend dry-run requires source_root"
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_lowering_skeleton_builds_typed_ir_for_add_one_fixture() {
    let int_ty = ClangTypeSkeleton {
        spelled: "int".to_string(),
        canonical: "int".to_string(),
        kind: ClangTypeKind::Integer {
            signed: true,
            width: 32,
        },
    };
    let skeleton = ClangFunctionSkeleton {
        name: "add_one".to_string(),
        return_type: int_ty.clone(),
        params: vec![ClangParamSkeleton {
            name: "value".to_string(),
            ty: int_ty.clone(),
        }],
        body: vec![ClangStmtSkeleton::Return {
            value: Some(ClangExprSkeleton::Binary {
                op: ClangBinaryOperator::Add,
                lhs: Box::new(ClangExprSkeleton::DeclRef {
                    name: "value".to_string(),
                    ty: int_ty.clone(),
                }),
                rhs: Box::new(ClangExprSkeleton::IntegerLiteral {
                    value: 1,
                    spelling: "1".to_string(),
                    ty: int_ty.clone(),
                }),
                ty: int_ty.clone(),
            }),
        }],
    };

    let ir = lower_function_skeleton(&skeleton).expect("lower add_one skeleton");

    assert_eq!(ir.name, "add_one");
    assert!(matches!(
        ir.return_type.kind,
        IrTypeKind::Integer {
            signed: true,
            width: 32
        }
    ));
    assert_eq!(ir.params.len(), 1);
    assert_eq!(ir.params[0].name, "value");
    let [IrStmt::Return {
        value:
            Some(IrExpr::Binary {
                op: IrBinOp::Add,
                lhs,
                rhs,
                ty,
                ..
            }),
        ..
    }] = ir.body.as_slice()
    else {
        panic!("expected single return-add statement");
    };
    assert!(matches!(ty.kind, IrTypeKind::Integer { width: 32, .. }));
    assert!(matches!(
        lhs.as_ref(),
        IrExpr::Var { name, .. } if name == "value"
    ));
    assert!(matches!(
        rhs.as_ref(),
        IrExpr::LitInt { value: 1, spelling, .. } if spelling == "1"
    ));
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn typed_ir_emits_add_one_from_clang_lowered_ir() {
    let int_ty = ClangTypeSkeleton {
        spelled: "int".to_string(),
        canonical: "int".to_string(),
        kind: ClangTypeKind::Integer {
            signed: true,
            width: 32,
        },
    };
    let skeleton = ClangFunctionSkeleton {
        name: "add_one".to_string(),
        return_type: int_ty.clone(),
        params: vec![ClangParamSkeleton {
            name: "value".to_string(),
            ty: int_ty.clone(),
        }],
        body: vec![ClangStmtSkeleton::Return {
            value: Some(ClangExprSkeleton::Binary {
                op: ClangBinaryOperator::Add,
                lhs: Box::new(ClangExprSkeleton::DeclRef {
                    name: "value".to_string(),
                    ty: int_ty.clone(),
                }),
                rhs: Box::new(ClangExprSkeleton::IntegerLiteral {
                    value: 1,
                    spelling: "1".to_string(),
                    ty: int_ty.clone(),
                }),
                ty: int_ty,
            }),
        }],
    };
    let ir = lower_function_skeleton(&skeleton).expect("lower add_one skeleton");

    let rust = emit_rust_from_ir(&ir).expect("emit add_one from lowered typed IR");

    assert!(rust.contains("pub fn add_one(value: i32) -> i32"));
    assert!(rust.contains("return value.checked_add(1i32).expect(\"signed addition overflow\");"));
    assert!(!rust.contains("crc32_update_byte"));
    assert_rust_snippet_compiles("typed-ir-add-one", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn typed_ir_emits_scalar_subtraction_from_clang_lowered_ir() {
    let int_ty = ClangTypeSkeleton {
        spelled: "int".to_string(),
        canonical: "int".to_string(),
        kind: ClangTypeKind::Integer {
            signed: true,
            width: 32,
        },
    };
    let skeleton = ClangFunctionSkeleton {
        name: "sub_one".to_string(),
        return_type: int_ty.clone(),
        params: vec![ClangParamSkeleton {
            name: "value".to_string(),
            ty: int_ty.clone(),
        }],
        body: vec![ClangStmtSkeleton::Return {
            value: Some(ClangExprSkeleton::Binary {
                op: ClangBinaryOperator::Sub,
                lhs: Box::new(ClangExprSkeleton::DeclRef {
                    name: "value".to_string(),
                    ty: int_ty.clone(),
                }),
                rhs: Box::new(ClangExprSkeleton::IntegerLiteral {
                    value: 1,
                    spelling: "1".to_string(),
                    ty: int_ty.clone(),
                }),
                ty: int_ty,
            }),
        }],
    };
    let ir = lower_function_skeleton(&skeleton).expect("lower sub_one skeleton");

    let [IrStmt::Return {
        value:
            Some(IrExpr::Binary {
                op: IrBinOp::Sub,
                lhs,
                rhs,
                ..
            }),
        ..
    }] = ir.body.as_slice()
    else {
        panic!("expected single return-sub statement");
    };
    assert!(matches!(
        lhs.as_ref(),
        IrExpr::Var { name, .. } if name == "value"
    ));
    assert!(matches!(
        rhs.as_ref(),
        IrExpr::LitInt { value: 1, spelling, .. } if spelling == "1"
    ));

    let rust = emit_rust_from_ir(&ir).expect("emit sub_one from lowered typed IR");

    assert!(rust.contains("pub fn sub_one(value: i32) -> i32"));
    assert!(
        rust.contains("return value.checked_sub(1i32).expect(\"signed subtraction overflow\");")
    );
    assert!(!rust.contains("crc32_update_byte"));
    assert_rust_snippet_compiles("typed-ir-sub-one", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn typed_ir_emits_scalar_mul_div_mod_from_clang_lowered_ir() {
    let int_ty = ClangTypeSkeleton {
        spelled: "int".to_string(),
        canonical: "int".to_string(),
        kind: ClangTypeKind::Integer {
            signed: true,
            width: 32,
        },
    };
    let mul = ClangExprSkeleton::Binary {
        op: ClangBinaryOperator::Mul,
        lhs: Box::new(ClangExprSkeleton::DeclRef {
            name: "value".to_string(),
            ty: int_ty.clone(),
        }),
        rhs: Box::new(ClangExprSkeleton::IntegerLiteral {
            value: 3,
            spelling: "3".to_string(),
            ty: int_ty.clone(),
        }),
        ty: int_ty.clone(),
    };
    let div = ClangExprSkeleton::Binary {
        op: ClangBinaryOperator::Div,
        lhs: Box::new(mul),
        rhs: Box::new(ClangExprSkeleton::IntegerLiteral {
            value: 2,
            spelling: "2".to_string(),
            ty: int_ty.clone(),
        }),
        ty: int_ty.clone(),
    };
    let skeleton = ClangFunctionSkeleton {
        name: "mul_div_mod".to_string(),
        return_type: int_ty.clone(),
        params: vec![ClangParamSkeleton {
            name: "value".to_string(),
            ty: int_ty.clone(),
        }],
        body: vec![ClangStmtSkeleton::Return {
            value: Some(ClangExprSkeleton::Binary {
                op: ClangBinaryOperator::Mod,
                lhs: Box::new(div),
                rhs: Box::new(ClangExprSkeleton::IntegerLiteral {
                    value: 5,
                    spelling: "5".to_string(),
                    ty: int_ty.clone(),
                }),
                ty: int_ty,
            }),
        }],
    };
    let ir = lower_function_skeleton(&skeleton).expect("lower mul_div_mod skeleton");

    let [IrStmt::Return {
        value:
            Some(IrExpr::Binary {
                op: IrBinOp::Mod,
                lhs,
                rhs,
                ..
            }),
        ..
    }] = ir.body.as_slice()
    else {
        panic!("expected single return-mod statement");
    };
    assert!(matches!(
        lhs.as_ref(),
        IrExpr::Binary {
            op: IrBinOp::Div,
            ..
        }
    ));
    assert!(matches!(
        rhs.as_ref(),
        IrExpr::LitInt { value: 5, spelling, .. } if spelling == "5"
    ));

    let rust = emit_rust_from_ir(&ir).expect("emit mul_div_mod from lowered typed IR");

    assert!(rust.contains("pub fn mul_div_mod(value: i32) -> i32"));
    assert!(rust.contains("return value.checked_mul(3i32).expect(\"signed multiplication overflow\").checked_div(2i32).expect(\"division by zero or signed overflow\").checked_rem(5i32).expect(\"modulo by zero or signed overflow\");"));
    assert!(!rust.contains("crc32_update_byte"));
    assert_rust_snippet_compiles("typed-ir-clang-scalar-mul-div-mod", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn typed_ir_emits_scalar_bit_or_and_left_shift_from_clang_lowered_ir() {
    let uint32_ty = ClangTypeSkeleton {
        spelled: "uint32_t".to_string(),
        canonical: "uint32_t".to_string(),
        kind: ClangTypeKind::Integer {
            signed: false,
            width: 32,
        },
    };
    let shifted = ClangExprSkeleton::Binary {
        op: ClangBinaryOperator::Shl,
        lhs: Box::new(ClangExprSkeleton::DeclRef {
            name: "value".to_string(),
            ty: uint32_ty.clone(),
        }),
        rhs: Box::new(ClangExprSkeleton::IntegerLiteral {
            value: 4,
            spelling: "4U".to_string(),
            ty: uint32_ty.clone(),
        }),
        ty: uint32_ty.clone(),
    };
    let skeleton = ClangFunctionSkeleton {
        name: "pack_flags".to_string(),
        return_type: uint32_ty.clone(),
        params: vec![ClangParamSkeleton {
            name: "value".to_string(),
            ty: uint32_ty.clone(),
        }],
        body: vec![ClangStmtSkeleton::Return {
            value: Some(ClangExprSkeleton::Binary {
                op: ClangBinaryOperator::BitOr,
                lhs: Box::new(shifted),
                rhs: Box::new(ClangExprSkeleton::IntegerLiteral {
                    value: 3,
                    spelling: "3U".to_string(),
                    ty: uint32_ty.clone(),
                }),
                ty: uint32_ty,
            }),
        }],
    };
    let ir = lower_function_skeleton(&skeleton).expect("lower bit-or left-shift skeleton");

    let [IrStmt::Return {
        value:
            Some(IrExpr::Binary {
                op: IrBinOp::BitOr,
                lhs,
                rhs,
                ..
            }),
        ..
    }] = ir.body.as_slice()
    else {
        panic!("expected bit-or return, got {:?}", ir.body);
    };
    assert!(matches!(
        lhs.as_ref(),
        IrExpr::Binary {
            op: IrBinOp::Shl,
            ..
        }
    ));
    assert!(matches!(
        rhs.as_ref(),
        IrExpr::LitInt { value: 3, spelling, .. } if spelling == "3U"
    ));

    let rust = emit_rust_from_ir(&ir).expect("emit bit-or left-shift from lowered typed IR");

    assert!(rust.contains("pub fn pack_flags(value: u32) -> u32"));
    assert!(rust.contains("return (value.checked_shl(core::convert::TryFrom::try_from(4u32).expect(\"shift count must be nonnegative and fit u32\")).expect(\"shift count out of range\") | 3u32);"));
    assert_rust_snippet_compiles("typed-ir-clang-bit-or-left-shift", &rust);
}
