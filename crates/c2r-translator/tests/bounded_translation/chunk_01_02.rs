#[cfg(feature = "typed-ir")]
fn ir_record(name: &str) -> IrType {
    IrType {
        spelled: format!("struct {name}"),
        canonical: format!("struct {name}"),
        kind: IrTypeKind::Record {
            name: name.to_string(),
            fields: None,
        },
        is_const: false,
        width_bits: None,
        source_span: None,
    }
}

#[cfg(feature = "typed-ir")]
fn ir_record_with_fields(name: &str, fields: Vec<(&str, IrType)>) -> IrType {
    IrType {
        spelled: format!("struct {name}"),
        canonical: format!("struct {name}"),
        kind: IrTypeKind::Record {
            name: name.to_string(),
            fields: Some(
                fields
                    .into_iter()
                    .map(|(name, ty)| IrRecordField {
                        name: name.to_string(),
                        ty,
                    })
                    .collect(),
            ),
        },
        is_const: false,
        width_bits: None,
        source_span: None,
    }
}

#[cfg(feature = "typed-ir")]
fn ir_var(name: &str, ty: IrType) -> IrExpr {
    IrExpr::Var {
        name: name.to_string(),
        ty,
        source_span: None,
    }
}

#[cfg(feature = "typed-ir")]
fn ir_null_ptr(ty: IrType) -> IrExpr {
    IrExpr::NullPtr {
        ty,
        source_span: None,
    }
}

#[cfg(feature = "typed-ir")]
fn ir_lit(value: u64, spelling: &str, ty: IrType) -> IrExpr {
    IrExpr::LitInt {
        value,
        spelling: spelling.to_string(),
        ty,
        source_span: None,
    }
}

#[cfg(feature = "typed-ir")]
fn ir_array(element: IrType, len: usize) -> IrType {
    IrType {
        spelled: format!("{}[{len}]", element.spelled),
        canonical: format!("{}[{len}]", element.canonical),
        kind: IrTypeKind::Array {
            element: Box::new(element),
            len: Some(len),
        },
        is_const: false,
        width_bits: None,
        source_span: None,
    }
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn without_implicit_cast(expr: &IrExpr) -> &IrExpr {
    match expr {
        IrExpr::Cast {
            expr,
            implicit: true,
            ..
        } => without_implicit_cast(expr),
        _ => expr,
    }
}

#[cfg(feature = "typed-ir")]
fn ir_binary(op: IrBinOp, lhs: IrExpr, rhs: IrExpr, ty: IrType) -> IrExpr {
    IrExpr::Binary {
        op,
        lhs: Box::new(lhs),
        rhs: Box::new(rhs),
        ty,
        source_span: None,
    }
}

#[cfg(feature = "typed-ir")]
fn ir_conditional(condition: IrExpr, then_expr: IrExpr, else_expr: IrExpr, ty: IrType) -> IrExpr {
    IrExpr::Conditional {
        condition: Box::new(condition),
        then_expr: Box::new(then_expr),
        else_expr: Box::new(else_expr),
        ty,
        source_span: None,
    }
}

#[cfg(feature = "typed-ir")]
fn ir_deref(ptr: IrExpr, ty: IrType) -> IrExpr {
    IrExpr::Deref {
        ptr: Box::new(ptr),
        ty,
        source_span: None,
    }
}

#[cfg(feature = "typed-ir")]
fn ir_bitnot(expr: IrExpr, ty: IrType) -> IrExpr {
    IrExpr::Unary {
        op: IrUnOp::BitNot,
        operand: Box::new(expr),
        ty,
        source_span: None,
    }
}

#[cfg(feature = "typed-ir")]
fn ir_neg(expr: IrExpr, ty: IrType) -> IrExpr {
    IrExpr::Unary {
        op: IrUnOp::Neg,
        operand: Box::new(expr),
        ty,
        source_span: None,
    }
}

#[cfg(feature = "typed-ir")]
fn ir_not(expr: IrExpr, ty: IrType) -> IrExpr {
    IrExpr::Unary {
        op: IrUnOp::Not,
        operand: Box::new(expr),
        ty,
        source_span: None,
    }
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_replays_control_flow_refusals_without_clang() {
    let ast: Value = serde_json::from_str(include_str!(
        "../../fixtures/clang_ast/control_flow_refusals_ast.json"
    ))
    .expect("fixture JSON");

    for (function_name, expected_reason, expected_range) in [
        (
            "label_refusal",
            "unsupported control-flow LabelStmt",
            "source_range=2:3-2:15",
        ),
        (
            "goto_refusal",
            "unsupported control-flow GotoStmt",
            "source_range=5:3-5:12",
        ),
        (
            "switch_refusal",
            "unsupported control-flow SwitchStmt",
            "source_range=8:3-8:48",
        ),
        (
            "case_refusal",
            "unsupported control-flow CaseStmt",
            "source_range=11:3-11:18",
        ),
        (
            "default_refusal",
            "unsupported control-flow DefaultStmt",
            "source_range=14:3-14:18",
        ),
    ] {
        let error = lower_function_and_globals_from_clang_ast_json_value(&ast, function_name)
            .expect_err("control-flow fixture must fail closed during clang AST lowering");
        assert_eq!(error.kind, "unsupported_clang_stmt");
        assert!(
            error.message.contains(expected_reason),
            "expected {function_name} refusal to contain {expected_reason:?}, got {:?}",
            error.message
        );
        assert!(
            error
                .message
                .contains("requires structured CFG/relooper support"),
            "expected {function_name} refusal to mention CFG/relooper support, got {:?}",
            error.message
        );
        assert!(
            error.message.contains(expected_range),
            "expected {function_name} refusal to contain {expected_range:?}, got {:?}",
            error.message
        );
    }
}
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
