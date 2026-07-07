#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_signed_right_shift_with_explicit_contract_policy() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "signed_rshift_contract".to_string(),
        return_type: i32_ty.clone(),
        params: vec![
            IrParam {
                name: "value".to_string(),
                ty: i32_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "count".to_string(),
                ty: i32_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![IrStmt::Return {
            value: Some(ir_binary(
                IrBinOp::Shr,
                ir_var("value", i32_ty.clone()),
                ir_var("count", i32_ty.clone()),
                i32_ty,
            )),
            source_span: None,
        }],
        source_span: None,
    };
    let policy = EmitPolicy {
        signed_right_shift: SignedRightShiftPolicy::ImplementationDefinedArithmetic,
        ..Default::default()
    };

    let emitted = emit_rust_from_ir_with_globals_and_policy(&ir, &[], policy)
        .expect("explicit contract policy should allow signed right shift");

    assert!(emitted.rust.contains("pub fn signed_rshift_contract"));
    assert!(emitted.rust.contains(".checked_shr("));
    assert_rust_snippet_compiles("typed-ir-signed-rshift-contract", &emitted.rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_scalar_mul_div_mod() {
    let i32_ty = ir_i32();
    let mul = ir_binary(
        IrBinOp::Mul,
        ir_var("value", i32_ty.clone()),
        ir_lit(3, "3", i32_ty.clone()),
        i32_ty.clone(),
    );
    let div = ir_binary(
        IrBinOp::Div,
        mul,
        ir_lit(2, "2", i32_ty.clone()),
        i32_ty.clone(),
    );
    let rem = ir_binary(
        IrBinOp::Mod,
        div,
        ir_lit(5, "5", i32_ty.clone()),
        i32_ty.clone(),
    );
    let ir = IrFunction {
        name: "mul_div_mod".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty,
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(rem),
            source_span: None,
        }],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit scalar mul/div/mod");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub fn mul_div_mod(value: i32) -> i32"));
    assert!(rust.contains("return value.checked_mul(3i32).expect(\"signed multiplication overflow\").checked_div(2i32).expect(\"division by zero or signed overflow\").checked_rem(5i32).expect(\"modulo by zero or signed overflow\");"));
    assert_rust_snippet_compiles("typed-ir-scalar-mul-div-mod", rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_scalar_bit_or_and_left_shift() {
    let u32_ty = ir_u32();
    let shifted = ir_binary(
        IrBinOp::Shl,
        ir_var("value", u32_ty.clone()),
        ir_lit(4, "4U", u32_ty.clone()),
        u32_ty.clone(),
    );
    let mask = ir_binary(
        IrBinOp::BitOr,
        shifted,
        ir_lit(3, "3U", u32_ty.clone()),
        u32_ty.clone(),
    );
    let ir = IrFunction {
        name: "pack_flags".to_string(),
        return_type: u32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: u32_ty,
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(mask),
            source_span: None,
        }],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit scalar bit-or and left shift");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub fn pack_flags(value: u32) -> u32"));
    assert!(rust.contains("return (value.checked_shl(core::convert::TryFrom::try_from(4u32).expect(\"shift count must be nonnegative and fit u32\")).expect(\"shift count out of range\") | 3u32);"));
    assert!(!rust.contains("crc32_update_byte"));
    assert_rust_snippet_compiles("typed-ir-scalar-bit-or-left-shift", rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_signed_unary_minus() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "neg_value".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(ir_neg(ir_var("value", i32_ty.clone()), i32_ty)),
            source_span: None,
        }],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit signed unary minus");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub fn neg_value(value: i32) -> i32"));
    assert!(rust.contains("return (-value);"));
    assert!(!rust.contains("crc32_update_byte"));
    assert_rust_snippet_compiles("typed-ir-signed-unary-minus", rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_direct_identifier_call_expressions() {
    let i32_ty = ir_i32();
    let helper_call = |arg: IrExpr| IrExpr::Call {
        callee: "helper".to_string(),
        args: vec![arg],
        ty: i32_ty.clone(),
        source_span: None,
    };
    let ir = IrFunction {
        name: "call_expression".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::Decl {
                name: "first".to_string(),
                ty: i32_ty.clone(),
                init: Some(helper_call(ir_var("value", i32_ty.clone()))),
                source_span: None,
            },
            IrStmt::Assign {
                target: ir_var("value", i32_ty.clone()),
                value: helper_call(ir_var("first", i32_ty.clone())),
                source_span: None,
            },
            IrStmt::Return {
                value: Some(helper_call(ir_var("value", i32_ty.clone()))),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit direct call expressions");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub fn call_expression(mut value: i32) -> i32"));
    assert!(rust.contains("let mut first: i32 = helper(value);"));
    assert!(rust.contains("value = helper(first);"));
    assert!(rust.contains("return helper(value);"));
    assert_rust_snippet_compiles(
        "typed-ir-direct-call-expressions",
        &format!("fn helper(value: i32) -> i32 {{ value }}\n{rust}"),
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_direct_identifier_call_statement() {
    let i32_ty = ir_i32();
    let void_ty = ir_void();
    let ir = IrFunction {
        name: "call_hook".to_string(),
        return_type: void_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Expr {
            expr: IrExpr::Call {
                callee: "observe".to_string(),
                args: vec![ir_var("value", i32_ty)],
                ty: void_ty,
                source_span: None,
            },
            source_span: None,
        }],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit direct call statement");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub fn call_hook(value: i32)"));
    assert!(rust.contains("observe(value);"));
    assert_rust_snippet_compiles(
        "typed-ir-direct-call-statement",
        &format!("fn observe(_: i32) {{}}\n{rust}"),
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_direct_call_argument_integral_cast() {
    let u8_ty = ir_u8();
    let u32_ty = ir_u32();
    let void_ty = ir_void();
    let ir = IrFunction {
        name: "call_hook_cast".to_string(),
        return_type: void_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: u8_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Expr {
            expr: IrExpr::Call {
                callee: "observe".to_string(),
                args: vec![IrExpr::Cast {
                    target: u32_ty,
                    expr: Box::new(ir_var("value", u8_ty)),
                    implicit: true,
                    source_span: None,
                }],
                ty: void_ty,
                source_span: None,
            },
            source_span: None,
        }],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit direct call argument cast");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub fn call_hook_cast(value: u8)"));
    assert!(rust.contains("observe((value as u32));"));
    assert_rust_snippet_compiles(
        "typed-ir-direct-call-argument-integral-cast",
        &format!("fn observe(_: u32) {{}}\n{rust}"),
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_assert_int_direct_call_as_rust_assert_macro() {
    let i32_ty = ir_i32();
    let void_ty = ir_void();
    let ir = IrFunction {
        name: "assert_positive".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::Expr {
                expr: IrExpr::Call {
                    callee: "assert".to_string(),
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

    let emitted = emit_rust_from_ir(&ir).expect("emit modeled C assert(int)");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub fn assert_positive(value: i32) -> i32"));
    assert!(rust.contains("assert!(value != 0i32);"));
    assert!(rust.contains("return value;"));
    assert_rust_snippet_compiles("typed-ir-assert-int-model", rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_abs_int_direct_call_with_checked_precondition() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "abs_value".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(IrExpr::Call {
                callee: "abs".to_string(),
                args: vec![ir_var("value", i32_ty.clone())],
                ty: i32_ty,
                source_span: None,
            }),
            source_span: None,
        }],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit modeled C abs(int)");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(
        rust.contains("pub fn abs_value(value: i32) -> i32"),
        "{rust}"
    );
    assert!(
        rust.contains("return value.checked_abs().expect(\"C abs(int) precondition violated\");"),
        "{rust}"
    );
    assert!(!rust.contains("abs(value)"), "{rust}");
    assert_rust_snippet_compiles("typed-ir-abs-int-model", rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_abs_calls_outside_minimal_model() {
    let i32_ty = ir_i32();
    let u32_ty = ir_u32();
    let cases = [
        (
            "abs_no_args",
            vec![],
            i32_ty.clone(),
            "requires exactly one i32 argument",
        ),
        (
            "abs_two_args",
            vec![
                ir_var("value", i32_ty.clone()),
                ir_lit(1, "1", i32_ty.clone()),
            ],
            i32_ty.clone(),
            "requires exactly one i32 argument",
        ),
        (
            "abs_unsigned_arg",
            vec![ir_var("value", u32_ty.clone())],
            i32_ty.clone(),
            "argument must be i32",
        ),
        (
            "abs_unsigned_result",
            vec![ir_var("value", i32_ty.clone())],
            u32_ty.clone(),
            "requires i32 result type",
        ),
    ];

    for (name, args, call_ty, expected_reason) in cases {
        let param_ty = if name == "abs_unsigned_arg" {
            u32_ty.clone()
        } else {
            i32_ty.clone()
        };
        let return_ty = if name == "abs_unsigned_result" {
            u32_ty.clone()
        } else {
            i32_ty.clone()
        };
        let ir = IrFunction {
            name: name.to_string(),
            return_type: return_ty,
            params: vec![IrParam {
                name: "value".to_string(),
                ty: param_ty,
                source_span: None,
            }],
            body: vec![IrStmt::Return {
                value: Some(IrExpr::Call {
                    callee: "abs".to_string(),
                    args,
                    ty: call_ty,
                    source_span: None,
                }),
                source_span: None,
            }],
            source_span: None,
        };

        let error = emit_rust_from_ir(&ir).expect_err("unsupported abs shape must fail closed");
        assert!(
            error.reason.contains(expected_reason),
            "{name}: {:?}",
            error.reason
        );
    }
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_strlen_direct_call_with_nul_precondition() {
    let usize_ty = ir_usize();
    let const_u8_ptr_ty = ir_pointer(
        "const uint8_t *",
        "const unsigned char *",
        ir_const(ir_u8()),
        true,
    );
    let ir = IrFunction {
        name: "name_len".to_string(),
        return_type: usize_ty.clone(),
        params: vec![IrParam {
            name: "name".to_string(),
            ty: const_u8_ptr_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(IrExpr::Call {
                callee: "strlen".to_string(),
                args: vec![ir_var("name", const_u8_ptr_ty)],
                ty: usize_ty,
                source_span: None,
            }),
            source_span: None,
        }],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit modeled C strlen");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(
        rust.contains("pub fn name_len(name: &[u8]) -> usize"),
        "{rust}"
    );
    assert!(
        rust.contains(
            "return name.iter().position(|&byte| byte == 0).expect(\"C strlen precondition violated\");"
        ),
        "{rust}"
    );
    assert!(!rust.contains("strlen(name)"), "{rust}");
    assert_rust_snippet_compiles("typed-ir-strlen-model", rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_strnlen_direct_call_with_bound_precondition() {
    let usize_ty = ir_usize();
    let const_u8_ptr_ty = ir_pointer(
        "const uint8_t *",
        "const unsigned char *",
        ir_const(ir_u8()),
        true,
    );
    let ir = IrFunction {
        name: "bounded_name_len".to_string(),
        return_type: usize_ty.clone(),
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
        ],
        body: vec![IrStmt::Return {
            value: Some(IrExpr::Call {
                callee: "strnlen".to_string(),
                args: vec![ir_var("name", const_u8_ptr_ty), ir_var("max", usize_ty)],
                ty: ir_usize(),
                source_span: None,
            }),
            source_span: None,
        }],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit modeled C strnlen");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(
        rust.contains("pub fn bounded_name_len(name: &[u8], max: usize) -> usize"),
        "{rust}"
    );
    assert!(rust.contains("C strnlen precondition violated"), "{rust}");
    assert!(rust.contains("position(|&byte| byte == 0)"), "{rust}");
    assert!(!rust.contains("strnlen(name, max)"), "{rust}");
    assert_rust_snippet_runs(
        "typed-ir-strnlen-model",
        rust,
        r#"
    assert_eq!(bounded_name_len(b"abc\0tail", 8), 3);
    assert_eq!(bounded_name_len(b"abcdef", 4), 4);
    assert_eq!(bounded_name_len(b"\0tail", 5), 0);
"#,
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_strnlen_as_nested_direct_call_argument() {
    let usize_ty = ir_usize();
    let void_ty = ir_void();
    let const_u8_ptr_ty = ir_pointer(
        "const uint8_t *",
        "const unsigned char *",
        ir_const(ir_u8()),
        true,
    );
    let ir = IrFunction {
        name: "observe_bounded_name_len".to_string(),
        return_type: void_ty.clone(),
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
        ],
        body: vec![IrStmt::Expr {
            expr: IrExpr::Call {
                callee: "observe".to_string(),
                args: vec![IrExpr::Call {
                    callee: "strnlen".to_string(),
                    args: vec![ir_var("name", const_u8_ptr_ty), ir_var("max", usize_ty)],
                    ty: ir_usize(),
                    source_span: None,
                }],
                ty: void_ty,
                source_span: None,
            },
            source_span: None,
        }],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit nested modeled C strnlen argument");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(
        rust.contains("pub fn observe_bounded_name_len(name: &[u8], max: usize)"),
        "{rust}"
    );
    assert!(rust.contains("observe({ let bytes = name.get(..(max as usize)).expect(\"C strnlen precondition violated\");"), "{rust}");
    assert!(!rust.contains("strnlen(name, max)"), "{rust}");
    assert_rust_snippet_compiles(
        "typed-ir-nested-strnlen-argument",
        &format!("fn observe(_: usize) {{}}\n{rust}"),
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_strnlen_calls_outside_minimal_model() {
    let i32_ty = ir_i32();
    let u32_ty = ir_u32();
    let usize_ty = ir_usize();
    let const_u8_ptr_ty = ir_pointer(
        "const uint8_t *",
        "const unsigned char *",
        ir_const(ir_u8()),
        true,
    );
    let const_i32_ptr_ty = ir_pointer("const int *", "const int *", ir_const(i32_ty.clone()), true);
    let cases = [
        (
            "strnlen_no_args",
            vec![],
            usize_ty.clone(),
            vec![],
            "requires exactly one string pointer and one size argument",
        ),
        (
            "strnlen_non_size_result",
            vec![
                ir_var("name", const_u8_ptr_ty.clone()),
                ir_var("max", usize_ty.clone()),
            ],
            u32_ty.clone(),
            vec![("name", const_u8_ptr_ty.clone()), ("max", usize_ty.clone())],
            "requires size_t/usize result type",
        ),
        (
            "strnlen_non_byte_pointer",
            vec![
                ir_var("name", const_i32_ptr_ty.clone()),
                ir_var("max", usize_ty.clone()),
            ],
            usize_ty.clone(),
            vec![
                ("name", const_i32_ptr_ty.clone()),
                ("max", usize_ty.clone()),
            ],
            "argument must be a readonly 8-bit integer pointer",
        ),
        (
            "strnlen_null_pointer",
            vec![
                IrExpr::NullPtr {
                    ty: const_u8_ptr_ty.clone(),
                    source_span: None,
                },
                ir_var("max", usize_ty.clone()),
            ],
            usize_ty.clone(),
            vec![("max", usize_ty.clone())],
            "argument must be a direct readonly pointer parameter",
        ),
        (
            "strnlen_non_size_count",
            vec![
                ir_var("name", const_u8_ptr_ty.clone()),
                ir_var("max", i32_ty.clone()),
            ],
            usize_ty.clone(),
            vec![("name", const_u8_ptr_ty.clone()), ("max", i32_ty.clone())],
            "size argument must be size_t/usize",
        ),
    ];

    for (name, args, call_ty, params, expected_reason) in cases {
        let return_type = if name == "strnlen_non_size_result" {
            u32_ty.clone()
        } else {
            usize_ty.clone()
        };
        let ir = IrFunction {
            name: name.to_string(),
            return_type,
            params: params
                .into_iter()
                .map(|(name, ty)| IrParam {
                    name: name.to_string(),
                    ty,
                    source_span: None,
                })
                .collect(),
            body: vec![IrStmt::Return {
                value: Some(IrExpr::Call {
                    callee: "strnlen".to_string(),
                    args,
                    ty: call_ty,
                    source_span: None,
                }),
                source_span: None,
            }],
            source_span: None,
        };

        let error = emit_rust_from_ir(&ir).expect_err("unsupported strnlen shape must fail closed");
        assert!(
            error.reason.contains(expected_reason),
            "{name}: {:?}",
            error.reason
        );
    }
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_strlen_as_nested_direct_call_argument() {
    let usize_ty = ir_usize();
    let void_ty = ir_void();
    let const_u8_ptr_ty = ir_pointer(
        "const uint8_t *",
        "const unsigned char *",
        ir_const(ir_u8()),
        true,
    );
    let ir = IrFunction {
        name: "observe_name_len".to_string(),
        return_type: void_ty.clone(),
        params: vec![IrParam {
            name: "name".to_string(),
            ty: const_u8_ptr_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Expr {
            expr: IrExpr::Call {
                callee: "observe".to_string(),
                args: vec![IrExpr::Call {
                    callee: "strlen".to_string(),
                    args: vec![ir_var("name", const_u8_ptr_ty)],
                    ty: usize_ty,
                    source_span: None,
                }],
                ty: void_ty,
                source_span: None,
            },
            source_span: None,
        }],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit nested modeled C strlen argument");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(
        rust.contains("pub fn observe_name_len(name: &[u8])"),
        "{rust}"
    );
    assert!(
        rust.contains(
            "observe(name.iter().position(|&byte| byte == 0).expect(\"C strlen precondition violated\"));"
        ),
        "{rust}"
    );
    assert!(!rust.contains("strlen(name)"), "{rust}");
    assert_rust_snippet_compiles(
        "typed-ir-nested-strlen-argument",
        &format!("fn observe(_: usize) {{}}\n{rust}"),
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_memcmp_direct_call_for_readonly_byte_slices() {
    let i32_ty = ir_i32();
    let usize_ty = ir_usize();
    let const_u8_ptr_ty = ir_pointer(
        "const uint8_t *",
        "const unsigned char *",
        ir_const(ir_u8()),
        true,
    );
    let ir = IrFunction {
        name: "compare_prefix".to_string(),
        return_type: i32_ty.clone(),
        params: vec![
            IrParam {
                name: "left".to_string(),
                ty: const_u8_ptr_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "right".to_string(),
                ty: const_u8_ptr_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "count".to_string(),
                ty: usize_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![IrStmt::Return {
            value: Some(IrExpr::Call {
                callee: "memcmp".to_string(),
                args: vec![
                    ir_var("left", const_u8_ptr_ty.clone()),
                    ir_var("right", const_u8_ptr_ty),
                    ir_var("count", usize_ty),
                ],
                ty: i32_ty,
                source_span: None,
            }),
            source_span: None,
        }],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit modeled C memcmp");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(
        rust.contains("pub fn compare_prefix(left: &[u8], right: &[u8], count: usize) -> i32"),
        "{rust}"
    );
    assert!(rust.contains(".get(..(count as usize))"), "{rust}");
    assert!(rust.contains("C memcmp precondition violated"), "{rust}");
    assert!(!rust.contains("memcmp(left, right, count)"), "{rust}");
    assert_rust_snippet_runs(
        "typed-ir-memcmp-model",
        rust,
        r#"
    let left = [1u8, 2, 3, 4];
    let equal = [1u8, 2, 9, 9];
    let greater = [1u8, 3, 0, 0];
    let shorter = [1u8, 2, 3, 4];
    assert_eq!(compare_prefix(&left, &equal, 2), 0);
    assert!(compare_prefix(&left, &greater, 3) < 0);
    assert_eq!(compare_prefix(&left, &shorter, 4), 0);
"#,
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_memcmp_treats_signed_byte_slices_as_unsigned_bytes() {
    let i32_ty = ir_i32();
    let usize_ty = ir_usize();
    let i8_ty = ir_integer("int8_t", "signed char", true, 8);
    let const_i8_ptr_ty = ir_pointer(
        "const int8_t *",
        "const signed char *",
        ir_const(i8_ty),
        true,
    );
    let ir = IrFunction {
        name: "compare_signed_prefix".to_string(),
        return_type: i32_ty.clone(),
        params: vec![
            IrParam {
                name: "left".to_string(),
                ty: const_i8_ptr_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "right".to_string(),
                ty: const_i8_ptr_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "count".to_string(),
                ty: usize_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![IrStmt::Return {
            value: Some(IrExpr::Call {
                callee: "memcmp".to_string(),
                args: vec![
                    ir_var("left", const_i8_ptr_ty.clone()),
                    ir_var("right", const_i8_ptr_ty),
                    ir_var("count", usize_ty),
                ],
                ty: i32_ty,
                source_span: None,
            }),
            source_span: None,
        }],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit signed-byte C memcmp");
    assert_rust_snippet_runs(
        "typed-ir-memcmp-signed-byte-model",
        &emitted.rust,
        r#"
    let high = [-1i8];
    let low = [1i8];
    assert!(compare_signed_prefix(&high, &low, 1) > 0);
"#,
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_memcmp_calls_outside_minimal_model() {
    let i32_ty = ir_i32();
    let u32_ty = ir_u32();
    let usize_ty = ir_usize();
    let const_u8_ptr_ty = ir_pointer(
        "const uint8_t *",
        "const unsigned char *",
        ir_const(ir_u8()),
        true,
    );
    let const_i32_ptr_ty = ir_pointer("const int *", "const int *", ir_const(i32_ty.clone()), true);
    let cases = [
        (
            "memcmp_no_args",
            vec![],
            i32_ty.clone(),
            vec![],
            "requires exactly two readonly byte pointers and one size argument",
        ),
        (
            "memcmp_non_int_result",
            vec![
                ir_var("left", const_u8_ptr_ty.clone()),
                ir_var("right", const_u8_ptr_ty.clone()),
                ir_var("count", usize_ty.clone()),
            ],
            u32_ty.clone(),
            vec![
                ("left", const_u8_ptr_ty.clone()),
                ("right", const_u8_ptr_ty.clone()),
                ("count", usize_ty.clone()),
            ],
            "requires i32 result type",
        ),
        (
            "memcmp_non_byte_pointer",
            vec![
                ir_var("left", const_i32_ptr_ty.clone()),
                ir_var("right", const_i32_ptr_ty.clone()),
                ir_var("count", usize_ty.clone()),
            ],
            i32_ty.clone(),
            vec![
                ("left", const_i32_ptr_ty.clone()),
                ("right", const_i32_ptr_ty.clone()),
                ("count", usize_ty.clone()),
            ],
            "left argument must be a readonly 8-bit integer pointer",
        ),
        (
            "memcmp_null_pointer",
            vec![
                IrExpr::NullPtr {
                    ty: const_u8_ptr_ty.clone(),
                    source_span: None,
                },
                ir_var("right", const_u8_ptr_ty.clone()),
                ir_var("count", usize_ty.clone()),
            ],
            i32_ty.clone(),
            vec![
                ("right", const_u8_ptr_ty.clone()),
                ("count", usize_ty.clone()),
            ],
            "left argument must be a direct readonly pointer parameter",
        ),
        (
            "memcmp_non_size_count",
            vec![
                ir_var("left", const_u8_ptr_ty.clone()),
                ir_var("right", const_u8_ptr_ty.clone()),
                ir_var("count", i32_ty.clone()),
            ],
            i32_ty.clone(),
            vec![
                ("left", const_u8_ptr_ty.clone()),
                ("right", const_u8_ptr_ty),
                ("count", i32_ty.clone()),
            ],
            "size argument must be size_t/usize",
        ),
    ];

    for (name, args, call_ty, params, expected_reason) in cases {
        let return_type = if name == "memcmp_non_int_result" {
            u32_ty.clone()
        } else {
            i32_ty.clone()
        };
        let ir = IrFunction {
            name: name.to_string(),
            return_type,
            params: params
                .into_iter()
                .map(|(name, ty)| IrParam {
                    name: name.to_string(),
                    ty,
                    source_span: None,
                })
                .collect(),
            body: vec![IrStmt::Return {
                value: Some(IrExpr::Call {
                    callee: "memcmp".to_string(),
                    args,
                    ty: call_ty,
                    source_span: None,
                }),
                source_span: None,
            }],
            source_span: None,
        };

        let error = emit_rust_from_ir(&ir).expect_err("unsupported memcmp shape must fail closed");
        assert!(
            error.reason.contains(expected_reason),
            "{name}: {:?}",
            error.reason
        );
    }
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_memset_zero_for_mutable_byte_slice_statement() {
    let void_ty = ir_void();
    let usize_ty = ir_usize();
    let mutable_u8_ptr_ty = ir_pointer("uint8_t *", "unsigned char *", ir_u8(), false);
    let ir = IrFunction {
        name: "clear_prefix".to_string(),
        return_type: void_ty.clone(),
        params: vec![
            IrParam {
                name: "out".to_string(),
                ty: mutable_u8_ptr_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "count".to_string(),
                ty: usize_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![
            IrStmt::Expr {
                expr: IrExpr::Call {
                    callee: "memset".to_string(),
                    args: vec![
                        ir_var("out", mutable_u8_ptr_ty),
                        ir_lit(0, "0", ir_i32()),
                        ir_var("count", usize_ty),
                    ],
                    ty: void_ty.clone(),
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

    let emitted = emit_rust_from_ir(&ir).expect("emit modeled C memset statement");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(
        rust.contains("pub fn clear_prefix(mut out: &mut [u8], count: usize)"),
        "{rust}"
    );
    assert!(rust.contains(".get_mut(..(count as usize))"), "{rust}");
    assert!(rust.contains("C memset precondition violated"), "{rust}");
    assert!(rust.contains(".fill(0u8);"), "{rust}");
    assert!(!rust.contains("memset(out, 0, count)"), "{rust}");
    assert_rust_snippet_runs(
        "typed-ir-memset-zero-model",
        rust,
        r#"
    let mut out = [1u8, 2, 3, 4];
    clear_prefix(&mut out, 3);
    assert_eq!(out, [0u8, 0, 0, 4]);
"#,
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_memset_zero_for_discarded_void_pointer_result_statement() {
    let void_ty = ir_void();
    let usize_ty = ir_usize();
    let mutable_u8_ptr_ty = ir_pointer("uint8_t *", "unsigned char *", ir_u8(), false);
    let void_ptr_ty = ir_pointer("void *", "void *", void_ty.clone(), false);
    let ir = IrFunction {
        name: "clear_prefix".to_string(),
        return_type: void_ty,
        params: vec![
            IrParam {
                name: "out".to_string(),
                ty: mutable_u8_ptr_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "count".to_string(),
                ty: usize_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![IrStmt::Expr {
            expr: IrExpr::Call {
                callee: "memset".to_string(),
                args: vec![
                    ir_var("out", mutable_u8_ptr_ty),
                    ir_lit(0, "0", ir_i32()),
                    ir_var("count", usize_ty),
                ],
                ty: void_ptr_ty,
                source_span: None,
            },
            source_span: None,
        }],
        source_span: None,
    };

    let emitted =
        emit_rust_from_ir(&ir).expect("emit modeled C memset statement with discarded void *");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains(".get_mut(..(count as usize))"), "{rust}");
    assert!(rust.contains(".fill(0u8);"), "{rust}");
    assert!(!rust.contains("memset(out, 0, count)"), "{rust}");
    assert_rust_snippet_runs(
        "typed-ir-memset-discarded-void-pointer-result-model",
        rust,
        r#"
    let mut out = [1u8, 2, 3, 4];
    clear_prefix(&mut out, 3);
    assert_eq!(out, [0u8, 0, 0, 4]);
"#,
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_memset_byte_literal_for_mutable_byte_slice_statement() {
    let usize_ty = ir_usize();
    let void_ty = ir_void();
    let i32_ty = ir_i32();
    let mutable_u8_ptr_ty = ir_pointer("uint8_t *", "unsigned char *", ir_u8(), false);
    let ir = IrFunction {
        name: "fill_prefix".to_string(),
        return_type: void_ty.clone(),
        params: vec![
            IrParam {
                name: "out".to_string(),
                ty: mutable_u8_ptr_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "count".to_string(),
                ty: usize_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![IrStmt::Expr {
            expr: IrExpr::Call {
                callee: "memset".to_string(),
                args: vec![
                    ir_var("out", mutable_u8_ptr_ty),
                    ir_lit(255, "255", i32_ty),
                    ir_var("count", usize_ty),
                ],
                ty: void_ty,
                source_span: None,
            },
            source_span: None,
        }],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit modeled C memset byte literal statement");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains(".fill(255u8);"), "{rust}");
    assert!(!rust.contains("memset(out, 255, count)"), "{rust}");
    assert_rust_snippet_runs(
        "typed-ir-memset-byte-literal-model",
        rust,
        r#"
    let mut out = [1u8, 2, 3, 4];
    fill_prefix(&mut out, 2);
    assert_eq!(out, [255u8, 255, 3, 4]);
"#,
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_memset_calls_outside_minimal_statement_model() {
    let void_ty = ir_void();
    let i32_ty = ir_i32();
    let usize_ty = ir_usize();
    let mutable_u8_ptr_ty = ir_pointer("uint8_t *", "unsigned char *", ir_u8(), false);
    let const_u8_ptr_ty = ir_pointer(
        "const uint8_t *",
        "const unsigned char *",
        ir_const(ir_u8()),
        true,
    );
    let mutable_i8_ptr_ty = ir_pointer(
        "int8_t *",
        "signed char *",
        ir_integer("int8_t", "signed char", true, 8),
        false,
    );
    let mutable_i32_ptr_ty = ir_pointer("int *", "int *", i32_ty.clone(), false);
    let cases = [
        (
            "memset_no_args",
            vec![],
            void_ty.clone(),
            vec![],
            "requires destination, byte value, and size arguments",
        ),
        (
            "memset_non_void_result",
            vec![
                ir_var("out", mutable_u8_ptr_ty.clone()),
                ir_lit(0, "0", i32_ty.clone()),
                ir_var("count", usize_ty.clone()),
            ],
            i32_ty.clone(),
            vec![
                ("out", mutable_u8_ptr_ty.clone()),
                ("count", usize_ty.clone()),
            ],
            "requires void or discarded void * result type",
        ),
        (
            "memset_truncating_value",
            vec![
                ir_var("out", mutable_u8_ptr_ty.clone()),
                ir_lit(256, "256", i32_ty.clone()),
                ir_var("count", usize_ty.clone()),
            ],
            void_ty.clone(),
            vec![
                ("out", mutable_u8_ptr_ty.clone()),
                ("count", usize_ty.clone()),
            ],
            "byte value literal must fit in unsigned char",
        ),
        (
            "memset_non_literal_value",
            vec![
                ir_var("out", mutable_u8_ptr_ty.clone()),
                ir_var("value", i32_ty.clone()),
                ir_var("count", usize_ty.clone()),
            ],
            void_ty.clone(),
            vec![
                ("out", mutable_u8_ptr_ty.clone()),
                ("value", i32_ty.clone()),
                ("count", usize_ty.clone()),
            ],
            "supports only literal byte values",
        ),
        (
            "memset_const_destination",
            vec![
                ir_var("out", const_u8_ptr_ty.clone()),
                ir_lit(0, "0", i32_ty.clone()),
                ir_var("count", usize_ty.clone()),
            ],
            void_ty.clone(),
            vec![
                ("out", const_u8_ptr_ty.clone()),
                ("count", usize_ty.clone()),
            ],
            "destination argument must be a mutable unsigned 8-bit integer pointer",
        ),
        (
            "memset_signed_destination",
            vec![
                ir_var("out", mutable_i8_ptr_ty.clone()),
                ir_lit(0, "0", i32_ty.clone()),
                ir_var("count", usize_ty.clone()),
            ],
            void_ty.clone(),
            vec![
                ("out", mutable_i8_ptr_ty.clone()),
                ("count", usize_ty.clone()),
            ],
            "destination argument must be a mutable unsigned 8-bit integer pointer",
        ),
        (
            "memset_non_byte_destination",
            vec![
                ir_var("out", mutable_i32_ptr_ty.clone()),
                ir_lit(0, "0", i32_ty.clone()),
                ir_var("count", usize_ty.clone()),
            ],
            void_ty.clone(),
            vec![
                ("out", mutable_i32_ptr_ty.clone()),
                ("count", usize_ty.clone()),
            ],
            "destination argument must be a mutable unsigned 8-bit integer pointer",
        ),
        (
            "memset_non_size_count",
            vec![
                ir_var("out", mutable_u8_ptr_ty.clone()),
                ir_lit(0, "0", i32_ty.clone()),
                ir_var("count", i32_ty.clone()),
            ],
            void_ty.clone(),
            vec![("out", mutable_u8_ptr_ty), ("count", i32_ty.clone())],
            "size argument must be size_t/usize",
        ),
    ];

    for (name, args, call_ty, params, expected_reason) in cases {
        let ir = IrFunction {
            name: name.to_string(),
            return_type: void_ty.clone(),
            params: params
                .into_iter()
                .map(|(name, ty)| IrParam {
                    name: name.to_string(),
                    ty,
                    source_span: None,
                })
                .collect(),
            body: vec![
                IrStmt::Expr {
                    expr: IrExpr::Call {
                        callee: "memset".to_string(),
                        args,
                        ty: call_ty,
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

        let error = emit_rust_from_ir(&ir).expect_err("unsupported memset shape must fail closed");
        assert!(
            error.reason.contains(expected_reason),
            "{name}: {:?}",
            error.reason
        );
    }
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_memcpy_for_restrict_byte_slices_statement() {
    let usize_ty = ir_usize();
    let void_ty = ir_void();
    let const_u8_ptr_ty = ir_pointer(
        "const uint8_t *restrict",
        "const unsigned char *restrict",
        ir_const(ir_u8()),
        true,
    );
    let mutable_u8_ptr_ty = ir_pointer(
        "uint8_t *restrict",
        "unsigned char *restrict",
        ir_u8(),
        false,
    );
    let ir = IrFunction {
        name: "copy_bytes_restrict".to_string(),
        return_type: void_ty.clone(),
        params: vec![
            IrParam {
                name: "src".to_string(),
                ty: const_u8_ptr_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "out".to_string(),
                ty: mutable_u8_ptr_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "count".to_string(),
                ty: usize_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![IrStmt::Expr {
            expr: IrExpr::Call {
                callee: "memcpy".to_string(),
                args: vec![
                    ir_var("out", mutable_u8_ptr_ty),
                    ir_var("src", const_u8_ptr_ty),
                    ir_var("count", usize_ty),
                ],
                ty: void_ty,
                source_span: None,
            },
            source_span: None,
        }],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit modeled C memcpy statement");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(
        rust.contains("pub fn copy_bytes_restrict(src: &[u8], mut out: &mut [u8], count: usize)"),
        "{rust}"
    );
    assert!(
        rust.contains("C memcpy source precondition violated"),
        "{rust}"
    );
    assert!(
        rust.contains("C memcpy destination precondition violated"),
        "{rust}"
    );
    assert!(rust.contains("copy_from_slice"), "{rust}");
    assert!(!rust.contains("memcpy(out, src, count)"), "{rust}");
    assert_rust_snippet_runs(
        "typed-ir-memcpy-model",
        rust,
        r#"
    let src = [1u8, 2, 3, 4];
    let mut out = [0u8; 4];
    copy_bytes_restrict(&src, &mut out, 3);
    assert_eq!(out, [1, 2, 3, 0]);
"#,
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_memcpy_for_discarded_void_pointer_result_statement() {
    let usize_ty = ir_usize();
    let void_ty = ir_void();
    let void_pointer_ty = ir_pointer("void *", "void *", void_ty.clone(), false);
    let const_u8_ptr_ty = ir_pointer(
        "const uint8_t *restrict",
        "const unsigned char *restrict",
        ir_const(ir_u8()),
        true,
    );
    let mutable_u8_ptr_ty = ir_pointer(
        "uint8_t *restrict",
        "unsigned char *restrict",
        ir_u8(),
        false,
    );
    let ir = IrFunction {
        name: "copy_bytes_discarding_result".to_string(),
        return_type: void_ty,
        params: vec![
            IrParam {
                name: "src".to_string(),
                ty: const_u8_ptr_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "out".to_string(),
                ty: mutable_u8_ptr_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "count".to_string(),
                ty: usize_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![IrStmt::Expr {
            expr: IrExpr::Call {
                callee: "memcpy".to_string(),
                args: vec![
                    ir_var("out", mutable_u8_ptr_ty),
                    ir_var("src", const_u8_ptr_ty),
                    ir_var("count", usize_ty),
                ],
                ty: void_pointer_ty,
                source_span: None,
            },
            source_span: None,
        }],
        source_span: None,
    };

    let emitted =
        emit_rust_from_ir(&ir).expect("emit modeled C memcpy statement with discarded void *");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("copy_from_slice"), "{rust}");
    assert!(!rust.contains("memcpy(out, src, count)"), "{rust}");
    assert_rust_snippet_runs(
        "typed-ir-memcpy-discarded-void-pointer-result-model",
        rust,
        r#"
    let src = [1u8, 2, 3, 4];
    let mut out = [0u8; 4];
    copy_bytes_discarding_result(&src, &mut out, 3);
    assert_eq!(out, [1, 2, 3, 0]);
"#,
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_memcpy_discarded_void_pointer_without_noalias_proof() {
    let usize_ty = ir_usize();
    let void_ty = ir_void();
    let void_pointer_ty = ir_pointer("void *", "void *", void_ty.clone(), false);
    let const_u8_ptr_ty = ir_pointer(
        "const uint8_t *",
        "const unsigned char *",
        ir_const(ir_u8()),
        true,
    );
    let mutable_u8_ptr_ty = ir_pointer("uint8_t *", "unsigned char *", ir_u8(), false);
    let ir = IrFunction {
        name: "copy_bytes_without_noalias_discarding_result".to_string(),
        return_type: void_ty,
        params: vec![
            IrParam {
                name: "src".to_string(),
                ty: const_u8_ptr_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "out".to_string(),
                ty: mutable_u8_ptr_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "count".to_string(),
                ty: usize_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![IrStmt::Expr {
            expr: IrExpr::Call {
                callee: "memcpy".to_string(),
                args: vec![
                    ir_var("out", mutable_u8_ptr_ty),
                    ir_var("src", const_u8_ptr_ty),
                    ir_var("count", usize_ty),
                ],
                ty: void_pointer_ty,
                source_span: None,
            },
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("memcpy void * requires noalias proof");
    assert!(
        error
            .reason
            .contains("mutable pointer write with readonly pointer read requires noalias proof"),
        "{:?}",
        error.reason
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_memcpy_without_noalias_proof() {
    let usize_ty = ir_usize();
    let void_ty = ir_void();
    let const_u8_ptr_ty = ir_pointer(
        "const uint8_t *",
        "const unsigned char *",
        ir_const(ir_u8()),
        true,
    );
    let mutable_u8_ptr_ty = ir_pointer("uint8_t *", "unsigned char *", ir_u8(), false);
    let ir = IrFunction {
        name: "copy_bytes_without_noalias".to_string(),
        return_type: void_ty.clone(),
        params: vec![
            IrParam {
                name: "src".to_string(),
                ty: const_u8_ptr_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "out".to_string(),
                ty: mutable_u8_ptr_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "count".to_string(),
                ty: usize_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![IrStmt::Expr {
            expr: IrExpr::Call {
                callee: "memcpy".to_string(),
                args: vec![
                    ir_var("out", mutable_u8_ptr_ty),
                    ir_var("src", const_u8_ptr_ty),
                    ir_var("count", usize_ty),
                ],
                ty: void_ty,
                source_span: None,
            },
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("memcpy requires noalias proof");
    assert!(
        error
            .reason
            .contains("mutable pointer write with readonly pointer read requires noalias proof"),
        "{:?}",
        error.reason
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_memcpy_value_expression_outside_statement_model() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "observe_memcpy_result".to_string(),
        return_type: i32_ty.clone(),
        params: vec![],
        body: vec![IrStmt::Return {
            value: Some(IrExpr::Call {
                callee: "memcpy".to_string(),
                args: vec![
                    ir_lit(0, "0", i32_ty.clone()),
                    ir_lit(0, "0", i32_ty.clone()),
                    ir_lit(0, "0", i32_ty.clone()),
                ],
                ty: i32_ty,
                source_span: None,
            }),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("expression-position memcpy must fail closed");
    assert!(
        error
            .reason
            .contains("reserved C macro/stdlib/extern surface")
            && error
                .reason
                .contains("requires explicit lowering or extern binding"),
        "{:?}",
        error.reason
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_strlen_calls_outside_minimal_model() {
    let usize_ty = ir_usize();
    let i32_ty = ir_i32();
    let u64_ty = ir_integer("uint64_t", "uint64_t", false, 64);
    let const_u8_ptr_ty = ir_pointer(
        "const uint8_t *",
        "const unsigned char *",
        ir_const(ir_u8()),
        true,
    );
    let mutable_u8_ptr_ty = ir_pointer(
        "char *",
        "char *",
        ir_integer("char", "char", true, 8),
        false,
    );
    let const_i32_ptr_ty = ir_pointer("const int *", "const int *", ir_const(i32_ty.clone()), true);
    let cases = [
        (
            "strlen_no_args",
            vec![],
            usize_ty.clone(),
            const_u8_ptr_ty.clone(),
            usize_ty.clone(),
            "requires exactly one string pointer argument",
        ),
        (
            "strlen_two_args",
            vec![
                ir_var("name", const_u8_ptr_ty.clone()),
                ir_var("name", const_u8_ptr_ty.clone()),
            ],
            usize_ty.clone(),
            const_u8_ptr_ty.clone(),
            usize_ty.clone(),
            "requires exactly one string pointer argument",
        ),
        (
            "strlen_non_size_result",
            vec![ir_var("name", const_u8_ptr_ty.clone())],
            i32_ty.clone(),
            const_u8_ptr_ty.clone(),
            i32_ty.clone(),
            "requires size_t/usize result type",
        ),
        (
            "strlen_uint64_result",
            vec![ir_var("name", const_u8_ptr_ty.clone())],
            u64_ty.clone(),
            const_u8_ptr_ty.clone(),
            u64_ty,
            "requires size_t/usize result type",
        ),
        (
            "strlen_non_byte_pointer",
            vec![ir_var("name", const_i32_ptr_ty.clone())],
            usize_ty.clone(),
            const_i32_ptr_ty,
            usize_ty.clone(),
            "argument must be a readonly 8-bit integer pointer",
        ),
        (
            "strlen_mutable_byte_pointer",
            vec![ir_var("name", mutable_u8_ptr_ty.clone())],
            usize_ty.clone(),
            mutable_u8_ptr_ty,
            usize_ty.clone(),
            "param name has pointer type char * is unsupported",
        ),
        (
            "strlen_null_pointer",
            vec![IrExpr::NullPtr {
                ty: const_u8_ptr_ty.clone(),
                source_span: None,
            }],
            usize_ty.clone(),
            const_u8_ptr_ty.clone(),
            usize_ty,
            "argument must be a direct readonly pointer parameter",
        ),
    ];

    for (name, args, call_ty, param_ty, return_ty, expected_reason) in cases {
        let params = if name == "strlen_no_args" || name == "strlen_null_pointer" {
            vec![]
        } else {
            vec![IrParam {
                name: "name".to_string(),
                ty: param_ty,
                source_span: None,
            }]
        };
        let ir = IrFunction {
            name: name.to_string(),
            return_type: return_ty,
            params,
            body: vec![IrStmt::Return {
                value: Some(IrExpr::Call {
                    callee: "strlen".to_string(),
                    args,
                    ty: call_ty,
                    source_span: None,
                }),
                source_span: None,
            }],
            source_span: None,
        };

        let error = emit_rust_from_ir(&ir).expect_err("unsupported strlen shape must fail closed");
        assert!(
            error.reason.contains(expected_reason),
            "{name}: {:?}",
            error.reason
        );
    }
}

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
