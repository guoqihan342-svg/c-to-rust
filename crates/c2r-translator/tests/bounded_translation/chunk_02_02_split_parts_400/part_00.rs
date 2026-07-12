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
fn typed_ir_runs_record_field_compound_rhs_from_readonly_record_pointer() {
    let usize_ty = ir_usize();
    let u32_ty = ir_u32();
    let quota_ty = ir_record_with_fields("renamed_quota", vec![("slots_left", usize_ty.clone())]);
    let quota_ptr_ty = ir_pointer(
        "struct renamed_quota *",
        "struct renamed_quota *",
        quota_ty,
        false,
    );
    let sample_ty = ir_record_with_fields("renamed_sample", vec![("slots_taken", u32_ty.clone())]);
    let sample_ptr_ty = ir_pointer(
        "const struct renamed_sample *",
        "const struct renamed_sample *",
        ir_const(sample_ty),
        true,
    );
    let target = IrExpr::Member {
        base: Box::new(ir_var("quota", quota_ptr_ty.clone())),
        field: "slots_left".to_string(),
        ty: usize_ty.clone(),
        is_arrow: true,
        source_span: None,
    };
    let rhs_member = IrExpr::Member {
        base: Box::new(ir_var("sample", sample_ptr_ty.clone())),
        field: "slots_taken".to_string(),
        ty: u32_ty.clone(),
        is_arrow: true,
        source_span: None,
    };
    let rhs = IrExpr::Cast {
        target: usize_ty.clone(),
        expr: Box::new(IrExpr::LValueToRValue {
            target: u32_ty,
            expr: Box::new(rhs_member),
            source_span: None,
        }),
        implicit: true,
        source_span: None,
    };
    let ir = IrFunction {
        name: "consume_readonly_sample".to_string(),
        return_type: ir_void(),
        params: vec![
            IrParam {
                name: "quota".to_string(),
                ty: quota_ptr_ty,
                source_span: None,
            },
            IrParam {
                name: "sample".to_string(),
                ty: sample_ptr_ty,
                source_span: None,
            },
        ],
        body: vec![IrStmt::Assign {
            target: target.clone(),
            value: ir_binary(IrBinOp::Sub, target, rhs, usize_ty),
            source_span: None,
        }],
        source_span: None,
    };

    let policy = EmitPolicy {
        noalias_param_pairs: vec![NoAliasParamPair {
            readonly_param: "sample".to_string(),
            mutable_param: "quota".to_string(),
        }],
        ..Default::default()
    };
    let emitted = emit_rust_from_ir_with_globals_and_policy(&ir, &[], policy)
        .expect("emit readonly record pointer scalar field compound RHS with noalias evidence");
    let rust = &emitted.rust;
    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(
        rust.contains(
            "quota.slots_left = quota.slots_left.wrapping_sub((sample.slots_taken as usize));"
        ),
        "{rust}"
    );
    assert_rust_snippet_runs(
        "typed-ir-readonly-record-field-compound-rhs",
        rust,
        r#"
let baseline = (u32::MAX as usize) + 23usize;
let mut quota = RenamedQuota { slots_left: baseline };
consume_readonly_sample(&mut quota, &RenamedSample { slots_taken: 0u32 });
assert_eq!(quota.slots_left, baseline);
consume_readonly_sample(&mut quota, &RenamedSample { slots_taken: u32::MAX });
assert_eq!(quota.slots_left, 23usize);
"#,
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_runs_record_field_compound_rhs_from_by_value_record() {
    let usize_ty = ir_usize();
    let u32_ty = ir_u32();
    let ledger_ty =
        ir_record_with_fields("renamed_ledger", vec![("credits_left", usize_ty.clone())]);
    let ledger_ptr_ty = ir_pointer(
        "struct renamed_ledger *",
        "struct renamed_ledger *",
        ledger_ty,
        false,
    );
    let debit_ty = ir_record_with_fields("renamed_debit", vec![("credits_used", u32_ty.clone())]);
    let target = IrExpr::Member {
        base: Box::new(ir_var("ledger", ledger_ptr_ty.clone())),
        field: "credits_left".to_string(),
        ty: usize_ty.clone(),
        is_arrow: true,
        source_span: None,
    };
    let rhs = IrExpr::Cast {
        target: usize_ty.clone(),
        expr: Box::new(IrExpr::LValueToRValue {
            target: u32_ty.clone(),
            expr: Box::new(IrExpr::Member {
                base: Box::new(ir_var("debit", debit_ty.clone())),
                field: "credits_used".to_string(),
                ty: u32_ty,
                is_arrow: false,
                source_span: None,
            }),
            source_span: None,
        }),
        implicit: false,
        source_span: None,
    };
    let ir = IrFunction {
        name: "apply_renamed_debit".to_string(),
        return_type: ir_void(),
        params: vec![
            IrParam {
                name: "ledger".to_string(),
                ty: ledger_ptr_ty,
                source_span: None,
            },
            IrParam {
                name: "debit".to_string(),
                ty: debit_ty,
                source_span: None,
            },
        ],
        body: vec![IrStmt::Assign {
            target: target.clone(),
            value: ir_binary(IrBinOp::Sub, target, rhs, usize_ty),
            source_span: None,
        }],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit by-value record scalar field compound RHS");
    let rust = &emitted.rust;
    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(
        rust.contains(
            "ledger.credits_left = ledger.credits_left.wrapping_sub((debit.credits_used as usize));"
        ),
        "{rust}"
    );
    assert_rust_snippet_runs(
        "typed-ir-by-value-record-field-compound-rhs",
        rust,
        r#"
let baseline = (u32::MAX as usize) + 29usize;
let mut ledger = RenamedLedger { credits_left: baseline };
apply_renamed_debit(&mut ledger, RenamedDebit { credits_used: 0u32 });
assert_eq!(ledger.credits_left, baseline);
apply_renamed_debit(&mut ledger, RenamedDebit { credits_used: u32::MAX });
assert_eq!(ledger.credits_left, 29usize);
"#,
    );
}
