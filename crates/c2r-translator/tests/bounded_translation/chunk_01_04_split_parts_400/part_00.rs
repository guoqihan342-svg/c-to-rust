#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_local_record_address_with_nested_record_zero_initializer() {
    let mut_void_ptr_ty = ir_pointer("void *", "void *", ir_void(), false);
    let u32_ty = ir_u32();
    let usize_ty = ir_usize();
    let saved_ty = ir_record_with_fields(
        "fdb_blob_saved",
        vec![
            ("meta_addr", u32_ty.clone()),
            ("addr", u32_ty),
            ("len", usize_ty.clone()),
        ],
    );
    let blob_ty = ir_record_with_fields(
        "fdb_blob",
        vec![
            ("buf", mut_void_ptr_ty.clone()),
            ("size", usize_ty),
            ("saved", saved_ty),
        ],
    );
    let blob_ptr_ty = ir_pointer(
        "struct fdb_blob *",
        "struct fdb_blob *",
        blob_ty.clone(),
        false,
    );
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "call_with_nested_local_blob".to_string(),
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

    let emitted = emit_rust_from_ir(&ir).expect("emit nested local record call arg");
    let rust = &emitted.rust;

    assert!(rust.contains("pub struct FdbBlobSaved"), "{rust}");
    assert!(rust.contains("pub struct FdbBlob"), "{rust}");
    assert!(rust.contains("saved: FdbBlobSaved {"), "{rust}");
    assert!(rust.contains("meta_addr: 0u32"), "{rust}");
    assert!(rust.contains("addr: 0u32"), "{rust}");
    assert!(rust.contains("len: 0usize"), "{rust}");
    assert_rust_snippet_compiles(
        "typed-ir-local-record-address-nested-record",
        &format!(
            "fn observe_blob(blob: &mut FdbBlob) -> i32 {{ blob.saved.len = 7usize; 7i32 }}\n{rust}"
        ),
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_discarded_pointer_return_call_with_opaque_void_arg() {
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
        name: "call_blob_make".to_string(),
        return_type: i32_ty.clone(),
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
            IrStmt::Expr {
                expr: IrExpr::Call {
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
                },
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
        emit_rust_from_ir(&ir).expect("emit discarded pointer-return direct call statement");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(
        rust.contains("pub fn call_blob_make(value: *const core::ffi::c_void, len: usize) -> i32"),
        "{rust}"
    );
    assert!(
        rust.contains("let _ = fdb_blob_make(&mut blob, value, len);"),
        "{rust}"
    );
    assert_rust_snippet_runs(
        "typed-ir-discarded-pointer-return-call-opaque-arg",
        &format!(
            "fn fdb_blob_make(blob: &mut FdbBlob, value: *const core::ffi::c_void, len: usize) -> *mut FdbBlob {{ blob.buf = value as *mut core::ffi::c_void; blob.size = len; blob as *mut FdbBlob }}\n{rust}"
        ),
        "assert_eq!(call_blob_make(core::ptr::null(), 3usize), 0i32);",
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_null_pointer_direct_call_arg() {
    let const_void_ptr_ty = ir_pointer("const void *", "void *", ir_const(ir_void()), false);
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "call_with_null".to_string(),
        return_type: i32_ty.clone(),
        params: vec![],
        body: vec![IrStmt::Return {
            value: Some(IrExpr::Call {
                callee: "observe_null".to_string(),
                args: vec![IrExpr::NullPtr {
                    ty: const_void_ptr_ty,
                    source_span: None,
                }],
                ty: i32_ty,
                source_span: None,
            }),
            source_span: None,
        }],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit null pointer direct call arg");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("return observe_null(core::ptr::null());"), "{rust}");
    assert_rust_snippet_runs(
        "typed-ir-null-pointer-direct-call-arg",
        &format!(
            "fn observe_null(value: *const core::ffi::c_void) -> i32 {{ if value.is_null() {{ 7i32 }} else {{ -1i32 }} }}\n{rust}"
        ),
        "assert_eq!(call_with_null(), 7i32);",
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_typedef_opaque_void_pointer_param_used_as_call_arg() {
    let db_param_ty = ir_pointer("fdb_kvdb_t", "void *", ir_void(), false);
    let db_arg_ty = ir_pointer("void *", "void *", ir_void(), false);
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "call_db_init_ok".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "db".to_string(),
            ty: db_param_ty,
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(IrExpr::Call {
                callee: "db_init_ok".to_string(),
                args: vec![ir_var("db", db_arg_ty)],
                ty: i32_ty,
                source_span: None,
            }),
            source_span: None,
        }],
        source_span: None,
    };

    let emitted =
        emit_rust_from_ir(&ir).expect("emit typedef opaque void pointer direct call param");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(
        rust.contains("pub fn call_db_init_ok(db: *mut core::ffi::c_void) -> i32"),
        "{rust}"
    );
    assert!(rust.contains("return db_init_ok(db);"), "{rust}");
    assert_rust_snippet_runs(
        "typed-ir-typedef-opaque-pointer-direct-call-param",
        &format!(
            "fn db_init_ok(db: *mut core::ffi::c_void) -> i32 {{ if db.is_null() {{ 0i32 }} else {{ 1i32 }} }}\n{rust}"
        ),
        "let mut byte = 0u8; assert_eq!(call_db_init_ok((&mut byte as *mut u8).cast()), 1i32);",
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_negated_direct_bool_call_condition() {
    let db_param_ty = ir_pointer("fdb_kvdb_t", "void *", ir_void(), false);
    let db_arg_ty = ir_pointer("void *", "void *", ir_void(), false);
    let bool_ty = ir_integer("bool", "_Bool", false, 8);
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "guard_db_init".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "db".to_string(),
            ty: db_param_ty,
            source_span: None,
        }],
        body: vec![
            IrStmt::If {
                condition: IrExpr::Unary {
                    op: IrUnOp::Not,
                    operand: Box::new(IrExpr::Call {
                        callee: "db_init_ok".to_string(),
                        args: vec![ir_var("db", db_arg_ty)],
                        ty: bool_ty,
                        source_span: None,
                    }),
                    ty: i32_ty.clone(),
                    source_span: None,
                },
                then_body: vec![IrStmt::Return {
                    value: Some(ir_lit(7, "7", i32_ty.clone())),
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

    let emitted = emit_rust_from_ir(&ir).expect("emit negated direct bool call condition");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("if db_init_ok(db) == false {"), "{rust}");
    assert_rust_snippet_runs(
        "typed-ir-negated-direct-bool-call-condition",
        &format!(
            "fn db_init_ok(db: *mut core::ffi::c_void) -> bool {{ !db.is_null() }}\n{rust}"
        ),
        "let mut byte = 0u8; assert_eq!(guard_db_init((&mut byte as *mut u8).cast()), 0i32); assert_eq!(guard_db_init(core::ptr::null_mut()), 7i32);",
    );
}
