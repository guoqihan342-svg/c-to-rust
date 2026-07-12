#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_const_u8_pointer_param_post_increment_read() {
    let u8_ty = ir_u8();
    let const_u8_ptr = ir_pointer(
        "const uint8_t *",
        "const unsigned char *",
        ir_const(u8_ty.clone()),
        false,
    );
    let ir = IrFunction {
        name: "read_byte".to_string(),
        return_type: u8_ty.clone(),
        params: vec![IrParam {
            name: "p".to_string(),
            ty: const_u8_ptr.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(IrExpr::Deref {
                ptr: Box::new(IrExpr::IncDec {
                    target: Box::new(ir_var("p", const_u8_ptr.clone())),
                    op: IrIncDecOp::Inc,
                    prefix: false,
                    ty: const_u8_ptr,
                    source_span: None,
                }),
                ty: u8_ty.clone(),
                source_span: None,
            }),
            source_span: None,
        }],
        source_span: None,
    };

    let rust = emit_rust_from_ir(&ir).expect("emit const u8 post-increment read");

    assert!(rust.contains("pub fn read_byte(p: &[u8]) -> u8"));
    assert!(rust.contains("let mut p_index: usize = 0;"));
    assert!(rust.contains("let byte0: u8 = p[p_index];"));
    assert!(rust.contains("p_index += 1;"));
    assert!(rust.contains("return byte0;"));
    assert_rust_snippet_compiles("typed-ir-const-u8-post-increment-read", &rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_const_void_cast_cursor_post_increment_read() {
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
        true,
    );
    let const_u8_ptr = ir_pointer(
        "const uint8_t *",
        "const unsigned char *",
        ir_const(u8_ty.clone()),
        false,
    );
    let ir = IrFunction {
        name: "read_byte_from_void".to_string(),
        return_type: u8_ty.clone(),
        params: vec![IrParam {
            name: "buf".to_string(),
            ty: const_void_ptr.clone(),
            source_span: None,
        }],
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
                    target: const_u8_ptr.clone(),
                    expr: Box::new(ir_var("buf", const_void_ptr)),
                    implicit: false,
                    source_span: None,
                },
                source_span: None,
            },
            IrStmt::Return {
                value: Some(IrExpr::Deref {
                    ptr: Box::new(IrExpr::IncDec {
                        target: Box::new(ir_var("p", const_u8_ptr.clone())),
                        op: IrIncDecOp::Inc,
                        prefix: false,
                        ty: const_u8_ptr,
                        source_span: None,
                    }),
                    ty: u8_ty.clone(),
                    source_span: None,
                }),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let rust = emit_rust_from_ir(&ir).expect("emit const void byte cursor read");

    assert!(rust.contains("pub fn read_byte_from_void(buf: &[u8]) -> u8"));
    assert!(rust.contains("let mut p: usize = 0;"));
    assert!(rust.contains("let byte0: u8 = buf[p];"));
    assert!(rust.contains("p += 1;"));
    assert!(rust.contains("return byte0;"));
    assert_rust_snippet_compiles("typed-ir-const-void-byte-cursor-read", &rust);
}
