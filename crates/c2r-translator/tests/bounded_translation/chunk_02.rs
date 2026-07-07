#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_top_level_blob_make_pointer_return_expression() {
    let mut_void_ptr_ty = ir_pointer("void *", "void *", ir_void(), false);
    let const_void_ptr_ty = ir_pointer("const void *", "void *", ir_const(ir_void()), false);
    let usize_ty = ir_usize();
    let blob_ty = ir_record_with_fields(
        "fdb_blob",
        vec![("buf", mut_void_ptr_ty.clone()), ("size", usize_ty.clone())],
    );
    let blob_ptr_ty = ir_pointer(
        "struct fdb_blob *",
        "struct fdb_blob *",
        blob_ty.clone(),
        false,
    );
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "return_blob_make_as_i32".to_string(),
        return_type: i32_ty,
        params: vec![
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
            IrStmt::Decl {
                name: "blob".to_string(),
                ty: blob_ty.clone(),
                init: None,
                source_span: None,
            },
            IrStmt::Return {
                value: Some(IrExpr::Call {
                    callee: "fdb_blob_make".to_string(),
                    args: vec![
                        IrExpr::AddrOf {
                            operand: Box::new(ir_var("blob", blob_ty)),
                            ty: blob_ptr_ty.clone(),
                            source_span: None,
                        },
                        ir_var("value", const_void_ptr_ty),
                        ir_var("len", usize_ty),
                    ],
                    ty: blob_ptr_ty,
                    source_span: None,
                }),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("top-level pointer-return call must fail closed");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(
        error
            .reason
            .contains("return expr has pointer type struct fdb_blob * is unsupported"),
        "{:?}",
        error.reason
    );
    assert!(
        error.reason.contains("struct fdb_blob *"),
        "{:?}",
        error.reason
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_blob_make_pointer_return_argument_with_unmodeled_nested_arg() {
    let mut_void_ptr_ty = ir_pointer("void *", "void *", ir_void(), false);
    let const_void_ptr_ty = ir_pointer("const void *", "void *", ir_const(ir_void()), false);
    let usize_ty = ir_usize();
    let blob_ty = ir_record_with_fields(
        "fdb_blob",
        vec![("buf", mut_void_ptr_ty.clone()), ("size", usize_ty.clone())],
    );
    let blob_ptr_ty = ir_pointer(
        "struct fdb_blob *",
        "struct fdb_blob *",
        blob_ty.clone(),
        false,
    );
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "call_kv_set_blob_with_bad_nested_len".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: const_void_ptr_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::Decl {
                name: "blob".to_string(),
                ty: blob_ty.clone(),
                init: None,
                source_span: None,
            },
            IrStmt::Return {
                value: Some(IrExpr::Call {
                    callee: "fdb_kv_set_blob".to_string(),
                    args: vec![IrExpr::Call {
                        callee: "fdb_blob_make".to_string(),
                        args: vec![
                            IrExpr::AddrOf {
                                operand: Box::new(ir_var("blob", blob_ty)),
                                ty: blob_ptr_ty.clone(),
                                source_span: None,
                            },
                            ir_var("value", const_void_ptr_ty.clone()),
                            IrExpr::Call {
                                callee: "helper_len".to_string(),
                                args: vec![ir_var("value", const_void_ptr_ty)],
                                ty: usize_ty,
                                source_span: None,
                            },
                        ],
                        ty: blob_ptr_ty,
                        source_span: None,
                    }],
                    ty: i32_ty,
                    source_span: None,
                }),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error =
        emit_rust_from_ir(&ir).expect_err("unmodeled nested constructor arg must fail closed");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(
        error
            .reason
            .contains("nested call expressions are outside the bounded call subset"),
        "{:?}",
        error.reason
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_discarded_pointer_return_call_with_non_opaque_pointer_arg() {
    let mut_void_ptr_ty = ir_pointer("void *", "void *", ir_void(), false);
    let usize_ty = ir_usize();
    let i32_ty = ir_i32();
    let int_ptr_ty = ir_pointer("const int *", "const int *", ir_const(i32_ty.clone()), true);
    let blob_ty = ir_record_with_fields(
        "fdb_blob",
        vec![("buf", mut_void_ptr_ty), ("size", usize_ty.clone())],
    );
    let blob_ptr_ty = ir_pointer(
        "struct fdb_blob *",
        "struct fdb_blob *",
        blob_ty.clone(),
        false,
    );
    let ir = IrFunction {
        name: "call_blob_make_bad_pointer_arg".to_string(),
        return_type: i32_ty.clone(),
        params: vec![],
        body: vec![
            IrStmt::Decl {
                name: "blob".to_string(),
                ty: blob_ty.clone(),
                init: None,
                source_span: None,
            },
            IrStmt::Expr {
                expr: IrExpr::Call {
                    callee: "fdb_blob_make".to_string(),
                    args: vec![
                        IrExpr::AddrOf {
                            operand: Box::new(ir_var("blob", blob_ty)),
                            ty: blob_ptr_ty.clone(),
                            source_span: None,
                        },
                        ir_lit(0, "0", int_ptr_ty),
                        ir_lit(3, "3", usize_ty),
                    ],
                    ty: blob_ptr_ty,
                    source_span: None,
                },
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_lit(0, "0", i32_ty)),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir)
        .expect_err("non-opaque pointer value args must fail closed in discarded pointer calls");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(
        error.reason.contains("call arg[1] pointer value argument"),
        "{:?}",
        error.reason
    );
    assert!(error.reason.contains("const int *"), "{:?}", error.reason);
    assert!(
        error
            .reason
            .contains("explicit ownership/lifetime/ABI lowering"),
        "{:?}",
        error.reason
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_record_return_value_without_complete_field_model() {
    let point_ty = ir_record("point");
    let ir = IrFunction {
        name: "identity_point".to_string(),
        return_type: point_ty.clone(),
        params: vec![IrParam {
            name: "p".to_string(),
            ty: point_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(ir_var("p", point_ty)),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("whole-record return must fail closed");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(error.reason.contains("record type point is unsupported"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_record_return_value_with_complete_field_inventory() {
    let point_ty = ir_record_with_fields("point", vec![("x", ir_i32()), ("y", ir_u32())]);
    let ir = IrFunction {
        name: "identity_point".to_string(),
        return_type: point_ty.clone(),
        params: vec![IrParam {
            name: "p".to_string(),
            ty: point_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(ir_var("p", point_ty)),
            source_span: None,
        }],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit whole-record return with field inventory");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub struct Point"));
    assert!(rust.contains("pub x: i32"));
    assert!(rust.contains("pub y: u32"));
    assert!(rust.contains("pub fn identity_point(p: Point) -> Point"));
    assert!(rust.contains("return p;"));
    assert_rust_snippet_compiles("typed-ir-record-return-complete-field-inventory", rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_record_return_value_with_non_scalar_field_inventory() {
    let child_ty = ir_record("child");
    let point_ty = ir_record_with_fields("point", vec![("child", child_ty)]);
    let ir = IrFunction {
        name: "identity_point".to_string(),
        return_type: point_ty.clone(),
        params: vec![IrParam {
            name: "p".to_string(),
            ty: point_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(ir_var("p", point_ty)),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir)
        .expect_err("whole-record return with non-scalar fields must fail closed");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(error
        .reason
        .contains("record point field child has record type child is unsupported"));
}

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

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_prefix_inc_value_decl_initializer_for_i32_scalar() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "prefix_inc_value_decl".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::Decl {
                name: "out".to_string(),
                ty: i32_ty.clone(),
                init: Some(IrExpr::IncDec {
                    target: Box::new(ir_var("value", i32_ty.clone())),
                    op: IrIncDecOp::Inc,
                    prefix: true,
                    ty: i32_ty.clone(),
                    source_span: None,
                }),
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_binary(
                    IrBinOp::Add,
                    ir_var("out", i32_ty.clone()),
                    ir_var("value", i32_ty.clone()),
                    i32_ty.clone(),
                )),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit prefix inc value decl initializer");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub fn prefix_inc_value_decl(mut value: i32) -> i32"));
    assert!(rust.contains("value = value.checked_add(1i32).expect(\"signed addition overflow\");"));
    assert!(rust.contains("let mut out: i32 = value;"));
    assert_rust_snippet_runs(
        "typed-ir-prefix-inc-value-decl",
        rust,
        "    assert_eq!(prefix_inc_value_decl(5), 12);",
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_postfix_inc_value_decl_initializer_for_i32_scalar() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "postfix_inc_value_decl".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::Decl {
                name: "out".to_string(),
                ty: i32_ty.clone(),
                init: Some(IrExpr::IncDec {
                    target: Box::new(ir_var("value", i32_ty.clone())),
                    op: IrIncDecOp::Inc,
                    prefix: false,
                    ty: i32_ty.clone(),
                    source_span: None,
                }),
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_binary(
                    IrBinOp::Add,
                    ir_var("out", i32_ty.clone()),
                    ir_var("value", i32_ty.clone()),
                    i32_ty.clone(),
                )),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit postfix inc value decl initializer");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub fn postfix_inc_value_decl(mut value: i32) -> i32"));
    assert!(rust.contains("let post_inc_value: i32 = value;"));
    assert!(rust.contains("value = value.checked_add(1i32).expect(\"signed addition overflow\");"));
    assert!(rust.contains("let mut out: i32 = post_inc_value;"));
    assert_rust_snippet_runs(
        "typed-ir-postfix-inc-value-decl",
        rust,
        "    assert_eq!(postfix_inc_value_decl(5), 11);",
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_prefix_dec_statement_for_usize_scalar() {
    let usize_ty = ir_usize();
    let ir = IrFunction {
        name: "prefix_dec_usize".to_string(),
        return_type: ir_void(),
        params: vec![IrParam {
            name: "count".to_string(),
            ty: usize_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Expr {
            expr: IrExpr::IncDec {
                target: Box::new(ir_var("count", usize_ty.clone())),
                op: IrIncDecOp::Dec,
                prefix: true,
                ty: usize_ty.clone(),
                source_span: None,
            },
            source_span: None,
        }],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit prefix dec statement for usize scalar");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub fn prefix_dec_usize(mut count: usize)"));
    assert!(rust.contains("count = count.wrapping_sub(1usize);"));
    assert_rust_snippet_compiles("typed-ir-prefix-dec-usize", rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_keeps_prefix_inc_dec_member_target_fail_closed() {
    let i32_ty = ir_i32();
    let point_ty = ir_record_with_fields("point", vec![("x", i32_ty.clone())]);
    let point_ptr_ty = ir_pointer("struct point *", "struct point *", point_ty, false);
    let ir = IrFunction {
        name: "prefix_inc_member".to_string(),
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
                        base: Box::new(ir_var("p", point_ptr_ty)),
                        field: "x".to_string(),
                        ty: i32_ty.clone(),
                        is_arrow: true,
                        source_span: None,
                    }),
                    op: IrIncDecOp::Inc,
                    prefix: true,
                    ty: i32_ty,
                    source_span: None,
                },
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("member target remains unsupported");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(
        error.reason.contains("inc/dec expression is unsupported"),
        "{}",
        error.reason
    );
}

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
fn typed_ir_emits_mutable_record_pointer_arrow_field_read_after_if_else_return() {
    let i32_ty = ir_i32();
    let point_ty =
        ir_record_with_fields("point", vec![("x", i32_ty.clone()), ("y", i32_ty.clone())]);
    let point_ptr_ty = ir_pointer("struct point *", "struct point *", point_ty, false);
    let ir = IrFunction {
        name: "set_then_read_point_x_if_present".to_string(),
        return_type: i32_ty.clone(),
        params: vec![
            IrParam {
                name: "p".to_string(),
                ty: point_ptr_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "cond".to_string(),
                ty: i32_ty.clone(),
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
                condition: ir_var("cond", i32_ty.clone()),
                then_body: vec![IrStmt::Assign {
                    target: IrExpr::Member {
                        base: Box::new(ir_var("p", point_ptr_ty.clone())),
                        field: "x".to_string(),
                        ty: i32_ty.clone(),
                        is_arrow: true,
                        source_span: None,
                    },
                    value: ir_var("value", i32_ty.clone()),
                    source_span: None,
                }],
                else_body: vec![IrStmt::Return {
                    value: Some(ir_lit(0, "0", i32_ty.clone())),
                    source_span: None,
                }],
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

    let emitted = emit_rust_from_ir(&ir)
        .expect("emit mutable record pointer field read after if/else-return write");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub struct Point"), "{rust}");
    assert!(
        rust.contains(
            "pub fn set_then_read_point_x_if_present(mut p: &mut Point, cond: i32, value: i32) -> i32"
        ),
        "{rust}"
    );
    assert!(rust.contains("if cond != 0i32 {"), "{rust}");
    assert!(rust.contains("p.x = value;"), "{rust}");
    assert!(rust.contains("return 0i32;"), "{rust}");
    assert!(rust.contains("return p.x;"), "{rust}");
    assert_rust_snippet_compiles(
        "typed-ir-mutable-record-pointer-field-read-after-if-return",
        rust,
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_mutable_record_pointer_arrow_field_read_after_if_then_return_else_write() {
    let i32_ty = ir_i32();
    let point_ty =
        ir_record_with_fields("point", vec![("x", i32_ty.clone()), ("y", i32_ty.clone())]);
    let point_ptr_ty = ir_pointer("struct point *", "struct point *", point_ty, false);
    let ir = IrFunction {
        name: "set_then_read_point_x_if_absent".to_string(),
        return_type: i32_ty.clone(),
        params: vec![
            IrParam {
                name: "p".to_string(),
                ty: point_ptr_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "cond".to_string(),
                ty: i32_ty.clone(),
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
                condition: ir_var("cond", i32_ty.clone()),
                then_body: vec![IrStmt::Return {
                    value: Some(ir_lit(0, "0", i32_ty.clone())),
                    source_span: None,
                }],
                else_body: vec![IrStmt::Assign {
                    target: IrExpr::Member {
                        base: Box::new(ir_var("p", point_ptr_ty.clone())),
                        field: "x".to_string(),
                        ty: i32_ty.clone(),
                        is_arrow: true,
                        source_span: None,
                    },
                    value: ir_var("value", i32_ty.clone()),
                    source_span: None,
                }],
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

    let emitted = emit_rust_from_ir(&ir)
        .expect("emit mutable record pointer field read after if-return/else-write");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(
        rust.contains(
            "pub fn set_then_read_point_x_if_absent(mut p: &mut Point, cond: i32, value: i32) -> i32"
        ),
        "{rust}"
    );
    assert!(rust.contains("return 0i32;"), "{rust}");
    assert!(rust.contains("p.x = value;"), "{rust}");
    assert!(rust.contains("return p.x;"), "{rust}");
    assert_rust_snippet_compiles(
        "typed-ir-mutable-record-pointer-field-read-after-then-return",
        rust,
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_uninitialized_scalar_local_after_if_return_assignment() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "assign_local_or_return".to_string(),
        return_type: i32_ty.clone(),
        params: vec![
            IrParam {
                name: "cond".to_string(),
                ty: i32_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "value".to_string(),
                ty: i32_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![
            IrStmt::Decl {
                name: "out".to_string(),
                ty: i32_ty.clone(),
                init: None,
                source_span: None,
            },
            IrStmt::If {
                condition: ir_var("cond", i32_ty.clone()),
                then_body: vec![IrStmt::Assign {
                    target: ir_var("out", i32_ty.clone()),
                    value: ir_var("value", i32_ty.clone()),
                    source_span: None,
                }],
                else_body: vec![IrStmt::Return {
                    value: Some(ir_lit(0, "0", i32_ty.clone())),
                    source_span: None,
                }],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("out", i32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let emitted =
        emit_rust_from_ir(&ir).expect("emit uninitialized scalar local after if-return assignment");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("let mut out: i32;"), "{rust}");
    assert!(rust.contains("out = value;"), "{rust}");
    assert!(rust.contains("return out;"), "{rust}");
    assert_rust_snippet_compiles("typed-ir-scalar-local-if-return-assignment", rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_mutable_record_pointer_arrow_field_read_before_assignment() {
    let i32_ty = ir_i32();
    let point_ty = ir_record_with_fields("point", vec![("x", i32_ty.clone())]);
    let point_ptr_ty = ir_pointer("struct point *", "struct point *", point_ty, false);
    let ir = IrFunction {
        name: "bad_read_then_set_point_x".to_string(),
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
            IrStmt::Decl {
                name: "old".to_string(),
                ty: i32_ty.clone(),
                init: Some(IrExpr::Member {
                    base: Box::new(ir_var("p", point_ptr_ty.clone())),
                    field: "x".to_string(),
                    ty: i32_ty.clone(),
                    is_arrow: true,
                    source_span: None,
                }),
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
                value: ir_var("value", i32_ty.clone()),
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("old", i32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir)
        .expect_err("mutable record pointer field read before assignment must fail closed");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(
        error
            .reason
            .contains("mutable record pointer field p.x is read before definite assignment"),
        "{:?}",
        error
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_mutable_record_pointer_arrow_field_read_inside_returning_branch_before_assignment(
) {
    let i32_ty = ir_i32();
    let point_ty = ir_record_with_fields("point", vec![("x", i32_ty.clone())]);
    let point_ptr_ty = ir_pointer("struct point *", "struct point *", point_ty, false);
    let ir = IrFunction {
        name: "bad_return_read_or_set_point_x".to_string(),
        return_type: i32_ty.clone(),
        params: vec![
            IrParam {
                name: "p".to_string(),
                ty: point_ptr_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "cond".to_string(),
                ty: i32_ty.clone(),
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
                condition: ir_var("cond", i32_ty.clone()),
                then_body: vec![IrStmt::Return {
                    value: Some(IrExpr::Member {
                        base: Box::new(ir_var("p", point_ptr_ty.clone())),
                        field: "x".to_string(),
                        ty: i32_ty.clone(),
                        is_arrow: true,
                        source_span: None,
                    }),
                    source_span: None,
                }],
                else_body: vec![IrStmt::Assign {
                    target: IrExpr::Member {
                        base: Box::new(ir_var("p", point_ptr_ty.clone())),
                        field: "x".to_string(),
                        ty: i32_ty.clone(),
                        is_arrow: true,
                        source_span: None,
                    },
                    value: ir_var("value", i32_ty.clone()),
                    source_span: None,
                }],
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

    let error = emit_rust_from_ir(&ir)
        .expect_err("returning branch must not read mutable record pointer field before write");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(
        error.reason.contains(
            "if then[0].return expr mutable record pointer field p.x is read before definite assignment"
        ),
        "{:?}",
        error
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_mutable_record_pointer_arrow_field_read_when_only_returning_branch_writes() {
    let i32_ty = ir_i32();
    let point_ty = ir_record_with_fields("point", vec![("x", i32_ty.clone())]);
    let point_ptr_ty = ir_pointer("struct point *", "struct point *", point_ty, false);
    let ir = IrFunction {
        name: "bad_write_and_return_then_read_point_x".to_string(),
        return_type: i32_ty.clone(),
        params: vec![
            IrParam {
                name: "p".to_string(),
                ty: point_ptr_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "cond".to_string(),
                ty: i32_ty.clone(),
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
                condition: ir_var("cond", i32_ty.clone()),
                then_body: vec![
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
                        value: Some(ir_lit(0, "0", i32_ty.clone())),
                        source_span: None,
                    },
                ],
                else_body: vec![],
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

    let error = emit_rust_from_ir(&ir)
        .expect_err("write on returning branch must not prove fallthrough field assignment");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(
        error
            .reason
            .contains("mutable record pointer field p.x is read before definite assignment"),
        "{:?}",
        error
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_mutable_record_pointer_arrow_field_read_after_loop_return_branch() {
    let i32_ty = ir_i32();
    let point_ty = ir_record_with_fields("point", vec![("x", i32_ty.clone())]);
    let point_ptr_ty = ir_pointer("struct point *", "struct point *", point_ty, false);
    let ir = IrFunction {
        name: "bad_loop_return_or_set_then_read_point_x".to_string(),
        return_type: i32_ty.clone(),
        params: vec![
            IrParam {
                name: "p".to_string(),
                ty: point_ptr_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "cond".to_string(),
                ty: i32_ty.clone(),
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
                condition: ir_var("cond", i32_ty.clone()),
                then_body: vec![IrStmt::Assign {
                    target: IrExpr::Member {
                        base: Box::new(ir_var("p", point_ptr_ty.clone())),
                        field: "x".to_string(),
                        ty: i32_ty.clone(),
                        is_arrow: true,
                        source_span: None,
                    },
                    value: ir_var("value", i32_ty.clone()),
                    source_span: None,
                }],
                else_body: vec![IrStmt::While {
                    condition: ir_binary(
                        IrBinOp::Gt,
                        ir_var("value", i32_ty.clone()),
                        ir_lit(0, "0", i32_ty.clone()),
                        i32_ty.clone(),
                    ),
                    body: vec![IrStmt::Return {
                        value: Some(ir_lit(0, "0", i32_ty.clone())),
                        source_span: None,
                    }],
                    source_span: None,
                }],
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

    let error = emit_rust_from_ir(&ir)
        .expect_err("loop-body return must not prove branch-level field assignment");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(
        error
            .reason
            .contains("mutable record pointer field p.x is read before definite assignment"),
        "{:?}",
        error
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_mutable_record_pointer_arrow_field_read_after_maybe_assignment() {
    let i32_ty = ir_i32();
    let point_ty = ir_record_with_fields("point", vec![("x", i32_ty.clone())]);
    let point_ptr_ty = ir_pointer("struct point *", "struct point *", point_ty, false);
    let ir = IrFunction {
        name: "bad_maybe_set_then_read_point_x".to_string(),
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
            IrStmt::If {
                condition: ir_binary(
                    IrBinOp::Gt,
                    ir_var("value", i32_ty.clone()),
                    ir_lit(0, "0", i32_ty.clone()),
                    i32_ty.clone(),
                ),
                then_body: vec![IrStmt::Assign {
                    target: IrExpr::Member {
                        base: Box::new(ir_var("p", point_ptr_ty.clone())),
                        field: "x".to_string(),
                        ty: i32_ty.clone(),
                        is_arrow: true,
                        source_span: None,
                    },
                    value: ir_var("value", i32_ty.clone()),
                    source_span: None,
                }],
                else_body: vec![],
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

    let error = emit_rust_from_ir(&ir)
        .expect_err("mutable record pointer field read after maybe-assignment must fail closed");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(
        error
            .reason
            .contains("mutable record pointer field p.x is read before definite assignment"),
        "{:?}",
        error
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_mutable_record_pointer_arrow_different_field_read_after_assignment() {
    let i32_ty = ir_i32();
    let point_ty =
        ir_record_with_fields("point", vec![("x", i32_ty.clone()), ("y", i32_ty.clone())]);
    let point_ptr_ty = ir_pointer("struct point *", "struct point *", point_ty, false);
    let ir = IrFunction {
        name: "bad_set_x_read_y".to_string(),
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
                    field: "y".to_string(),
                    ty: i32_ty.clone(),
                    is_arrow: true,
                    source_span: None,
                }),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir)
        .expect_err("mutable record pointer different field read must fail closed");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(
        error
            .reason
            .contains("mutable record pointer field p.y is read before definite assignment"),
        "{:?}",
        error
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_record_arrow_field_compound_assignment_shape() {
    let point_ty = ir_record("point");
    let point_ptr_ty = ir_pointer(
        "const struct point *",
        "const struct point *",
        ir_const(point_ty),
        false,
    );
    let i32_ty = ir_i32();
    let field_target = IrExpr::Member {
        base: Box::new(ir_var("p", point_ptr_ty.clone())),
        field: "x".to_string(),
        ty: i32_ty.clone(),
        is_arrow: true,
        source_span: None,
    };
    let ir = IrFunction {
        name: "add_point_x".to_string(),
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
                target: field_target.clone(),
                value: ir_binary(
                    IrBinOp::Add,
                    field_target,
                    ir_var("value", i32_ty.clone()),
                    i32_ty.clone(),
                ),
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_lit(0, "0", i32_ty)),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error =
        emit_rust_from_ir(&ir).expect_err("record pointer compound member write must fail closed");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(error.reason.contains("arrow member assignment"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_mutable_record_pointer_arrow_field_read() {
    let point_ty = ir_record("point");
    let point_ptr_ty = ir_pointer("struct point *", "struct point *", point_ty, false);
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

    let error = emit_rust_from_ir(&ir).expect_err("mutable record pointer read must fail closed");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(
        error
            .reason
            .contains("param p has pointer type struct point * is unsupported")
            || error
                .reason
                .contains("arrow member expression base has unsupported type struct point *"),
        "{:?}",
        error
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_record_param_without_modeled_field_use() {
    let point_ty = ir_record("point");
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "ignore_point".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "p".to_string(),
            ty: point_ty,
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(ir_lit(0, "0", i32_ty)),
            source_span: None,
        }],
        source_span: None,
    };

    let error =
        emit_rust_from_ir(&ir).expect_err("record params need at least one modeled field use");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(error.reason.contains("record point has no modeled fields"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_local_fixed_array_index_read() {
    let u32_ty = ir_u32();
    let usize_ty = ir_usize();
    let table_ty = ir_array(u32_ty.clone(), 3);
    let ir = IrFunction {
        name: "lookup_local_table".to_string(),
        return_type: u32_ty.clone(),
        params: vec![IrParam {
            name: "i".to_string(),
            ty: usize_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::Decl {
                name: "table".to_string(),
                ty: table_ty.clone(),
                init: Some(IrExpr::ArrayLiteral {
                    elements: vec![
                        ir_lit(1, "1U", u32_ty.clone()),
                        ir_lit(2, "2U", u32_ty.clone()),
                        ir_lit(3, "3U", u32_ty.clone()),
                    ],
                    ty: table_ty.clone(),
                    source_span: None,
                }),
                source_span: None,
            },
            IrStmt::Return {
                value: Some(IrExpr::Index {
                    base: Box::new(ir_var("table", table_ty)),
                    index: Box::new(ir_var("i", usize_ty)),
                    ty: u32_ty,
                    source_span: None,
                }),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit local fixed array index read");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("let table: [u32; 3] = [1u32, 2u32, 3u32];"));
    assert!(rust.contains("return table[i as usize];"));
    assert_rust_snippet_compiles("typed-ir-local-fixed-array-index-read", rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_unused_readonly_pointer_param_without_slice_evidence() {
    let i32_ty = ir_i32();
    let const_i32_ty = ir_const(i32_ty.clone());
    let const_i32_ptr_ty = ir_pointer("const int *", "const int *", const_i32_ty, false);
    let ir = IrFunction {
        name: "ignore_values".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "values".to_string(),
            ty: const_i32_ptr_ty,
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(ir_lit(0, "0", i32_ty)),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir)
        .expect_err("readonly pointer params need explicit slice lowering evidence");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(
        error.reason.contains("pointer-to-slice lowering evidence"),
        "{:?}",
        error.reason
    );
    assert!(error.reason.contains("values"), "{:?}", error.reason);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_readonly_pointer_deref_read_as_slice_zero_index() {
    let u8_ty = ir_u8();
    let const_u8_ty = ir_const(u8_ty.clone());
    let const_u8_ptr_ty = ir_pointer("const uint8_t *", "uint8_t *", const_u8_ty, false);
    let ir = IrFunction {
        name: "read_first_byte".to_string(),
        return_type: u8_ty.clone(),
        params: vec![IrParam {
            name: "p".to_string(),
            ty: const_u8_ptr_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(ir_deref(ir_var("p", const_u8_ptr_ty), u8_ty)),
            source_span: None,
        }],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit readonly pointer deref read");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub fn read_first_byte(p: &[u8]) -> u8"));
    assert!(rust.contains("return p[0usize];"));
    assert_rust_snippet_compiles("typed-ir-readonly-pointer-deref-read", rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_readonly_pointer_add_index_deref_read() {
    let u8_ty = ir_u8();
    let usize_ty = ir_usize();
    let const_u8_ty = ir_const(u8_ty.clone());
    let const_u8_ptr_ty = ir_pointer("const uint8_t *", "uint8_t *", const_u8_ty, false);
    let ptr_plus_index = ir_binary(
        IrBinOp::Add,
        ir_var("p", const_u8_ptr_ty.clone()),
        ir_var("i", usize_ty.clone()),
        const_u8_ptr_ty.clone(),
    );
    let ir = IrFunction {
        name: "read_byte_at".to_string(),
        return_type: u8_ty.clone(),
        params: vec![
            IrParam {
                name: "p".to_string(),
                ty: const_u8_ptr_ty,
                source_span: None,
            },
            IrParam {
                name: "i".to_string(),
                ty: usize_ty,
                source_span: None,
            },
        ],
        body: vec![IrStmt::Return {
            value: Some(ir_deref(ptr_plus_index, u8_ty)),
            source_span: None,
        }],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit readonly pointer add-index deref read");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub fn read_byte_at(p: &[u8], i: usize) -> u8"));
    assert!(rust.contains("return p[i as usize];"));
    assert_rust_snippet_compiles("typed-ir-readonly-pointer-add-index-deref-read", rust);
}
