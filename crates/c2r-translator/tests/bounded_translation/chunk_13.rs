#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_nested_direct_call_with_single_prefix_inc_argument() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "nested_prefix_inc_call_argument".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(IrExpr::Call {
                callee: "outer".to_string(),
                args: vec![IrExpr::Call {
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
                }],
                ty: i32_ty.clone(),
                source_span: None,
            }),
            source_span: None,
        }],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit nested prefix inc direct call arg");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub fn nested_prefix_inc_call_argument(mut value: i32) -> i32"));
    assert!(rust.contains("value = value.checked_add(1i32).expect(\"signed addition overflow\");"));
    assert!(rust.contains("return outer(inner(value));"));
    assert_rust_snippet_runs(
        "typed-ir-nested-prefix-inc-direct-call-arg",
        &format!(
            "fn inner(value: i32) -> i32 {{ value + 1 }}\nfn outer(value: i32) -> i32 {{ value * 2 }}\n{rust}"
        ),
        "    assert_eq!(nested_prefix_inc_call_argument(5), 14);",
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_nested_direct_call_with_single_postfix_inc_argument() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "nested_postfix_inc_call_argument".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(IrExpr::Call {
                callee: "outer".to_string(),
                args: vec![IrExpr::Call {
                    callee: "inner".to_string(),
                    args: vec![IrExpr::IncDec {
                        target: Box::new(ir_var("value", i32_ty.clone())),
                        op: IrIncDecOp::Inc,
                        prefix: false,
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

    let emitted = emit_rust_from_ir(&ir).expect("emit nested postfix inc direct call arg");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub fn nested_postfix_inc_call_argument(mut value: i32) -> i32"));
    assert!(rust.contains("let post_inc_value: i32 = value;"));
    assert!(rust.contains("value = value.checked_add(1i32).expect(\"signed addition overflow\");"));
    assert!(rust.contains("return outer(inner(post_inc_value));"));
    assert_rust_snippet_runs(
        "typed-ir-nested-postfix-inc-direct-call-arg",
        &format!(
            "fn inner(value: i32) -> i32 {{ value + 1 }}\nfn outer(value: i32) -> i32 {{ value * 2 }}\n{rust}"
        ),
        "    assert_eq!(nested_postfix_inc_call_argument(5), 12);",
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_single_chain_nested_direct_call_with_prefix_inc_argument() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "single_chain_nested_prefix_inc_call_argument".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(IrExpr::Call {
                callee: "outer".to_string(),
                args: vec![IrExpr::Call {
                    callee: "middle".to_string(),
                    args: vec![IrExpr::Call {
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

    let emitted =
        emit_rust_from_ir(&ir).expect("emit single-chain nested prefix inc direct call arg");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains(
        "pub fn single_chain_nested_prefix_inc_call_argument(mut value: i32) -> i32"
    ));
    assert!(rust.contains("value = value.checked_add(1i32).expect(\"signed addition overflow\");"));
    assert!(rust.contains("return outer(middle(inner(value)));"));
    assert_rust_snippet_runs(
        "typed-ir-single-chain-nested-prefix-inc-direct-call-arg",
        &format!(
            "fn inner(value: i32) -> i32 {{ value + 1 }}\nfn middle(value: i32) -> i32 {{ value * 3 }}\nfn outer(value: i32) -> i32 {{ value - 2 }}\n{rust}"
        ),
        "    assert_eq!(single_chain_nested_prefix_inc_call_argument(5), 19);",
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_single_chain_nested_direct_call_with_postfix_inc_argument() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "single_chain_nested_postfix_inc_call_argument".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(IrExpr::Call {
                callee: "outer".to_string(),
                args: vec![IrExpr::Call {
                    callee: "middle".to_string(),
                    args: vec![IrExpr::Call {
                        callee: "inner".to_string(),
                        args: vec![IrExpr::IncDec {
                            target: Box::new(ir_var("value", i32_ty.clone())),
                            op: IrIncDecOp::Inc,
                            prefix: false,
                            ty: i32_ty.clone(),
                            source_span: None,
                        }],
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

    let emitted =
        emit_rust_from_ir(&ir).expect("emit single-chain nested postfix inc direct call arg");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains(
        "pub fn single_chain_nested_postfix_inc_call_argument(mut value: i32) -> i32"
    ));
    assert!(rust.contains("let post_inc_value: i32 = value;"));
    assert!(rust.contains("value = value.checked_add(1i32).expect(\"signed addition overflow\");"));
    assert!(rust.contains("return outer(middle(inner(post_inc_value)));"));
    assert_rust_snippet_runs(
        "typed-ir-single-chain-nested-postfix-inc-direct-call-arg",
        &format!(
            "fn inner(value: i32) -> i32 {{ value + 1 }}\nfn middle(value: i32) -> i32 {{ value * 3 }}\nfn outer(value: i32) -> i32 {{ value - 2 }}\n{rust}"
        ),
        "    assert_eq!(single_chain_nested_postfix_inc_call_argument(5), 16);",
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_nested_side_effect_direct_call_argument_with_same_var_sibling_read() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "nested_side_effect_call_with_plain_arg".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
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
                    ir_var("value", i32_ty.clone()),
                ],
                ty: i32_ty.clone(),
                source_span: None,
            }),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir)
        .expect_err("nested side-effect call argument cannot mix with same-var sibling read");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(
        error
            .reason
            .contains("sibling argument reading modified variable value"),
        "{:?}",
        error.reason
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_single_chain_side_effect_call_with_inner_same_var_sibling_read() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "single_chain_side_effect_call_with_inner_plain_arg".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(IrExpr::Call {
                callee: "outer".to_string(),
                args: vec![IrExpr::Call {
                    callee: "middle".to_string(),
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
                        ir_var("value", i32_ty.clone()),
                    ],
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

    let error = emit_rust_from_ir(&ir)
        .expect_err("inner side-effect call argument cannot mix with same-var sibling read");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(
        error
            .reason
            .contains("sibling argument reading modified variable value"),
        "{:?}",
        error.reason
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_binary_with_side_effect_call_and_independent_plain_operand() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "binary_side_effect_call_independent_operand".to_string(),
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
            value: Some(ir_binary(
                IrBinOp::Add,
                IrExpr::Call {
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
                ir_var("other", i32_ty.clone()),
                i32_ty.clone(),
            )),
            source_span: None,
        }],
        source_span: None,
    };

    let emitted =
        emit_rust_from_ir(&ir).expect("emit side-effect call plus independent binary operand");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains(
        "pub fn binary_side_effect_call_independent_operand(mut value: i32, other: i32) -> i32"
    ));
    assert!(rust.contains("let post_inc_value: i32 = value;"));
    assert!(rust.contains("value = value.checked_add(1i32).expect(\"signed addition overflow\");"));
    assert!(rust.contains(
        "return helper(post_inc_value).checked_add(other).expect(\"signed addition overflow\");"
    ));
    assert_rust_snippet_runs(
        "typed-ir-binary-side-effect-call-independent-operand",
        &format!("fn helper(value: i32) -> i32 {{ value * 2 }}\n{rust}"),
        "    assert_eq!(binary_side_effect_call_independent_operand(5, 7), 17);",
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_binary_same_var_read_with_side_effect_call_operand() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "binary_side_effect_call_same_var_read".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(ir_binary(
                IrBinOp::Add,
                ir_var("value", i32_ty.clone()),
                IrExpr::Call {
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
                i32_ty.clone(),
            )),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir)
        .expect_err("binary same-var read next to side-effect call must fail closed");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(
        error
            .reason
            .contains("binary lhs reads variable value modified by rhs side-effect expression"),
        "{:?}",
        error.reason
    );
}
