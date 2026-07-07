#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_const_void_cast_cursor_nested_post_increment_read_in_binary_expr() {
    let u32_ty = ir_u32();
    let u8_ty = ir_u8();
    let const_void_ptr = ir_pointer(
        "const void *",
        "const void *",
        IrType {
            spelled: "void".to_string(),
            canonical: "void".to_string(),
            kind: IrTypeKind::Void,
            is_const: true,
            width_bits: None,
            source_span: None,
        },
        false,
    );
    let const_u8_ptr = ir_pointer(
        "const uint8_t *",
        "const unsigned char *",
        ir_const(u8_ty.clone()),
        false,
    );
    let byte_read = IrExpr::Deref {
        ptr: Box::new(IrExpr::IncDec {
            target: Box::new(ir_var("p", const_u8_ptr.clone())),
            op: IrIncDecOp::Inc,
            prefix: false,
            ty: const_u8_ptr.clone(),
            source_span: None,
        }),
        ty: u8_ty.clone(),
        source_span: None,
    };
    let ir = IrFunction {
        name: "crc_xor_byte".to_string(),
        return_type: u32_ty.clone(),
        params: vec![
            IrParam {
                name: "crc".to_string(),
                ty: u32_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "buf".to_string(),
                ty: const_void_ptr.clone(),
                source_span: None,
            },
        ],
        body: vec![
            IrStmt::Decl {
                name: "p".to_string(),
                ty: const_u8_ptr.clone(),
                init: None,
                source_span: None,
            },
            IrStmt::Assign {
                target: ir_var("p", const_u8_ptr.clone()),
                value: IrExpr::Cast {
                    target: const_u8_ptr,
                    expr: Box::new(ir_var("buf", const_void_ptr)),
                    implicit: false,
                    source_span: None,
                },
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_binary(
                    IrBinOp::BitXor,
                    ir_var("crc", u32_ty.clone()),
                    IrExpr::Cast {
                        target: u32_ty.clone(),
                        expr: Box::new(byte_read),
                        implicit: true,
                        source_span: None,
                    },
                    u32_ty.clone(),
                )),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let rust = emit_rust_from_ir(&ir).expect("emit nested post-increment byte read");

    assert!(rust.contains("pub fn crc_xor_byte(crc: u32, buf: &[u8]) -> u32"));
    assert!(rust.contains("let mut p: usize = 0;"));
    assert!(rust.contains("let byte0: u8 = buf[p];"));
    assert!(rust.contains("p += 1;"));
    assert!(rust.contains("return (crc ^ (byte0 as u32));"));
    assert_rust_snippet_compiles("typed-ir-nested-post-increment-byte-read", &rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_avoids_byte_temp_name_collision_for_nested_post_increment_read() {
    let u32_ty = ir_u32();
    let u8_ty = ir_u8();
    let const_u8_ptr = ir_pointer(
        "const uint8_t *",
        "const unsigned char *",
        ir_const(u8_ty.clone()),
        false,
    );
    let byte_read = IrExpr::Deref {
        ptr: Box::new(IrExpr::IncDec {
            target: Box::new(ir_var("p", const_u8_ptr.clone())),
            op: IrIncDecOp::Inc,
            prefix: false,
            ty: const_u8_ptr.clone(),
            source_span: None,
        }),
        ty: u8_ty.clone(),
        source_span: None,
    };
    let ir = IrFunction {
        name: "crc_xor_byte_collision".to_string(),
        return_type: u32_ty.clone(),
        params: vec![
            IrParam {
                name: "crc".to_string(),
                ty: u32_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "p".to_string(),
                ty: const_u8_ptr,
                source_span: None,
            },
            IrParam {
                name: "byte0".to_string(),
                ty: u8_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![IrStmt::Return {
            value: Some(ir_binary(
                IrBinOp::BitXor,
                ir_var("crc", u32_ty.clone()),
                IrExpr::Cast {
                    target: u32_ty.clone(),
                    expr: Box::new(byte_read),
                    implicit: true,
                    source_span: None,
                },
                u32_ty.clone(),
            )),
            source_span: None,
        }],
        source_span: None,
    };

    let rust = emit_rust_from_ir(&ir).expect("emit nested byte read without temp collision");

    assert!(rust.contains("let mut p_index: usize = 0;"));
    assert!(rust.contains("let byte1: u8 = p[p_index];"));
    assert!(rust.contains("return (crc ^ (byte1 as u32));"));
    assert_rust_snippet_compiles("typed-ir-nested-byte-temp-collision", &rust);
}
#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_avoids_cursor_temp_name_collision_for_nested_post_increment_read() {
    let u32_ty = ir_u32();
    let u8_ty = ir_u8();
    let const_u8_ptr = ir_pointer(
        "const uint8_t *",
        "const unsigned char *",
        ir_const(u8_ty.clone()),
        false,
    );
    let byte_read = IrExpr::Deref {
        ptr: Box::new(IrExpr::IncDec {
            target: Box::new(ir_var("p", const_u8_ptr.clone())),
            op: IrIncDecOp::Inc,
            prefix: false,
            ty: const_u8_ptr.clone(),
            source_span: None,
        }),
        ty: u8_ty.clone(),
        source_span: None,
    };
    let ir = IrFunction {
        name: "crc_xor_byte_cursor_collision".to_string(),
        return_type: u32_ty.clone(),
        params: vec![
            IrParam {
                name: "crc".to_string(),
                ty: u32_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "p".to_string(),
                ty: const_u8_ptr,
                source_span: None,
            },
            IrParam {
                name: "p_index".to_string(),
                ty: u32_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![IrStmt::Return {
            value: Some(ir_binary(
                IrBinOp::BitXor,
                ir_binary(
                    IrBinOp::BitXor,
                    ir_var("crc", u32_ty.clone()),
                    IrExpr::Cast {
                        target: u32_ty.clone(),
                        expr: Box::new(byte_read),
                        implicit: true,
                        source_span: None,
                    },
                    u32_ty.clone(),
                ),
                ir_var("p_index", u32_ty.clone()),
                u32_ty.clone(),
            )),
            source_span: None,
        }],
        source_span: None,
    };

    let rust = emit_rust_from_ir(&ir).expect("emit nested byte read without cursor collision");

    assert!(rust.contains("let mut p_index1: usize = 0;"));
    assert!(rust.contains("let byte0: u8 = p[p_index1];"));
    assert!(rust.contains("p_index1 += 1;"));
    assert!(rust.contains("return ((crc ^ (byte0 as u32)) ^ p_index);"));
    assert_rust_snippet_compiles("typed-ir-nested-byte-cursor-collision", &rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_undeclared_var_named_like_generated_byte_temp() {
    let u32_ty = ir_u32();
    let u8_ty = ir_u8();
    let const_u8_ptr = ir_pointer(
        "const uint8_t *",
        "const unsigned char *",
        ir_const(u8_ty.clone()),
        false,
    );
    let byte_read = IrExpr::Deref {
        ptr: Box::new(IrExpr::IncDec {
            target: Box::new(ir_var("p", const_u8_ptr.clone())),
            op: IrIncDecOp::Inc,
            prefix: false,
            ty: const_u8_ptr.clone(),
            source_span: None,
        }),
        ty: u8_ty.clone(),
        source_span: None,
    };
    let ir = IrFunction {
        name: "bad_generated_temp_ref".to_string(),
        return_type: u32_ty.clone(),
        params: vec![IrParam {
            name: "p".to_string(),
            ty: const_u8_ptr,
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(ir_binary(
                IrBinOp::BitXor,
                IrExpr::Cast {
                    target: u32_ty.clone(),
                    expr: Box::new(byte_read),
                    implicit: true,
                    source_span: None,
                },
                ir_var("byte0", u32_ty.clone()),
                u32_ty.clone(),
            )),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("generated temp must not declare source var");

    assert!(error.reason.contains("return expr binary rhs"));
    assert!(error.reason.contains("var byte0 is not declared"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_multiple_nested_post_increment_reads_in_one_expr() {
    let u8_ty = ir_u8();
    let const_u8_ptr = ir_pointer(
        "const uint8_t *",
        "const unsigned char *",
        ir_const(u8_ty.clone()),
        false,
    );
    let byte_read = || IrExpr::Deref {
        ptr: Box::new(IrExpr::IncDec {
            target: Box::new(ir_var("p", const_u8_ptr.clone())),
            op: IrIncDecOp::Inc,
            prefix: false,
            ty: const_u8_ptr.clone(),
            source_span: None,
        }),
        ty: u8_ty.clone(),
        source_span: None,
    };
    let ir = IrFunction {
        name: "double_byte_read".to_string(),
        return_type: u8_ty.clone(),
        params: vec![IrParam {
            name: "p".to_string(),
            ty: const_u8_ptr.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(ir_binary(
                IrBinOp::BitXor,
                byte_read(),
                byte_read(),
                u8_ty.clone(),
            )),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("multiple post-increment reads must fail closed");

    assert!(error
        .reason
        .contains("multiple post-increment byte reads are unsupported"));
    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert_eq!(error.route.candidate_generator, CandidateGenerator::None);
    assert_eq!(error.route.fallback, None);
    assert!(error.route.reasons.iter().any(|reason| reason
        .detail
        .contains("multiple post-increment byte reads are unsupported")));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_postfix_decrement_while_condition_for_size_counter() {
    let usize_ty = ir_usize();
    let ir = IrFunction {
        name: "countdown_sum".to_string(),
        return_type: usize_ty.clone(),
        params: vec![
            IrParam {
                name: "size".to_string(),
                ty: usize_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "acc".to_string(),
                ty: usize_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![
            IrStmt::While {
                condition: IrExpr::IncDec {
                    target: Box::new(ir_var("size", usize_ty.clone())),
                    op: IrIncDecOp::Dec,
                    prefix: false,
                    ty: usize_ty.clone(),
                    source_span: None,
                },
                body: vec![IrStmt::Assign {
                    target: ir_var("acc", usize_ty.clone()),
                    value: ir_binary(
                        IrBinOp::Add,
                        ir_var("acc", usize_ty.clone()),
                        ir_var("size", usize_ty.clone()),
                        usize_ty.clone(),
                    ),
                    source_span: None,
                }],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("acc", usize_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let rust = emit_rust_from_ir(&ir).expect("emit postfix decrement while condition");

    assert!(rust.contains("pub fn countdown_sum(mut size: usize, mut acc: usize) -> usize"));
    assert!(rust.contains("loop {"));
    assert!(rust.contains("let size_before_dec0: usize = size;"));
    assert!(rust.contains("size = size.wrapping_sub(1usize);"));
    assert!(rust.contains("if size_before_dec0 == 0usize {"));
    assert!(rust.contains("break;"));
    assert!(rust.contains("acc = acc.wrapping_add(size);"));
    assert!(rust.contains("return acc;"));
    assert_rust_snippet_compiles("typed-ir-postfix-decrement-while", &rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_prefix_decrement_while_loop() {
    let usize_ty = ir_usize();
    let ir = IrFunction {
        name: "countdown_sum_prefix".to_string(),
        return_type: usize_ty.clone(),
        params: vec![
            IrParam {
                name: "size".to_string(),
                ty: usize_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "acc".to_string(),
                ty: usize_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![
            IrStmt::While {
                condition: IrExpr::IncDec {
                    target: Box::new(ir_var("size", usize_ty.clone())),
                    op: IrIncDecOp::Dec,
                    prefix: true,
                    ty: usize_ty.clone(),
                    source_span: None,
                },
                body: vec![IrStmt::Assign {
                    target: ir_var("acc", usize_ty.clone()),
                    value: ir_binary(
                        IrBinOp::Add,
                        ir_var("acc", usize_ty.clone()),
                        ir_var("size", usize_ty.clone()),
                        usize_ty.clone(),
                    ),
                    source_span: None,
                }],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("acc", usize_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let rust = emit_rust_from_ir(&ir).expect("emit prefix decrement while condition");

    assert!(rust.contains("pub fn countdown_sum_prefix(mut size: usize, mut acc: usize) -> usize"));
    assert!(rust.contains("loop {"));
    assert!(rust.contains("size = size.wrapping_sub(1usize);"));
    assert!(rust.contains("if size == 0usize {"));
    assert!(rust.contains("break;"));
    assert!(rust.contains("acc = acc.wrapping_add(size);"));
    assert!(rust.contains("return acc;"));
    assert_rust_snippet_compiles("typed-ir-prefix-decrement-while", &rust);
}
