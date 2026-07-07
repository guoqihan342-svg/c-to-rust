#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_strlen_read_and_mutable_output_assignment_without_noalias_proof() {
    let i32_ty = ir_i32();
    let usize_ty = ir_usize();
    let const_u8_ptr_ty = ir_pointer(
        "const uint8_t *",
        "const unsigned char *",
        ir_const(ir_u8()),
        false,
    );
    let mutable_i32_ptr = ir_pointer("int *", "int *", i32_ty.clone(), false);
    let ir = IrFunction {
        name: "store_name_len".to_string(),
        return_type: ir_void(),
        params: vec![
            IrParam {
                name: "name".to_string(),
                ty: const_u8_ptr_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "out".to_string(),
                ty: mutable_i32_ptr.clone(),
                source_span: None,
            },
        ],
        body: vec![
            IrStmt::Assign {
                target: IrExpr::Index {
                    base: Box::new(ir_var("out", mutable_i32_ptr)),
                    index: Box::new(ir_lit(0, "0", i32_ty.clone())),
                    ty: i32_ty.clone(),
                    source_span: None,
                },
                value: IrExpr::Cast {
                    expr: Box::new(IrExpr::Call {
                        callee: "strlen".to_string(),
                        args: vec![ir_var("name", const_u8_ptr_ty)],
                        ty: usize_ty,
                        source_span: None,
                    }),
                    target: i32_ty,
                    implicit: false,
                    source_span: None,
                },
                source_span: None,
            },
            IrStmt::Return {
                value: None,
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error =
        emit_rust_from_ir(&ir).expect_err("strlen read plus mutable output needs noalias proof");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(
        error
            .reason
            .contains("mutable pointer write with readonly pointer read requires noalias proof"),
        "unexpected reason: {}",
        error.reason
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_strnlen_read_and_mutable_output_assignment_without_noalias_proof() {
    let i32_ty = ir_i32();
    let usize_ty = ir_usize();
    let const_u8_ptr_ty = ir_pointer(
        "const uint8_t *",
        "const unsigned char *",
        ir_const(ir_u8()),
        false,
    );
    let mutable_i32_ptr = ir_pointer("int *", "int *", i32_ty.clone(), false);
    let ir = IrFunction {
        name: "store_bounded_name_len".to_string(),
        return_type: ir_void(),
        params: vec![
            IrParam {
                name: "name".to_string(),
                ty: const_u8_ptr_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "max".to_string(),
                ty: usize_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "out".to_string(),
                ty: mutable_i32_ptr.clone(),
                source_span: None,
            },
        ],
        body: vec![
            IrStmt::Assign {
                target: IrExpr::Index {
                    base: Box::new(ir_var("out", mutable_i32_ptr)),
                    index: Box::new(ir_lit(0, "0", i32_ty.clone())),
                    ty: i32_ty.clone(),
                    source_span: None,
                },
                value: IrExpr::Cast {
                    expr: Box::new(IrExpr::Call {
                        callee: "strnlen".to_string(),
                        args: vec![ir_var("name", const_u8_ptr_ty), ir_var("max", usize_ty)],
                        ty: ir_usize(),
                        source_span: None,
                    }),
                    target: i32_ty,
                    implicit: false,
                    source_span: None,
                },
                source_span: None,
            },
            IrStmt::Return {
                value: None,
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error =
        emit_rust_from_ir(&ir).expect_err("strnlen read plus mutable output needs noalias proof");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(
        error
            .reason
            .contains("mutable pointer write with readonly pointer read requires noalias proof"),
        "unexpected reason: {}",
        error.reason
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_assert_calls_outside_minimal_model() {
    let i32_ty = ir_i32();
    let void_ty = ir_void();
    let pointer_ty = ir_pointer("const int *", "const int *", ir_const(i32_ty.clone()), true);
    let cases = [
        (
            "assert_no_args",
            vec![],
            void_ty.clone(),
            "requires exactly one condition argument",
        ),
        (
            "assert_two_args",
            vec![
                ir_var("value", i32_ty.clone()),
                ir_lit(1, "1", i32_ty.clone()),
            ],
            void_ty.clone(),
            "requires exactly one condition argument",
        ),
        (
            "assert_non_void_result",
            vec![ir_var("value", i32_ty.clone())],
            i32_ty.clone(),
            "requires void result type",
        ),
        (
            "assert_pointer_arg",
            vec![ir_var("values", pointer_ty.clone())],
            void_ty.clone(),
            "pointer value argument",
        ),
        (
            "assert_nested_call_arg",
            vec![IrExpr::Call {
                callee: "helper".to_string(),
                args: vec![ir_var("value", i32_ty.clone())],
                ty: i32_ty.clone(),
                source_span: None,
            }],
            void_ty.clone(),
            "nested call expressions",
        ),
    ];

    for (name, args, call_ty, expected_reason) in cases {
        let mut params = vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }];
        if name == "assert_pointer_arg" {
            params.push(IrParam {
                name: "values".to_string(),
                ty: pointer_ty.clone(),
                source_span: None,
            });
        }
        let ir = IrFunction {
            name: name.to_string(),
            return_type: i32_ty.clone(),
            params,
            body: vec![
                IrStmt::Expr {
                    expr: IrExpr::Call {
                        callee: "assert".to_string(),
                        args,
                        ty: call_ty,
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

        let error = emit_rust_from_ir(&ir).expect_err("unsupported assert shape must fail closed");
        assert!(
            error.reason.contains(expected_reason),
            "{name}: {:?}",
            error.reason
        );
    }
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_unmodeled_reserved_c_macro_direct_call() {
    for callee in [
        "static_assert",
        "_Static_assert",
        "sizeof",
        "offsetof",
        "labs",
        "llabs",
        "fabs",
        "fabsf",
        "fabsl",
        "malloc",
        "calloc",
        "realloc",
        "free",
        "memmove",
        "strnlen_s",
        "printf",
        "fprintf",
        "sprintf",
        "snprintf",
        "puts",
        "putchar",
        "getchar",
        "exit",
        "abort",
    ] {
        let i32_ty = ir_i32();
        let void_ty = ir_void();
        let ir = IrFunction {
            name: "reserved_call".to_string(),
            return_type: i32_ty.clone(),
            params: vec![IrParam {
                name: "value".to_string(),
                ty: i32_ty.clone(),
                source_span: None,
            }],
            body: vec![
                IrStmt::Expr {
                    expr: IrExpr::Call {
                        callee: callee.to_string(),
                        args: vec![ir_var("value", i32_ty.clone())],
                        ty: void_ty,
                        source_span: None,
                    },
                    source_span: None,
                },
                IrStmt::Return {
                    value: Some(ir_var("value", i32_ty)),
                    source_span: None,
                },
            ],
            source_span: None,
        };

        let error = emit_rust_from_ir(&ir).unwrap_err();

        assert_eq!(error.route.route, CandidateRoute::Unsupported);
        assert!(error.reason.contains(callee), "{:?}", error.reason);
        assert!(
            error.reason.contains("reserved C macro"),
            "{:?}",
            error.reason
        );
        assert!(
            error.reason.contains("explicit lowering or extern binding"),
            "{:?}",
            error.reason
        );
    }
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_record_value_direct_call_arguments() {
    let point_ty = ir_record("point");
    let i32_ty = ir_i32();
    let void_ty = ir_void();
    let ir = IrFunction {
        name: "bad_record_call_arg".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "p".to_string(),
            ty: point_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::Expr {
                expr: IrExpr::Call {
                    callee: "observe".to_string(),
                    args: vec![ir_var("p", point_ty.clone())],
                    ty: void_ty,
                    source_span: None,
                },
                source_span: None,
            },
            IrStmt::Return {
                value: Some(IrExpr::Member {
                    base: Box::new(ir_var("p", point_ty)),
                    field: "x".to_string(),
                    ty: i32_ty,
                    is_arrow: false,
                    source_span: None,
                }),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("record call arguments must fail closed");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(error
        .reason
        .contains("call arg[0] record type point is unsupported"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_pointer_value_direct_call_arguments_with_explicit_boundary() {
    let i32_ty = ir_i32();
    let ptr_ty = ir_pointer("const int *", "const int *", ir_const(i32_ty.clone()), true);
    let ir = IrFunction {
        name: "call_take_ptr".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "values".to_string(),
            ty: ptr_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(IrExpr::Call {
                callee: "take_ptr".to_string(),
                args: vec![ir_var("values", ptr_ty)],
                ty: i32_ty,
                source_span: None,
            }),
            source_span: None,
        }],
        source_span: None,
    };

    let error =
        emit_rust_from_ir(&ir).expect_err("pointer value direct call arguments must fail closed");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(
        error.reason.contains("call arg[0] pointer value argument"),
        "{:?}",
        error.reason
    );
    assert!(error.reason.contains("const int *"), "{:?}", error.reason);
    assert!(
        error
            .reason
            .contains("explicit ownership/lifetime/ABI lowering"),
        "{:?}",
        error.reason
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_pointer_value_return_with_explicit_boundary() {
    let i32_ty = ir_i32();
    let ptr_ty = ir_pointer("const int *", "const int *", ir_const(i32_ty), true);
    let ir = IrFunction {
        name: "return_pointer".to_string(),
        return_type: ptr_ty.clone(),
        params: vec![IrParam {
            name: "values".to_string(),
            ty: ptr_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(ir_var("values", ptr_ty)),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("pointer value returns must fail closed");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(
        error.reason.contains("pointer value return"),
        "{:?}",
        error.reason
    );
    assert!(error.reason.contains("const int *"), "{:?}", error.reason);
    assert!(
        error
            .reason
            .contains("explicit ownership/lifetime/ABI lowering"),
        "{:?}",
        error.reason
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_nested_direct_call_argument() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "nested_call_expression".to_string(),
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
                    args: vec![ir_var("value", i32_ty.clone())],
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

    let emitted = emit_rust_from_ir(&ir).expect("emit one-level nested direct call arg");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub fn nested_call_expression(value: i32) -> i32"));
    assert!(rust.contains("return helper(other(value));"));
    assert_rust_snippet_compiles(
        "typed-ir-nested-direct-call-argument",
        &format!(
            "fn other(value: i32) -> i32 {{ value + 1 }}\nfn helper(value: i32) -> i32 {{ value }}\n{rust}"
        ),
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_single_prefix_inc_direct_call_argument() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "prefix_inc_call_argument".to_string(),
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
                    prefix: true,
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

    let emitted = emit_rust_from_ir(&ir).expect("emit prefix inc direct call arg");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub fn prefix_inc_call_argument(mut value: i32) -> i32"));
    assert!(rust.contains("value = value.checked_add(1i32).expect(\"signed addition overflow\");"));
    assert!(rust.contains("return helper(value);"));
    assert_rust_snippet_runs(
        "typed-ir-prefix-inc-direct-call-arg",
        &format!("fn helper(value: i32) -> i32 {{ value * 2 }}\n{rust}"),
        "    assert_eq!(prefix_inc_call_argument(5), 12);",
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
