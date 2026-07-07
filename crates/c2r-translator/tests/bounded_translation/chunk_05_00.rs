#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_side_effect_direct_call_argument_with_same_var_sibling_read() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "side_effect_call_argument_with_ordinary_arg".to_string(),
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
                    IrExpr::IncDec {
                        target: Box::new(ir_var("value", i32_ty.clone())),
                        op: IrIncDecOp::Inc,
                        prefix: true,
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
        .expect_err("side-effect plus same-var sibling read must fail closed");

    assert!(error
        .reason
        .contains("sibling argument reading modified variable value"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_multiple_side_effect_direct_call_arguments() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "multiple_side_effect_call_arguments".to_string(),
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
                    IrExpr::IncDec {
                        target: Box::new(ir_var("value", i32_ty.clone())),
                        op: IrIncDecOp::Inc,
                        prefix: true,
                        ty: i32_ty.clone(),
                        source_span: None,
                    },
                    IrExpr::IncDec {
                        target: Box::new(ir_var("value", i32_ty.clone())),
                        op: IrIncDecOp::Dec,
                        prefix: false,
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

    let error =
        emit_rust_from_ir(&ir).expect_err("multiple side-effect call args must fail closed");

    assert!(error
        .reason
        .contains("call arguments cannot use increment/decrement value semantics"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_index_over_const_u32_pointer_param() {
    let u32_ty = ir_u32();
    let const_u32_ptr = ir_pointer(
        "const uint32_t *",
        "const unsigned int *",
        ir_const(u32_ty.clone()),
        false,
    );
    let ir = IrFunction {
        name: "read_table".to_string(),
        return_type: u32_ty.clone(),
        params: vec![
            IrParam {
                name: "table".to_string(),
                ty: const_u32_ptr.clone(),
                source_span: None,
            },
            IrParam {
                name: "idx".to_string(),
                ty: u32_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![IrStmt::Return {
            value: Some(IrExpr::Index {
                base: Box::new(ir_var("table", const_u32_ptr)),
                index: Box::new(ir_var("idx", u32_ty.clone())),
                ty: u32_ty.clone(),
                source_span: None,
            }),
            source_span: None,
        }],
        source_span: None,
    };

    let rust = emit_rust_from_ir(&ir).expect("emit const u32 pointer index");

    assert!(rust.contains("pub fn read_table(table: &[u32], idx: u32) -> u32"));
    assert!(rust.contains("return table[idx as usize];"));
    assert_rust_snippet_compiles("typed-ir-const-u32-pointer-index", &rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_crc_update_assignment_with_nested_byte_read() {
    let u32_ty = ir_u32();
    let u8_ty = ir_u8();
    let const_u8_ptr = ir_pointer(
        "const uint8_t *",
        "const unsigned char *",
        ir_const(u8_ty.clone()),
        false,
    );
    let const_u32_ptr = ir_pointer(
        "const uint32_t *",
        "const unsigned int *",
        ir_const(u32_ty.clone()),
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
    let table_index = ir_binary(
        IrBinOp::BitAnd,
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
        ir_lit(0xFF, "0xFFU", u32_ty.clone()),
        u32_ty.clone(),
    );
    let table_lookup = IrExpr::Index {
        base: Box::new(ir_var("table", const_u32_ptr.clone())),
        index: Box::new(table_index),
        ty: u32_ty.clone(),
        source_span: None,
    };
    let shift = ir_binary(
        IrBinOp::Shr,
        ir_var("crc", u32_ty.clone()),
        ir_lit(8, "8U", u32_ty.clone()),
        u32_ty.clone(),
    );
    let ir = IrFunction {
        name: "update_crc_step".to_string(),
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
                name: "table".to_string(),
                ty: const_u32_ptr,
                source_span: None,
            },
        ],
        body: vec![
            IrStmt::Assign {
                target: ir_var("crc", u32_ty.clone()),
                value: ir_binary(IrBinOp::BitXor, table_lookup, shift, u32_ty.clone()),
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("crc", u32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit crc update assignment");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(!emitted.route.deprecated);
    assert!(rust.contains("pub fn update_crc_step(mut crc: u32, p: &[u8], table: &[u32]) -> u32"));
    assert!(rust.contains("let mut p_index: usize = 0;"));
    assert!(rust.contains("let byte0: u8 = p[p_index];"));
    assert!(rust.contains("p_index += 1;"));
    assert!(
        rust.contains("crc = (table[((crc ^ (byte0 as u32)) & 255u32) as usize] ^ crc.checked_shr(core::convert::TryFrom::try_from(8u32).expect(\"shift count must be nonnegative and fit u32\")).expect(\"shift count out of range\"));")
    );
    assert!(rust.contains("return crc;"));
    assert!(!rust.contains("crc32_update_byte"));
    assert_rust_snippet_compiles("typed-ir-crc-update-assignment", rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_multiple_post_increment_reads_in_assign_value() {
    let u32_ty = ir_u32();
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
        name: "bad_assign_double_byte_read".to_string(),
        return_type: u32_ty.clone(),
        params: vec![
            IrParam {
                name: "crc".to_string(),
                ty: u32_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "p".to_string(),
                ty: const_u8_ptr.clone(),
                source_span: None,
            },
        ],
        body: vec![
            IrStmt::Assign {
                target: ir_var("crc", u32_ty.clone()),
                value: ir_binary(
                    IrBinOp::BitXor,
                    IrExpr::Cast {
                        target: u32_ty.clone(),
                        expr: Box::new(byte_read()),
                        implicit: true,
                        source_span: None,
                    },
                    IrExpr::Cast {
                        target: u32_ty.clone(),
                        expr: Box::new(byte_read()),
                        implicit: true,
                        source_span: None,
                    },
                    u32_ty.clone(),
                ),
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("crc", u32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error =
        emit_rust_from_ir(&ir).expect_err("assign with multiple byte reads must fail closed");

    assert!(error
        .reason
        .contains("assign value multiple post-increment byte reads are unsupported"));
    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert_eq!(error.route.candidate_generator, CandidateGenerator::None);
    assert_eq!(error.route.fallback, None);
    assert!(error.route.reasons.iter().any(|reason| reason
        .detail
        .contains("assign value multiple post-increment byte reads are unsupported")));
}

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
