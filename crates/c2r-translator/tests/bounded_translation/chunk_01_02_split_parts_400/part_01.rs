#[cfg(feature = "typed-ir")]
fn flashdb_crc32_typed_ir() -> IrFunction {
    let u32_ty = ir_u32();
    let u8_ty = ir_u8();
    let usize_ty = ir_usize();
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
        true,
    );

    let crc = || ir_var("crc", u32_ty.clone());
    let p = || ir_var("p", const_u8_ptr.clone());
    let size = || ir_var("size", usize_ty.clone());
    let crc32_table = || IrExpr::Var {
        name: "crc32_table".to_string(),
        ty: IrType {
            spelled: "const uint32_t[256]".to_string(),
            canonical: "const unsigned int[256]".to_string(),
            kind: IrTypeKind::Array {
                element: Box::new(u32_ty.clone()),
                len: Some(256),
            },
            is_const: true,
            width_bits: None,
            source_span: None,
        },
        source_span: None,
    };

    let post_inc_p = IrExpr::IncDec {
        target: Box::new(p()),
        op: IrIncDecOp::Inc,
        prefix: false,
        ty: const_u8_ptr.clone(),
        source_span: None,
    };
    let byte_read = IrExpr::Deref {
        ptr: Box::new(post_inc_p),
        ty: u8_ty.clone(),
        source_span: None,
    };
    let promoted_byte = IrExpr::Cast {
        target: u32_ty.clone(),
        expr: Box::new(byte_read),
        implicit: true,
        source_span: None,
    };
    let table_index = ir_binary(
        IrBinOp::BitAnd,
        ir_binary(IrBinOp::BitXor, crc(), promoted_byte, u32_ty.clone()),
        ir_lit(0xFF, "0xFFU", u32_ty.clone()),
        u32_ty.clone(),
    );
    let table_lookup = IrExpr::Index {
        base: Box::new(crc32_table()),
        index: Box::new(table_index),
        ty: u32_ty.clone(),
        source_span: None,
    };
    let shift = ir_binary(
        IrBinOp::Shr,
        crc(),
        ir_lit(8, "8U", u32_ty.clone()),
        u32_ty.clone(),
    );

    IrFunction {
        name: "fdb_calc_crc32".to_string(),
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
            IrParam {
                name: "size".to_string(),
                ty: usize_ty.clone(),
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
                target: p(),
                value: IrExpr::Cast {
                    target: const_u8_ptr.clone(),
                    expr: Box::new(ir_var("buf", const_void_ptr)),
                    implicit: false,
                    source_span: None,
                },
                source_span: None,
            },
            IrStmt::Assign {
                target: crc(),
                value: ir_binary(
                    IrBinOp::BitXor,
                    crc(),
                    ir_bitnot(ir_lit(0, "0U", u32_ty.clone()), u32_ty.clone()),
                    u32_ty.clone(),
                ),
                source_span: None,
            },
            IrStmt::While {
                condition: IrExpr::IncDec {
                    target: Box::new(size()),
                    op: IrIncDecOp::Dec,
                    prefix: false,
                    ty: usize_ty,
                    source_span: None,
                },
                body: vec![IrStmt::Assign {
                    target: crc(),
                    value: ir_binary(IrBinOp::BitXor, table_lookup, shift, u32_ty.clone()),
                    source_span: None,
                }],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_binary(
                    IrBinOp::BitXor,
                    crc(),
                    ir_bitnot(ir_lit(0, "0U", u32_ty.clone()), u32_ty.clone()),
                    u32_ty,
                )),
                source_span: None,
            },
        ],
        source_span: None,
    }
}

#[cfg(feature = "typed-ir")]
fn ir_u32_global_array(name: &str, len: usize, values: Vec<u64>) -> IrGlobal {
    let u32_ty = ir_u32();
    IrGlobal {
        name: name.to_string(),
        ty: IrType {
            spelled: format!("const uint32_t[{len}]"),
            canonical: format!("const unsigned int[{len}]"),
            kind: IrTypeKind::Array {
                element: Box::new(u32_ty),
                len: Some(len),
            },
            is_const: true,
            width_bits: None,
            source_span: None,
        },
        init: if values.iter().all(|value| *value == 0) {
            IrGlobalInit::Zeroed
        } else {
            IrGlobalInit::IntegerArray(values)
        },
        source_span: None,
    }
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn repeated_c_u32_initializer(len: usize, value: &str) -> String {
    std::iter::repeat_n(value, len)
        .collect::<Vec<_>>()
        .join(", ")
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_flashdb_crc32_without_readonly_global_table() {
    let error = emit_rust_from_ir(&flashdb_crc32_typed_ir())
        .expect_err("crc32 typed IR without a modeled readonly global table must fail closed");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert_eq!(error.route.candidate_generator, CandidateGenerator::None);
    assert!(!error.route.deprecated);
    assert!(error.reason.contains("crc32_table"));
    assert!(error.reason.contains("not declared"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_flashdb_crc32_with_readonly_global_table_as_generic_route() {
    let global = ir_u32_global_array("crc32_table", 256, vec![0; 256]);
    let emitted = emit_rust_from_ir_with_globals(&flashdb_crc32_typed_ir(), &[global])
        .expect("emit flashdb crc32 through generic typed IR with global table");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(!emitted.route.deprecated);
    assert!(rust.contains("const CRC32_TABLE: [u32; 256] = [0u32; 256];"));
    assert!(
        rust.contains("pub fn fdb_calc_crc32(mut crc: u32, buf: &[u8], mut size: usize) -> u32")
    );
    assert!(rust.contains("let byte0: u8 = buf[p];"));
    assert!(rust.contains("p += 1;"));
    assert!(rust.contains(
        "crc = (CRC32_TABLE[((crc ^ (byte0 as u32)) & 255u32) as usize] ^ crc.checked_shr(core::convert::TryFrom::try_from(8u32).expect(\"shift count must be nonnegative and fit u32\")).expect(\"shift count out of range\"));"
    ));
    assert!(!rust.contains("crc32_update_byte"));
    assert_rust_snippet_compiles("typed-ir-crc32-global-table-generic", rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_readonly_global_array_initializer_length_mismatch() {
    let global = ir_u32_global_array("table", 4, vec![1, 2]);
    let ir = IrFunction {
        name: "return_zero".to_string(),
        return_type: ir_u32(),
        params: vec![],
        body: vec![IrStmt::Return {
            value: Some(ir_lit(0, "0U", ir_u32())),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir_with_globals(&ir, &[global])
        .expect_err("global initializer length mismatch must fail closed");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(error
        .reason
        .contains("initializer length 2 does not match array length 4"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_record_value_field_read() {
    let point_ty = ir_record("point");
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "point_x".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "p".to_string(),
            ty: point_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(IrExpr::Member {
                base: Box::new(ir_var("p", point_ty)),
                field: "x".to_string(),
                ty: i32_ty,
                is_arrow: false,
                source_span: None,
            }),
            source_span: None,
        }],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit by-value record field read");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("#[derive(Clone, Copy, Debug, Eq, PartialEq)]"));
    assert!(rust.contains("pub struct Point"));
    assert!(rust.contains("pub x: i32"));
    assert!(rust.contains("pub fn point_x(p: Point) -> i32"));
    assert!(rust.contains("return p.x;"));
    assert_rust_snippet_compiles("typed-ir-record-value-field-read", rust);
}
