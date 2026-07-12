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
