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
