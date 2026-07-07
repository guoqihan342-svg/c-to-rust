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
fn typed_ir_rejects_readonly_input_and_mutable_output_index_assignment_without_noalias_proof() {
    let i32_ty = ir_i32();
    let usize_ty = ir_usize();
    let const_i32_ptr = ir_pointer(
        "const int *",
        "const int *",
        ir_const(i32_ty.clone()),
        false,
    );
    let mutable_i32_ptr = ir_pointer("int *", "int *", i32_ty.clone(), false);
    let ir = IrFunction {
        name: "copy_one".to_string(),
        return_type: i32_ty.clone(),
        params: vec![
            IrParam {
                name: "values".to_string(),
                ty: const_i32_ptr.clone(),
                source_span: None,
            },
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
        ],
        body: vec![
            IrStmt::Assign {
                target: IrExpr::Index {
                    base: Box::new(ir_var("out", mutable_i32_ptr)),
                    index: Box::new(ir_var("i", usize_ty.clone())),
                    ty: i32_ty.clone(),
                    source_span: None,
                },
                value: IrExpr::Index {
                    base: Box::new(ir_var("values", const_i32_ptr)),
                    index: Box::new(ir_var("i", usize_ty)),
                    ty: i32_ty.clone(),
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

    let error =
        emit_rust_from_ir(&ir).expect_err("readonly input plus mutable output needs noalias proof");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(
        error
            .reason
            .contains("mutable pointer write with readonly pointer read requires noalias proof"),
        "unexpected reason: {}",
        error.reason
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_readonly_input_and_mutable_output_index_assignment_with_restrict_noalias_proof() {
    let i32_ty = ir_i32();
    let usize_ty = ir_usize();
    let const_i32_ptr = ir_pointer(
        "const int *restrict",
        "const int *restrict",
        ir_const(i32_ty.clone()),
        false,
    );
    let mutable_i32_ptr = ir_pointer("int *restrict", "int *restrict", i32_ty.clone(), false);
    let ir = IrFunction {
        name: "copy_one_restrict".to_string(),
        return_type: i32_ty.clone(),
        params: vec![
            IrParam {
                name: "values".to_string(),
                ty: const_i32_ptr.clone(),
                source_span: None,
            },
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
        ],
        body: vec![
            IrStmt::Assign {
                target: IrExpr::Index {
                    base: Box::new(ir_var("out", mutable_i32_ptr)),
                    index: Box::new(ir_var("i", usize_ty.clone())),
                    ty: i32_ty.clone(),
                    source_span: None,
                },
                value: IrExpr::Index {
                    base: Box::new(ir_var("values", const_i32_ptr)),
                    index: Box::new(ir_var("i", usize_ty)),
                    ty: i32_ty.clone(),
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

    let emitted = emit_rust_from_ir(&ir).expect("restrict params provide noalias proof");

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(emitted.rust.contains(
        "pub fn copy_one_restrict(values: &[i32], mut out: &mut [i32], i: usize) -> i32"
    ));
    assert!(emitted
        .rust
        .contains("out[i as usize] = values[i as usize];"));
    assert_rust_snippet_compiles("typed-ir-readonly-mutable-restrict-copy-one", &emitted.rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_readonly_input_and_mutable_output_index_assignment_with_policy_noalias_pair() {
    let i32_ty = ir_i32();
    let usize_ty = ir_usize();
    let const_i32_ptr = ir_pointer(
        "const int *",
        "const int *",
        ir_const(i32_ty.clone()),
        false,
    );
    let mutable_i32_ptr = ir_pointer("int *", "int *", i32_ty.clone(), false);
    let ir = IrFunction {
        name: "copy_one_policy_noalias".to_string(),
        return_type: i32_ty.clone(),
        params: vec![
            IrParam {
                name: "values".to_string(),
                ty: const_i32_ptr.clone(),
                source_span: None,
            },
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
        ],
        body: vec![
            IrStmt::Assign {
                target: IrExpr::Index {
                    base: Box::new(ir_var("out", mutable_i32_ptr)),
                    index: Box::new(ir_var("i", usize_ty.clone())),
                    ty: i32_ty.clone(),
                    source_span: None,
                },
                value: IrExpr::Index {
                    base: Box::new(ir_var("values", const_i32_ptr)),
                    index: Box::new(ir_var("i", usize_ty)),
                    ty: i32_ty.clone(),
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
    let policy = EmitPolicy {
        noalias_param_pairs: vec![NoAliasParamPair {
            readonly_param: "values".to_string(),
            mutable_param: "out".to_string(),
        }],
        ..Default::default()
    };

    let emitted = emit_rust_from_ir_with_globals_and_policy(&ir, &[], policy)
        .expect("explicit policy noalias pair should allow safe slice lowering");

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(emitted.rust.contains(
        "pub fn copy_one_policy_noalias(values: &[i32], mut out: &mut [i32], i: usize) -> i32"
    ));
    assert!(emitted
        .rust
        .contains("out[i as usize] = values[i as usize];"));
    assert_rust_snippet_compiles(
        "typed-ir-readonly-mutable-policy-noalias-copy-one",
        &emitted.rust,
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_readonly_deref_and_mutable_output_assignment_without_noalias_proof() {
    let i32_ty = ir_i32();
    let const_i32_ptr = ir_pointer(
        "const int *",
        "const int *",
        ir_const(i32_ty.clone()),
        false,
    );
    let mutable_i32_ptr = ir_pointer("int *", "int *", i32_ty.clone(), false);
    let ir = IrFunction {
        name: "copy_first".to_string(),
        return_type: ir_void(),
        params: vec![
            IrParam {
                name: "values".to_string(),
                ty: const_i32_ptr.clone(),
                source_span: None,
            },
            IrParam {
                name: "out".to_string(),
                ty: mutable_i32_ptr.clone(),
                source_span: None,
            },
        ],
        body: vec![
            IrStmt::Assign {
                target: IrExpr::Index {
                    base: Box::new(ir_var("out", mutable_i32_ptr)),
                    index: Box::new(ir_lit(0, "0", i32_ty.clone())),
                    ty: i32_ty.clone(),
                    source_span: None,
                },
                value: ir_deref(ir_var("values", const_i32_ptr), i32_ty),
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
        emit_rust_from_ir(&ir).expect_err("readonly deref plus mutable output needs noalias proof");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(
        error
            .reason
            .contains("mutable pointer write with readonly pointer read requires noalias proof"),
        "unexpected reason: {}",
        error.reason
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_readonly_deref_and_mutable_output_assignment_with_restrict_noalias_proof() {
    let i32_ty = ir_i32();
    let const_i32_ptr = ir_pointer(
        "const int *restrict",
        "const int *restrict",
        ir_const(i32_ty.clone()),
        false,
    );
    let mutable_i32_ptr = ir_pointer("int *restrict", "int *restrict", i32_ty.clone(), false);
    let ir = IrFunction {
        name: "copy_first_restrict".to_string(),
        return_type: ir_void(),
        params: vec![
            IrParam {
                name: "values".to_string(),
                ty: const_i32_ptr.clone(),
                source_span: None,
            },
            IrParam {
                name: "out".to_string(),
                ty: mutable_i32_ptr.clone(),
                source_span: None,
            },
        ],
        body: vec![
            IrStmt::Assign {
                target: IrExpr::Index {
                    base: Box::new(ir_var("out", mutable_i32_ptr)),
                    index: Box::new(ir_lit(0, "0", i32_ty.clone())),
                    ty: i32_ty.clone(),
                    source_span: None,
                },
                value: ir_deref(ir_var("values", const_i32_ptr), i32_ty),
                source_span: None,
            },
            IrStmt::Return {
                value: None,
                source_span: None,
            },
        ],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("restrict params provide noalias proof");

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(emitted
        .rust
        .contains("pub fn copy_first_restrict(values: &[i32], mut out: &mut [i32])"));
    assert!(emitted
        .rust
        .contains("out[0i32 as usize] = values[0usize];"));
    assert_rust_snippet_compiles(
        "typed-ir-readonly-deref-mutable-restrict-copy-first",
        &emitted.rust,
    );
}
