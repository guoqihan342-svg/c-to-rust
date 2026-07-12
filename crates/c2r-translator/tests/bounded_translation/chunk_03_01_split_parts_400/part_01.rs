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
fn typed_ir_rejects_multiple_mutable_pointer_index_compound_shapes_without_alias_proof() {
    let i32_ty = ir_i32();
    let mutable_i32_ptr = ir_pointer("int *", "int *", i32_ty.clone(), false);
    let index = |name: &str| IrExpr::Index {
        base: Box::new(ir_var(name, mutable_i32_ptr.clone())),
        index: Box::new(ir_lit(0, "0", i32_ty.clone())),
        ty: i32_ty.clone(),
        source_span: None,
    };
    let left_target = index("left");
    let right_target = index("right");
    let ir = IrFunction {
        name: "reject_two_compound_writes".to_string(),
        return_type: ir_void(),
        params: vec![
            IrParam {
                name: "left".to_string(),
                ty: mutable_i32_ptr.clone(),
                source_span: None,
            },
            IrParam {
                name: "right".to_string(),
                ty: mutable_i32_ptr,
                source_span: None,
            },
        ],
        body: vec![
            IrStmt::Assign {
                target: left_target.clone(),
                value: ir_binary(
                    IrBinOp::BitAnd,
                    left_target,
                    ir_lit(7, "7", i32_ty.clone()),
                    i32_ty.clone(),
                ),
                source_span: None,
            },
            IrStmt::Assign {
                target: right_target.clone(),
                value: ir_binary(
                    IrBinOp::BitOr,
                    right_target,
                    ir_lit(8, "8", i32_ty.clone()),
                    i32_ty,
                ),
                source_span: None,
            },
            IrStmt::Return {
                value: None,
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir)
        .expect_err("multiple mutable pointer compound writes need alias proof");

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
    let mutable_i32_restrict_ptr =
        ir_pointer("int *restrict", "int *restrict", i32_ty.clone(), false);
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

    let emitted =
        emit_rust_from_ir(&ir).expect("restrict params provide multi-output noalias proof");
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
