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
