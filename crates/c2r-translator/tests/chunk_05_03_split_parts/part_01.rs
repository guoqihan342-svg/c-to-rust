
#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_while_with_incdec_condition_expr() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "bad_while_incdec".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "count".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::While {
                condition: IrExpr::IncDec {
                    target: Box::new(ir_var("count", i32_ty.clone())),
                    op: IrIncDecOp::Dec,
                    prefix: false,
                    ty: i32_ty.clone(),
                    source_span: None,
                },
                body: vec![IrStmt::Assign {
                    target: ir_var("count", i32_ty.clone()),
                    value: ir_var("count", i32_ty.clone()),
                    source_span: None,
                }],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("count", i32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("while incdec condition must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("stmt[0].while condition"));
    assert!(error.reason.contains("inc/dec expression is unsupported"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_while_comparison_with_post_inc_operand_per_iteration() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "while_cmp_post_inc".to_string(),
        return_type: i32_ty.clone(),
        params: vec![
            IrParam {
                name: "value".to_string(),
                ty: i32_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "limit".to_string(),
                ty: i32_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![
            IrStmt::Decl {
                name: "total".to_string(),
                ty: i32_ty.clone(),
                init: Some(ir_lit(0, "0", i32_ty.clone())),
                source_span: None,
            },
            IrStmt::While {
                condition: ir_binary(
                    IrBinOp::Lt,
                    IrExpr::IncDec {
                        target: Box::new(ir_var("value", i32_ty.clone())),
                        op: IrIncDecOp::Inc,
                        prefix: false,
                        ty: i32_ty.clone(),
                        source_span: None,
                    },
                    ir_var("limit", i32_ty.clone()),
                    i32_ty.clone(),
                ),
                body: vec![
                    IrStmt::If {
                        condition: ir_binary(
                            IrBinOp::Eq,
                            ir_var("value", i32_ty.clone()),
                            ir_lit(2, "2", i32_ty.clone()),
                            i32_ty.clone(),
                        ),
                        then_body: vec![IrStmt::Continue { source_span: None }],
                        else_body: vec![],
                        source_span: None,
                    },
                    IrStmt::If {
                        condition: ir_binary(
                            IrBinOp::Eq,
                            ir_var("value", i32_ty.clone()),
                            ir_lit(4, "4", i32_ty.clone()),
                            i32_ty.clone(),
                        ),
                        then_body: vec![IrStmt::Break { source_span: None }],
                        else_body: vec![],
                        source_span: None,
                    },
                    IrStmt::Assign {
                        target: ir_var("total", i32_ty.clone()),
                        value: ir_binary(
                            IrBinOp::Add,
                            ir_binary(
                                IrBinOp::Mul,
                                ir_var("total", i32_ty.clone()),
                                ir_lit(10, "10", i32_ty.clone()),
                                i32_ty.clone(),
                            ),
                            ir_var("value", i32_ty.clone()),
                            i32_ty.clone(),
                        ),
                        source_span: None,
                    },
                ],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_binary(
                    IrBinOp::Add,
                    ir_binary(
                        IrBinOp::Mul,
                        ir_var("total", i32_ty.clone()),
                        ir_lit(10, "10", i32_ty.clone()),
                        i32_ty.clone(),
                    ),
                    ir_var("value", i32_ty.clone()),
                    i32_ty.clone(),
                )),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir)
        .expect("emit while comparison post-inc operand with per-iteration prelude");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub fn while_cmp_post_inc(mut value: i32, limit: i32) -> i32"));
    assert!(rust.contains("loop {\n        let post_inc_value: i32 = value;"));
    assert!(rust.contains("value = value.checked_add(1i32).expect(\"signed addition overflow\");"));
    assert!(rust.contains("if !(post_inc_value < limit) {"));
    assert!(rust.contains("continue;"));
    assert!(rust.contains("break;"));
    assert_rust_snippet_runs(
        "typed-ir-while-comparison-post-inc-per-iteration",
        rust,
        "    assert_eq!(while_cmp_post_inc(0, 6), 134);\n    assert_eq!(while_cmp_post_inc(3, 3), 4);",
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_while_comparison_incdec_with_same_scalar_sibling_read() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "bad_while_cmp_incdec_sibling_read".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::While {
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
                body: vec![],
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
        .expect_err("while comparison incdec plus same-scalar read must fail closed");

    assert!(error.reason.contains("stmt[0].while condition"));
    assert!(error
        .reason
        .contains("binary rhs reads variable value modified by lhs side-effect expression"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_while_comparison_with_two_incdec_operands() {
    let i32_ty = ir_i32();
    let inc = |name: &str| IrExpr::IncDec {
        target: Box::new(ir_var(name, i32_ty.clone())),
        op: IrIncDecOp::Inc,
        prefix: false,
        ty: i32_ty.clone(),
        source_span: None,
    };
    let ir = IrFunction {
        name: "bad_while_cmp_two_incdec".to_string(),
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
            IrStmt::While {
                condition: ir_binary(
                    IrBinOp::Lt,
                    inc("left"),
                    inc("right"),
                    i32_ty.clone(),
                ),
                body: vec![],
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
        .expect_err("while comparison with two incdec operands must fail closed");

    assert!(error.reason.contains("stmt[0].while condition"));
    assert!(error
        .reason
        .contains("comparison cannot lower two direct increment/decrement operands"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_while_comparison_incdec_with_complex_target() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "bad_while_cmp_incdec_complex_target".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::While {
                condition: ir_binary(
                    IrBinOp::Lt,
                    IrExpr::IncDec {
                        target: Box::new(ir_binary(
                            IrBinOp::Add,
                            ir_var("value", i32_ty.clone()),
                            ir_lit(1, "1", i32_ty.clone()),
                            i32_ty.clone(),
                        )),
                        op: IrIncDecOp::Inc,
                        prefix: false,
                        ty: i32_ty.clone(),
                        source_span: None,
                    },
                    ir_lit(4, "4", i32_ty.clone()),
                    i32_ty.clone(),
                ),
                body: vec![],
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
        .expect_err("while comparison incdec with complex target must fail closed");

    assert!(error.reason.contains("stmt[0].while condition"));
    assert!(error.reason.contains("comparison lhs"));
    assert!(error.reason.contains("inc/dec expression is unsupported"));
}
#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_while_with_non_var_assignment_target() {
    let i32_ty = ir_i32();
    let pointer_ty = ir_pointer("int *", "int *", i32_ty.clone(), false);
    let ir = IrFunction {
        name: "bad_while_target".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "count".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::While {
                condition: ir_var("count", i32_ty.clone()),
                body: vec![IrStmt::Assign {
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
                value: Some(ir_var("count", i32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("while non-var assignment must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("stmt[0].while body[0]"));
    assert!(error
        .reason
        .contains("deref assignment pointer ptr is not declared"));
}
