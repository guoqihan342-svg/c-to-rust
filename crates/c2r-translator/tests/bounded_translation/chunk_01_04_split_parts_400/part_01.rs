#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_readonly_pointer_return_nested_call_arg() {
    let db_param_ty = ir_pointer("fdb_kvdb_t", "void *", ir_void(), false);
    let db_arg_ty = ir_pointer("void *", "void *", ir_void(), false);
    let const_char_ty = ir_integer("const char", "char", true, 8);
    let const_char_ptr_ty = ir_pointer("const char *", "char *", ir_const(const_char_ty), false);
    let void_ty = ir_void();
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "log_db_name".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "db".to_string(),
            ty: db_param_ty,
            source_span: None,
        }],
        body: vec![
            IrStmt::Expr {
                expr: IrExpr::Call {
                    callee: "FDB_INFO".to_string(),
                    args: vec![
                        IrExpr::NullPtr {
                            ty: const_char_ptr_ty.clone(),
                            source_span: None,
                        },
                        IrExpr::Call {
                            callee: "db_name".to_string(),
                            args: vec![ir_var("db", db_arg_ty)],
                            ty: const_char_ptr_ty,
                            source_span: None,
                        },
                    ],
                    ty: void_ty,
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

    let emitted = emit_rust_from_ir(&ir).expect("emit readonly pointer return nested call arg");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("FDB_INFO(core::ptr::null(), db_name(db));"), "{rust}");
    assert_rust_snippet_runs(
        "typed-ir-readonly-pointer-return-nested-call-arg",
        &format!(
            "fn db_name(_: *mut core::ffi::c_void) -> *const core::ffi::c_void {{ core::ptr::null() }}\nfn FDB_INFO(_: *const core::ffi::c_void, _: *const core::ffi::c_void) {{}}\n{rust}"
        ),
        "let mut byte = 0u8; assert_eq!(log_db_name((&mut byte as *mut u8).cast()), 0i32);",
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_blob_make_pointer_return_as_direct_call_argument() {
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
        name: "call_kv_set_blob".to_string(),
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
                            ir_var("value", const_void_ptr_ty),
                            ir_var("len", usize_ty),
                        ],
                        ty: blob_ptr_ty,
                        source_span: None,
                    }],
                    ty: i32_ty.clone(),
                    source_span: None,
                }),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let emitted =
        emit_rust_from_ir(&ir).expect("emit fdb_blob_make pointer return as direct call arg");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(
        rust.contains("return fdb_kv_set_blob(fdb_blob_make(&mut blob, value, len));"),
        "{rust}"
    );
    assert_rust_snippet_runs(
        "typed-ir-blob-make-pointer-return-direct-call-arg",
        &format!(
            "fn fdb_blob_make(blob: &mut FdbBlob, value: *const core::ffi::c_void, len: usize) -> *mut FdbBlob {{ blob.buf = value as *mut core::ffi::c_void; blob.size = len; blob as *mut FdbBlob }}\nfn fdb_kv_set_blob(blob: *mut FdbBlob) -> i32 {{ unsafe {{ if blob.is_null() {{ -1i32 }} else {{ (*blob).size as i32 }} }} }}\n{rust}"
        ),
        "assert_eq!(call_kv_set_blob(core::ptr::null(), 5usize), 5i32);",
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_blob_make_pointer_return_argument_with_strlen_leaf() {
    let mut_void_ptr_ty = ir_pointer("void *", "void *", ir_void(), false);
    let const_u8_ptr_ty = ir_pointer(
        "const uint8_t *",
        "const unsigned char *",
        ir_const(ir_u8()),
        true,
    );
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
        name: "call_kv_set_blob_strlen".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: const_u8_ptr_ty.clone(),
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
                            ir_var("value", const_u8_ptr_ty.clone()),
                            IrExpr::Call {
                                callee: "strlen".to_string(),
                                args: vec![ir_var("value", const_u8_ptr_ty)],
                                ty: usize_ty,
                                source_span: None,
                            },
                        ],
                        ty: blob_ptr_ty,
                        source_span: None,
                    }],
                    ty: i32_ty.clone(),
                    source_span: None,
                }),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let emitted =
        emit_rust_from_ir(&ir).expect("emit fdb_blob_make strlen leaf as direct call arg");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(
        rust.contains("pub fn call_kv_set_blob_strlen(value: &[u8]) -> i32"),
        "{rust}"
    );
    assert!(
        rust.contains(
            "return fdb_kv_set_blob(fdb_blob_make(&mut blob, value.as_ptr() as *const core::ffi::c_void, value.iter().position(|&byte| byte == 0).expect(\"C strlen precondition violated\")));"
        ),
        "{rust}"
    );
    assert_rust_snippet_runs(
        "typed-ir-blob-make-pointer-return-strlen-leaf",
        &format!(
            "fn fdb_blob_make(blob: &mut FdbBlob, value: *const core::ffi::c_void, len: usize) -> *mut FdbBlob {{ blob.buf = value as *mut core::ffi::c_void; blob.size = len; blob as *mut FdbBlob }}\nfn fdb_kv_set_blob(blob: *mut FdbBlob) -> i32 {{ unsafe {{ if blob.is_null() {{ -1i32 }} else {{ (*blob).size as i32 }} }} }}\n{rust}"
        ),
        "assert_eq!(call_kv_set_blob_strlen(b\"abc\\0\"), 3i32);",
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_external_direct_call_pointer_passthrough_with_blob_constructor_arg() {
    let mut_void_ptr_ty = ir_pointer("void *", "void *", ir_void(), false);
    let const_u8_ptr_ty = ir_pointer(
        "const char *",
        "const unsigned char *",
        ir_const(ir_u8()),
        true,
    );
    let usize_ty = ir_usize();
    let kvdb_ty = ir_record("fdb_kvdb");
    let kvdb_ptr_ty = ir_pointer("fdb_kvdb_t", "struct fdb_kvdb *", kvdb_ty, false);
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
        name: "call_kv_set_blob_with_context".to_string(),
        return_type: i32_ty.clone(),
        params: vec![
            IrParam {
                name: "db".to_string(),
                ty: kvdb_ptr_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "key".to_string(),
                ty: const_u8_ptr_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "value".to_string(),
                ty: const_u8_ptr_ty.clone(),
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
                    callee: "fdb_kv_set_blob".to_string(),
                    args: vec![
                        ir_var("db", kvdb_ptr_ty),
                        ir_var("key", const_u8_ptr_ty.clone()),
                        IrExpr::Call {
                            callee: "fdb_blob_make".to_string(),
                            args: vec![
                                IrExpr::AddrOf {
                                    operand: Box::new(ir_var("blob", blob_ty)),
                                    ty: blob_ptr_ty.clone(),
                                    source_span: None,
                                },
                                ir_var("value", const_u8_ptr_ty.clone()),
                                IrExpr::Call {
                                    callee: "strlen".to_string(),
                                    args: vec![ir_var("value", const_u8_ptr_ty)],
                                    ty: usize_ty,
                                    source_span: None,
                                },
                            ],
                            ty: blob_ptr_ty,
                            source_span: None,
                        },
                    ],
                    ty: i32_ty.clone(),
                    source_span: None,
                }),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir)
        .expect("emit external direct call pointer passthrough compile-context candidate");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub struct FdbBlob"), "{rust}");
    assert!(
        rust.contains(
            "pub fn call_kv_set_blob_with_context(db: *mut core::ffi::c_void, key: *const core::ffi::c_void, value: &[u8]) -> i32"
        ),
        "{rust}"
    );
    assert!(
        rust.contains(
            "return fdb_kv_set_blob(db, key, fdb_blob_make(&mut blob, value.as_ptr() as *const core::ffi::c_void, value.iter().position(|&byte| byte == 0).expect(\"C strlen precondition violated\")));"
        ),
        "{rust}"
    );
    assert_rust_snippet_runs(
        "typed-ir-external-direct-call-pointer-passthrough-blob-constructor",
        &format!(
            "fn fdb_blob_make(blob: &mut FdbBlob, value: *const core::ffi::c_void, len: usize) -> *mut FdbBlob {{ blob.buf = value as *mut core::ffi::c_void; blob.size = len; blob as *mut FdbBlob }}\nfn fdb_kv_set_blob(_: *mut core::ffi::c_void, _: *const core::ffi::c_void, blob: *mut FdbBlob) -> i32 {{ unsafe {{ if blob.is_null() {{ -1i32 }} else {{ (*blob).size as i32 }} }} }}\n{rust}"
        ),
        "let mut db = 0u8; assert_eq!(call_kv_set_blob_with_context((&mut db as *mut u8).cast::<core::ffi::c_void>(), b\"boot\\0\".as_ptr().cast::<core::ffi::c_void>(), b\"123\\0\"), 3i32);",
    );
}
