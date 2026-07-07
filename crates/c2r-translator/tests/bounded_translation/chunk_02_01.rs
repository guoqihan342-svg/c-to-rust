#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_mutable_record_pointer_identity_return_after_field_write() {
    let usize_ty = ir_usize();
    let blob_ty = ir_record_with_fields("blob", vec![("size", usize_ty.clone())]);
    let blob_ptr_ty = ir_pointer("struct blob *", "struct blob *", blob_ty, false);
    let ir = IrFunction {
        name: "set_blob_size".to_string(),
        return_type: blob_ptr_ty.clone(),
        params: vec![
            IrParam {
                name: "blob".to_string(),
                ty: blob_ptr_ty.clone(),
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
        .expect("emit mutable record pointer identity return after field write");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub struct Blob"), "{rust}");
    assert!(rust.contains("pub size: usize"), "{rust}");
    assert!(
        rust.contains("pub fn set_blob_size(mut blob: &mut Blob, len: usize) -> &mut Blob"),
        "{rust}"
    );
    assert!(rust.contains("blob.size = len;"), "{rust}");
    assert!(rust.contains("return blob;"), "{rust}");
    assert_rust_snippet_compiles("typed-ir-mutable-record-pointer-identity-return", rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_mutable_record_pointer_opaque_pointer_field_write() {
    let usize_ty = ir_usize();
    let const_void_ptr_ty = ir_pointer("const void *", "void *", ir_const(ir_void()), false);
    let blob_ty = ir_record_with_fields(
        "blob",
        vec![
            ("buf", const_void_ptr_ty.clone()),
            ("size", usize_ty.clone()),
        ],
    );
    let blob_ptr_ty = ir_pointer("struct blob *", "struct blob *", blob_ty, false);
    let ir = IrFunction {
        name: "set_blob_buf".to_string(),
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
                    ty: const_void_ptr_ty.clone(),
                    is_arrow: true,
                    source_span: None,
                },
                value: ir_var("value", const_void_ptr_ty),
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

    let emitted =
        emit_rust_from_ir(&ir).expect("emit opaque pointer field write on mutable record pointer");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub buf: *const core::ffi::c_void"), "{rust}");
    assert!(
        rust.contains(
            "pub fn set_blob_buf(mut blob: &mut Blob, value: *const core::ffi::c_void, len: usize) -> &mut Blob"
        ),
        "{rust}"
    );
    assert!(rust.contains("blob.buf = value;"), "{rust}");
    assert!(rust.contains("blob.size = len;"), "{rust}");
    assert!(rust.contains("return blob;"), "{rust}");
    assert_rust_snippet_compiles("typed-ir-mutable-record-pointer-opaque-pointer-field", rust);
}
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
