#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_prefix_inc_value_decl_initializer_for_i32_scalar() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "prefix_inc_value_decl".to_string(),
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
                    ir_var("value", i32_ty.clone()),
                    i32_ty.clone(),
                )),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit prefix inc value decl initializer");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub fn prefix_inc_value_decl(mut value: i32) -> i32"));
    assert!(rust.contains("value = value.checked_add(1i32).expect(\"signed addition overflow\");"));
    assert!(rust.contains("let mut out: i32 = value;"));
    assert_rust_snippet_runs(
        "typed-ir-prefix-inc-value-decl",
        rust,
        "    assert_eq!(prefix_inc_value_decl(5), 12);",
    );
}

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
fn typed_ir_keeps_prefix_inc_dec_member_target_fail_closed() {
    let i32_ty = ir_i32();
    let point_ty = ir_record_with_fields("point", vec![("x", i32_ty.clone())]);
    let point_ptr_ty = ir_pointer("struct point *", "struct point *", point_ty, false);
    let ir = IrFunction {
        name: "prefix_inc_member".to_string(),
        return_type: ir_void(),
        params: vec![IrParam {
            name: "p".to_string(),
            ty: point_ptr_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::Assign {
                target: IrExpr::Member {
                    base: Box::new(ir_var("p", point_ptr_ty.clone())),
                    field: "x".to_string(),
                    ty: i32_ty.clone(),
                    is_arrow: true,
                    source_span: None,
                },
                value: ir_lit(0, "0", i32_ty.clone()),
                source_span: None,
            },
            IrStmt::Expr {
                expr: IrExpr::IncDec {
                    target: Box::new(IrExpr::Member {
                        base: Box::new(ir_var("p", point_ptr_ty)),
                        field: "x".to_string(),
                        ty: i32_ty.clone(),
                        is_arrow: true,
                        source_span: None,
                    }),
                    op: IrIncDecOp::Inc,
                    prefix: true,
                    ty: i32_ty,
                    source_span: None,
                },
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("member target remains unsupported");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(
        error.reason.contains("inc/dec expression is unsupported"),
        "{}",
        error.reason
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_mutable_record_pointer_arrow_field_compound_assignment_complex_rhs() {
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
        name: "bad_add_point_x".to_string(),
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
                ir_binary(
                    IrBinOp::Add,
                    ir_var("value", i32_ty.clone()),
                    ir_lit(1, "1", i32_ty.clone()),
                    i32_ty.clone(),
                ),
                i32_ty,
            ),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir)
        .expect_err("mutable record pointer field compound assignment complex RHS must fail");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(
        error
            .reason
            .contains("mutable record pointer field compound assignment RHS"),
        "{:?}",
        error
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_mutable_record_pointer_arrow_field_read_after_assignment() {
    let i32_ty = ir_i32();
    let point_ty =
        ir_record_with_fields("point", vec![("x", i32_ty.clone()), ("y", i32_ty.clone())]);
    let point_ptr_ty = ir_pointer("struct point *", "struct point *", point_ty, false);
    let ir = IrFunction {
        name: "set_then_read_point_x".to_string(),
        return_type: i32_ty.clone(),
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
            IrStmt::Assign {
                target: IrExpr::Member {
                    base: Box::new(ir_var("p", point_ptr_ty.clone())),
                    field: "x".to_string(),
                    ty: i32_ty.clone(),
                    is_arrow: true,
                    source_span: None,
                },
                value: ir_var("value", i32_ty.clone()),
                source_span: None,
            },
            IrStmt::Return {
                value: Some(IrExpr::Member {
                    base: Box::new(ir_var("p", point_ptr_ty)),
                    field: "x".to_string(),
                    ty: i32_ty.clone(),
                    is_arrow: true,
                    source_span: None,
                }),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let emitted =
        emit_rust_from_ir(&ir).expect("emit mutable record pointer field read after assignment");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub struct Point"), "{rust}");
    assert!(rust.contains("pub x: i32"), "{rust}");
    assert!(rust.contains("pub y: i32"), "{rust}");
    assert!(
        rust.contains("pub fn set_then_read_point_x(mut p: &mut Point, value: i32) -> i32"),
        "{rust}"
    );
    assert!(rust.contains("p.x = value;"), "{rust}");
    assert!(rust.contains("return p.x;"), "{rust}");
    assert_rust_snippet_compiles(
        "typed-ir-mutable-record-pointer-field-read-after-write",
        rust,
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_mutable_record_pointer_arrow_field_read_after_if_else_return() {
    let i32_ty = ir_i32();
    let point_ty =
        ir_record_with_fields("point", vec![("x", i32_ty.clone()), ("y", i32_ty.clone())]);
    let point_ptr_ty = ir_pointer("struct point *", "struct point *", point_ty, false);
    let ir = IrFunction {
        name: "set_then_read_point_x_if_present".to_string(),
        return_type: i32_ty.clone(),
        params: vec![
            IrParam {
                name: "p".to_string(),
                ty: point_ptr_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "cond".to_string(),
                ty: i32_ty.clone(),
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
                condition: ir_var("cond", i32_ty.clone()),
                then_body: vec![IrStmt::Assign {
                    target: IrExpr::Member {
                        base: Box::new(ir_var("p", point_ptr_ty.clone())),
                        field: "x".to_string(),
                        ty: i32_ty.clone(),
                        is_arrow: true,
                        source_span: None,
                    },
                    value: ir_var("value", i32_ty.clone()),
                    source_span: None,
                }],
                else_body: vec![IrStmt::Return {
                    value: Some(ir_lit(0, "0", i32_ty.clone())),
                    source_span: None,
                }],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(IrExpr::Member {
                    base: Box::new(ir_var("p", point_ptr_ty)),
                    field: "x".to_string(),
                    ty: i32_ty.clone(),
                    is_arrow: true,
                    source_span: None,
                }),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir)
        .expect("emit mutable record pointer field read after if/else-return write");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub struct Point"), "{rust}");
    assert!(
        rust.contains(
            "pub fn set_then_read_point_x_if_present(mut p: &mut Point, cond: i32, value: i32) -> i32"
        ),
        "{rust}"
    );
    assert!(rust.contains("if cond != 0i32 {"), "{rust}");
    assert!(rust.contains("p.x = value;"), "{rust}");
    assert!(rust.contains("return 0i32;"), "{rust}");
    assert!(rust.contains("return p.x;"), "{rust}");
    assert_rust_snippet_compiles(
        "typed-ir-mutable-record-pointer-field-read-after-if-return",
        rust,
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_mutable_record_pointer_arrow_field_read_after_if_then_return_else_write() {
    let i32_ty = ir_i32();
    let point_ty =
        ir_record_with_fields("point", vec![("x", i32_ty.clone()), ("y", i32_ty.clone())]);
    let point_ptr_ty = ir_pointer("struct point *", "struct point *", point_ty, false);
    let ir = IrFunction {
        name: "set_then_read_point_x_if_absent".to_string(),
        return_type: i32_ty.clone(),
        params: vec![
            IrParam {
                name: "p".to_string(),
                ty: point_ptr_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "cond".to_string(),
                ty: i32_ty.clone(),
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
                condition: ir_var("cond", i32_ty.clone()),
                then_body: vec![IrStmt::Return {
                    value: Some(ir_lit(0, "0", i32_ty.clone())),
                    source_span: None,
                }],
                else_body: vec![IrStmt::Assign {
                    target: IrExpr::Member {
                        base: Box::new(ir_var("p", point_ptr_ty.clone())),
                        field: "x".to_string(),
                        ty: i32_ty.clone(),
                        is_arrow: true,
                        source_span: None,
                    },
                    value: ir_var("value", i32_ty.clone()),
                    source_span: None,
                }],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(IrExpr::Member {
                    base: Box::new(ir_var("p", point_ptr_ty)),
                    field: "x".to_string(),
                    ty: i32_ty.clone(),
                    is_arrow: true,
                    source_span: None,
                }),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir)
        .expect("emit mutable record pointer field read after if-return/else-write");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(
        rust.contains(
            "pub fn set_then_read_point_x_if_absent(mut p: &mut Point, cond: i32, value: i32) -> i32"
        ),
        "{rust}"
    );
    assert!(rust.contains("return 0i32;"), "{rust}");
    assert!(rust.contains("p.x = value;"), "{rust}");
    assert!(rust.contains("return p.x;"), "{rust}");
    assert_rust_snippet_compiles(
        "typed-ir-mutable-record-pointer-field-read-after-then-return",
        rust,
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_uninitialized_scalar_local_after_if_return_assignment() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "assign_local_or_return".to_string(),
        return_type: i32_ty.clone(),
        params: vec![
            IrParam {
                name: "cond".to_string(),
                ty: i32_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "value".to_string(),
                ty: i32_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![
            IrStmt::Decl {
                name: "out".to_string(),
                ty: i32_ty.clone(),
                init: None,
                source_span: None,
            },
            IrStmt::If {
                condition: ir_var("cond", i32_ty.clone()),
                then_body: vec![IrStmt::Assign {
                    target: ir_var("out", i32_ty.clone()),
                    value: ir_var("value", i32_ty.clone()),
                    source_span: None,
                }],
                else_body: vec![IrStmt::Return {
                    value: Some(ir_lit(0, "0", i32_ty.clone())),
                    source_span: None,
                }],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("out", i32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let emitted =
        emit_rust_from_ir(&ir).expect("emit uninitialized scalar local after if-return assignment");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("let mut out: i32;"), "{rust}");
    assert!(rust.contains("out = value;"), "{rust}");
    assert!(rust.contains("return out;"), "{rust}");
    assert_rust_snippet_compiles("typed-ir-scalar-local-if-return-assignment", rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_mutable_record_pointer_arrow_field_read_before_assignment() {
    let i32_ty = ir_i32();
    let point_ty = ir_record_with_fields("point", vec![("x", i32_ty.clone())]);
    let point_ptr_ty = ir_pointer("struct point *", "struct point *", point_ty, false);
    let ir = IrFunction {
        name: "bad_read_then_set_point_x".to_string(),
        return_type: i32_ty.clone(),
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
            IrStmt::Decl {
                name: "old".to_string(),
                ty: i32_ty.clone(),
                init: Some(IrExpr::Member {
                    base: Box::new(ir_var("p", point_ptr_ty.clone())),
                    field: "x".to_string(),
                    ty: i32_ty.clone(),
                    is_arrow: true,
                    source_span: None,
                }),
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
                value: ir_var("value", i32_ty.clone()),
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("old", i32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir)
        .expect_err("mutable record pointer field read before assignment must fail closed");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(
        error
            .reason
            .contains("mutable record pointer field p.x is read before definite assignment"),
        "{:?}",
        error
    );
}
