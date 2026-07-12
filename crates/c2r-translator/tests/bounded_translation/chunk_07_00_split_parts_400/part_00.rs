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
fn typed_ir_emits_if_comparison_condition_with_incdec_operand_ordered_prelude() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "cmp_post_inc_if".to_string(),
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
            IrStmt::If {
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
                then_body: vec![IrStmt::Return {
                    value: Some(ir_binary(
                        IrBinOp::Add,
                        ir_binary(
                            IrBinOp::Mul,
                            ir_var("value", i32_ty.clone()),
                            ir_lit(10, "10", i32_ty.clone()),
                            i32_ty.clone(),
                        ),
                        ir_lit(1, "1", i32_ty.clone()),
                        i32_ty.clone(),
                    )),
                    source_span: None,
                }],
                else_body: vec![],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_binary(
                    IrBinOp::Mul,
                    ir_var("value", i32_ty.clone()),
                    ir_lit(10, "10", i32_ty.clone()),
                    i32_ty.clone(),
                )),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit if comparison incdec ordered prelude");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub fn cmp_post_inc_if(mut value: i32, limit: i32) -> i32"));
    assert!(rust.contains("let post_inc_value: i32 = value;"));
    assert!(rust.contains("value = value.checked_add(1i32).expect(\"signed addition overflow\");"));
    assert!(rust.contains("if (post_inc_value < limit) {"));
    assert_rust_snippet_runs(
        "typed-ir-if-comparison-incdec-ordered-prelude",
        rust,
        "    assert_eq!(cmp_post_inc_if(4, 5), 51);\n    assert_eq!(cmp_post_inc_if(5, 5), 60);",
    );
}
