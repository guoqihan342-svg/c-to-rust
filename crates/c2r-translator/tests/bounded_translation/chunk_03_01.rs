#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_readonly_pointer_add_deref_result_type_mismatch() {
    let i32_ty = ir_i32();
    let u8_ty = ir_u8();
    let usize_ty = ir_usize();
    let const_u8_ty = ir_const(u8_ty);
    let const_u8_ptr_ty = ir_pointer("const uint8_t *", "uint8_t *", const_u8_ty, false);
    let ptr_plus_index = ir_binary(
        IrBinOp::Add,
        ir_var("p", const_u8_ptr_ty.clone()),
        ir_var("i", usize_ty.clone()),
        const_u8_ptr_ty.clone(),
    );
    let ir = IrFunction {
        name: "bad_deref_result_type".to_string(),
        return_type: i32_ty.clone(),
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
            value: Some(ir_deref(ptr_plus_index, i32_ty)),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("deref result type mismatch must fail closed");

    assert!(error
        .reason
        .contains("deref result type i32 does not match pointer element type u8"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_local_fixed_array_index_assignment() {
    let u32_ty = ir_u32();
    let usize_ty = ir_usize();
    let table_ty = ir_array(u32_ty.clone(), 3);
    let table_var = || ir_var("table", table_ty.clone());
    let index_var = || ir_var("i", usize_ty.clone());
    let ir = IrFunction {
        name: "replace_local_table_slot".to_string(),
        return_type: u32_ty.clone(),
        params: vec![
            IrParam {
                name: "i".to_string(),
                ty: usize_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "value".to_string(),
                ty: u32_ty.clone(),
                source_span: None,
            },
        ],
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
            IrStmt::Assign {
                target: IrExpr::Index {
                    base: Box::new(table_var()),
                    index: Box::new(index_var()),
                    ty: u32_ty.clone(),
                    source_span: None,
                },
                value: ir_var("value", u32_ty.clone()),
                source_span: None,
            },
            IrStmt::Return {
                value: Some(IrExpr::Index {
                    base: Box::new(table_var()),
                    index: Box::new(index_var()),
                    ty: u32_ty,
                    source_span: None,
                }),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit local fixed array index assignment");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("let mut table: [u32; 3] = [1u32, 2u32, 3u32];"));
    assert!(rust.contains("table[i as usize] = value;"));
    assert!(rust.contains("return table[i as usize];"));
    assert_rust_snippet_compiles("typed-ir-local-fixed-array-index-assignment", rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_readonly_global_array_index_assignment() {
    let u32_ty = ir_u32();
    let usize_ty = ir_usize();
    let global = ir_u32_global_array("table", 3, vec![1, 2, 3]);
    let ir = IrFunction {
        name: "write_global_table".to_string(),
        return_type: u32_ty.clone(),
        params: vec![IrParam {
            name: "i".to_string(),
            ty: usize_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::Assign {
                target: IrExpr::Index {
                    base: Box::new(ir_var("table", global.ty.clone())),
                    index: Box::new(ir_var("i", usize_ty)),
                    ty: u32_ty.clone(),
                    source_span: None,
                },
                value: ir_lit(0, "0U", u32_ty.clone()),
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_lit(0, "0U", u32_ty)),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error = emit_rust_from_ir_with_globals(&ir, &[global])
        .expect_err("readonly global array assignment must fail closed");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(error.reason.contains("assign index base table"));
    assert!(error.reason.contains("readonly global"));
}
#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_const_pointer_index_assignment() {
    let u32_ty = ir_u32();
    let usize_ty = ir_usize();
    let const_u32_ptr = ir_pointer(
        "const uint32_t *",
        "const unsigned int *",
        ir_const(u32_ty.clone()),
        false,
    );
    let ir = IrFunction {
        name: "write_const_pointer_slot".to_string(),
        return_type: u32_ty.clone(),
        params: vec![
            IrParam {
                name: "table".to_string(),
                ty: const_u32_ptr.clone(),
                source_span: None,
            },
            IrParam {
                name: "i".to_string(),
                ty: usize_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![
            IrStmt::Assign {
                target: IrExpr::Index {
                    base: Box::new(ir_var("table", const_u32_ptr)),
                    index: Box::new(ir_var("i", usize_ty)),
                    ty: u32_ty.clone(),
                    source_span: None,
                },
                value: ir_lit(0, "0U", u32_ty.clone()),
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_lit(0, "0U", u32_ty)),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error =
        emit_rust_from_ir(&ir).expect_err("const pointer index assignment must fail closed");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(error.reason.contains("assign index base table"));
    assert!(error.reason.contains("unsupported type"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_mutable_pointer_deref_assignment_as_mut_slice_zero_index() {
    let i32_ty = ir_i32();
    let mutable_i32_ptr = ir_pointer("int *", "int *", i32_ty.clone(), false);
    let ir = IrFunction {
        name: "store_first".to_string(),
        return_type: ir_void(),
        params: vec![
            IrParam {
                name: "out".to_string(),
                ty: mutable_i32_ptr.clone(),
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
                target: ir_deref(ir_var("out", mutable_i32_ptr), i32_ty.clone()),
                value: ir_var("value", i32_ty),
                source_span: None,
            },
            IrStmt::Return {
                value: None,
                source_span: None,
            },
        ],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit mutable pointer deref assignment");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub fn store_first(mut out: &mut [i32], value: i32)"));
    assert!(rust.contains("out[0usize] = value;"));
    assert_rust_snippet_compiles("typed-ir-mutable-pointer-deref-assignment", rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_mutable_pointer_deref_read_after_write() {
    let i32_ty = ir_i32();
    let mutable_i32_ptr = ir_pointer("int *", "int *", i32_ty.clone(), false);
    let ir = IrFunction {
        name: "store_and_read_first".to_string(),
        return_type: i32_ty.clone(),
        params: vec![
            IrParam {
                name: "out".to_string(),
                ty: mutable_i32_ptr.clone(),
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
                target: ir_deref(ir_var("out", mutable_i32_ptr.clone()), i32_ty.clone()),
                value: ir_var("value", i32_ty.clone()),
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_deref(ir_var("out", mutable_i32_ptr), i32_ty)),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit mutable pointer deref read after write");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub fn store_and_read_first(mut out: &mut [i32], value: i32) -> i32"));
    assert!(rust.contains("out[0usize] = value;"));
    assert!(rust.contains("return out[0usize];"));
    assert_rust_snippet_compiles("typed-ir-mutable-pointer-deref-read-after-write", rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_mutable_pointer_deref_read_before_definite_write() {
    let i32_ty = ir_i32();
    let mutable_i32_ptr = ir_pointer("int *", "int *", i32_ty.clone(), false);
    let ir = IrFunction {
        name: "maybe_store_then_read_first".to_string(),
        return_type: i32_ty.clone(),
        params: vec![
            IrParam {
                name: "out".to_string(),
                ty: mutable_i32_ptr.clone(),
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
                    target: ir_deref(ir_var("out", mutable_i32_ptr.clone()), i32_ty.clone()),
                    value: ir_var("value", i32_ty.clone()),
                    source_span: None,
                }],
                else_body: vec![],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_deref(ir_var("out", mutable_i32_ptr), i32_ty)),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error =
        emit_rust_from_ir(&ir).expect_err("mutable pointer read before write must fail closed");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(
        error
            .reason
            .contains("mutable pointer slot out[0] is read before definite assignment"),
        "unexpected reason: {}",
        error.reason
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_mutable_pointer_index_assignment() {
    let i32_ty = ir_i32();
    let usize_ty = ir_usize();
    let mutable_i32_ptr = ir_pointer("int *", "int *", i32_ty.clone(), false);
    let ir = IrFunction {
        name: "store_at".to_string(),
        return_type: ir_void(),
        params: vec![
            IrParam {
                name: "out".to_string(),
                ty: mutable_i32_ptr.clone(),
                source_span: None,
            },
            IrParam {
                name: "i".to_string(),
                ty: usize_ty.clone(),
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
                target: IrExpr::Index {
                    base: Box::new(ir_var("out", mutable_i32_ptr)),
                    index: Box::new(ir_var("i", usize_ty)),
                    ty: i32_ty.clone(),
                    source_span: None,
                },
                value: ir_var("value", i32_ty),
                source_span: None,
            },
            IrStmt::Return {
                value: None,
                source_span: None,
            },
        ],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit mutable pointer index assignment");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub fn store_at(mut out: &mut [i32], i: usize, value: i32)"));
    assert!(rust.contains("out[i as usize] = value;"));
    assert_rust_snippet_compiles("typed-ir-mutable-pointer-index-assignment", rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_nullable_mutable_pointer_index_assignment() {
    let i32_ty = ir_i32();
    let mutable_i32_ptr = ir_pointer("int *", "int *", i32_ty.clone(), false);
    let ir = IrFunction {
        name: "bad_nullable_out_write".to_string(),
        return_type: i32_ty.clone(),
        params: vec![
            IrParam {
                name: "out".to_string(),
                ty: mutable_i32_ptr.clone(),
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
                    ir_var("out", mutable_i32_ptr.clone()),
                    ir_null_ptr(mutable_i32_ptr.clone()),
                    i32_ty.clone(),
                ),
                then_body: vec![IrStmt::Return {
                    value: Some(ir_lit(-1i64 as u64, "-1", i32_ty.clone())),
                    source_span: None,
                }],
                else_body: vec![],
                source_span: None,
            },
            IrStmt::Assign {
                target: IrExpr::Index {
                    base: Box::new(ir_var("out", mutable_i32_ptr)),
                    index: Box::new(ir_lit(0, "0", i32_ty.clone())),
                    ty: i32_ty.clone(),
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

    let error =
        emit_rust_from_ir(&ir).expect_err("nullable mutable pointer write must fail closed");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(
        error
            .reason
            .contains("nullable mutable pointer param out cannot be lowered to &mut [T]"),
        "unexpected reason: {}",
        error.reason
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_multiple_mutable_pointer_index_assignments_without_alias_proof() {
    let i32_ty = ir_i32();
    let mutable_i32_ptr = ir_pointer("int *", "int *", i32_ty.clone(), false);
    let ir = IrFunction {
        name: "bad_two_out_writes".to_string(),
        return_type: ir_void(),
        params: vec![
            IrParam {
                name: "left".to_string(),
                ty: mutable_i32_ptr.clone(),
                source_span: None,
            },
            IrParam {
                name: "right".to_string(),
                ty: mutable_i32_ptr.clone(),
                source_span: None,
            },
        ],
        body: vec![
            IrStmt::Assign {
                target: IrExpr::Index {
                    base: Box::new(ir_var("left", mutable_i32_ptr.clone())),
                    index: Box::new(ir_lit(0, "0", i32_ty.clone())),
                    ty: i32_ty.clone(),
                    source_span: None,
                },
                value: ir_lit(1, "1", i32_ty.clone()),
                source_span: None,
            },
            IrStmt::Assign {
                target: IrExpr::Index {
                    base: Box::new(ir_var("right", mutable_i32_ptr)),
                    index: Box::new(ir_lit(0, "0", i32_ty.clone())),
                    ty: i32_ty.clone(),
                    source_span: None,
                },
                value: ir_lit(2, "2", i32_ty.clone()),
                source_span: None,
            },
            IrStmt::Return {
                value: None,
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error =
        emit_rust_from_ir(&ir).expect_err("multiple mutable pointer writes need alias proof");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(
        error
            .reason
            .contains("mutable pointer write requires exactly one pointer param for alias proof"),
        "unexpected reason: {}",
        error.reason
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_multiple_restrict_mutable_out_pointer_writes() {
    let i32_ty = ir_i32();
    let mutable_i32_restrict_ptr = ir_pointer("int *restrict", "int *restrict", i32_ty.clone(), false);
    let ir = IrFunction {
        name: "store_pair_restrict".to_string(),
        return_type: ir_void(),
        params: vec![
            IrParam {
                name: "left".to_string(),
                ty: mutable_i32_restrict_ptr.clone(),
                source_span: None,
            },
            IrParam {
                name: "right".to_string(),
                ty: mutable_i32_restrict_ptr.clone(),
                source_span: None,
            },
            IrParam {
                name: "first".to_string(),
                ty: i32_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "second".to_string(),
                ty: i32_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![
            IrStmt::Assign {
                target: IrExpr::Index {
                    base: Box::new(ir_var("left", mutable_i32_restrict_ptr.clone())),
                    index: Box::new(ir_lit(0, "0", i32_ty.clone())),
                    ty: i32_ty.clone(),
                    source_span: None,
                },
                value: ir_var("first", i32_ty.clone()),
                source_span: None,
            },
            IrStmt::Assign {
                target: IrExpr::Index {
                    base: Box::new(ir_var("right", mutable_i32_restrict_ptr)),
                    index: Box::new(ir_lit(0, "0", i32_ty.clone())),
                    ty: i32_ty.clone(),
                    source_span: None,
                },
                value: ir_var("second", i32_ty.clone()),
                source_span: None,
            },
            IrStmt::Return {
                value: None,
                source_span: None,
            },
        ],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("restrict params provide multi-output noalias proof");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains(
        "pub fn store_pair_restrict(mut left: &mut [i32], mut right: &mut [i32], first: i32, second: i32)"
    ));
    assert!(rust.contains("left[0i32 as usize] = first;"));
    assert!(rust.contains("right[0i32 as usize] = second;"));
    assert_rust_snippet_runs(
        "typed-ir-multiple-restrict-mutable-out-pointer-writes",
        rust,
        r#"
    let mut left = [0i32];
    let mut right = [0i32];
    store_pair_restrict(&mut left, &mut right, 11, 22);
    assert_eq!(left[0], 11);
    assert_eq!(right[0], 22);
"#,
    );
}
