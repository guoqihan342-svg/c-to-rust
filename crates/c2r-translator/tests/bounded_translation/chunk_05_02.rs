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
