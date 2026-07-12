#[cfg(feature = "typed-ir")]
fn mutable_byte_pointer_index_reader_ir() -> IrFunction {
    let u8_ty = ir_u8();
    let usize_ty = ir_usize();
    let pointer_ty = ir_pointer("uint8_t *", "unsigned char *", u8_ty.clone(), false);
    IrFunction {
        name: "read_mutable_byte_at".to_string(),
        return_type: u8_ty.clone(),
        params: vec![
            IrParam {
                name: "value".to_string(),
                ty: pointer_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "index".to_string(),
                ty: usize_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![IrStmt::Return {
            value: Some(IrExpr::Index {
                base: Box::new(ir_var("value", pointer_ty)),
                index: Box::new(ir_var("index", usize_ty)),
                ty: u8_ty,
                source_span: None,
            }),
            source_span: None,
        }],
        source_span: None,
    }
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_body_proven_readonly_mutable_pointer_index_as_shared_slice() {
    let emitted = emit_rust_from_ir(&mutable_byte_pointer_index_reader_ir())
        .expect("emit body-proven readonly mutable pointer index");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(
        rust.contains("pub fn read_mutable_byte_at(value: &[u8], index: usize) -> u8"),
        "{rust}"
    );
    assert!(rust.contains("return value[index as usize];"), "{rust}");
    assert_rust_snippet_compiles("typed-ir-readonly-mutable-pointer-index", rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_mutable_pointer_with_index_read_and_call_escape() {
    let mut ir = mutable_byte_pointer_index_reader_ir();
    let pointer_ty = ir.params[0].ty.clone();
    let void_ty = ir_void();
    ir.body.insert(
        0,
        IrStmt::Expr {
            expr: IrExpr::Call {
                callee: "consume".to_string(),
                args: vec![ir_var("value", pointer_ty)],
                ty: void_ty,
                source_span: None,
            },
            source_span: None,
        },
    );

    let error = emit_rust_from_ir(&ir).expect_err("escaped pointer must fail closed");
    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(error.reason.contains("pointer type"), "{}", error.reason);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_readonly_mutable_pointer_beside_write_without_noalias() {
    let mut ir = mutable_byte_pointer_index_reader_ir();
    let u8_ty = ir_u8();
    let out_ty = ir_pointer("uint8_t *", "unsigned char *", u8_ty.clone(), false);
    ir.params.push(IrParam {
        name: "out".to_string(),
        ty: out_ty.clone(),
        source_span: None,
    });
    ir.body.insert(
        0,
        IrStmt::Assign {
            target: IrExpr::Index {
                base: Box::new(ir_var("out", out_ty)),
                index: Box::new(ir_lit(0, "0", ir_i32())),
                ty: u8_ty.clone(),
                source_span: None,
            },
            value: ir_lit(1, "1", u8_ty),
            source_span: None,
        },
    );

    let error = emit_rust_from_ir(&ir).expect_err("missing noalias must fail closed");
    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(
        error.reason.contains("requires noalias proof"),
        "{}",
        error.reason
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_readonly_mutable_pointer_beside_write_with_noalias() {
    let mut ir = mutable_byte_pointer_index_reader_ir();
    let u8_ty = ir_u8();
    let out_ty = ir_pointer("uint8_t *", "unsigned char *", u8_ty.clone(), false);
    ir.params.push(IrParam {
        name: "out".to_string(),
        ty: out_ty.clone(),
        source_span: None,
    });
    ir.body.insert(
        0,
        IrStmt::Assign {
            target: IrExpr::Index {
                base: Box::new(ir_var("out", out_ty)),
                index: Box::new(ir_lit(0, "0", ir_i32())),
                ty: u8_ty.clone(),
                source_span: None,
            },
            value: ir_lit(1, "1", u8_ty),
            source_span: None,
        },
    );
    let policy = EmitPolicy {
        noalias_param_pairs: vec![NoAliasParamPair {
            readonly_param: "value".to_string(),
            mutable_param: "out".to_string(),
        }],
        ..EmitPolicy::default()
    };

    let emitted = emit_rust_from_ir_with_globals_and_policy(&ir, &[], policy)
        .expect("explicit noalias permits shared input beside mutable output");
    let rust = &emitted.rust;
    assert!(rust.contains("value: &[u8]"), "{rust}");
    assert!(rust.contains("mut out: &mut [u8]"), "{rust}");
    assert_rust_snippet_compiles("typed-ir-readonly-mutable-pointer-noalias", rust);
}

#[cfg(feature = "typed-ir")]
fn direct_record_array_member(
    base_name: &str,
    pointer_ty: IrType,
    field: &str,
    array_ty: IrType,
) -> IrExpr {
    IrExpr::Member {
        base: Box::new(ir_var(base_name, pointer_ty)),
        field: field.to_string(),
        ty: array_ty,
        is_arrow: true,
        source_span: None,
    }
}

#[cfg(feature = "typed-ir")]
fn direct_record_array_index(
    base_name: &str,
    pointer_ty: IrType,
    field: &str,
    array_ty: IrType,
    index: IrExpr,
    element_ty: IrType,
) -> IrExpr {
    IrExpr::Index {
        base: Box::new(direct_record_array_member(
            base_name, pointer_ty, field, array_ty,
        )),
        index: Box::new(index),
        ty: element_ty,
        source_span: None,
    }
}

#[cfg(feature = "typed-ir")]
fn renamed_record_array_lookup_ir() -> IrFunction {
    let u32_ty = ir_u32();
    let usize_ty = ir_usize();
    let array_ty = ir_array(u32_ty.clone(), 5);
    let record_ty = ir_record_with_fields(
        "RenamedBucket",
        vec![("codes", array_ty.clone()), ("payloads", array_ty.clone())],
    );
    let pointer_ty = ir_pointer(
        "struct RenamedBucket *",
        "struct RenamedBucket *",
        record_ty,
        false,
    );
    let position = ir_var("position", usize_ty.clone());
    let code = direct_record_array_index(
        "entry",
        pointer_ty.clone(),
        "codes",
        array_ty.clone(),
        position.clone(),
        u32_ty.clone(),
    );
    let payload = direct_record_array_index(
        "entry",
        pointer_ty.clone(),
        "payloads",
        array_ty,
        position,
        u32_ty.clone(),
    );
    IrFunction {
        name: "lookup_renamed_cell".to_string(),
        return_type: u32_ty.clone(),
        params: vec![
            IrParam {
                name: "entry".to_string(),
                ty: pointer_ty,
                source_span: None,
            },
            IrParam {
                name: "position".to_string(),
                ty: usize_ty,
                source_span: None,
            },
            IrParam {
                name: "needle".to_string(),
                ty: u32_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![
            IrStmt::If {
                condition: ir_binary(
                    IrBinOp::Eq,
                    code,
                    ir_var("needle", u32_ty.clone()),
                    ir_i32(),
                ),
                then_body: vec![IrStmt::Return {
                    value: Some(payload),
                    source_span: None,
                }],
                else_body: vec![],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_lit(0, "0", u32_ty)),
                source_span: None,
            },
        ],
        source_span: None,
    }
}

#[cfg(feature = "typed-ir")]
fn single_record_array_reader_ir(array_ty: IrType, element_ty: IrType) -> IrFunction {
    let usize_ty = ir_usize();
    let record_ty = ir_record_with_fields("GenericCatalog", vec![("cells", array_ty.clone())]);
    let pointer_ty = ir_pointer(
        "struct GenericCatalog *",
        "struct GenericCatalog *",
        record_ty,
        false,
    );
    IrFunction {
        name: "read_catalog_cell".to_string(),
        return_type: element_ty.clone(),
        params: vec![
            IrParam {
                name: "catalog".to_string(),
                ty: pointer_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "offset".to_string(),
                ty: usize_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![IrStmt::Return {
            value: Some(direct_record_array_index(
                "catalog",
                pointer_ty,
                "cells",
                array_ty,
                ir_var("offset", usize_ty),
                element_ty,
            )),
            source_span: None,
        }],
        source_span: None,
    }
}
