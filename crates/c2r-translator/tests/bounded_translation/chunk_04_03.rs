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
