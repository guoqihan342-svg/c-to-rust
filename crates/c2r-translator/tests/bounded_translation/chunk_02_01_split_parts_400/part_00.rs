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
