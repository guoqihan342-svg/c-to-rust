#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_prefix_dec_statement_for_usize_scalar() {
    let usize_ty = ir_usize();
    let ir = IrFunction {
        name: "prefix_dec_usize".to_string(),
        return_type: ir_void(),
        params: vec![IrParam {
            name: "count".to_string(),
            ty: usize_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Expr {
            expr: IrExpr::IncDec {
                target: Box::new(ir_var("count", usize_ty.clone())),
                op: IrIncDecOp::Dec,
                prefix: true,
                ty: usize_ty.clone(),
                source_span: None,
            },
            source_span: None,
        }],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit prefix dec statement for usize scalar");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub fn prefix_dec_usize(mut count: usize)"));
    assert!(rust.contains("count = count.wrapping_sub(1usize);"));
    assert_rust_snippet_compiles("typed-ir-prefix-dec-usize", rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_prefix_inc_dec_statement_for_mutable_record_pointer_field() {
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
        name: "prefix_inc_member".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "p".to_string(),
            ty: point_ptr_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::Expr {
                expr: IrExpr::IncDec {
                    target: Box::new(member_target.clone()),
                    op: IrIncDecOp::Inc,
                    prefix: true,
                    ty: i32_ty.clone(),
                    source_span: None,
                },
                source_span: None,
            },
            IrStmt::Return {
                value: Some(member_target),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let emitted =
        emit_rust_from_ir(&ir).expect("emit prefix inc statement for record pointer field");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub fn prefix_inc_member(p: &mut Point) -> i32"));
    assert!(rust.contains("p.x = p.x.checked_add(1i32).expect(\"signed addition overflow\");"));
    assert_rust_snippet_runs(
        "typed-ir-prefix-inc-member-statement",
        rust,
        "    let mut point = Point { x: 5 };
    assert_eq!(prefix_inc_member(&mut point), 6);
    assert_eq!(point.x, 6);",
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_postfix_inc_dec_statement_for_mutable_record_pointer_field() {
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
        name: "postfix_inc_member_statement".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "p".to_string(),
            ty: point_ptr_ty,
            source_span: None,
        }],
        body: vec![
            IrStmt::Expr {
                expr: IrExpr::IncDec {
                    target: Box::new(member_target.clone()),
                    op: IrIncDecOp::Inc,
                    prefix: false,
                    ty: i32_ty.clone(),
                    source_span: None,
                },
                source_span: None,
            },
            IrStmt::Return {
                value: Some(member_target),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let emitted =
        emit_rust_from_ir(&ir).expect("emit postfix inc statement for record pointer field");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub fn postfix_inc_member_statement(p: &mut Point) -> i32"));
    assert!(rust.contains("p.x = p.x.checked_add(1i32).expect(\"signed addition overflow\");"));
    assert!(!rust.contains("post_inc_value"), "{rust}");
    assert_rust_snippet_runs(
        "typed-ir-postfix-inc-member-statement",
        rust,
        "    let mut point = Point { x: 5 };
    assert_eq!(postfix_inc_member_statement(&mut point), 6);
    assert_eq!(point.x, 6);",
    );
}
