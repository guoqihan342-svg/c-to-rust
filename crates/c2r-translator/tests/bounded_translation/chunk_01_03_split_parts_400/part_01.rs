#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_record_local_assignment_value_copy() {
    let point_ty = ir_record("point");
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "assign_local_point_x".to_string(),
        return_type: i32_ty.clone(),
        params: vec![
            IrParam {
                name: "p".to_string(),
                ty: point_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "r".to_string(),
                ty: point_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![
            IrStmt::Decl {
                name: "q".to_string(),
                ty: point_ty.clone(),
                init: Some(ir_var("p", point_ty.clone())),
                source_span: None,
            },
            IrStmt::Assign {
                target: ir_var("q", point_ty.clone()),
                value: ir_var("r", point_ty.clone()),
                source_span: None,
            },
            IrStmt::Return {
                value: Some(IrExpr::Member {
                    base: Box::new(ir_var("q", point_ty)),
                    field: "x".to_string(),
                    ty: i32_ty,
                    is_arrow: false,
                    source_span: None,
                }),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit by-value record local assignment copy");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub struct Point"));
    assert!(rust.contains("pub fn assign_local_point_x(p: Point, r: Point) -> i32"));
    assert!(rust.contains("let mut q: Point = p;"));
    assert!(rust.contains("q = r;"));
    assert!(rust.contains("return q.x;"));
    assert_rust_snippet_compiles("typed-ir-record-local-assignment-value-copy", rust);
}
#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_uninitialized_record_local_decl() {
    let i32_ty = ir_i32();
    let point_ty = ir_record_with_fields("point", vec![("x", i32_ty.clone())]);
    let ir = IrFunction {
        name: "bad_record_local".to_string(),
        return_type: i32_ty.clone(),
        params: vec![],
        body: vec![
            IrStmt::Decl {
                name: "q".to_string(),
                ty: point_ty.clone(),
                init: None,
                source_span: None,
            },
            IrStmt::Return {
                value: Some(IrExpr::Member {
                    base: Box::new(ir_var("q", point_ty)),
                    field: "x".to_string(),
                    ty: i32_ty,
                    is_arrow: false,
                    source_span: None,
                }),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("record locals need explicit initializer");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(error
        .reason
        .contains("decl q record initializer is required"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_uninitialized_record_local_address_when_field_is_read() {
    let i32_ty = ir_i32();
    let point_ty = ir_record_with_fields("point", vec![("x", i32_ty.clone())]);
    let point_ptr_ty = ir_pointer("struct point *", "struct point *", point_ty.clone(), false);
    let ir = IrFunction {
        name: "bad_record_address_and_read".to_string(),
        return_type: i32_ty.clone(),
        params: vec![],
        body: vec![
            IrStmt::Decl {
                name: "q".to_string(),
                ty: point_ty.clone(),
                init: None,
                source_span: None,
            },
            IrStmt::Expr {
                expr: IrExpr::Call {
                    callee: "touch_point".to_string(),
                    args: vec![IrExpr::AddrOf {
                        operand: Box::new(ir_var("q", point_ty.clone())),
                        ty: point_ptr_ty,
                        source_span: None,
                    }],
                    ty: ir_void(),
                    source_span: None,
                },
                source_span: None,
            },
            IrStmt::Return {
                value: Some(IrExpr::Member {
                    base: Box::new(ir_var("q", point_ty)),
                    field: "x".to_string(),
                    ty: i32_ty,
                    is_arrow: false,
                    source_span: None,
                }),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir)
        .expect_err("address-taken record locals cannot also be read without an initializer");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(error
        .reason
        .contains("decl q record initializer is required"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_local_record_address_passed_to_direct_call() {
    let mut_void_ptr_ty = ir_pointer("void *", "void *", ir_void(), false);
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
        name: "call_with_local_blob".to_string(),
        return_type: i32_ty.clone(),
        params: vec![],
        body: vec![
            IrStmt::Decl {
                name: "blob".to_string(),
                ty: blob_ty.clone(),
                init: None,
                source_span: None,
            },
            IrStmt::Return {
                value: Some(IrExpr::Call {
                    callee: "observe_blob".to_string(),
                    args: vec![IrExpr::AddrOf {
                        operand: Box::new(ir_var("blob", blob_ty)),
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

    let emitted = emit_rust_from_ir(&ir).expect("emit address-of local record call arg");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub struct FdbBlob"), "{rust}");
    assert!(rust.contains("let mut blob: FdbBlob = FdbBlob {"), "{rust}");
    assert!(rust.contains("buf: core::ptr::null_mut()"), "{rust}");
    assert!(rust.contains("size: 0usize"), "{rust}");
    assert!(rust.contains("return observe_blob(&mut blob);"), "{rust}");
    assert_rust_snippet_compiles(
        "typed-ir-local-record-address-call-arg",
        &format!(
            "fn observe_blob(blob: &mut FdbBlob) -> i32 {{ blob.size = 7usize; 7i32 }}\n{rust}"
        ),
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_readonly_record_pointer_raw_pointer_field_return() {
    let u8_ty = ir_u8();
    let mut_u8_ptr_ty = ir_pointer("uint8_t *", "uint8_t *", u8_ty, false);
    let blob_ty = ir_record_with_fields(
        "fdb_blob",
        vec![("buf", mut_u8_ptr_ty.clone()), ("size", ir_usize())],
    );
    let const_blob_ptr_ty = ir_pointer(
        "const struct fdb_blob *",
        "const struct fdb_blob *",
        ir_const(blob_ty.clone()),
        false,
    );
    let ir = IrFunction {
        name: "blob_buf".to_string(),
        return_type: mut_u8_ptr_ty.clone(),
        params: vec![IrParam {
            name: "blob".to_string(),
            ty: const_blob_ptr_ty,
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(IrExpr::Member {
                base: Box::new(ir_var("blob", ir_pointer(
                    "const struct fdb_blob *",
                    "const struct fdb_blob *",
                    ir_const(blob_ty),
                    false,
                ))),
                field: "buf".to_string(),
                ty: mut_u8_ptr_ty,
                is_arrow: true,
                source_span: None,
            }),
            source_span: None,
        }],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit readonly record pointer raw field return");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub struct FdbBlob"), "{rust}");
    assert!(rust.contains("pub buf: *mut u8"), "{rust}");
    assert!(rust.contains("pub fn blob_buf(blob: &FdbBlob) -> *mut u8"), "{rust}");
    assert!(rust.contains("return blob.buf;"), "{rust}");
    assert_rust_snippet_compiles("typed-ir-readonly-record-pointer-raw-field-return", rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_keeps_direct_raw_pointer_return_fail_closed() {
    let u8_ty = ir_u8();
    let mut_u8_ptr_ty = ir_pointer("uint8_t *", "uint8_t *", u8_ty, false);
    let ir = IrFunction {
        name: "return_raw_pointer".to_string(),
        return_type: mut_u8_ptr_ty.clone(),
        params: vec![IrParam {
            name: "ptr".to_string(),
            ty: mut_u8_ptr_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(ir_var("ptr", mut_u8_ptr_ty)),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("direct raw pointer return must stay closed");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(error.reason.contains("pointer value return"), "{:?}", error.reason);
    assert!(error.reason.contains("uint8_t *"), "{:?}", error.reason);
}
