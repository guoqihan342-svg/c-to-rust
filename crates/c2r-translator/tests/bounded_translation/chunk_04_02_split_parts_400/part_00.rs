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
