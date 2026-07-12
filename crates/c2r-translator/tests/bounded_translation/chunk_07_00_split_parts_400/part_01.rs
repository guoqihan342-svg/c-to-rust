#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_if_comparison_incdec_with_same_scalar_sibling_read() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "bad_cmp_incdec_sibling_read_if".to_string(),
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
                    ir_var("value", i32_ty.clone()),
                    i32_ty.clone(),
                ),
                then_body: vec![],
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

    let error = emit_rust_from_ir(&ir)
        .expect_err("if comparison incdec plus same-scalar read must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("stmt[0].if condition"));
    assert!(error
        .reason
        .contains("binary rhs reads variable value modified by lhs side-effect expression"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_if_comparison_with_two_incdec_operands() {
    let i32_ty = ir_i32();
    let inc = |name: &str| IrExpr::IncDec {
        target: Box::new(ir_var(name, i32_ty.clone())),
        op: IrIncDecOp::Inc,
        prefix: false,
        ty: i32_ty.clone(),
        source_span: None,
    };
    let ir = IrFunction {
        name: "bad_cmp_two_incdec_if".to_string(),
        return_type: i32_ty.clone(),
        params: vec![
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
            IrStmt::If {
                condition: ir_binary(
                    IrBinOp::Lt,
                    inc("left"),
                    inc("right"),
                    i32_ty.clone(),
                ),
                then_body: vec![],
                else_body: vec![],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("left", i32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir)
        .expect_err("if comparison with two incdec operands must fail closed");

    assert!(error.reason.contains("stmt[0].if condition"));
    assert!(error
        .reason
        .contains("comparison cannot lower two direct increment/decrement operands"));
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
