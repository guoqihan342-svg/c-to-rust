#[cfg(feature = "typed-ir")]
fn for_condition_test_param(name: &str, ty: IrType) -> IrParam {
    IrParam {
        name: name.to_string(),
        ty,
        source_span: None,
    }
}

#[cfg(feature = "typed-ir")]
fn for_condition_inc_dec(target: IrExpr, op: IrIncDecOp, prefix: bool, ty: IrType) -> IrExpr {
    IrExpr::IncDec {
        target: Box::new(target),
        op,
        prefix,
        ty,
        source_span: None,
    }
}

#[cfg(feature = "typed-ir")]
fn for_condition_test_ir(name: &str, params: Vec<IrParam>, condition: IrExpr) -> IrFunction {
    let i32_ty = ir_i32();
    IrFunction {
        name: name.to_string(),
        return_type: i32_ty.clone(),
        params,
        body: vec![
            IrStmt::For {
                init: vec![],
                condition: Some(condition),
                step: None,
                body: vec![IrStmt::Break { source_span: None }],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_lit(0, "0", i32_ty)),
                source_span: None,
            },
        ],
        source_span: None,
    }
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_for_condition_prelude_postfix_runs_step_before_continue_and_stops_at_break() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "scan_window".to_string(),
        return_type: i32_ty.clone(),
        params: vec![
            for_condition_test_param("cursor", i32_ty.clone()),
            for_condition_test_param("ceiling", i32_ty.clone()),
            for_condition_test_param("margin", i32_ty.clone()),
            for_condition_test_param("return_at", i32_ty.clone()),
        ],
        body: vec![
            IrStmt::Decl {
                name: "trace".to_string(),
                ty: i32_ty.clone(),
                init: Some(ir_lit(0, "0", i32_ty.clone())),
                source_span: None,
            },
            IrStmt::Decl {
                name: "ticks".to_string(),
                ty: i32_ty.clone(),
                init: Some(ir_lit(0, "0", i32_ty.clone())),
                source_span: None,
            },
            IrStmt::For {
                init: vec![],
                condition: Some(ir_binary(
                    IrBinOp::Lt,
                    for_condition_inc_dec(
                        ir_var("cursor", i32_ty.clone()),
                        IrIncDecOp::Inc,
                        false,
                        i32_ty.clone(),
                    ),
                    ir_binary(
                        IrBinOp::Add,
                        ir_var("ceiling", i32_ty.clone()),
                        ir_var("margin", i32_ty.clone()),
                        i32_ty.clone(),
                    ),
                    i32_ty.clone(),
                )),
                step: Some(Box::new(IrStmt::Assign {
                    target: ir_var("ticks", i32_ty.clone()),
                    value: ir_binary(
                        IrBinOp::Add,
                        ir_var("ticks", i32_ty.clone()),
                        ir_lit(1, "1", i32_ty.clone()),
                        i32_ty.clone(),
                    ),
                    source_span: None,
                })),
                body: vec![
                    IrStmt::If {
                        condition: ir_binary(
                            IrBinOp::Eq,
                            ir_var("cursor", i32_ty.clone()),
                            ir_var("return_at", i32_ty.clone()),
                            i32_ty.clone(),
                        ),
                        then_body: vec![IrStmt::Return {
                            value: Some(ir_binary(
                                IrBinOp::Add,
                                ir_binary(
                                    IrBinOp::Add,
                                    ir_lit(9000, "9000", i32_ty.clone()),
                                    ir_binary(
                                        IrBinOp::Mul,
                                        ir_var("cursor", i32_ty.clone()),
                                        ir_lit(10, "10", i32_ty.clone()),
                                        i32_ty.clone(),
                                    ),
                                    i32_ty.clone(),
                                ),
                                ir_var("ticks", i32_ty.clone()),
                                i32_ty.clone(),
                            )),
                            source_span: None,
                        }],
                        else_body: vec![],
                        source_span: None,
                    },
                    IrStmt::If {
                        condition: ir_binary(
                            IrBinOp::Eq,
                            ir_var("cursor", i32_ty.clone()),
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
                            ir_var("cursor", i32_ty.clone()),
                            ir_lit(4, "4", i32_ty.clone()),
                            i32_ty.clone(),
                        ),
                        then_body: vec![IrStmt::Break { source_span: None }],
                        else_body: vec![],
                        source_span: None,
                    },
                    IrStmt::Assign {
                        target: ir_var("trace", i32_ty.clone()),
                        value: ir_binary(
                            IrBinOp::Add,
                            ir_binary(
                                IrBinOp::Mul,
                                ir_var("trace", i32_ty.clone()),
                                ir_lit(10, "10", i32_ty.clone()),
                                i32_ty.clone(),
                            ),
                            ir_var("cursor", i32_ty.clone()),
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
                        IrBinOp::Add,
                        ir_binary(
                            IrBinOp::Mul,
                            ir_var("trace", i32_ty.clone()),
                            ir_lit(100, "100", i32_ty.clone()),
                            i32_ty.clone(),
                        ),
                        ir_binary(
                            IrBinOp::Mul,
                            ir_var("cursor", i32_ty.clone()),
                            ir_lit(10, "10", i32_ty.clone()),
                            i32_ty.clone(),
                        ),
                        i32_ty.clone(),
                    ),
                    ir_var("ticks", i32_ty.clone()),
                    i32_ty.clone(),
                )),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit renamed postfix for condition prelude");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains(
        "pub fn scan_window(mut cursor: i32, ceiling: i32, margin: i32, return_at: i32)"
    ));
    assert!(rust.contains("let post_inc_value: i32 = cursor;"), "{rust}");
    assert!(
        rust.contains("if !(post_inc_value < ceiling.checked_add(margin)"),
        "{rust}"
    );
    assert_eq!(
        rust.matches("ticks = ticks.checked_add(1i32).expect(\"signed addition overflow\");")
            .count(),
        2,
        "{rust}"
    );
    assert_rust_snippet_runs(
        "typed-ir-for-postfix-condition-step-continue-break",
        rust,
        "    assert_eq!(scan_window(0, 8, 0, 99), 1343);\n    assert_eq!(scan_window(0, 8, 0, 2), 9021);",
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_for_condition_prelude_prefix_without_step_rechecks_after_continue() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "count_down".to_string(),
        return_type: i32_ty.clone(),
        params: vec![
            for_condition_test_param("remaining", i32_ty.clone()),
            for_condition_test_param("floor", i32_ty.clone()),
        ],
        body: vec![
            IrStmt::Decl {
                name: "trace".to_string(),
                ty: i32_ty.clone(),
                init: Some(ir_lit(0, "0", i32_ty.clone())),
                source_span: None,
            },
            IrStmt::For {
                init: vec![],
                condition: Some(ir_binary(
                    IrBinOp::Lt,
                    ir_var("floor", i32_ty.clone()),
                    for_condition_inc_dec(
                        ir_var("remaining", i32_ty.clone()),
                        IrIncDecOp::Dec,
                        true,
                        i32_ty.clone(),
                    ),
                    i32_ty.clone(),
                )),
                step: None,
                body: vec![
                    IrStmt::If {
                        condition: ir_binary(
                            IrBinOp::Eq,
                            ir_var("remaining", i32_ty.clone()),
                            ir_lit(3, "3", i32_ty.clone()),
                            i32_ty.clone(),
                        ),
                        then_body: vec![IrStmt::Continue { source_span: None }],
                        else_body: vec![],
                        source_span: None,
                    },
                    IrStmt::Assign {
                        target: ir_var("trace", i32_ty.clone()),
                        value: ir_binary(
                            IrBinOp::Add,
                            ir_binary(
                                IrBinOp::Mul,
                                ir_var("trace", i32_ty.clone()),
                                ir_lit(10, "10", i32_ty.clone()),
                                i32_ty.clone(),
                            ),
                            ir_var("remaining", i32_ty.clone()),
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
                        ir_var("trace", i32_ty.clone()),
                        ir_lit(10, "10", i32_ty.clone()),
                        i32_ty.clone(),
                    ),
                    ir_var("remaining", i32_ty.clone()),
                    i32_ty.clone(),
                )),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit renamed prefix for condition prelude");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub fn count_down(mut remaining: i32, floor: i32) -> i32"));
    assert!(rust.contains(
        "remaining = remaining.checked_sub(1i32).expect(\"signed subtraction overflow\");"
    ));
    assert!(rust.contains("if !(floor < remaining) {"), "{rust}");
    assert_rust_snippet_runs(
        "typed-ir-for-prefix-condition-no-step-continue",
        rust,
        "    assert_eq!(count_down(5, 1), 421);",
    );
}
