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
