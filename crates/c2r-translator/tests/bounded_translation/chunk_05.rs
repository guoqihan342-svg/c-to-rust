#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_side_effect_direct_call_argument_with_ordinary_arg() {
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

    let error =
        emit_rust_from_ir(&ir).expect_err("side-effect plus ordinary call args must fail closed");

    assert!(error
        .reason
        .contains("call arguments cannot use increment/decrement value semantics"));
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

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_const_void_cast_cursor_without_byte_read() {
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
    let ir = IrFunction {
        name: "cast_without_read".to_string(),
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
                target: ir_var("p", const_u8_ptr),
                value: IrExpr::Cast {
                    target: ir_pointer(
                        "const uint8_t *",
                        "const unsigned char *",
                        ir_const(u8_ty.clone()),
                        false,
                    ),
                    expr: Box::new(ir_var("buf", const_void_ptr)),
                    implicit: false,
                    source_span: None,
                },
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_lit(0, "0", u8_ty)),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("cast without byte read must fail closed");

    assert!(error
        .reason
        .contains("param buf has pointer type const void * is unsupported"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_const_u32_pointer_param_post_increment_read() {
    let u32_ty = ir_u32();
    let const_u32_ptr = ir_pointer(
        "const uint32_t *",
        "const unsigned int *",
        ir_const(u32_ty.clone()),
        false,
    );
    let ir = IrFunction {
        name: "read_word".to_string(),
        return_type: u32_ty.clone(),
        params: vec![IrParam {
            name: "p".to_string(),
            ty: const_u32_ptr.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(IrExpr::Deref {
                ptr: Box::new(IrExpr::IncDec {
                    target: Box::new(ir_var("p", const_u32_ptr.clone())),
                    op: IrIncDecOp::Inc,
                    prefix: false,
                    ty: const_u32_ptr,
                    source_span: None,
                }),
                ty: u32_ty.clone(),
                source_span: None,
            }),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("u32 post-increment read must fail closed");

    assert!(error
        .reason
        .contains("post-increment cursor p has unsupported type const uint32_t *"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_mutable_pointer_param_in_generic_emitter() {
    let i32_ty = ir_i32();
    let mutable_i32_ptr = ir_pointer("int *", "int *", i32_ty, false);
    let ir = IrFunction {
        name: "mutable_pointer".to_string(),
        return_type: IrType {
            spelled: "void".to_string(),
            canonical: "void".to_string(),
            kind: IrTypeKind::Void,
            is_const: false,
            width_bits: None,
            source_span: None,
        },
        params: vec![IrParam {
            name: "out".to_string(),
            ty: mutable_i32_ptr,
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: None,
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("mutable pointer param must fail closed");

    assert!(error
        .reason
        .contains("param out has pointer type int * is unsupported"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_non_const_pointer_param_in_generic_emitter() {
    let u32_ty = ir_u32();
    let mutable_u32_ptr = ir_pointer("uint32_t *", "unsigned int *", u32_ty.clone(), false);
    let ir = IrFunction {
        name: "read_mutable_table".to_string(),
        return_type: u32_ty.clone(),
        params: vec![
            IrParam {
                name: "table".to_string(),
                ty: mutable_u32_ptr.clone(),
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
                base: Box::new(ir_var("table", mutable_u32_ptr)),
                index: Box::new(ir_var("idx", u32_ty.clone())),
                ty: u32_ty,
                source_span: None,
            }),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("non-const pointer param must fail closed");

    assert!(error
        .reason
        .contains("param table has pointer type uint32_t * is unsupported"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_crc32_loop_with_extra_top_level_term() {
    let mut ir = flashdb_crc32_typed_ir();
    let IrStmt::While { body, .. } = &mut ir.body[3] else {
        panic!("expected crc32 while loop");
    };
    let IrStmt::Assign { value, .. } = &mut body[0] else {
        panic!("expected crc32 assignment");
    };
    let original = value.clone();
    *value = ir_binary(
        IrBinOp::BitXor,
        original,
        ir_lit(1, "1U", ir_u32()),
        ir_u32(),
    );

    let error = emit_rust_from_ir(&ir).expect_err("extra top-level term must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_scalar_assignment_to_mut_param() {
    let u32_ty = ir_u32();
    let ir = IrFunction {
        name: "invert_crc".to_string(),
        return_type: u32_ty.clone(),
        params: vec![IrParam {
            name: "crc".to_string(),
            ty: u32_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::Assign {
                target: ir_var("crc", u32_ty.clone()),
                value: ir_binary(
                    IrBinOp::BitXor,
                    ir_var("crc", u32_ty.clone()),
                    ir_bitnot(ir_lit(0, "0U", u32_ty.clone()), u32_ty.clone()),
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

    let rust = emit_rust_from_ir(&ir).expect("emit scalar param assignment");

    assert!(rust.contains("pub fn invert_crc(mut crc: u32) -> u32"));
    assert!(rust.contains("crc = (crc ^ !0u32);"));
    assert!(rust.contains("return crc;"));
    assert_rust_snippet_compiles("typed-ir-scalar-assignment", &rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_scalar_assignment_with_integer_promotion_and_truncation() {
    let u8_ty = ir_u8();
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "inc8".to_string(),
        return_type: u8_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: u8_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::Assign {
                target: ir_var("value", u8_ty.clone()),
                value: IrExpr::Cast {
                    target: u8_ty.clone(),
                    expr: Box::new(ir_binary(
                        IrBinOp::Add,
                        IrExpr::Cast {
                            target: i32_ty.clone(),
                            expr: Box::new(ir_var("value", u8_ty.clone())),
                            implicit: true,
                            source_span: None,
                        },
                        ir_lit(1, "1", i32_ty.clone()),
                        i32_ty.clone(),
                    )),
                    implicit: true,
                    source_span: None,
                },
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("value", u8_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let rust = emit_rust_from_ir(&ir).expect("emit promoted/truncated scalar assignment");

    assert!(rust.contains("pub fn inc8(mut value: u8) -> u8"));
    assert!(rust.contains(
        "value = ((value as i32).checked_add(1i32).expect(\"signed addition overflow\") as u8);"
    ));
    assert!(rust.contains("return value;"));
    assert_rust_snippet_compiles("typed-ir-scalar-assignment-promote-truncate", &rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_binary_arithmetic_with_integral_operand_cast() {
    let u32_ty = ir_u32();
    let u8_ty = ir_u8();
    let ir = IrFunction {
        name: "add_byte".to_string(),
        return_type: u32_ty.clone(),
        params: vec![
            IrParam {
                name: "acc".to_string(),
                ty: u32_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "byte".to_string(),
                ty: u8_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![IrStmt::Return {
            value: Some(ir_binary(
                IrBinOp::Add,
                ir_var("acc", u32_ty.clone()),
                IrExpr::Cast {
                    target: u32_ty.clone(),
                    expr: Box::new(ir_var("byte", u8_ty)),
                    implicit: true,
                    source_span: None,
                },
                u32_ty,
            )),
            source_span: None,
        }],
        source_span: None,
    };

    let rust = emit_rust_from_ir(&ir).expect("emit binary arithmetic integral cast");

    assert!(rust.contains("pub fn add_byte(acc: u32, byte: u8) -> u32"));
    assert!(rust.contains("return acc.wrapping_add((byte as u32));"));
    assert_rust_snippet_compiles("typed-ir-binary-integral-operand-cast", &rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_scalar_decl_init_and_integer_cast() {
    let i32_ty = ir_i32();
    let u32_ty = ir_u32();
    let ir = IrFunction {
        name: "widen".to_string(),
        return_type: u32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::Decl {
                name: "tmp".to_string(),
                ty: u32_ty.clone(),
                init: Some(IrExpr::Cast {
                    target: u32_ty.clone(),
                    expr: Box::new(ir_var("value", i32_ty.clone())),
                    implicit: false,
                    source_span: None,
                }),
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("tmp", u32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let rust = emit_rust_from_ir(&ir).expect("emit scalar decl and cast");

    assert!(rust.contains("pub fn widen(value: i32) -> u32"));
    assert!(rust.contains("let mut tmp: u32 = (value as u32);"));
    assert!(rust.contains("return tmp;"));
    assert_rust_snippet_compiles("typed-ir-scalar-decl-cast", &rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_scalar_while_with_integer_condition() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "countdown".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "count".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::While {
                condition: ir_var("count", i32_ty.clone()),
                body: vec![IrStmt::Assign {
                    target: ir_var("count", i32_ty.clone()),
                    value: ir_binary(
                        IrBinOp::Add,
                        ir_var("count", i32_ty.clone()),
                        ir_bitnot(ir_lit(0, "0", i32_ty.clone()), i32_ty.clone()),
                        i32_ty.clone(),
                    ),
                    source_span: None,
                }],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("count", i32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let rust = emit_rust_from_ir(&ir).expect("emit scalar while");

    assert!(rust.contains("pub fn countdown(mut count: i32) -> i32"));
    assert!(rust.contains("while count != 0i32 {"));
    assert!(rust.contains("count = count.checked_add(!0i32).expect(\"signed addition overflow\");"));
    assert!(rust.contains("return count;"));
    assert_rust_snippet_compiles("typed-ir-scalar-while", &rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_break_in_scalar_while_body() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "stop_at_limit".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::While {
                condition: ir_var("value", i32_ty.clone()),
                body: vec![IrStmt::If {
                    condition: ir_binary(
                        IrBinOp::Gt,
                        ir_var("value", i32_ty.clone()),
                        ir_lit(3, "3", i32_ty.clone()),
                        i32_ty.clone(),
                    ),
                    then_body: vec![IrStmt::Break { source_span: None }],
                    else_body: vec![],
                    source_span: None,
                }],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("value", i32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let rust = emit_rust_from_ir(&ir).expect("emit break in scalar while");

    assert!(rust.contains("pub fn stop_at_limit(value: i32) -> i32"));
    assert!(rust.contains("while value != 0i32 {"));
    assert!(rust.contains("if (value > 3i32) {"));
    assert!(rust.contains("break;"));
    assert!(rust.contains("return value;"));
    assert_rust_snippet_compiles("typed-ir-scalar-while-break", &rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_break_outside_loop() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "bad_break".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::Break { source_span: None },
            IrStmt::Return {
                value: Some(ir_var("value", i32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("top-level break must fail closed");

    assert!(error.reason.contains("break outside loop"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_continue_in_scalar_while_body() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "skip_large".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::While {
                condition: ir_var("value", i32_ty.clone()),
                body: vec![
                    IrStmt::If {
                        condition: ir_binary(
                            IrBinOp::Gt,
                            ir_var("value", i32_ty.clone()),
                            ir_lit(3, "3", i32_ty.clone()),
                            i32_ty.clone(),
                        ),
                        then_body: vec![IrStmt::Continue { source_span: None }],
                        else_body: vec![],
                        source_span: None,
                    },
                    IrStmt::Assign {
                        target: ir_var("value", i32_ty.clone()),
                        value: ir_binary(
                            IrBinOp::Sub,
                            ir_var("value", i32_ty.clone()),
                            ir_lit(1, "1", i32_ty.clone()),
                            i32_ty.clone(),
                        ),
                        source_span: None,
                    },
                ],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("value", i32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let rust = emit_rust_from_ir(&ir).expect("emit continue in scalar while");

    assert!(rust.contains("pub fn skip_large(mut value: i32) -> i32"));
    assert!(rust.contains("while value != 0i32 {"));
    assert!(rust.contains("continue;"));
    assert!(
        rust.contains("value = value.checked_sub(1i32).expect(\"signed subtraction overflow\");")
    );
    assert_rust_snippet_compiles("typed-ir-scalar-while-continue", &rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_scalar_do_while_with_condition_check_after_body() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "do_countdown".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::DoWhile {
                body: vec![IrStmt::Assign {
                    target: ir_var("value", i32_ty.clone()),
                    value: ir_binary(
                        IrBinOp::Sub,
                        ir_var("value", i32_ty.clone()),
                        ir_lit(1, "1", i32_ty.clone()),
                        i32_ty.clone(),
                    ),
                    source_span: None,
                }],
                condition: ir_var("value", i32_ty.clone()),
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("value", i32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let rust = emit_rust_from_ir(&ir).expect("emit scalar do-while");

    assert!(rust.contains("pub fn do_countdown(mut value: i32) -> i32"));
    assert!(rust.contains("loop {"));
    assert!(
        rust.contains("value = value.checked_sub(1i32).expect(\"signed subtraction overflow\");")
    );
    assert!(rust.contains("if !(value != 0i32) {"));
    assert!(rust.contains("break;"));
    assert!(rust.contains("return value;"));
    assert_rust_snippet_compiles("typed-ir-scalar-do-while", &rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_do_while_continue_checks_condition_before_continuing() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "do_skip_large".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::DoWhile {
                body: vec![
                    IrStmt::Assign {
                        target: ir_var("value", i32_ty.clone()),
                        value: ir_binary(
                            IrBinOp::Sub,
                            ir_var("value", i32_ty.clone()),
                            ir_lit(1, "1", i32_ty.clone()),
                            i32_ty.clone(),
                        ),
                        source_span: None,
                    },
                    IrStmt::If {
                        condition: ir_binary(
                            IrBinOp::Gt,
                            ir_var("value", i32_ty.clone()),
                            ir_lit(3, "3", i32_ty.clone()),
                            i32_ty.clone(),
                        ),
                        then_body: vec![IrStmt::Continue { source_span: None }],
                        else_body: vec![],
                        source_span: None,
                    },
                    IrStmt::Assign {
                        target: ir_var("value", i32_ty.clone()),
                        value: ir_binary(
                            IrBinOp::Sub,
                            ir_var("value", i32_ty.clone()),
                            ir_lit(1, "1", i32_ty.clone()),
                            i32_ty.clone(),
                        ),
                        source_span: None,
                    },
                ],
                condition: ir_var("value", i32_ty.clone()),
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("value", i32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let rust = emit_rust_from_ir(&ir).expect("emit do-while continue");

    assert!(rust.contains("pub fn do_skip_large(mut value: i32) -> i32"));
    assert!(rust.contains(
        "if (value > 3i32) {\n            if !(value != 0i32) {\n                break;\n            }\n            continue;"
    ));
    assert_eq!(rust.matches("if !(value != 0i32) {").count(), 2, "{rust:?}");
    assert_rust_snippet_compiles("typed-ir-do-while-continue", &rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_for_emits_continue_after_step_in_body() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "sum_skip".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "limit".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::Decl {
                name: "total".to_string(),
                ty: i32_ty.clone(),
                init: Some(ir_lit(0, "0", i32_ty.clone())),
                source_span: None,
            },
            IrStmt::For {
                init: vec![IrStmt::Decl {
                    name: "i".to_string(),
                    ty: i32_ty.clone(),
                    init: Some(ir_lit(0, "0", i32_ty.clone())),
                    source_span: None,
                }],
                condition: Some(ir_binary(
                    IrBinOp::Lt,
                    ir_var("i", i32_ty.clone()),
                    ir_var("limit", i32_ty.clone()),
                    i32_ty.clone(),
                )),
                step: Some(Box::new(IrStmt::Assign {
                    target: ir_var("i", i32_ty.clone()),
                    value: ir_binary(
                        IrBinOp::Add,
                        ir_var("i", i32_ty.clone()),
                        ir_lit(1, "1", i32_ty.clone()),
                        i32_ty.clone(),
                    ),
                    source_span: None,
                })),
                body: vec![
                    IrStmt::If {
                        condition: ir_binary(
                            IrBinOp::Gt,
                            ir_var("i", i32_ty.clone()),
                            ir_lit(3, "3", i32_ty.clone()),
                            i32_ty.clone(),
                        ),
                        then_body: vec![IrStmt::Continue { source_span: None }],
                        else_body: vec![],
                        source_span: None,
                    },
                    IrStmt::Assign {
                        target: ir_var("total", i32_ty.clone()),
                        value: ir_binary(
                            IrBinOp::Add,
                            ir_var("total", i32_ty.clone()),
                            ir_var("i", i32_ty.clone()),
                            i32_ty.clone(),
                        ),
                        source_span: None,
                    },
                ],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("total", i32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let rust = emit_rust_from_ir(&ir).expect("emit for continue with step");

    assert!(rust.contains("pub fn sum_skip(limit: i32) -> i32"));
    assert!(rust.contains("if (i > 3i32) {"));
    assert!(
        rust.contains("            if (i > 3i32) {\n                i = i.checked_add(1i32).expect(\"signed addition overflow\");\n                continue;\n            }"),
        "{rust:?}"
    );
    assert_eq!(
        rust.matches("i = i.checked_add(1i32).expect(\"signed addition overflow\");")
            .count(),
        2,
        "{rust:?}"
    );
    assert_rust_snippet_compiles("typed-ir-for-continue-step", &rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_for_nested_while_continue_does_not_emit_outer_step() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "nested_continue".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "limit".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::For {
                init: vec![IrStmt::Decl {
                    name: "i".to_string(),
                    ty: i32_ty.clone(),
                    init: Some(ir_lit(0, "0", i32_ty.clone())),
                    source_span: None,
                }],
                condition: Some(ir_binary(
                    IrBinOp::Lt,
                    ir_var("i", i32_ty.clone()),
                    ir_var("limit", i32_ty.clone()),
                    i32_ty.clone(),
                )),
                step: Some(Box::new(IrStmt::Assign {
                    target: ir_var("i", i32_ty.clone()),
                    value: ir_binary(
                        IrBinOp::Add,
                        ir_var("i", i32_ty.clone()),
                        ir_lit(1, "1", i32_ty.clone()),
                        i32_ty.clone(),
                    ),
                    source_span: None,
                })),
                body: vec![IrStmt::While {
                    condition: ir_var("limit", i32_ty.clone()),
                    body: vec![IrStmt::Continue { source_span: None }],
                    source_span: None,
                }],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_lit(0, "0", i32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let rust = emit_rust_from_ir(&ir).expect("emit nested while continue in for body");

    assert_eq!(
        rust.matches("i = i.checked_add(1i32).expect(\"signed addition overflow\");")
            .count(),
        1,
        "{rust:?}"
    );
    assert!(
        rust.contains("while limit != 0i32 {\n                continue;\n            }"),
        "{rust:?}"
    );
    assert_rust_snippet_compiles("typed-ir-for-nested-while-continue", &rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_continue_outside_loop() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "bad_continue".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::Continue { source_span: None },
            IrStmt::Return {
                value: Some(ir_var("value", i32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("top-level continue must fail closed");

    assert!(error.reason.contains("continue outside loop"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_while_with_unsupported_condition_expr() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "bad_while_call".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "count".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::While {
                condition: IrExpr::Call {
                    callee: "helper".to_string(),
                    args: vec![],
                    ty: i32_ty.clone(),
                    source_span: None,
                },
                body: vec![IrStmt::Assign {
                    target: ir_var("count", i32_ty.clone()),
                    value: ir_var("count", i32_ty.clone()),
                    source_span: None,
                }],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("count", i32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("while call condition must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("stmt[0].while condition"));
    assert!(error
        .reason
        .contains("call expression helper is unsupported"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_while_with_incdec_condition_expr() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "bad_while_incdec".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "count".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::While {
                condition: IrExpr::IncDec {
                    target: Box::new(ir_var("count", i32_ty.clone())),
                    op: IrIncDecOp::Dec,
                    prefix: false,
                    ty: i32_ty.clone(),
                    source_span: None,
                },
                body: vec![IrStmt::Assign {
                    target: ir_var("count", i32_ty.clone()),
                    value: ir_var("count", i32_ty.clone()),
                    source_span: None,
                }],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("count", i32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("while incdec condition must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("stmt[0].while condition"));
    assert!(error.reason.contains("inc/dec expression is unsupported"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_while_with_non_var_assignment_target() {
    let i32_ty = ir_i32();
    let pointer_ty = ir_pointer("int *", "int *", i32_ty.clone(), false);
    let ir = IrFunction {
        name: "bad_while_target".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "count".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::While {
                condition: ir_var("count", i32_ty.clone()),
                body: vec![IrStmt::Assign {
                    target: IrExpr::Deref {
                        ptr: Box::new(ir_var("ptr", pointer_ty)),
                        ty: i32_ty.clone(),
                        source_span: None,
                    },
                    value: ir_lit(1, "1", i32_ty.clone()),
                    source_span: None,
                }],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("count", i32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("while non-var assignment must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("stmt[0].while body[0]"));
    assert!(error
        .reason
        .contains("deref assignment pointer ptr is not declared"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_while_body_decl_scope_leak() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "bad_while_scope".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "count".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::While {
                condition: ir_var("count", i32_ty.clone()),
                body: vec![IrStmt::Decl {
                    name: "tmp".to_string(),
                    ty: i32_ty.clone(),
                    init: Some(ir_lit(1, "1", i32_ty.clone())),
                    source_span: None,
                }],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("tmp", i32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("while body decl must not leak");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("var tmp is not declared"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_scalar_if_else_with_integer_condition() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "adjust".to_string(),
        return_type: i32_ty.clone(),
        params: vec![
            IrParam {
                name: "value".to_string(),
                ty: i32_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "flag".to_string(),
                ty: i32_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![
            IrStmt::If {
                condition: ir_var("flag", i32_ty.clone()),
                then_body: vec![IrStmt::Assign {
                    target: ir_var("value", i32_ty.clone()),
                    value: ir_binary(
                        IrBinOp::Add,
                        ir_var("value", i32_ty.clone()),
                        ir_lit(1, "1", i32_ty.clone()),
                        i32_ty.clone(),
                    ),
                    source_span: None,
                }],
                else_body: vec![IrStmt::Assign {
                    target: ir_var("value", i32_ty.clone()),
                    value: ir_binary(
                        IrBinOp::Add,
                        ir_var("value", i32_ty.clone()),
                        ir_bitnot(ir_lit(0, "0", i32_ty.clone()), i32_ty.clone()),
                        i32_ty.clone(),
                    ),
                    source_span: None,
                }],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("value", i32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let rust = emit_rust_from_ir(&ir).expect("emit scalar if");

    assert!(rust.contains("pub fn adjust(mut value: i32, flag: i32) -> i32"));
    assert!(rust.contains("if flag != 0i32 {"));
    assert!(rust.contains("value = value.checked_add(1i32).expect(\"signed addition overflow\");"));
    assert!(rust.contains("} else {"));
    assert!(rust.contains("value = value.checked_add(!0i32).expect(\"signed addition overflow\");"));
    assert!(rust.contains("return value;"));
    assert_rust_snippet_compiles("typed-ir-scalar-if", &rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_scalar_if_with_comparison_condition() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "adjust_positive".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::If {
                condition: ir_binary(
                    IrBinOp::Gt,
                    ir_var("value", i32_ty.clone()),
                    ir_lit(0, "0", i32_ty.clone()),
                    i32_ty.clone(),
                ),
                then_body: vec![IrStmt::Assign {
                    target: ir_var("value", i32_ty.clone()),
                    value: ir_binary(
                        IrBinOp::Add,
                        ir_var("value", i32_ty.clone()),
                        ir_lit(1, "1", i32_ty.clone()),
                        i32_ty.clone(),
                    ),
                    source_span: None,
                }],
                else_body: vec![],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("value", i32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let rust = emit_rust_from_ir(&ir).expect("emit scalar if comparison condition");

    assert!(rust.contains("pub fn adjust_positive(mut value: i32) -> i32"));
    assert!(rust.contains("if (value > 0i32) {"));
    assert!(rust.contains("value = value.checked_add(1i32).expect(\"signed addition overflow\");"));
    assert!(rust.contains("return value;"));
    assert_rust_snippet_compiles("typed-ir-scalar-if-comparison", &rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_comparison_condition_with_integral_cast_operand() {
    let i32_ty = ir_i32();
    let u32_ty = ir_u32();
    let ir = IrFunction {
        name: "cmp_condition_cast".to_string(),
        return_type: u32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: u32_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::If {
                condition: ir_binary(
                    IrBinOp::Gt,
                    ir_var("value", u32_ty.clone()),
                    IrExpr::Cast {
                        target: u32_ty.clone(),
                        expr: Box::new(ir_lit(0, "0", i32_ty.clone())),
                        implicit: true,
                        source_span: None,
                    },
                    i32_ty.clone(),
                ),
                then_body: vec![IrStmt::Assign {
                    target: ir_var("value", u32_ty.clone()),
                    value: ir_binary(
                        IrBinOp::Add,
                        ir_var("value", u32_ty.clone()),
                        ir_lit(1, "1", u32_ty.clone()),
                        u32_ty.clone(),
                    ),
                    source_span: None,
                }],
                else_body: vec![],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("value", u32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let rust = emit_rust_from_ir(&ir).expect("emit comparison integral cast operand");

    assert!(rust.contains("pub fn cmp_condition_cast(mut value: u32) -> u32"));
    assert!(rust.contains("if (value > (0i32 as u32)) {"));
    assert!(rust.contains("value = value.wrapping_add(1u32);"));
    assert!(rust.contains("return value;"));
    assert_rust_snippet_compiles("typed-ir-comparison-condition-cast", &rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_all_scalar_comparison_conditions_without_integer_truthiness_wrap() {
    let cases = vec![
        (IrBinOp::Lt, "<", "lt"),
        (IrBinOp::Le, "<=", "le"),
        (IrBinOp::Gt, ">", "gt"),
        (IrBinOp::Ge, ">=", "ge"),
        (IrBinOp::Eq, "==", "eq"),
        (IrBinOp::Neq, "!=", "neq"),
    ];

    for (op, expected, suffix) in cases {
        let i32_ty = ir_i32();
        let ir = IrFunction {
            name: format!("cmp_{suffix}"),
            return_type: i32_ty.clone(),
            params: vec![IrParam {
                name: "value".to_string(),
                ty: i32_ty.clone(),
                source_span: None,
            }],
            body: vec![
                IrStmt::If {
                    condition: ir_binary(
                        op,
                        ir_var("value", i32_ty.clone()),
                        ir_lit(0, "0", i32_ty.clone()),
                        i32_ty.clone(),
                    ),
                    then_body: vec![IrStmt::Assign {
                        target: ir_var("value", i32_ty.clone()),
                        value: ir_binary(
                            IrBinOp::Add,
                            ir_var("value", i32_ty.clone()),
                            ir_lit(1, "1", i32_ty.clone()),
                            i32_ty.clone(),
                        ),
                        source_span: None,
                    }],
                    else_body: vec![],
                    source_span: None,
                },
                IrStmt::Return {
                    value: Some(ir_var("value", i32_ty.clone())),
                    source_span: None,
                },
            ],
            source_span: None,
        };

        let rust = emit_rust_from_ir(&ir).expect("emit scalar comparison condition");

        assert!(rust.contains(&format!("if (value {expected} 0i32) {{")));
        assert!(!rust.contains(&format!("(value {expected} 0i32) != 0i32")));
        assert_rust_snippet_compiles(&format!("typed-ir-scalar-if-comparison-{suffix}"), &rust);
    }
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_scalar_while_with_comparison_condition() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "countdown_positive".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::While {
                condition: ir_binary(
                    IrBinOp::Gt,
                    ir_var("value", i32_ty.clone()),
                    ir_lit(0, "0", i32_ty.clone()),
                    i32_ty.clone(),
                ),
                body: vec![IrStmt::Assign {
                    target: ir_var("value", i32_ty.clone()),
                    value: ir_binary(
                        IrBinOp::Add,
                        ir_var("value", i32_ty.clone()),
                        ir_bitnot(ir_lit(0, "0", i32_ty.clone()), i32_ty.clone()),
                        i32_ty.clone(),
                    ),
                    source_span: None,
                }],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("value", i32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let rust = emit_rust_from_ir(&ir).expect("emit scalar while comparison condition");

    assert!(rust.contains("pub fn countdown_positive(mut value: i32) -> i32"));
    assert!(rust.contains("while (value > 0i32) {"));
    assert!(!rust.contains("(value > 0i32) != 0i32"));
    assert!(rust.contains("value = value.checked_add(!0i32).expect(\"signed addition overflow\");"));
    assert_rust_snippet_compiles("typed-ir-scalar-while-comparison", &rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_scalar_if_with_logical_not_integer_condition() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "is_zero".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::If {
                condition: ir_not(ir_var("value", i32_ty.clone()), i32_ty.clone()),
                then_body: vec![IrStmt::Return {
                    value: Some(ir_lit(1, "1", i32_ty.clone())),
                    source_span: None,
                }],
                else_body: vec![],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_lit(0, "0", i32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let rust = emit_rust_from_ir(&ir).expect("emit scalar if logical not condition");

    assert!(rust.contains("pub fn is_zero(value: i32) -> i32"));
    assert!(rust.contains("if value == 0i32 {"));
    assert!(rust.contains("return 1i32;"));
    assert!(rust.contains("return 0i32;"));
    assert_rust_snippet_compiles("typed-ir-scalar-if-logical-not", &rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_logical_not_condition_with_readonly_pointer_add_index_deref_operand() {
    let i32_ty = ir_i32();
    let usize_ty = ir_usize();
    let u8_ty = ir_u8();
    let const_u8_ty = ir_const(u8_ty.clone());
    let const_u8_ptr_ty = ir_pointer("const uint8_t *", "uint8_t *", const_u8_ty, false);
    let ptr_plus_index = ir_binary(
        IrBinOp::Add,
        ir_var("p", const_u8_ptr_ty.clone()),
        ir_var("i", usize_ty.clone()),
        const_u8_ptr_ty.clone(),
    );
    let ir = IrFunction {
        name: "offset_is_zero_not_condition".to_string(),
        return_type: i32_ty.clone(),
        params: vec![
            IrParam {
                name: "p".to_string(),
                ty: const_u8_ptr_ty,
                source_span: None,
            },
            IrParam {
                name: "i".to_string(),
                ty: usize_ty,
                source_span: None,
            },
        ],
        body: vec![
            IrStmt::If {
                condition: ir_not(ir_deref(ptr_plus_index, u8_ty), i32_ty.clone()),
                then_body: vec![IrStmt::Return {
                    value: Some(ir_lit(1, "1", i32_ty.clone())),
                    source_span: None,
                }],
                else_body: vec![],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_lit(0, "0", i32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let rust = emit_rust_from_ir(&ir).expect("emit logical not offset deref condition");

    assert!(rust.contains("pub fn offset_is_zero_not_condition(p: &[u8], i: usize) -> i32"));
    assert!(rust.contains("if p[i as usize] == 0u8 {"));
    assert!(rust.contains("return 1i32;"));
    assert!(rust.contains("return 0i32;"));
    assert_rust_snippet_compiles("typed-ir-offset-deref-logical-not-condition", &rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_logical_not_condition_with_readonly_pointer_add_compound_index_deref_operand() {
    let i32_ty = ir_i32();
    let usize_ty = ir_usize();
    let u8_ty = ir_u8();
    let const_u8_ty = ir_const(u8_ty.clone());
    let const_u8_ptr_ty = ir_pointer("const uint8_t *", "uint8_t *", const_u8_ty, false);
    let compound_index = ir_binary(
        IrBinOp::Add,
        ir_var("i", usize_ty.clone()),
        ir_lit(1, "1", usize_ty.clone()),
        usize_ty.clone(),
    );
    let ptr_plus_compound = ir_binary(
        IrBinOp::Add,
        ir_var("p", const_u8_ptr_ty.clone()),
        compound_index,
        const_u8_ptr_ty.clone(),
    );
    let ir = IrFunction {
        name: "bad_logical_not_offset_compound_index".to_string(),
        return_type: i32_ty.clone(),
        params: vec![
            IrParam {
                name: "p".to_string(),
                ty: const_u8_ptr_ty,
                source_span: None,
            },
            IrParam {
                name: "i".to_string(),
                ty: usize_ty,
                source_span: None,
            },
        ],
        body: vec![
            IrStmt::If {
                condition: ir_not(ir_deref(ptr_plus_compound, u8_ty), i32_ty.clone()),
                then_body: vec![IrStmt::Return {
                    value: Some(ir_lit(1, "1", i32_ty.clone())),
                    source_span: None,
                }],
                else_body: vec![],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_lit(0, "0", i32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error =
        emit_rust_from_ir(&ir).expect_err("compound index logical-not deref must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("stmt[0].if condition"));
    assert!(error.reason.contains("logical not operand"));
    assert!(error
        .reason
        .contains("deref pointer add index cannot use compound expression"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_scalar_while_with_logical_not_integer_condition() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "bump_until_nonzero".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::While {
                condition: ir_not(ir_var("value", i32_ty.clone()), i32_ty.clone()),
                body: vec![IrStmt::Assign {
                    target: ir_var("value", i32_ty.clone()),
                    value: ir_binary(
                        IrBinOp::Add,
                        ir_var("value", i32_ty.clone()),
                        ir_lit(1, "1", i32_ty.clone()),
                        i32_ty.clone(),
                    ),
                    source_span: None,
                }],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("value", i32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let rust = emit_rust_from_ir(&ir).expect("emit scalar while logical not condition");

    assert!(rust.contains("pub fn bump_until_nonzero(mut value: i32) -> i32"));
    assert!(rust.contains("while value == 0i32 {"));
    assert!(rust.contains("value = value.checked_add(1i32).expect(\"signed addition overflow\");"));
    assert!(rust.contains("return value;"));
    assert_rust_snippet_compiles("typed-ir-scalar-while-logical-not", &rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_scalar_if_with_logical_not_comparison_condition() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "clamp_nonpositive".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::If {
                condition: ir_not(
                    ir_binary(
                        IrBinOp::Gt,
                        ir_var("value", i32_ty.clone()),
                        ir_lit(0, "0", i32_ty.clone()),
                        i32_ty.clone(),
                    ),
                    i32_ty.clone(),
                ),
                then_body: vec![IrStmt::Return {
                    value: Some(ir_lit(0, "0", i32_ty.clone())),
                    source_span: None,
                }],
                else_body: vec![],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("value", i32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let rust = emit_rust_from_ir(&ir).expect("emit scalar if logical not comparison condition");

    assert!(rust.contains("pub fn clamp_nonpositive(value: i32) -> i32"));
    assert!(rust.contains("if (value <= 0i32) {"));
    assert!(!rust.contains("!(value > 0i32)"));
    assert!(!rust.contains("(value > 0i32) == 0i32"));
    assert!(rust.contains("return 0i32;"));
    assert!(rust.contains("return value;"));
    assert_rust_snippet_compiles("typed-ir-scalar-if-logical-not-comparison", &rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_comparison_return_value_as_c_int() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "positive_as_int".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(ir_binary(
                IrBinOp::Gt,
                ir_var("value", i32_ty.clone()),
                ir_lit(0, "0", i32_ty.clone()),
                i32_ty.clone(),
            )),
            source_span: None,
        }],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit comparison return value as C int");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub fn positive_as_int(value: i32) -> i32"));
    assert!(rust.contains("return (if (value > 0i32) { 1i32 } else { 0i32 });"));
    assert!(!rust.contains("return (value > 0i32);"));
    assert_rust_snippet_compiles("typed-ir-comparison-return-value", rust);
}
