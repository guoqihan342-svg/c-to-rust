#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_nullable_record_pointer_arrow_field_read_in_null_branch() {
    let i32_ty = ir_i32();
    let point_ty = ir_record_with_fields("point", vec![("x", i32_ty.clone())]);
    let ptr_ty = ir_pointer(
        "const struct point *",
        "const struct point *",
        ir_const(point_ty),
        false,
    );
    let ir = IrFunction {
        name: "bad_null_branch_point_x".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "p".to_string(),
            ty: ptr_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::If {
                condition: ir_binary(
                    IrBinOp::Eq,
                    ir_var("p", ptr_ty.clone()),
                    ir_null_ptr(ptr_ty.clone()),
                    i32_ty.clone(),
                ),
                then_body: vec![IrStmt::Return {
                    value: Some(IrExpr::Member {
                        base: Box::new(ir_var("p", ptr_ty)),
                        field: "x".to_string(),
                        ty: i32_ty.clone(),
                        is_arrow: true,
                        source_span: None,
                    }),
                    source_span: None,
                }],
                else_body: vec![IrStmt::Return {
                    value: Some(ir_lit(0, "0", i32_ty.clone())),
                    source_span: None,
                }],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_lit(0, "0", i32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("null branch must not allow nullable field read");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(error
        .reason
        .contains("nullable pointer param p is only supported in null comparisons"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_nullable_record_pointer_arrow_non_scalar_field_read_even_when_guarded() {
    let i32_ty = ir_i32();
    let child_ty = ir_record_with_fields("child", vec![("value", i32_ty.clone())]);
    let point_ty = ir_record_with_fields("point", vec![("child", child_ty.clone())]);
    let ptr_ty = ir_pointer(
        "const struct point *",
        "const struct point *",
        ir_const(point_ty),
        false,
    );
    let ir = IrFunction {
        name: "bad_guarded_point_child".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "p".to_string(),
            ty: ptr_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::If {
                condition: ir_binary(
                    IrBinOp::Eq,
                    ir_var("p", ptr_ty.clone()),
                    ir_null_ptr(ptr_ty.clone()),
                    i32_ty.clone(),
                ),
                then_body: vec![IrStmt::Return {
                    value: Some(ir_lit(0, "0", i32_ty.clone())),
                    source_span: None,
                }],
                else_body: vec![],
                source_span: None,
            },
            IrStmt::Expr {
                expr: IrExpr::Member {
                    base: Box::new(ir_var("p", ptr_ty)),
                    field: "child".to_string(),
                    ty: child_ty,
                    is_arrow: true,
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

    let error = emit_rust_from_ir(&ir)
        .expect_err("guarded nullable record pointer read must still require scalar field");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(error.reason.contains(
        "nullable record pointer arrow field child has record type child is unsupported"
    ));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_nullable_record_pointer_arrow_field_read_after_inverse_guard() {
    let i32_ty = ir_i32();
    let point_ty = ir_record_with_fields("point", vec![("x", i32_ty.clone())]);
    let ptr_ty = ir_pointer(
        "const struct point *",
        "const struct point *",
        ir_const(point_ty),
        false,
    );
    let ir = IrFunction {
        name: "bad_inverse_guard_point_x".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "p".to_string(),
            ty: ptr_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::If {
                condition: ir_binary(
                    IrBinOp::Neq,
                    ir_var("p", ptr_ty.clone()),
                    ir_null_ptr(ptr_ty.clone()),
                    i32_ty.clone(),
                ),
                then_body: vec![IrStmt::Return {
                    value: Some(ir_lit(0, "0", i32_ty.clone())),
                    source_span: None,
                }],
                else_body: vec![],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(IrExpr::Member {
                    base: Box::new(ir_var("p", ptr_ty)),
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

    let error = emit_rust_from_ir(&ir)
        .expect_err("inverse nullable record pointer guard must not prove nonnull");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(error
        .reason
        .contains("nullable pointer param p is only supported in null comparisons"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_nullable_pointer_use_after_null_check() {
    let i32_ty = ir_i32();
    let const_i32_ty = ir_const(i32_ty.clone());
    let ptr_ty = ir_pointer("const int *", "const int *", const_i32_ty, false);
    let ir = IrFunction {
        name: "bad_nullable_use".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "values".to_string(),
            ty: ptr_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::If {
                condition: ir_binary(
                    IrBinOp::Neq,
                    ir_var("values", ptr_ty.clone()),
                    ir_null_ptr(ptr_ty.clone()),
                    i32_ty.clone(),
                ),
                then_body: vec![IrStmt::Return {
                    value: Some(IrExpr::Index {
                        base: Box::new(ir_var("values", ptr_ty.clone())),
                        index: Box::new(ir_lit(0, "0", i32_ty.clone())),
                        ty: i32_ty.clone(),
                        source_span: None,
                    }),
                    source_span: None,
                }],
                else_body: vec![],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_lit(0, "0", i32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error =
        emit_rust_from_ir(&ir).expect_err("nullable pointer follow-up use must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error
        .reason
        .contains("nullable pointer param values is only supported in null comparisons"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_comparison_condition_with_unsupported_operand_type() {
    let i32_ty = ir_i32();
    let unsupported_ty = IrType {
        spelled: "float".to_string(),
        canonical: "float".to_string(),
        kind: IrTypeKind::Unsupported {
            reason: "floating type is outside typed IR subset".to_string(),
        },
        is_const: false,
        width_bits: None,
        source_span: None,
    };
    let ir = IrFunction {
        name: "bad_cmp_float_condition".to_string(),
        return_type: i32_ty.clone(),
        params: vec![],
        body: vec![
            IrStmt::If {
                condition: ir_binary(
                    IrBinOp::Eq,
                    ir_var("left", unsupported_ty.clone()),
                    ir_var("right", unsupported_ty),
                    i32_ty.clone(),
                ),
                then_body: vec![],
                else_body: vec![],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_lit(0, "0", i32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error =
        emit_rust_from_ir(&ir).expect_err("unsupported comparison condition must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("stmt[0].if condition"));
    assert!(error.reason.contains(
        "comparison lhs has unsupported type float: floating type is outside typed IR subset"
    ));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_comparison_condition_with_deref_operand() {
    let i32_ty = ir_i32();
    let ptr_ty = ir_pointer("int *", "int *", i32_ty.clone(), false);
    let ir = IrFunction {
        name: "bad_cmp_deref_condition".to_string(),
        return_type: i32_ty.clone(),
        params: vec![],
        body: vec![
            IrStmt::If {
                condition: ir_binary(
                    IrBinOp::Eq,
                    IrExpr::Deref {
                        ptr: Box::new(ir_var("ptr", ptr_ty)),
                        ty: i32_ty.clone(),
                        source_span: None,
                    },
                    ir_lit(0, "0", i32_ty.clone()),
                    i32_ty.clone(),
                ),
                then_body: vec![],
                else_body: vec![],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_lit(0, "0", i32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("deref comparison condition must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("stmt[0].if condition"));
    assert!(error.reason.contains("comparison lhs"));
    assert!(error.reason.contains("deref pointer ptr is not declared"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_comparison_condition_with_readonly_pointer_deref_operand() {
    let i32_ty = ir_i32();
    let const_i32_ty = ir_const(i32_ty.clone());
    let const_i32_ptr_ty = ir_pointer("const int *", "int *", const_i32_ty, false);
    let ir = IrFunction {
        name: "first_is_zero_condition".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "p".to_string(),
            ty: const_i32_ptr_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::If {
                condition: ir_binary(
                    IrBinOp::Eq,
                    ir_deref(ir_var("p", const_i32_ptr_ty), i32_ty.clone()),
                    ir_lit(0, "0", i32_ty.clone()),
                    i32_ty.clone(),
                ),
                then_body: vec![IrStmt::Return {
                    value: Some(ir_lit(1, "1", i32_ty.clone())),
                    source_span: None,
                }],
                else_body: vec![],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_lit(0, "0", i32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit deref comparison condition");
    let rust = &emitted.rust;

    assert!(rust.contains("pub fn first_is_zero_condition(p: &[i32]) -> i32"));
    assert!(rust.contains("if (p[0usize] == 0i32) {"));
    assert_rust_snippet_compiles("typed-ir-deref-comparison-condition", rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_comparison_condition_with_readonly_pointer_add_index_deref_operand() {
    let i32_ty = ir_i32();
    let usize_ty = ir_usize();
    let const_i32_ty = ir_const(i32_ty.clone());
    let const_i32_ptr_ty = ir_pointer("const int *", "int *", const_i32_ty, false);
    let ptr_plus_index = ir_binary(
        IrBinOp::Add,
        ir_var("p", const_i32_ptr_ty.clone()),
        ir_var("i", usize_ty.clone()),
        const_i32_ptr_ty.clone(),
    );
    let ir = IrFunction {
        name: "offset_is_zero_condition".to_string(),
        return_type: i32_ty.clone(),
        params: vec![
            IrParam {
                name: "p".to_string(),
                ty: const_i32_ptr_ty,
                source_span: None,
            },
            IrParam {
                name: "i".to_string(),
                ty: usize_ty,
                source_span: None,
            },
        ],
        body: vec![
            IrStmt::If {
                condition: ir_binary(
                    IrBinOp::Eq,
                    ir_deref(ptr_plus_index, i32_ty.clone()),
                    ir_lit(0, "0", i32_ty.clone()),
                    i32_ty.clone(),
                ),
                then_body: vec![IrStmt::Return {
                    value: Some(ir_lit(1, "1", i32_ty.clone())),
                    source_span: None,
                }],
                else_body: vec![],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_lit(0, "0", i32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit offset deref comparison condition");
    let rust = &emitted.rust;

    assert!(rust.contains("pub fn offset_is_zero_condition(p: &[i32], i: usize) -> i32"));
    assert!(rust.contains("if (p[i as usize] == 0i32) {"));
    assert_rust_snippet_compiles("typed-ir-offset-deref-comparison-condition", rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_short_circuit_if_conditions() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "both_nonzero".to_string(),
        return_type: i32_ty.clone(),
        params: vec![
            IrParam {
                name: "left".to_string(),
                ty: i32_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "right".to_string(),
                ty: i32_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![
            IrStmt::If {
                condition: ir_binary(
                    IrBinOp::LogAnd,
                    ir_var("left", i32_ty.clone()),
                    ir_var("right", i32_ty.clone()),
                    i32_ty.clone(),
                ),
                then_body: vec![IrStmt::Return {
                    value: Some(ir_lit(1, "1", i32_ty.clone())),
                    source_span: None,
                }],
                else_body: vec![],
                source_span: None,
            },
            IrStmt::If {
                condition: ir_binary(
                    IrBinOp::LogOr,
                    ir_var("left", i32_ty.clone()),
                    ir_var("right", i32_ty.clone()),
                    i32_ty.clone(),
                ),
                then_body: vec![IrStmt::Return {
                    value: Some(ir_lit(2, "2", i32_ty.clone())),
                    source_span: None,
                }],
                else_body: vec![],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_lit(0, "0", i32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let rust = emit_rust_from_ir(&ir).expect("emit short-circuit if conditions");

    assert!(rust.contains("pub fn both_nonzero(left: i32, right: i32) -> i32"));
    assert!(rust.contains("if (left != 0i32 && right != 0i32) {"));
    assert!(rust.contains("if (left != 0i32 || right != 0i32) {"));
    assert_rust_snippet_compiles("typed-ir-short-circuit-if", &rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_short_circuit_while_condition_with_comparison_operands() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "loop_until_done".to_string(),
        return_type: i32_ty.clone(),
        params: vec![
            IrParam {
                name: "left".to_string(),
                ty: i32_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "right".to_string(),
                ty: i32_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![
            IrStmt::While {
                condition: ir_binary(
                    IrBinOp::LogOr,
                    ir_binary(
                        IrBinOp::Lt,
                        ir_var("left", i32_ty.clone()),
                        ir_lit(3, "3", i32_ty.clone()),
                        i32_ty.clone(),
                    ),
                    ir_binary(
                        IrBinOp::Neq,
                        ir_var("right", i32_ty.clone()),
                        ir_lit(0, "0", i32_ty.clone()),
                        i32_ty.clone(),
                    ),
                    i32_ty.clone(),
                ),
                body: vec![IrStmt::Assign {
                    target: ir_var("left", i32_ty.clone()),
                    value: ir_binary(
                        IrBinOp::Add,
                        ir_var("left", i32_ty.clone()),
                        ir_lit(1, "1", i32_ty.clone()),
                        i32_ty.clone(),
                    ),
                    source_span: None,
                }],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("left", i32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let rust = emit_rust_from_ir(&ir).expect("emit short-circuit while condition with comparisons");

    assert!(rust.contains("pub fn loop_until_done(mut left: i32, right: i32) -> i32"));
    assert!(rust.contains("while ((left < 3i32) || (right != 0i32)) {"));
    assert_rust_snippet_compiles("typed-ir-short-circuit-while-comparisons", &rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_for_emits_scoped_loop_with_decl_init_and_step_assignment() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "sum_to_limit".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "limit".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::Decl {
                name: "total".to_string(),
                ty: i32_ty.clone(),
                init: Some(ir_lit(0, "0", i32_ty.clone())),
                source_span: None,
            },
            IrStmt::For {
                init: vec![IrStmt::Decl {
                    name: "i".to_string(),
                    ty: i32_ty.clone(),
                    init: Some(ir_lit(0, "0", i32_ty.clone())),
                    source_span: None,
                }],
                condition: Some(ir_binary(
                    IrBinOp::Lt,
                    ir_var("i", i32_ty.clone()),
                    ir_var("limit", i32_ty.clone()),
                    i32_ty.clone(),
                )),
                step: Some(Box::new(IrStmt::Assign {
                    target: ir_var("i", i32_ty.clone()),
                    value: ir_binary(
                        IrBinOp::Add,
                        ir_var("i", i32_ty.clone()),
                        ir_lit(1, "1", i32_ty.clone()),
                        i32_ty.clone(),
                    ),
                    source_span: None,
                })),
                body: vec![IrStmt::Assign {
                    target: ir_var("total", i32_ty.clone()),
                    value: ir_binary(
                        IrBinOp::Add,
                        ir_var("total", i32_ty.clone()),
                        ir_var("i", i32_ty.clone()),
                        i32_ty.clone(),
                    ),
                    source_span: None,
                }],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("total", i32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let rust = emit_rust_from_ir(&ir).expect("emit scoped for loop");

    assert!(rust.contains("pub fn sum_to_limit(limit: i32) -> i32"));
    assert!(rust.contains("let mut total: i32 = 0i32;"));
    assert!(rust.contains("{\n        let mut i: i32 = 0i32;\n        while (i < limit) {"));
    assert!(rust.contains("total = total.checked_add(i).expect(\"signed addition overflow\");"));
    assert!(rust.contains("i = i.checked_add(1i32).expect(\"signed addition overflow\");"));
    assert!(rust.contains("return total;"));
    assert_rust_snippet_compiles("typed-ir-for-scoped-loop", &rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_for_emits_record_field_inc_dec_step_assignment() {
    let i32_ty = ir_i32();
    let point_ty = ir_record_with_fields(
        "point",
        vec![("x", i32_ty.clone()), ("y", i32_ty.clone())],
    );
    let point_x = || IrExpr::Member {
        base: Box::new(ir_var("p", point_ty.clone())),
        field: "x".to_string(),
        ty: i32_ty.clone(),
        is_arrow: false,
        source_span: None,
    };
    let ir = IrFunction {
        name: "bump_point_x_for_step".to_string(),
        return_type: i32_ty.clone(),
        params: vec![
            IrParam {
                name: "p".to_string(),
                ty: point_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "limit".to_string(),
                ty: i32_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![
            IrStmt::For {
                init: vec![IrStmt::Decl {
                    name: "i".to_string(),
                    ty: i32_ty.clone(),
                    init: Some(ir_lit(0, "0", i32_ty.clone())),
                    source_span: None,
                }],
                condition: Some(ir_binary(
                    IrBinOp::Lt,
                    ir_var("i", i32_ty.clone()),
                    ir_var("limit", i32_ty.clone()),
                    i32_ty.clone(),
                )),
                step: Some(Box::new(IrStmt::Assign {
                    target: point_x(),
                    value: ir_binary(
                        IrBinOp::Add,
                        point_x(),
                        ir_lit(1, "1", i32_ty.clone()),
                        i32_ty.clone(),
                    ),
                    source_span: None,
                })),
                body: vec![IrStmt::Assign {
                    target: ir_var("i", i32_ty.clone()),
                    value: ir_binary(
                        IrBinOp::Add,
                        ir_var("i", i32_ty.clone()),
                        ir_lit(1, "1", i32_ty.clone()),
                        i32_ty.clone(),
                    ),
                    source_span: None,
                }],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(point_x()),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit record field inc/dec for step assignment");
    let rust = &emitted.rust;

    assert!(rust.contains("pub struct Point"), "{rust}");
    assert!(
        rust.contains("pub fn bump_point_x_for_step(mut p: Point, limit: i32) -> i32"),
        "{rust}"
    );
    assert!(
        rust.contains("p.x = p.x.checked_add(1i32).expect(\"signed addition overflow\");"),
        "{rust}"
    );
    assert_rust_snippet_runs(
        "typed-ir-for-record-field-step-assignment",
        rust,
        "let p = Point { x: 2i32 };\nassert_eq!(bump_point_x_for_step(p, 3i32), 5i32);",
    );
}
