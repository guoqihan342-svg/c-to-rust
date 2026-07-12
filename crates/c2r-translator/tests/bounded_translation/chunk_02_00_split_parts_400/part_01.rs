#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_record_return_value_with_mismatched_field_inventory() {
    let return_ty = ir_record_with_fields("point", vec![("x", ir_i32()), ("y", ir_i32())]);
    let value_ty = ir_record_with_fields("point", vec![("x", ir_i32())]);
    let ir = IrFunction {
        name: "identity_point".to_string(),
        return_type: return_ty,
        params: vec![IrParam {
            name: "p".to_string(),
            ty: value_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(ir_var("p", value_ty)),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir)
        .expect_err("same-name records with different field inventory must fail closed");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(error.reason.contains("field inventory"), "{:?}", error);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_readonly_record_pointer_arrow_field_read() {
    let point_ty = ir_record("point");
    let point_ptr_ty = ir_pointer(
        "const struct point *",
        "const struct point *",
        ir_const(point_ty.clone()),
        false,
    );
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "point_x".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "p".to_string(),
            ty: point_ptr_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(IrExpr::Member {
                base: Box::new(ir_var("p", point_ptr_ty)),
                field: "x".to_string(),
                ty: i32_ty,
                is_arrow: true,
                source_span: None,
            }),
            source_span: None,
        }],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit readonly record pointer field read");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub struct Point"), "{rust}");
    assert!(rust.contains("pub x: i32"), "{rust}");
    assert!(rust.contains("pub fn point_x(p: &Point) -> i32"), "{rust}");
    assert!(rust.contains("return p.x;"), "{rust}");
    assert_rust_snippet_compiles("typed-ir-readonly-record-pointer-arrow-field-read", rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_record_arrow_field_assignment() {
    let point_ty = ir_record("point");
    let point_ptr_ty = ir_pointer(
        "const struct point *",
        "const struct point *",
        ir_const(point_ty),
        false,
    );
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "set_point_x".to_string(),
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
                    base: Box::new(ir_var("p", point_ptr_ty)),
                    field: "x".to_string(),
                    ty: i32_ty.clone(),
                    is_arrow: true,
                    source_span: None,
                },
                value: ir_var("value", i32_ty.clone()),
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_lit(0, "0", i32_ty)),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("record pointer member write must fail closed");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(error.reason.contains("arrow member assignment"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_mutable_record_pointer_arrow_field_assignment() {
    let i32_ty = ir_i32();
    let point_ty =
        ir_record_with_fields("point", vec![("x", i32_ty.clone()), ("y", i32_ty.clone())]);
    let point_ptr_ty = ir_pointer("struct point *", "struct point *", point_ty, false);
    let ir = IrFunction {
        name: "set_point_x".to_string(),
        return_type: ir_void(),
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
        body: vec![IrStmt::Assign {
            target: IrExpr::Member {
                base: Box::new(ir_var("p", point_ptr_ty)),
                field: "x".to_string(),
                ty: i32_ty.clone(),
                is_arrow: true,
                source_span: None,
            },
            value: ir_var("value", i32_ty),
            source_span: None,
        }],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit mutable record pointer field assignment");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub struct Point"), "{rust}");
    assert!(rust.contains("pub x: i32"), "{rust}");
    assert!(rust.contains("pub y: i32"), "{rust}");
    assert!(
        rust.contains("pub fn set_point_x(mut p: &mut Point, value: i32)"),
        "{rust}"
    );
    assert!(rust.contains("p.x = value;"), "{rust}");
    assert_rust_snippet_compiles("typed-ir-mutable-record-pointer-field-assignment", rust);
}
