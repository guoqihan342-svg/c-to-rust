#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_mutable_record_pointer_opaque_pointer_field_copy_after_write() {
    let const_void_ptr_ty = ir_pointer("const void *", "void *", ir_const(ir_void()), false);
    let blob_ty = ir_record_with_fields(
        "blob",
        vec![
            ("buf", const_void_ptr_ty.clone()),
            ("mirror", const_void_ptr_ty.clone()),
        ],
    );
    let blob_ptr_ty = ir_pointer("struct blob *", "struct blob *", blob_ty, false);
    let ir = IrFunction {
        name: "bad_mirror_blob_buf".to_string(),
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
            IrStmt::Assign {
                target: IrExpr::Member {
                    base: Box::new(ir_var("blob", blob_ptr_ty.clone())),
                    field: "mirror".to_string(),
                    ty: const_void_ptr_ty.clone(),
                    is_arrow: true,
                    source_span: None,
                },
                value: IrExpr::Member {
                    base: Box::new(ir_var("blob", blob_ptr_ty.clone())),
                    field: "buf".to_string(),
                    ty: const_void_ptr_ty,
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
    };

    let error = emit_rust_from_ir(&ir)
        .expect_err("opaque pointer field copy after write must still fail closed");
    assert!(
        error
            .reason
            .contains("opaque pointer field blob.buf read still requires pointer provenance evidence"),
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
fn typed_ir_emits_mutable_record_pointer_arrow_field_assignment_with_unused_readonly_8_bit_pointer_param(
) {
    let i32_ty = ir_i32();
    let char_ty = ir_integer("char", "char", true, 8);
    let const_char_ptr_ty = ir_pointer("const char *", "char *", ir_const(char_ty), false);
    let point_ty = ir_record_with_fields("point", vec![("x", i32_ty.clone())]);
    let point_ptr_ty = ir_pointer("struct point *", "struct point *", point_ty, false);
    let ir = IrFunction {
        name: "set_point_x_ignoring_name".to_string(),
        return_type: ir_void(),
        params: vec![
            IrParam {
                name: "name".to_string(),
                ty: const_char_ptr_ty,
                source_span: None,
            },
            IrParam {
                name: "p".to_string(),
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

    let emitted = emit_rust_from_ir(&ir)
        .expect("unused readonly 8-bit pointer must not block record field assignment candidate");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("name: *const core::ffi::c_void"), "{rust}");
    assert!(rust.contains("mut p: &mut Point"), "{rust}");
    assert!(rust.contains("p.x = 1i32;"), "{rust}");
    assert_rust_snippet_compiles(
        "typed-ir-record-field-assignment-unused-readonly-8-bit-pointer",
        rust,
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_mutable_record_pointer_arrow_field_assignment_with_read_readonly_pointer_param(
) {
    let i32_ty = ir_i32();
    let usize_ty = ir_usize();
    let char_ty = ir_integer("char", "char", true, 8);
    let const_char_ptr_ty = ir_pointer("const char *", "char *", ir_const(char_ty), false);
    let point_ty = ir_record_with_fields("point", vec![("x", i32_ty.clone())]);
    let point_ptr_ty = ir_pointer("struct point *", "struct point *", point_ty, false);
    let ir = IrFunction {
        name: "set_point_x_and_read_name".to_string(),
        return_type: usize_ty.clone(),
        params: vec![
            IrParam {
                name: "name".to_string(),
                ty: const_char_ptr_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "p".to_string(),
                ty: point_ptr_ty.clone(),
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
                value: ir_lit(1, "1", i32_ty),
                source_span: None,
            },
            IrStmt::Return {
                value: Some(IrExpr::Call {
                    callee: "strlen".to_string(),
                    args: vec![ir_var("name", const_char_ptr_ty)],
                    ty: usize_ty,
                    source_span: None,
                }),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir)
        .expect_err("read readonly pointer plus record field write still needs alias proof");

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
