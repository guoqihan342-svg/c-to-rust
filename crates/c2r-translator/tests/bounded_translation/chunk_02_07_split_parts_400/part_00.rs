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
fn typed_ir_emits_prefix_inc_value_decl_initializer_for_mutable_record_pointer_field() {
    let i32_ty = ir_i32();
    let point_ty = ir_record_with_fields("point", vec![("x", i32_ty.clone())]);
    let point_ptr_ty = ir_pointer("struct point *", "struct point *", point_ty, false);
    let member_target = IrExpr::Member {
        base: Box::new(ir_var("p", point_ptr_ty.clone())),
        field: "x".to_string(),
        ty: i32_ty.clone(),
        is_arrow: true,
        source_span: None,
    };
    let ir = IrFunction {
        name: "prefix_inc_member_value_decl".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "p".to_string(),
            ty: point_ptr_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::Decl {
                name: "out".to_string(),
                ty: i32_ty.clone(),
                init: Some(IrExpr::IncDec {
                    target: Box::new(member_target.clone()),
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
                    IrExpr::Member {
                        base: Box::new(ir_var("p", point_ptr_ty)),
                        field: "x".to_string(),
                        ty: i32_ty.clone(),
                        is_arrow: true,
                        source_span: None,
                    },
                    i32_ty.clone(),
                )),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let emitted =
        emit_rust_from_ir(&ir).expect("emit prefix inc value for mutable record pointer field");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub fn prefix_inc_member_value_decl(p: &mut Point) -> i32"));
    assert!(rust.contains("p.x = p.x.checked_add(1i32).expect(\"signed addition overflow\");"));
    assert!(rust.contains("let mut out: i32 = p.x;"), "{rust}");
    assert_rust_snippet_runs(
        "typed-ir-prefix-inc-member-value-decl",
        rust,
        "    let mut point = Point { x: 5 };
    assert_eq!(prefix_inc_member_value_decl(&mut point), 12);
    assert_eq!(point.x, 6);",
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_postfix_inc_value_decl_initializer_for_mutable_record_pointer_field() {
    let i32_ty = ir_i32();
    let point_ty = ir_record_with_fields("point", vec![("x", i32_ty.clone())]);
    let point_ptr_ty = ir_pointer("struct point *", "struct point *", point_ty, false);
    let member_target = IrExpr::Member {
        base: Box::new(ir_var("p", point_ptr_ty.clone())),
        field: "x".to_string(),
        ty: i32_ty.clone(),
        is_arrow: true,
        source_span: None,
    };
    let ir = IrFunction {
        name: "postfix_inc_member_value_decl".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "p".to_string(),
            ty: point_ptr_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::Decl {
                name: "out".to_string(),
                ty: i32_ty.clone(),
                init: Some(IrExpr::IncDec {
                    target: Box::new(member_target.clone()),
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
                    IrExpr::Member {
                        base: Box::new(ir_var("p", point_ptr_ty)),
                        field: "x".to_string(),
                        ty: i32_ty.clone(),
                        is_arrow: true,
                        source_span: None,
                    },
                    i32_ty.clone(),
                )),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let emitted =
        emit_rust_from_ir(&ir).expect("emit postfix inc value for mutable record pointer field");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub fn postfix_inc_member_value_decl(p: &mut Point) -> i32"));
    assert!(rust.contains("let post_inc_value: i32 = p.x;"), "{rust}");
    assert!(rust.contains("p.x = p.x.checked_add(1i32).expect(\"signed addition overflow\");"));
    assert!(rust.contains("let mut out: i32 = post_inc_value;"), "{rust}");
    assert_rust_snippet_runs(
        "typed-ir-postfix-inc-member-value-decl",
        rust,
        "    let mut point = Point { x: 5 };
    assert_eq!(postfix_inc_member_value_decl(&mut point), 11);
    assert_eq!(point.x, 6);",
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_postfix_inc_direct_call_arg_for_mutable_record_pointer_field() {
    let i32_ty = ir_i32();
    let point_ty = ir_record_with_fields("point", vec![("x", i32_ty.clone())]);
    let point_ptr_ty = ir_pointer("struct point *", "struct point *", point_ty, false);
    let member_target = IrExpr::Member {
        base: Box::new(ir_var("p", point_ptr_ty.clone())),
        field: "x".to_string(),
        ty: i32_ty.clone(),
        is_arrow: true,
        source_span: None,
    };
    let ir = IrFunction {
        name: "postfix_inc_member_direct_call_arg".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "p".to_string(),
            ty: point_ptr_ty,
            source_span: None,
        }],
        body: vec![
            IrStmt::Return {
                value: Some(IrExpr::Call {
                    callee: "observe".to_string(),
                    args: vec![IrExpr::IncDec {
                        target: Box::new(member_target),
                        op: IrIncDecOp::Inc,
                        prefix: false,
                        ty: i32_ty.clone(),
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
        emit_rust_from_ir(&ir).expect("emit postfix inc direct call arg for record pointer field");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("let post_inc_value: i32 = p.x;"), "{rust}");
    assert!(rust.contains("p.x = p.x.checked_add(1i32).expect(\"signed addition overflow\");"));
    assert!(rust.contains("return observe(post_inc_value);"), "{rust}");
    assert_rust_snippet_runs(
        "typed-ir-postfix-inc-member-direct-call-arg",
        &format!("fn observe(value: i32) -> i32 {{ value * 2 }}\n{rust}"),
        "    let mut point = Point { x: 5 };
    assert_eq!(postfix_inc_member_direct_call_arg(&mut point), 10);
    assert_eq!(point.x, 6);",
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_member_inc_dec_value_when_sibling_reads_same_record_pointer_base() {
    let i32_ty = ir_i32();
    let point_ty = ir_record_with_fields("point", vec![("x", i32_ty.clone())]);
    let point_ptr_ty = ir_pointer("struct point *", "struct point *", point_ty, false);
    let member_target = IrExpr::Member {
        base: Box::new(ir_var("p", point_ptr_ty.clone())),
        field: "x".to_string(),
        ty: i32_ty.clone(),
        is_arrow: true,
        source_span: None,
    };
    let ir = IrFunction {
        name: "bad_member_inc_dec_order".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "p".to_string(),
            ty: point_ptr_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::Return {
                value: Some(ir_binary(
                    IrBinOp::Add,
                    IrExpr::IncDec {
                        target: Box::new(member_target),
                        op: IrIncDecOp::Inc,
                        prefix: false,
                        ty: i32_ty.clone(),
                        source_span: None,
                    },
                    IrExpr::Member {
                        base: Box::new(ir_var("p", point_ptr_ty)),
                        field: "x".to_string(),
                        ty: i32_ty.clone(),
                        is_arrow: true,
                        source_span: None,
                    },
                    i32_ty.clone(),
                )),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir)
        .expect_err("member inc/dec next to same-base read must fail closed");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(
        error
            .reason
            .contains("binary rhs reads variable p modified by lhs side-effect expression"),
        "{}",
        error.reason
    );
}
