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
fn typed_ir_emits_memcpy_for_local_fixed_byte_array_decay_statement() {
    let usize_ty = ir_usize();
    let void_ty = ir_void();
    let u8_ty = ir_u8();
    let i32_ty = ir_i32();
    let array_ty = ir_array(ir_u8(), 4);
    let const_u8_ptr_ty = ir_pointer(
        "const uint8_t *",
        "const unsigned char *",
        ir_const(ir_u8()),
        true,
    );
    let mutable_u8_ptr_ty = ir_pointer("uint8_t *", "unsigned char *", ir_u8(), false);
    let ir = IrFunction {
        name: "copy_local_prefix".to_string(),
        return_type: u8_ty.clone(),
        params: vec![],
        body: vec![
            IrStmt::Decl {
                name: "src".to_string(),
                ty: array_ty.clone(),
                init: Some(IrExpr::ArrayLiteral {
                    elements: vec![
                        ir_lit(1, "1", ir_u8()),
                        ir_lit(2, "2", ir_u8()),
                        ir_lit(3, "3", ir_u8()),
                        ir_lit(4, "4", ir_u8()),
                    ],
                    ty: array_ty.clone(),
                    source_span: None,
                }),
                source_span: None,
            },
            IrStmt::Decl {
                name: "dst".to_string(),
                ty: array_ty.clone(),
                init: Some(IrExpr::ArrayLiteral {
                    elements: vec![
                        ir_lit(0, "0", ir_u8()),
                        ir_lit(0, "0", ir_u8()),
                        ir_lit(0, "0", ir_u8()),
                        ir_lit(0, "0", ir_u8()),
                    ],
                    ty: array_ty.clone(),
                    source_span: None,
                }),
                source_span: None,
            },
            IrStmt::Expr {
                expr: IrExpr::Call {
                    callee: "memcpy".to_string(),
                    args: vec![
                        IrExpr::ArrayToPointerDecay {
                            target: mutable_u8_ptr_ty,
                            expr: Box::new(ir_var("dst", array_ty.clone())),
                            source_span: None,
                        },
                        IrExpr::ArrayToPointerDecay {
                            target: const_u8_ptr_ty,
                            expr: Box::new(ir_var("src", array_ty.clone())),
                            source_span: None,
                        },
                        ir_lit(3, "3", usize_ty),
                    ],
                    ty: void_ty,
                    source_span: None,
                },
                source_span: None,
            },
            IrStmt::Return {
                value: Some(IrExpr::Index {
                    base: Box::new(ir_var("dst", array_ty)),
                    index: Box::new(ir_lit(2, "2", i32_ty)),
                    ty: u8_ty,
                    source_span: None,
                }),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let emitted =
        emit_rust_from_ir(&ir).expect("emit modeled C memcpy over local fixed byte arrays");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("let src: [u8; 4] = [1u8, 2u8, 3u8, 4u8];"), "{rust}");
    assert!(rust.contains("let mut dst: [u8; 4] = [0u8, 0u8, 0u8, 0u8];"), "{rust}");
    assert!(rust.contains("dst.get_mut(..(3usize as usize))"), "{rust}");
    assert!(rust.contains("src.get(..(3usize as usize))"), "{rust}");
    assert!(rust.contains("copy_from_slice"), "{rust}");
    assert_rust_snippet_runs(
        "typed-ir-memcpy-local-fixed-byte-array-decay",
        rust,
        r#"
    assert_eq!(copy_local_prefix(), 3);
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
