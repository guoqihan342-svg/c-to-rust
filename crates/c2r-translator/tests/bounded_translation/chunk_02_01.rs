#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_mutable_record_pointer_opaque_pointer_field_cast_write() {
    let usize_ty = ir_usize();
    let const_void_ptr_ty = ir_pointer("const void *", "void *", ir_const(ir_void()), false);
    let mut_void_ptr_ty = ir_pointer("void *", "void *", ir_void(), false);
    let blob_ty = ir_record_with_fields(
        "blob",
        vec![("buf", mut_void_ptr_ty.clone()), ("size", usize_ty.clone())],
    );
    let blob_ptr_ty = ir_pointer("struct blob *", "struct blob *", blob_ty, false);
    let ir = IrFunction {
        name: "make_blob".to_string(),
        return_type: blob_ptr_ty.clone(),
        params: vec![
            IrParam {
                name: "blob".to_string(),
                ty: blob_ptr_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "value".to_string(),
                ty: const_void_ptr_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "len".to_string(),
                ty: usize_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![
            IrStmt::Assign {
                target: IrExpr::Member {
                    base: Box::new(ir_var("blob", blob_ptr_ty.clone())),
                    field: "buf".to_string(),
                    ty: mut_void_ptr_ty.clone(),
                    is_arrow: true,
                    source_span: None,
                },
                value: IrExpr::Cast {
                    target: mut_void_ptr_ty,
                    expr: Box::new(ir_var("value", const_void_ptr_ty)),
                    implicit: false,
                    source_span: None,
                },
                source_span: None,
            },
            IrStmt::Assign {
                target: IrExpr::Member {
                    base: Box::new(ir_var("blob", blob_ptr_ty.clone())),
                    field: "size".to_string(),
                    ty: usize_ty.clone(),
                    is_arrow: true,
                    source_span: None,
                },
                value: ir_var("len", usize_ty),
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("blob", blob_ptr_ty)),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir)
        .expect("emit opaque pointer cast field write on mutable record pointer");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub buf: *mut core::ffi::c_void"), "{rust}");
    assert!(rust.contains("value: *const core::ffi::c_void"), "{rust}");
    assert!(
        rust.contains("blob.buf = (value as *mut core::ffi::c_void);"),
        "{rust}"
    );
    assert!(rust.contains("return blob;"), "{rust}");
    assert_rust_snippet_compiles(
        "typed-ir-mutable-record-pointer-opaque-pointer-cast-field",
        rust,
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_mutable_record_pointer_opaque_pointer_field_read() {
    let const_void_ptr_ty = ir_pointer("const void *", "void *", ir_const(ir_void()), false);
    let blob_ty = ir_record_with_fields("blob", vec![("buf", const_void_ptr_ty.clone())]);
    let blob_ptr_ty = ir_pointer("struct blob *", "struct blob *", blob_ty, false);
    let ir = IrFunction {
        name: "read_blob_buf".to_string(),
        return_type: ir_void(),
        params: vec![
            IrParam {
                name: "blob".to_string(),
                ty: blob_ptr_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "value".to_string(),
                ty: const_void_ptr_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![
            IrStmt::Assign {
                target: IrExpr::Member {
                    base: Box::new(ir_var("blob", blob_ptr_ty.clone())),
                    field: "buf".to_string(),
                    ty: const_void_ptr_ty.clone(),
                    is_arrow: true,
                    source_span: None,
                },
                value: ir_var("value", const_void_ptr_ty.clone()),
                source_span: None,
            },
            IrStmt::Expr {
                expr: IrExpr::Member {
                    base: Box::new(ir_var("blob", blob_ptr_ty)),
                    field: "buf".to_string(),
                    ty: const_void_ptr_ty,
                    is_arrow: true,
                    source_span: None,
                },
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error =
        emit_rust_from_ir(&ir).expect_err("opaque pointer record fields are write-only for now");
    assert!(
        error
            .reason
            .contains("pointer type const void * is unsupported")
            || error.reason.contains("opaque pointer"),
        "{:?}",
        error
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_integer_to_opaque_pointer_field_cast_write() {
    let i32_ty = ir_i32();
    let mut_void_ptr_ty = ir_pointer("void *", "void *", ir_void(), false);
    let blob_ty = ir_record_with_fields("blob", vec![("buf", mut_void_ptr_ty.clone())]);
    let blob_ptr_ty = ir_pointer("struct blob *", "struct blob *", blob_ty, false);
    let ir = IrFunction {
        name: "bad_blob_buf_cast".to_string(),
        return_type: ir_void(),
        params: vec![
            IrParam {
                name: "blob".to_string(),
                ty: blob_ptr_ty.clone(),
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
                base: Box::new(ir_var("blob", blob_ptr_ty)),
                field: "buf".to_string(),
                ty: mut_void_ptr_ty.clone(),
                is_arrow: true,
                source_span: None,
            },
            value: IrExpr::Cast {
                target: mut_void_ptr_ty,
                expr: Box::new(ir_var("value", i32_ty)),
                implicit: false,
                source_span: None,
            },
            source_span: None,
        }],
        source_span: None,
    };

    let error =
        emit_rust_from_ir(&ir).expect_err("integer-to-opaque-pointer cast must fail closed");
    assert!(
        error
            .reason
            .contains("opaque pointer cast source int is unsupported"),
        "{:?}",
        error
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_mutable_record_pointer_identity_return_without_field_write() {
    let i32_ty = ir_i32();
    let point_ty = ir_record_with_fields("point", vec![("x", i32_ty)]);
    let point_ptr_ty = ir_pointer("struct point *", "struct point *", point_ty, false);
    let ir = IrFunction {
        name: "return_point".to_string(),
        return_type: point_ptr_ty.clone(),
        params: vec![IrParam {
            name: "p".to_string(),
            ty: point_ptr_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(ir_var("p", point_ptr_ty)),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir)
        .expect_err("pointer identity return still needs mutable record pointer evidence");
    assert!(
        error.reason.contains(
            "mutable record pointer return p requires mutable record pointer ownership evidence"
        ) || error
            .reason
            .contains("param p has pointer type struct point * is unsupported"),
        "{:?}",
        error
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_mutable_record_pointer_arrow_field_assignment_with_multiple_pointer_params() {
    let i32_ty = ir_i32();
    let point_ty = ir_record_with_fields("point", vec![("x", i32_ty.clone())]);
    let point_ptr_ty = ir_pointer("struct point *", "struct point *", point_ty, false);
    let ir = IrFunction {
        name: "bad_aliased_set_point_x".to_string(),
        return_type: ir_void(),
        params: vec![
            IrParam {
                name: "p".to_string(),
                ty: point_ptr_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "q".to_string(),
                ty: point_ptr_ty.clone(),
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
            value: ir_lit(1, "1", i32_ty),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir)
        .expect_err("mutable record pointer field assignment needs alias proof");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(
        error
            .reason
            .contains("requires exactly one pointer param for alias proof"),
        "{:?}",
        error
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_mutable_record_pointer_arrow_non_scalar_field_assignment() {
    let i32_ty = ir_i32();
    let child_ty = ir_record_with_fields("child", vec![("value", i32_ty.clone())]);
    let point_ty = ir_record_with_fields("point", vec![("child", child_ty.clone())]);
    let point_ptr_ty = ir_pointer("struct point *", "struct point *", point_ty, false);
    let ir = IrFunction {
        name: "bad_set_point_child".to_string(),
        return_type: ir_void(),
        params: vec![IrParam {
            name: "p".to_string(),
            ty: point_ptr_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Assign {
            target: IrExpr::Member {
                base: Box::new(ir_var("p", point_ptr_ty)),
                field: "child".to_string(),
                ty: child_ty.clone(),
                is_arrow: true,
                source_span: None,
            },
            value: ir_var("child", child_ty),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir)
        .expect_err("mutable record pointer field assignment must require scalar field");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(
        error.reason.contains(
            "mutable record pointer arrow field child has record type child is unsupported"
        ),
        "{:?}",
        error
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_nullable_mutable_record_pointer_arrow_field_assignment() {
    let i32_ty = ir_i32();
    let point_ty = ir_record_with_fields("point", vec![("x", i32_ty.clone())]);
    let point_ptr_ty = ir_pointer("struct point *", "struct point *", point_ty, false);
    let ir = IrFunction {
        name: "bad_nullable_set_point_x".to_string(),
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
        body: vec![
            IrStmt::If {
                condition: ir_binary(
                    IrBinOp::Eq,
                    ir_var("p", point_ptr_ty.clone()),
                    ir_null_ptr(point_ptr_ty.clone()),
                    i32_ty.clone(),
                ),
                then_body: vec![IrStmt::Return {
                    value: None,
                    source_span: None,
                }],
                else_body: vec![],
                source_span: None,
            },
            IrStmt::Assign {
                target: IrExpr::Member {
                    base: Box::new(ir_var("p", point_ptr_ty)),
                    field: "x".to_string(),
                    ty: i32_ty.clone(),
                    is_arrow: true,
                    source_span: None,
                },
                value: ir_var("value", i32_ty),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir)
        .expect_err("nullable mutable record pointer field assignment must fail closed");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(
        error.reason.contains("comparison pointer operand")
            || error
                .reason
                .contains("comparison lhs has pointer type struct point *")
            || error
                .reason
                .contains("nullable pointer param p has unsupported type"),
        "{:?}",
        error
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_mutable_record_pointer_arrow_field_compound_assignment_shape() {
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
        name: "add_point_x".to_string(),
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
                ir_var("value", i32_ty.clone()),
                i32_ty,
            ),
            source_span: None,
        }],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir)
        .expect("emit mutable record pointer compound field assignment shape");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub struct Point"), "{rust}");
    assert!(rust.contains("pub x: i32"), "{rust}");
    assert!(
        rust.contains("pub fn add_point_x(mut p: &mut Point, value: i32)"),
        "{rust}"
    );
    assert!(
        rust.contains("p.x = p.x.checked_add(value).expect(\"signed addition overflow\");"),
        "{rust}"
    );
    assert_rust_snippet_compiles(
        "typed-ir-mutable-record-pointer-field-compound-assignment",
        rust,
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_mutable_record_pointer_arrow_field_inc_dec_desugar_shape() {
    let i32_ty = ir_i32();
    let point_ty = ir_record_with_fields("point", vec![("x", i32_ty.clone())]);
    let point_ptr_ty = ir_pointer("struct point *", "struct point *", point_ty, false);
    let inc_target = IrExpr::Member {
        base: Box::new(ir_var("p", point_ptr_ty.clone())),
        field: "x".to_string(),
        ty: i32_ty.clone(),
        is_arrow: true,
        source_span: None,
    };
    let dec_target = IrExpr::Member {
        base: Box::new(ir_var("p", point_ptr_ty.clone())),
        field: "x".to_string(),
        ty: i32_ty.clone(),
        is_arrow: true,
        source_span: None,
    };
    let ir = IrFunction {
        name: "bump_point_x".to_string(),
        return_type: ir_void(),
        params: vec![IrParam {
            name: "p".to_string(),
            ty: point_ptr_ty,
            source_span: None,
        }],
        body: vec![
            IrStmt::Assign {
                target: inc_target.clone(),
                value: ir_binary(
                    IrBinOp::Add,
                    inc_target,
                    ir_lit(1, "1", i32_ty.clone()),
                    i32_ty.clone(),
                ),
                source_span: None,
            },
            IrStmt::Assign {
                target: dec_target.clone(),
                value: ir_binary(
                    IrBinOp::Sub,
                    dec_target,
                    ir_lit(1, "1", i32_ty.clone()),
                    i32_ty,
                ),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let emitted =
        emit_rust_from_ir(&ir).expect("emit mutable record pointer field inc/dec desugar shape");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub struct Point"), "{rust}");
    assert!(rust.contains("pub x: i32"), "{rust}");
    assert!(
        rust.contains("pub fn bump_point_x(mut p: &mut Point)"),
        "{rust}"
    );
    assert!(
        rust.contains("p.x = p.x.checked_add(1i32).expect(\"signed addition overflow\");"),
        "{rust}"
    );
    assert!(
        rust.contains("p.x = p.x.checked_sub(1i32).expect(\"signed subtraction overflow\");"),
        "{rust}"
    );
    assert_rust_snippet_compiles(
        "typed-ir-mutable-record-pointer-field-inc-dec-desugar",
        rust,
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_mutable_record_pointer_arrow_field_raw_inc_dec_expr() {
    let i32_ty = ir_i32();
    let point_ty = ir_record_with_fields("point", vec![("x", i32_ty.clone())]);
    let point_ptr_ty = ir_pointer("struct point *", "struct point *", point_ty, false);
    let ir = IrFunction {
        name: "bad_raw_bump_point_x".to_string(),
        return_type: ir_void(),
        params: vec![IrParam {
            name: "p".to_string(),
            ty: point_ptr_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::Assign {
                target: IrExpr::Member {
                    base: Box::new(ir_var("p", point_ptr_ty.clone())),
                    field: "x".to_string(),
                    ty: i32_ty.clone(),
                    is_arrow: true,
                    source_span: None,
                },
                value: ir_lit(0, "0", i32_ty.clone()),
                source_span: None,
            },
            IrStmt::Expr {
                expr: IrExpr::IncDec {
                    target: Box::new(IrExpr::Member {
                        base: Box::new(ir_var("p", point_ptr_ty.clone())),
                        field: "x".to_string(),
                        ty: i32_ty.clone(),
                        is_arrow: true,
                        source_span: None,
                    }),
                    op: IrIncDecOp::Inc,
                    prefix: false,
                    ty: i32_ty,
                    source_span: None,
                },
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir)
        .expect_err("raw mutable record pointer field inc/dec expression must fail closed");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(
        error.reason.contains("inc/dec expression is unsupported"),
        "{}",
        error.reason
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_prefix_inc_statement_for_i32_scalar() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "prefix_inc_i32".to_string(),
        return_type: ir_void(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Expr {
            expr: IrExpr::IncDec {
                target: Box::new(ir_var("value", i32_ty.clone())),
                op: IrIncDecOp::Inc,
                prefix: true,
                ty: i32_ty.clone(),
                source_span: None,
            },
            source_span: None,
        }],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit prefix inc statement for i32 scalar");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub fn prefix_inc_i32(mut value: i32)"));
    assert!(rust.contains("value = value.checked_add(1i32).expect(\"signed addition overflow\");"));
    assert_rust_snippet_compiles("typed-ir-prefix-inc-i32", rust);
}
