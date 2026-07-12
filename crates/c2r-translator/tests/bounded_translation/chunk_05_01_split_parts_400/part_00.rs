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
fn typed_ir_emits_clang_lvalue_wrapped_post_increment_read_in_binary_expr() {
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
    let byte_read = IrExpr::LValueToRValue {
        target: u8_ty.clone(),
        expr: Box::new(IrExpr::Deref {
            ptr: Box::new(IrExpr::IncDec {
                target: Box::new(ir_var("p", const_u8_ptr.clone())),
                op: IrIncDecOp::Inc,
                prefix: false,
                ty: const_u8_ptr.clone(),
                source_span: None,
            }),
            ty: ir_const(u8_ty.clone()),
            source_span: None,
        }),
        source_span: None,
    };
    let ir = IrFunction {
        name: "crc_xor_clang_byte".to_string(),
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

    let rust = emit_rust_from_ir(&ir)
        .expect("emit clang lvalue-wrapped post-increment byte read");

    assert!(rust.contains("pub fn crc_xor_clang_byte(crc: u32, buf: &[u8]) -> u32"));
    assert!(rust.contains("let mut p: usize = 0;"));
    assert!(rust.contains("let byte0: u8 = buf[p];"));
    assert!(rust.contains("p += 1;"));
    assert!(rust.contains("return (crc ^ (byte0 as u32));"));
    assert_rust_snippet_compiles(
        "typed-ir-clang-lvalue-wrapped-post-increment-byte-read",
        &rust,
    );
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
