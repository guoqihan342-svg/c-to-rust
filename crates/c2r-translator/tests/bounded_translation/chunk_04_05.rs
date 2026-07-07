#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_prefix_inc_direct_call_argument_with_independent_plain_arg() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "prefix_inc_call_argument_with_plain_arg".to_string(),
        return_type: i32_ty.clone(),
        params: vec![
            IrParam {
                name: "value".to_string(),
                ty: i32_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "other".to_string(),
                ty: i32_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![IrStmt::Return {
            value: Some(IrExpr::Call {
                callee: "helper".to_string(),
                args: vec![
                    IrExpr::IncDec {
                        target: Box::new(ir_var("value", i32_ty.clone())),
                        op: IrIncDecOp::Inc,
                        prefix: true,
                        ty: i32_ty.clone(),
                        source_span: None,
                    },
                    ir_var("other", i32_ty.clone()),
                ],
                ty: i32_ty.clone(),
                source_span: None,
            }),
            source_span: None,
        }],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit one side-effect arg plus independent arg");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains(
        "pub fn prefix_inc_call_argument_with_plain_arg(mut value: i32, other: i32) -> i32"
    ));
    assert!(rust.contains("value = value.checked_add(1i32).expect(\"signed addition overflow\");"));
    assert!(rust.contains("return helper(value, other);"));
    assert_rust_snippet_runs(
        "typed-ir-prefix-inc-direct-call-arg-with-independent-plain-arg",
        &format!("fn helper(value: i32, other: i32) -> i32 {{ value * 10 + other }}\n{rust}"),
        "    assert_eq!(prefix_inc_call_argument_with_plain_arg(5, 7), 67);",
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_nested_prefix_inc_direct_call_argument_with_independent_plain_arg() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "nested_prefix_inc_call_argument_with_plain_arg".to_string(),
        return_type: i32_ty.clone(),
        params: vec![
            IrParam {
                name: "value".to_string(),
                ty: i32_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "other".to_string(),
                ty: i32_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![IrStmt::Return {
            value: Some(IrExpr::Call {
                callee: "outer".to_string(),
                args: vec![
                    IrExpr::Call {
                        callee: "inner".to_string(),
                        args: vec![IrExpr::IncDec {
                            target: Box::new(ir_var("value", i32_ty.clone())),
                            op: IrIncDecOp::Inc,
                            prefix: true,
                            ty: i32_ty.clone(),
                            source_span: None,
                        }],
                        ty: i32_ty.clone(),
                        source_span: None,
                    },
                    ir_var("other", i32_ty.clone()),
                ],
                ty: i32_ty.clone(),
                source_span: None,
            }),
            source_span: None,
        }],
        source_span: None,
    };

    let emitted =
        emit_rust_from_ir(&ir).expect("emit one nested side-effect arg plus independent arg");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains(
        "pub fn nested_prefix_inc_call_argument_with_plain_arg(mut value: i32, other: i32) -> i32"
    ));
    assert!(rust.contains("value = value.checked_add(1i32).expect(\"signed addition overflow\");"));
    assert!(rust.contains("return outer(inner(value), other);"));
    assert_rust_snippet_runs(
        "typed-ir-nested-prefix-inc-direct-call-arg-with-independent-plain-arg",
        &format!(
            "fn inner(value: i32) -> i32 {{ value * 2 }}\nfn outer(value: i32, other: i32) -> i32 {{ value + other }}\n{rust}"
        ),
        "    assert_eq!(nested_prefix_inc_call_argument_with_plain_arg(5, 7), 19);",
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_single_postfix_inc_direct_call_argument() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "postfix_inc_call_argument".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(IrExpr::Call {
                callee: "helper".to_string(),
                args: vec![IrExpr::IncDec {
                    target: Box::new(ir_var("value", i32_ty.clone())),
                    op: IrIncDecOp::Inc,
                    prefix: false,
                    ty: i32_ty.clone(),
                    source_span: None,
                }],
                ty: i32_ty.clone(),
                source_span: None,
            }),
            source_span: None,
        }],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit postfix inc direct call arg");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub fn postfix_inc_call_argument(mut value: i32) -> i32"));
    assert!(rust.contains("let post_inc_value: i32 = value;"));
    assert!(rust.contains("value = value.checked_add(1i32).expect(\"signed addition overflow\");"));
    assert!(rust.contains("return helper(post_inc_value);"));
    assert_rust_snippet_runs(
        "typed-ir-postfix-inc-direct-call-arg",
        &format!("fn helper(value: i32) -> i32 {{ value * 2 }}\n{rust}"),
        "    assert_eq!(postfix_inc_call_argument(5), 10);",
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_single_postfix_inc_direct_call_argument_statement() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "postfix_inc_call_argument_statement".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::Expr {
                expr: IrExpr::Call {
                    callee: "helper".to_string(),
                    args: vec![IrExpr::IncDec {
                        target: Box::new(ir_var("value", i32_ty.clone())),
                        op: IrIncDecOp::Inc,
                        prefix: false,
                        ty: i32_ty.clone(),
                        source_span: None,
                    }],
                    ty: i32_ty.clone(),
                    source_span: None,
                },
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("value", i32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit postfix inc direct call arg statement");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub fn postfix_inc_call_argument_statement(mut value: i32) -> i32"));
    assert!(rust.contains("let post_inc_value: i32 = value;"));
    assert!(rust.contains("value = value.checked_add(1i32).expect(\"signed addition overflow\");"));
    assert!(rust.contains("helper(post_inc_value);"));
    assert!(rust.contains("return value;"));
    assert_rust_snippet_runs(
        "typed-ir-postfix-inc-direct-call-arg-stmt",
        &format!("fn helper(value: i32) -> i32 {{ value * 2 }}\n{rust}"),
        "    assert_eq!(postfix_inc_call_argument_statement(5), 6);",
    );
}
#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_deeper_nested_direct_call_arguments() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "deeper_nested_call_expression".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(IrExpr::Call {
                callee: "helper".to_string(),
                args: vec![IrExpr::Call {
                    callee: "other".to_string(),
                    args: vec![IrExpr::Call {
                        callee: "third".to_string(),
                        args: vec![ir_var("value", i32_ty.clone())],
                        ty: i32_ty.clone(),
                        source_span: None,
                    }],
                    ty: i32_ty.clone(),
                    source_span: None,
                }],
                ty: i32_ty.clone(),
                source_span: None,
            }),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("deeper nested call arg must fail closed");

    assert!(error
        .reason
        .contains("nested call expressions are outside the bounded call subset"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_multiple_nested_direct_call_arguments() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "multiple_nested_call_expression".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(IrExpr::Call {
                callee: "helper".to_string(),
                args: vec![
                    IrExpr::Call {
                        callee: "left".to_string(),
                        args: vec![ir_var("value", i32_ty.clone())],
                        ty: i32_ty.clone(),
                        source_span: None,
                    },
                    IrExpr::Call {
                        callee: "right".to_string(),
                        args: vec![ir_var("value", i32_ty.clone())],
                        ty: i32_ty.clone(),
                        source_span: None,
                    },
                ],
                ty: i32_ty.clone(),
                source_span: None,
            }),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("multiple nested call args must fail closed");

    assert!(error
        .reason
        .contains("multiple nested call arguments are outside the bounded call subset"));
}
