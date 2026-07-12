#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_nullable_record_pointer_arrow_field_read_in_nonnull_branch() {
    let i32_ty = ir_i32();
    let point_ty = ir_record_with_fields("point", vec![("x", i32_ty.clone())]);
    let ptr_ty = ir_pointer(
        "const struct point *",
        "const struct point *",
        ir_const(point_ty),
        false,
    );
    let ir = IrFunction {
        name: "point_x_if_present".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "p".to_string(),
            ty: ptr_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::If {
                condition: ir_binary(
                    IrBinOp::Neq,
                    ir_var("p", ptr_ty.clone()),
                    ir_null_ptr(ptr_ty.clone()),
                    i32_ty.clone(),
                ),
                then_body: vec![IrStmt::Return {
                    value: Some(IrExpr::Member {
                        base: Box::new(ir_var("p", ptr_ty)),
                        field: "x".to_string(),
                        ty: i32_ty.clone(),
                        is_arrow: true,
                        source_span: None,
                    }),
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

    let emitted =
        emit_rust_from_ir(&ir).expect("emit nullable record pointer field read in nonnull branch");
    let rust = &emitted.rust;

    assert!(
        rust.contains("pub fn point_x_if_present(p: Option<&Point>) -> i32"),
        "{rust}"
    );
    assert!(rust.contains("if p.is_some() {"), "{rust}");
    assert!(rust.contains("return p.unwrap().x;"), "{rust}");
    assert!(rust.contains("return 0i32;"), "{rust}");
    assert_rust_snippet_compiles(
        "typed-ir-nullable-record-pointer-nonnull-branch-field-read",
        rust,
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_nullable_record_pointer_arrow_field_read_without_null_guard() {
    let i32_ty = ir_i32();
    let point_ty = ir_record_with_fields("point", vec![("x", i32_ty.clone())]);
    let ptr_ty = ir_pointer(
        "const struct point *",
        "const struct point *",
        ir_const(point_ty),
        false,
    );
    let ir = IrFunction {
        name: "bad_point_x".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "p".to_string(),
            ty: ptr_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::If {
                condition: ir_binary(
                    IrBinOp::Eq,
                    ir_var("p", ptr_ty.clone()),
                    ir_null_ptr(ptr_ty.clone()),
                    i32_ty.clone(),
                ),
                then_body: vec![],
                else_body: vec![],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(IrExpr::Member {
                    base: Box::new(ir_var("p", ptr_ty)),
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

    let error =
        emit_rust_from_ir(&ir).expect_err("nullable record pointer field read must need guard");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(error
        .reason
        .contains("nullable pointer param p is only supported in null comparisons"));
}
#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_nullable_record_pointer_arrow_field_read_in_null_branch() {
    let i32_ty = ir_i32();
    let point_ty = ir_record_with_fields("point", vec![("x", i32_ty.clone())]);
    let ptr_ty = ir_pointer(
        "const struct point *",
        "const struct point *",
        ir_const(point_ty),
        false,
    );
    let ir = IrFunction {
        name: "bad_null_branch_point_x".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "p".to_string(),
            ty: ptr_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::If {
                condition: ir_binary(
                    IrBinOp::Eq,
                    ir_var("p", ptr_ty.clone()),
                    ir_null_ptr(ptr_ty.clone()),
                    i32_ty.clone(),
                ),
                then_body: vec![IrStmt::Return {
                    value: Some(IrExpr::Member {
                        base: Box::new(ir_var("p", ptr_ty)),
                        field: "x".to_string(),
                        ty: i32_ty.clone(),
                        is_arrow: true,
                        source_span: None,
                    }),
                    source_span: None,
                }],
                else_body: vec![IrStmt::Return {
                    value: Some(ir_lit(0, "0", i32_ty.clone())),
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

    let error = emit_rust_from_ir(&ir).expect_err("null branch must not allow nullable field read");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(error
        .reason
        .contains("nullable pointer param p is only supported in null comparisons"));
}
