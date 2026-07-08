#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_pointer_truthiness_blob_constructor_with_clang_size_t_strlen_leaf() {
    let mut_void_ptr_ty = ir_pointer("void *", "void *", ir_void(), false);
    let char_ty = ir_integer("const char", "char", true, 8);
    let const_char_ptr_ty = ir_pointer("const char *", "char *", ir_const(char_ty), false);
    let clang_size_t_ty = ir_integer("__size_t", "__size_t", false, 64);
    let kvdb_ty = ir_record("fdb_kvdb");
    let kvdb_ptr_ty = ir_pointer("fdb_kvdb_t", "struct fdb_kvdb *", kvdb_ty, false);
    let blob_ty = ir_record_with_fields(
        "fdb_blob",
        vec![
            ("buf", mut_void_ptr_ty.clone()),
            ("size", clang_size_t_ty.clone()),
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
        name: "set_or_delete".to_string(),
        return_type: i32_ty.clone(),
        params: vec![
            IrParam {
                name: "db".to_string(),
                ty: kvdb_ptr_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "key".to_string(),
                ty: const_char_ptr_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "value".to_string(),
                ty: const_char_ptr_ty.clone(),
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
            IrStmt::If {
                condition: ir_var("value", const_char_ptr_ty.clone()),
                then_body: vec![IrStmt::Return {
                    value: Some(IrExpr::Call {
                        callee: "fdb_kv_set_blob".to_string(),
                        args: vec![
                            ir_var("db", kvdb_ptr_ty.clone()),
                            ir_var("key", const_char_ptr_ty.clone()),
                            IrExpr::Call {
                                callee: "fdb_blob_make".to_string(),
                                args: vec![
                                    IrExpr::AddrOf {
                                        operand: Box::new(ir_var("blob", blob_ty)),
                                        ty: blob_ptr_ty.clone(),
                                        source_span: None,
                                    },
                                    ir_var("value", const_char_ptr_ty.clone()),
                                    IrExpr::Call {
                                        callee: "strlen".to_string(),
                                        args: vec![ir_var("value", const_char_ptr_ty.clone())],
                                        ty: clang_size_t_ty,
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
                }],
                else_body: vec![],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(IrExpr::Call {
                    callee: "fdb_kv_del".to_string(),
                    args: vec![ir_var("db", kvdb_ptr_ty), ir_var("key", const_char_ptr_ty)],
                    ty: i32_ty.clone(),
                    source_span: None,
                }),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir)
        .expect("emit pointer truthiness blob constructor with clang __size_t strlen leaf");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(
        rust.contains(
            "pub fn set_or_delete(db: *mut core::ffi::c_void, key: *const core::ffi::c_void, value: Option<&[i8]>) -> i32"
        ),
        "{rust}"
    );
    assert!(rust.contains("if value.is_some() {"), "{rust}");
    assert!(
        rust.contains(
            "return fdb_kv_set_blob(db, key, fdb_blob_make(&mut blob, value.unwrap().as_ptr() as *const core::ffi::c_void, value.unwrap().iter().position(|&byte| byte == 0).expect(\"C strlen precondition violated\")));"
        ),
        "{rust}"
    );
    assert!(rust.contains("return fdb_kv_del(db, key);"), "{rust}");
    assert_rust_snippet_runs(
        "typed-ir-pointer-truthiness-blob-constructor-clang-size-t",
        &format!(
            "fn fdb_blob_make(blob: &mut FdbBlob, value: *const core::ffi::c_void, len: usize) -> *mut FdbBlob {{ blob.buf = value as *mut core::ffi::c_void; blob.size = len; blob as *mut FdbBlob }}\nfn fdb_kv_set_blob(_: *mut core::ffi::c_void, _: *const core::ffi::c_void, blob: *mut FdbBlob) -> i32 {{ unsafe {{ if blob.is_null() {{ -1i32 }} else {{ (*blob).size as i32 }} }} }}\nfn fdb_kv_del(_: *mut core::ffi::c_void, _: *const core::ffi::c_void) -> i32 {{ 7i32 }}\n{rust}"
        ),
        "let mut db = 0u8; assert_eq!(set_or_delete((&mut db as *mut u8).cast::<core::ffi::c_void>(), b\"boot\\0\".as_ptr().cast::<core::ffi::c_void>(), Some(&[49i8, 50i8, 51i8, 0i8])), 3i32); assert_eq!(set_or_delete((&mut db as *mut u8).cast::<core::ffi::c_void>(), b\"boot\\0\".as_ptr().cast::<core::ffi::c_void>(), None), 7i32);",
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_lvalue_wrapped_pointer_truthiness_blob_constructor() {
    let mut_void_ptr_ty = ir_pointer("void *", "void *", ir_void(), false);
    let char_ty = ir_integer("const char", "char", true, 8);
    let const_char_ptr_ty = ir_pointer("const char *", "char *", ir_const(char_ty), false);
    let clang_size_t_ty = ir_integer("__size_t", "__size_t", false, 64);
    let kvdb_ty = ir_record("fdb_kvdb");
    let kvdb_ptr_ty = ir_pointer("fdb_kvdb_t", "struct fdb_kvdb *", kvdb_ty, false);
    let blob_ty = ir_record_with_fields(
        "fdb_blob",
        vec![
            ("buf", mut_void_ptr_ty.clone()),
            ("size", clang_size_t_ty.clone()),
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
        name: "set_or_delete_lvalue_guard".to_string(),
        return_type: i32_ty.clone(),
        params: vec![
            IrParam {
                name: "db".to_string(),
                ty: kvdb_ptr_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "key".to_string(),
                ty: const_char_ptr_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "value".to_string(),
                ty: const_char_ptr_ty.clone(),
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
            IrStmt::If {
                condition: IrExpr::LValueToRValue {
                    target: const_char_ptr_ty.clone(),
                    expr: Box::new(ir_var("value", const_char_ptr_ty.clone())),
                    source_span: None,
                },
                then_body: vec![IrStmt::Return {
                    value: Some(IrExpr::Call {
                        callee: "fdb_kv_set_blob".to_string(),
                        args: vec![
                            ir_var("db", kvdb_ptr_ty.clone()),
                            ir_var("key", const_char_ptr_ty.clone()),
                            IrExpr::Call {
                                callee: "fdb_blob_make".to_string(),
                                args: vec![
                                    IrExpr::AddrOf {
                                        operand: Box::new(ir_var("blob", blob_ty)),
                                        ty: blob_ptr_ty.clone(),
                                        source_span: None,
                                    },
                                    ir_var("value", const_char_ptr_ty.clone()),
                                    IrExpr::Call {
                                        callee: "strlen".to_string(),
                                        args: vec![ir_var("value", const_char_ptr_ty.clone())],
                                        ty: clang_size_t_ty,
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
                }],
                else_body: vec![],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(IrExpr::Call {
                    callee: "fdb_kv_del".to_string(),
                    args: vec![ir_var("db", kvdb_ptr_ty), ir_var("key", const_char_ptr_ty)],
                    ty: i32_ty.clone(),
                    source_span: None,
                }),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir)
        .expect("emit lvalue-wrapped pointer truthiness blob constructor");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(
        rust.contains(
            "pub fn set_or_delete_lvalue_guard(db: *mut core::ffi::c_void, key: *const core::ffi::c_void, value: Option<&[i8]>) -> i32"
        ),
        "{rust}"
    );
    assert!(rust.contains("if value.is_some() {"), "{rust}");
    assert!(
        rust.contains(
            "return fdb_kv_set_blob(db, key, fdb_blob_make(&mut blob, value.unwrap().as_ptr() as *const core::ffi::c_void, value.unwrap().iter().position(|&byte| byte == 0).expect(\"C strlen precondition violated\")));"
        ),
        "{rust}"
    );
    assert!(rust.contains("return fdb_kv_del(db, key);"), "{rust}");
    assert_rust_snippet_runs(
        "typed-ir-lvalue-wrapped-pointer-truthiness-blob-constructor",
        &format!(
            "fn fdb_blob_make(blob: &mut FdbBlob, value: *const core::ffi::c_void, len: usize) -> *mut FdbBlob {{ blob.buf = value as *mut core::ffi::c_void; blob.size = len; blob as *mut FdbBlob }}\nfn fdb_kv_set_blob(_: *mut core::ffi::c_void, _: *const core::ffi::c_void, blob: *mut FdbBlob) -> i32 {{ unsafe {{ if blob.is_null() {{ -1i32 }} else {{ (*blob).size as i32 }} }} }}\nfn fdb_kv_del(_: *mut core::ffi::c_void, _: *const core::ffi::c_void) -> i32 {{ 7i32 }}\n{rust}"
        ),
        "let mut db = 0u8; assert_eq!(set_or_delete_lvalue_guard((&mut db as *mut u8).cast::<core::ffi::c_void>(), b\"boot\\0\".as_ptr().cast::<core::ffi::c_void>(), Some(&[49i8, 50i8, 51i8, 0i8])), 3i32); assert_eq!(set_or_delete_lvalue_guard((&mut db as *mut u8).cast::<core::ffi::c_void>(), b\"boot\\0\".as_ptr().cast::<core::ffi::c_void>(), None), 7i32);",
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_pointer_truthiness_blob_constructor_with_nested_blob_fields() {
    let mut_void_ptr_ty = ir_pointer("void *", "void *", ir_void(), false);
    let char_ty = ir_integer("const char", "char", true, 8);
    let const_char_ptr_ty = ir_pointer("const char *", "char *", ir_const(char_ty), false);
    let clang_size_t_ty = ir_integer("size_t", "size_t", false, 64);
    let clang_strlen_ty = ir_integer("unsigned long", "unsigned long", false, 64);
    let kvdb_ty = ir_record("fdb_kvdb");
    let kvdb_ptr_ty = ir_pointer("fdb_kvdb_t", "struct fdb_kvdb *", kvdb_ty, false);
    let saved_ty = ir_record_with_fields(
        "fdb_blob_saved",
        vec![
            ("meta_addr", ir_u32()),
            ("addr", ir_u32()),
            ("len", clang_size_t_ty.clone()),
        ],
    );
    let blob_ty = ir_record_with_fields(
        "fdb_blob",
        vec![
            ("buf", mut_void_ptr_ty.clone()),
            ("size", clang_size_t_ty.clone()),
            ("saved", saved_ty),
        ],
    );
    let blob_ptr_ty = ir_pointer(
        "struct fdb_blob *",
        "struct fdb_blob *",
        blob_ty.clone(),
        false,
    );
    let i32_ty = ir_integer("enum fdb_err_t", "int", true, 32);
    let ir = IrFunction {
        name: "set_or_delete_nested_blob".to_string(),
        return_type: i32_ty.clone(),
        params: vec![
            IrParam {
                name: "db".to_string(),
                ty: kvdb_ptr_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "key".to_string(),
                ty: const_char_ptr_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "value".to_string(),
                ty: const_char_ptr_ty.clone(),
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
            IrStmt::If {
                condition: ir_var("value", const_char_ptr_ty.clone()),
                then_body: vec![IrStmt::Return {
                    value: Some(IrExpr::Call {
                        callee: "fdb_kv_set_blob".to_string(),
                        args: vec![
                            ir_var("db", kvdb_ptr_ty.clone()),
                            ir_var("key", const_char_ptr_ty.clone()),
                            IrExpr::Call {
                                callee: "fdb_blob_make".to_string(),
                                args: vec![
                                    IrExpr::AddrOf {
                                        operand: Box::new(ir_var("blob", blob_ty)),
                                        ty: blob_ptr_ty.clone(),
                                        source_span: None,
                                    },
                                    ir_var("value", const_char_ptr_ty.clone()),
                                    IrExpr::Call {
                                        callee: "strlen".to_string(),
                                        args: vec![ir_var("value", const_char_ptr_ty.clone())],
                                        ty: clang_strlen_ty,
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
                }],
                else_body: vec![IrStmt::Return {
                    value: Some(IrExpr::Call {
                        callee: "fdb_kv_del".to_string(),
                        args: vec![ir_var("db", kvdb_ptr_ty), ir_var("key", const_char_ptr_ty)],
                        ty: i32_ty.clone(),
                        source_span: None,
                    }),
                    source_span: None,
                }],
                source_span: None,
            },
        ],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir)
        .expect("emit pointer truthiness blob constructor with nested blob fields");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(
        rust.contains(
            "pub fn set_or_delete_nested_blob(db: *mut core::ffi::c_void, key: *const core::ffi::c_void, value: Option<&[i8]>) -> i32"
        ),
        "{rust}"
    );
    assert!(rust.contains("pub struct FdbBlobSaved"), "{rust}");
    assert!(rust.contains("pub saved: FdbBlobSaved"), "{rust}");
    assert!(rust.contains("if value.is_some() {"), "{rust}");
    assert!(
        rust.contains(
            "return fdb_kv_set_blob(db, key, fdb_blob_make(&mut blob, value.unwrap().as_ptr() as *const core::ffi::c_void, value.unwrap().iter().position(|&byte| byte == 0).expect(\"C strlen precondition violated\")));"
        ),
        "{rust}"
    );
    assert!(rust.contains("return fdb_kv_del(db, key);"), "{rust}");
    assert_rust_snippet_runs(
        "typed-ir-pointer-truthiness-blob-constructor-nested-fields",
        &format!(
            "fn fdb_blob_make(blob: &mut FdbBlob, value: *const core::ffi::c_void, len: usize) -> *mut FdbBlob {{ blob.buf = value as *mut core::ffi::c_void; blob.size = len; blob as *mut FdbBlob }}\nfn fdb_kv_set_blob(_: *mut core::ffi::c_void, _: *const core::ffi::c_void, blob: *mut FdbBlob) -> i32 {{ unsafe {{ if blob.is_null() {{ -1i32 }} else {{ (*blob).size as i32 }} }} }}\nfn fdb_kv_del(_: *mut core::ffi::c_void, _: *const core::ffi::c_void) -> i32 {{ 7i32 }}\n{rust}"
        ),
        "let mut db = 0u8; assert_eq!(set_or_delete_nested_blob((&mut db as *mut u8).cast::<core::ffi::c_void>(), b\"boot\\0\".as_ptr().cast::<core::ffi::c_void>(), Some(&[49i8, 50i8, 51i8, 0i8])), 3i32); assert_eq!(set_or_delete_nested_blob((&mut db as *mut u8).cast::<core::ffi::c_void>(), b\"boot\\0\".as_ptr().cast::<core::ffi::c_void>(), None), 7i32);",
    );
}
