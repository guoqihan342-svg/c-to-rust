#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_mutable_record_pointer_arrow_field_compound_assignment_complex_rhs() {
    let i32_ty = ir_i32();
    let point_ty = ir_record_with_fields("point", vec![("x", i32_ty.clone())]);
    let point_ptr_ty = ir_pointer("struct point *", "struct point *", point_ty, false);
    let field_target = IrExpr::Member {
        base: Box::new(ir_var("p", point_ptr_ty.clone())),
        field: "x".to_string(),
        ty: i32_ty.clone(),
        is_arrow: true,
        source_span: None,
    };
    let ir = IrFunction {
        name: "bad_add_point_x".to_string(),
        return_type: ir_void(),
        params: vec![
            IrParam {
                name: "p".to_string(),
                ty: point_ptr_ty,
                source_span: None,
            },
            IrParam {
                name: "value".to_string(),
                ty: i32_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![IrStmt::Assign {
            target: field_target.clone(),
            value: ir_binary(
                IrBinOp::Add,
                field_target,
                ir_binary(
                    IrBinOp::Add,
                    ir_var("value", i32_ty.clone()),
                    ir_lit(1, "1", i32_ty.clone()),
                    i32_ty.clone(),
                ),
                i32_ty,
            ),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir)
        .expect_err("mutable record pointer field compound assignment complex RHS must fail");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(
        error
            .reason
            .contains("mutable record pointer field compound assignment RHS"),
        "{:?}",
        error
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_mutable_record_pointer_arrow_field_read_after_assignment() {
    let i32_ty = ir_i32();
    let point_ty =
        ir_record_with_fields("point", vec![("x", i32_ty.clone()), ("y", i32_ty.clone())]);
    let point_ptr_ty = ir_pointer("struct point *", "struct point *", point_ty, false);
    let ir = IrFunction {
        name: "set_then_read_point_x".to_string(),
        return_type: i32_ty.clone(),
        params: vec![
            IrParam {
                name: "p".to_string(),
                ty: point_ptr_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "value".to_string(),
                ty: i32_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![
            IrStmt::Assign {
                target: IrExpr::Member {
                    base: Box::new(ir_var("p", point_ptr_ty.clone())),
                    field: "x".to_string(),
                    ty: i32_ty.clone(),
                    is_arrow: true,
                    source_span: None,
                },
                value: ir_var("value", i32_ty.clone()),
                source_span: None,
            },
            IrStmt::Return {
                value: Some(IrExpr::Member {
                    base: Box::new(ir_var("p", point_ptr_ty)),
                    field: "x".to_string(),
                    ty: i32_ty.clone(),
                    is_arrow: true,
                    source_span: None,
                }),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let emitted =
        emit_rust_from_ir(&ir).expect("emit mutable record pointer field read after assignment");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub struct Point"), "{rust}");
    assert!(rust.contains("pub x: i32"), "{rust}");
    assert!(rust.contains("pub y: i32"), "{rust}");
    assert!(
        rust.contains("pub fn set_then_read_point_x(mut p: &mut Point, value: i32) -> i32"),
        "{rust}"
    );
    assert!(rust.contains("p.x = value;"), "{rust}");
    assert!(rust.contains("return p.x;"), "{rust}");
    assert_rust_snippet_compiles(
        "typed-ir-mutable-record-pointer-field-read-after-write",
        rust,
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_typedef_record_pointer_identity_return() {
    let i32_ty = ir_i32();
    let point_ty = ir_record_with_fields("point", vec![("x", i32_ty.clone())]);
    let point_ptr_ty = ir_pointer("struct point *", "struct point *", point_ty.clone(), false);
    let point_typedef_return_ty = ir_pointer("point_t", "struct point *", point_ty, false);
    let ir = IrFunction {
        name: "set_point_x_typedef_return".to_string(),
        return_type: point_typedef_return_ty,
        params: vec![
            IrParam {
                name: "p".to_string(),
                ty: point_ptr_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "value".to_string(),
                ty: i32_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![
            IrStmt::Assign {
                target: IrExpr::Member {
                    base: Box::new(ir_var("p", point_ptr_ty.clone())),
                    field: "x".to_string(),
                    ty: i32_ty.clone(),
                    is_arrow: true,
                    source_span: None,
                },
                value: ir_var("value", i32_ty),
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("p", point_ptr_ty)),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let emitted =
        emit_rust_from_ir(&ir).expect("emit typedef-spelled mutable record pointer return");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(
        rust.contains("pub fn set_point_x_typedef_return(mut p: &mut Point, value: i32) -> &mut Point"),
        "{rust}"
    );
    assert!(rust.contains("p.x = value;"), "{rust}");
    assert!(rust.contains("return p;"), "{rust}");
    assert_rust_snippet_compiles("typed-ir-typedef-record-pointer-identity-return", rust);
}

#[cfg(feature = "typed-ir")]
fn nested_record_pointer_scalar_field_copy_ir() -> IrFunction {
    let u32_ty = ir_u32();
    let saved_ty = ir_record_with_fields(
        "blob_saved",
        vec![
            ("meta_addr", u32_ty.clone()),
            ("addr", u32_ty.clone()),
            ("len", u32_ty.clone()),
        ],
    );
    let blob_ty = ir_record_with_fields("blob", vec![("saved", saved_ty.clone())]);
    let blob_ptr_ty = ir_pointer("struct blob *", "struct blob *", blob_ty, false);
    let kv_addr_ty = ir_record_with_fields(
        "kv_addr",
        vec![("start", u32_ty.clone()), ("value", u32_ty.clone())],
    );
    let kv_ty = ir_record_with_fields(
        "kv",
        vec![
            ("addr", kv_addr_ty.clone()),
            ("value_len", u32_ty.clone()),
        ],
    );
    let kv_ptr_ty = ir_pointer(
        "const struct kv *",
        "const struct kv *",
        ir_const(kv_ty),
        false,
    );
    IrFunction {
        name: "copy_nested_blob_saved".to_string(),
        return_type: blob_ptr_ty.clone(),
        params: vec![
            IrParam {
                name: "kv".to_string(),
                ty: kv_ptr_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "blob".to_string(),
                ty: blob_ptr_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![
            IrStmt::Assign {
                target: IrExpr::Member {
                    base: Box::new(IrExpr::Member {
                        base: Box::new(ir_var("blob", blob_ptr_ty.clone())),
                        field: "saved".to_string(),
                        ty: saved_ty.clone(),
                        is_arrow: true,
                        source_span: None,
                    }),
                    field: "meta_addr".to_string(),
                    ty: u32_ty.clone(),
                    is_arrow: false,
                    source_span: None,
                },
                value: IrExpr::Member {
                    base: Box::new(IrExpr::Member {
                        base: Box::new(ir_var("kv", kv_ptr_ty.clone())),
                        field: "addr".to_string(),
                        ty: kv_addr_ty,
                        is_arrow: true,
                        source_span: None,
                    }),
                    field: "start".to_string(),
                    ty: u32_ty.clone(),
                    is_arrow: false,
                    source_span: None,
                },
                source_span: None,
            },
            IrStmt::Assign {
                target: IrExpr::Member {
                    base: Box::new(IrExpr::Member {
                        base: Box::new(ir_var("blob", blob_ptr_ty.clone())),
                        field: "saved".to_string(),
                        ty: saved_ty,
                        is_arrow: true,
                        source_span: None,
                    }),
                    field: "len".to_string(),
                    ty: u32_ty.clone(),
                    is_arrow: false,
                    source_span: None,
                },
                value: IrExpr::Member {
                    base: Box::new(ir_var("kv", kv_ptr_ty.clone())),
                    field: "value_len".to_string(),
                    ty: u32_ty,
                    is_arrow: true,
                    source_span: None,
                },
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("blob", blob_ptr_ty)),
                source_span: None,
            },
        ],
        source_span: None,
    }
}
