#[cfg(feature = "typed-ir")]
fn do_while_inc_dec_test_param(name: &str, ty: IrType) -> IrParam {
    IrParam {
        name: name.to_string(),
        ty,
        source_span: None,
    }
}

#[cfg(feature = "typed-ir")]
fn do_while_post_inc(target: IrExpr, ty: IrType) -> IrExpr {
    IrExpr::IncDec {
        target: Box::new(target),
        op: IrIncDecOp::Inc,
        prefix: false,
        ty,
        source_span: None,
    }
}

#[cfg(feature = "typed-ir")]
fn do_while_inc_dec_condition_test_ir(
    name: &str,
    params: Vec<IrParam>,
    condition: IrExpr,
) -> IrFunction {
    let i32_ty = ir_i32();
    IrFunction {
        name: name.to_string(),
        return_type: i32_ty.clone(),
        params,
        body: vec![
            IrStmt::DoWhile {
                body: vec![],
                condition,
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("value", i32_ty)),
                source_span: None,
            },
        ],
        source_span: None,
    }
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_do_while_comparison_post_inc_at_each_tail_check() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "do_while_cmp_post_inc".to_string(),
        return_type: i32_ty.clone(),
        params: vec![
            do_while_inc_dec_test_param("value", i32_ty.clone()),
            do_while_inc_dec_test_param("limit", i32_ty.clone()),
        ],
        body: vec![
            IrStmt::Decl {
                name: "total".to_string(),
                ty: i32_ty.clone(),
                init: Some(ir_lit(0, "0", i32_ty.clone())),
                source_span: None,
            },
            IrStmt::DoWhile {
                body: vec![
                    IrStmt::If {
                        condition: ir_binary(
                            IrBinOp::Eq,
                            ir_var("value", i32_ty.clone()),
                            ir_lit(1, "1", i32_ty.clone()),
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
                            ir_lit(3, "3", i32_ty.clone()),
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
                condition: ir_binary(
                    IrBinOp::Lt,
                    do_while_post_inc(
                        ir_var("value", i32_ty.clone()),
                        i32_ty.clone(),
                    ),
                    ir_var("limit", i32_ty.clone()),
                    i32_ty.clone(),
                ),
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
        .expect("emit do-while comparison post-inc with tail-check preludes");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub fn do_while_cmp_post_inc(mut value: i32, limit: i32) -> i32"));
    assert_eq!(rust.matches("let post_inc_value: i32 = value;").count(), 2, "{rust}");
    assert_eq!(
        rust.matches("value = value.checked_add(1i32).expect(\"signed addition overflow\");")
            .count(),
        2,
        "{rust}"
    );
    assert_eq!(
        rust.matches("if !(post_inc_value < limit) {").count(),
        2,
        "{rust}"
    );
    assert!(rust.contains(
        "let post_inc_value: i32 = value;\n            value = value.checked_add(1i32).expect(\"signed addition overflow\");\n            if !(post_inc_value < limit) {\n                break;\n            }\n            continue;"
    ));
    assert_rust_snippet_runs(
        "typed-ir-do-while-comparison-post-inc-tail-check",
        rust,
        "    assert_eq!(do_while_cmp_post_inc(0, 2), 23);\n    assert_eq!(do_while_cmp_post_inc(0, 6), 23);",
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_do_while_inc_dec_comparison_outside_bounded_operands() {
    let i32_ty = ir_i32();
    let const_i32_ptr_ty = ir_pointer(
        "const int *",
        "int *",
        ir_const(i32_ty.clone()),
        false,
    );
    let point_ty = ir_record_with_fields("point", vec![("x", i32_ty.clone())]);
    let value_param = || do_while_inc_dec_test_param("value", i32_ty.clone());
    let post_inc_value = || {
        do_while_post_inc(ir_var("value", i32_ty.clone()), i32_ty.clone())
    };
    let cases = vec![
        (
            "same-variable-sibling",
            do_while_inc_dec_condition_test_ir(
                "bad_do_while_same_variable_sibling",
                vec![value_param()],
                ir_binary(
                    IrBinOp::Eq,
                    post_inc_value(),
                    ir_var("value", i32_ty.clone()),
                    i32_ty.clone(),
                ),
            ),
            "binary rhs reads variable value modified by lhs side-effect expression",
        ),
        (
            "two-incdec-operands",
            do_while_inc_dec_condition_test_ir(
                "bad_do_while_two_incdec",
                vec![
                    value_param(),
                    do_while_inc_dec_test_param("other", i32_ty.clone()),
                ],
                ir_binary(
                    IrBinOp::Lt,
                    post_inc_value(),
                    do_while_post_inc(
                        ir_var("other", i32_ty.clone()),
                        i32_ty.clone(),
                    ),
                    i32_ty.clone(),
                ),
            ),
            "comparison cannot lower two direct increment/decrement operands",
        ),
        (
            "complex-target",
            do_while_inc_dec_condition_test_ir(
                "bad_do_while_complex_target",
                vec![value_param()],
                ir_binary(
                    IrBinOp::Lt,
                    do_while_post_inc(
                        ir_binary(
                            IrBinOp::Add,
                            ir_var("value", i32_ty.clone()),
                            ir_lit(1, "1", i32_ty.clone()),
                            i32_ty.clone(),
                        ),
                        i32_ty.clone(),
                    ),
                    ir_lit(4, "4", i32_ty.clone()),
                    i32_ty.clone(),
                ),
            ),
            "inc/dec expression is unsupported",
        ),
        (
            "call-sibling",
            do_while_inc_dec_condition_test_ir(
                "bad_do_while_call_sibling",
                vec![value_param()],
                ir_binary(
                    IrBinOp::Lt,
                    post_inc_value(),
                    IrExpr::Call {
                        callee: "limit".to_string(),
                        args: vec![],
                        ty: i32_ty.clone(),
                        source_span: None,
                    },
                    i32_ty.clone(),
                ),
            ),
            "comparison operand call expression limit is unsupported",
        ),
        (
            "deref-sibling",
            do_while_inc_dec_condition_test_ir(
                "bad_do_while_deref_sibling",
                vec![
                    value_param(),
                    do_while_inc_dec_test_param("p", const_i32_ptr_ty.clone()),
                ],
                ir_binary(
                    IrBinOp::Lt,
                    post_inc_value(),
                    ir_deref(
                        ir_var("p", const_i32_ptr_ty.clone()),
                        i32_ty.clone(),
                    ),
                    i32_ty.clone(),
                ),
            ),
            "comparison operand deref expression is unsupported",
        ),
        (
            "member-sibling",
            do_while_inc_dec_condition_test_ir(
                "bad_do_while_member_sibling",
                vec![
                    value_param(),
                    do_while_inc_dec_test_param("p", point_ty.clone()),
                ],
                ir_binary(
                    IrBinOp::Lt,
                    post_inc_value(),
                    IrExpr::Member {
                        base: Box::new(ir_var("p", point_ty)),
                        field: "x".to_string(),
                        ty: i32_ty.clone(),
                        is_arrow: false,
                        source_span: None,
                    },
                    i32_ty.clone(),
                ),
            ),
            "comparison operand member expression is unsupported",
        ),
    ];

    for (case, ir, expected) in cases {
        let error = emit_rust_from_ir(&ir)
            .expect_err(&format!("{case} do-while condition must fail closed"));
        assert!(error.reason.contains("stmt[0].do while condition"), "{case}: {error:?}");
        assert!(error.reason.contains(expected), "{case}: {error:?}");
    }
}

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

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_for_condition_prelude_supports_all_six_comparisons() {
    let i32_ty = ir_i32();
    let cases = [
        ("cmp_eq", IrBinOp::Eq, 0, 0, 1),
        ("cmp_neq", IrBinOp::Neq, 0, 1, 1),
        ("cmp_lt", IrBinOp::Lt, 0, 1, 1),
        ("cmp_le", IrBinOp::Le, 0, 0, 1),
        ("cmp_gt", IrBinOp::Gt, 1, 0, 2),
        ("cmp_ge", IrBinOp::Ge, 0, 0, 1),
    ];
    let mut rust = String::new();
    let mut assertions = String::new();

    for (name, op, initial, boundary, expected) in cases {
        let mut ir = for_condition_test_ir(
            name,
            vec![
                for_condition_test_param("probe", i32_ty.clone()),
                for_condition_test_param("boundary", i32_ty.clone()),
            ],
            ir_binary(
                op,
                for_condition_inc_dec(
                    ir_var("probe", i32_ty.clone()),
                    IrIncDecOp::Inc,
                    false,
                    i32_ty.clone(),
                ),
                ir_var("boundary", i32_ty.clone()),
                i32_ty.clone(),
            ),
        );
        ir.body[1] = IrStmt::Return {
            value: Some(ir_var("probe", i32_ty.clone())),
            source_span: None,
        };
        let emitted = emit_rust_from_ir(&ir).expect("emit direct inc/dec comparison for condition");
        assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
        rust.push_str(&emitted.rust);
        assertions.push_str(&format!(
            "    assert_eq!({name}({initial}, {boundary}), {expected});\n"
        ));
    }

    assert_rust_snippet_runs("typed-ir-for-condition-all-comparisons", &rust, &assertions);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_for_condition_prelude_rejects_outside_bounded_operands() {
    let i32_ty = ir_i32();
    let const_i32_ptr_ty = ir_pointer("const int *", "int *", ir_const(i32_ty.clone()), false);
    let point_ty = ir_record_with_fields("point", vec![("x", i32_ty.clone())]);
    let param = |name: &str| for_condition_test_param(name, i32_ty.clone());
    let post_inc = || {
        for_condition_inc_dec(
            ir_var("probe", i32_ty.clone()),
            IrIncDecOp::Inc,
            false,
            i32_ty.clone(),
        )
    };
    let direct_comparison = |rhs: IrExpr| ir_binary(IrBinOp::Lt, post_inc(), rhs, i32_ty.clone());
    let cases = vec![
        (
            "same-variable-sibling",
            for_condition_test_ir(
                "bad_for_same_variable_sibling",
                vec![param("probe")],
                direct_comparison(ir_binary(
                    IrBinOp::Add,
                    ir_var("probe", i32_ty.clone()),
                    ir_lit(1, "1", i32_ty.clone()),
                    i32_ty.clone(),
                )),
            ),
            Some("binary rhs reads variable probe modified by lhs side-effect expression"),
        ),
        (
            "two-incdec-operands",
            for_condition_test_ir(
                "bad_for_two_incdec",
                vec![param("probe"), param("other")],
                direct_comparison(for_condition_inc_dec(
                    ir_var("other", i32_ty.clone()),
                    IrIncDecOp::Dec,
                    true,
                    i32_ty.clone(),
                )),
            ),
            Some("comparison cannot lower two direct increment/decrement operands"),
        ),
        (
            "call-sibling",
            for_condition_test_ir(
                "bad_for_call_sibling",
                vec![param("probe")],
                direct_comparison(IrExpr::Call {
                    callee: "read_boundary".to_string(),
                    args: vec![],
                    ty: i32_ty.clone(),
                    source_span: None,
                }),
            ),
            Some("comparison operand call expression read_boundary is unsupported"),
        ),
        (
            "deref-sibling",
            for_condition_test_ir(
                "bad_for_deref_sibling",
                vec![
                    param("probe"),
                    for_condition_test_param("ptr", const_i32_ptr_ty.clone()),
                ],
                direct_comparison(ir_deref(
                    ir_var("ptr", const_i32_ptr_ty.clone()),
                    i32_ty.clone(),
                )),
            ),
            Some("comparison operand deref expression is unsupported"),
        ),
        (
            "index-sibling",
            for_condition_test_ir(
                "bad_for_index_sibling",
                vec![
                    param("probe"),
                    for_condition_test_param("ptr", const_i32_ptr_ty.clone()),
                ],
                direct_comparison(IrExpr::Index {
                    base: Box::new(ir_var("ptr", const_i32_ptr_ty.clone())),
                    index: Box::new(ir_lit(0, "0", i32_ty.clone())),
                    ty: i32_ty.clone(),
                    source_span: None,
                }),
            ),
            Some("comparison operand index expression is unsupported"),
        ),
        (
            "member-sibling",
            for_condition_test_ir(
                "bad_for_member_sibling",
                vec![
                    param("probe"),
                    for_condition_test_param("point", point_ty.clone()),
                ],
                direct_comparison(IrExpr::Member {
                    base: Box::new(ir_var("point", point_ty.clone())),
                    field: "x".to_string(),
                    ty: i32_ty.clone(),
                    is_arrow: false,
                    source_span: None,
                }),
            ),
            Some("comparison operand member expression is unsupported"),
        ),
        (
            "complex-target",
            for_condition_test_ir(
                "bad_for_complex_target",
                vec![param("probe"), param("boundary")],
                ir_binary(
                    IrBinOp::Lt,
                    for_condition_inc_dec(
                        ir_binary(
                            IrBinOp::Add,
                            ir_var("probe", i32_ty.clone()),
                            ir_lit(1, "1", i32_ty.clone()),
                            i32_ty.clone(),
                        ),
                        IrIncDecOp::Inc,
                        false,
                        i32_ty.clone(),
                    ),
                    ir_var("boundary", i32_ty.clone()),
                    i32_ty.clone(),
                ),
            ),
            None,
        ),
        (
            "logical-combination",
            for_condition_test_ir(
                "bad_for_logical_combination",
                vec![param("probe"), param("boundary"), param("enabled")],
                ir_binary(
                    IrBinOp::LogAnd,
                    direct_comparison(ir_var("boundary", i32_ty.clone())),
                    ir_var("enabled", i32_ty.clone()),
                    i32_ty.clone(),
                ),
            ),
            None,
        ),
    ];

    for (case, ir, expected) in cases {
        let error =
            emit_rust_from_ir(&ir).expect_err(&format!("{case} for condition must fail closed"));
        assert_eq!(error.route.route, CandidateRoute::Unsupported, "{case}");
        assert!(
            error.reason.contains("stmt[0].for condition"),
            "{case}: {error:?}"
        );
        if let Some(expected) = expected {
            assert!(error.reason.contains(expected), "{case}: {error:?}");
        }
    }
}
