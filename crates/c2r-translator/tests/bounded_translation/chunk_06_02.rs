#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_conditional_value_with_assignment_arm() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "bad_conditional_assignment_arm".to_string(),
        return_type: i32_ty.clone(),
        params: vec![
            IrParam {
                name: "flag".to_string(),
                ty: i32_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "value".to_string(),
                ty: i32_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![IrStmt::Return {
            value: Some(ir_conditional(
                ir_var("flag", i32_ty.clone()),
                ir_binary(
                    IrBinOp::Assign,
                    ir_var("value", i32_ty.clone()),
                    ir_lit(1, "1", i32_ty.clone()),
                    i32_ty.clone(),
                ),
                ir_lit(0, "0", i32_ty.clone()),
                i32_ty.clone(),
            )),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("conditional assignment arm must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("return expr"));
    assert!(error
        .reason
        .contains("conditional then expression cannot use assignment or comma operators"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_conditional_in_if_condition_position() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "bad_conditional_if_condition".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "flag".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::If {
                condition: ir_conditional(
                    ir_var("flag", i32_ty.clone()),
                    ir_lit(1, "1", i32_ty.clone()),
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

    let error =
        emit_rust_from_ir(&ir).expect_err("condition-position conditional must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("if condition"));
    assert!(error
        .reason
        .contains("conditional expression is unsupported in condition positions"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_comparison_condition_with_mismatched_operand_types() {
    let i32_ty = ir_i32();
    let u32_ty = ir_u32();
    let ir = IrFunction {
        name: "bad_cmp_types".to_string(),
        return_type: i32_ty.clone(),
        params: vec![
            IrParam {
                name: "left".to_string(),
                ty: i32_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "right".to_string(),
                ty: u32_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![
            IrStmt::If {
                condition: ir_binary(
                    IrBinOp::Lt,
                    ir_var("left", i32_ty.clone()),
                    ir_var("right", u32_ty),
                    i32_ty.clone(),
                ),
                then_body: vec![],
                else_body: vec![],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("left", i32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("mismatched comparison types must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("stmt[0].if condition"));
    assert!(error
        .reason
        .contains("comparison operand types must match for <"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_comparison_condition_with_non_int_result_type() {
    let i32_ty = ir_i32();
    let u32_ty = ir_u32();
    let ir = IrFunction {
        name: "bad_cmp_result_type".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::If {
                condition: ir_binary(
                    IrBinOp::Gt,
                    ir_var("value", i32_ty.clone()),
                    ir_lit(0, "0", i32_ty.clone()),
                    u32_ty,
                ),
                then_body: vec![],
                else_body: vec![],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("value", i32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("non-int comparison result must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("stmt[0].if condition"));
    assert!(error
        .reason
        .contains("comparison result type must be C int"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_comparison_condition_with_pointer_operand() {
    let i32_ty = ir_i32();
    let ptr_ty = ir_pointer("int *", "int *", i32_ty.clone(), false);
    let ir = IrFunction {
        name: "bad_cmp_pointer_condition".to_string(),
        return_type: i32_ty.clone(),
        params: vec![],
        body: vec![
            IrStmt::If {
                condition: ir_binary(
                    IrBinOp::Eq,
                    ir_var("left", ptr_ty.clone()),
                    ir_var("right", ptr_ty),
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

    let error = emit_rust_from_ir(&ir).expect_err("pointer comparison condition must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("stmt[0].if condition"));
    assert!(error
        .reason
        .contains("comparison lhs has pointer type int * is unsupported"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_comparison_condition_with_null_pointer_operand() {
    let i32_ty = ir_i32();
    let const_i32_ty = ir_const(i32_ty.clone());
    let ptr_ty = ir_pointer("const int *", "const int *", const_i32_ty, false);
    let ir = IrFunction {
        name: "zero_if_missing".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "values".to_string(),
            ty: ptr_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::If {
                condition: ir_binary(
                    IrBinOp::Eq,
                    ir_var("values", ptr_ty.clone()),
                    ir_null_ptr(ptr_ty),
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
                value: Some(ir_lit(1, "1", i32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let rust = emit_rust_from_ir(&ir).expect("emit null pointer condition comparison");

    assert!(rust.contains("pub fn zero_if_missing(values: Option<&[i32]>) -> i32"));
    assert!(rust.contains("if values.is_none() {"));
    assert!(rust.contains("return 0i32;"));
    assert!(rust.contains("return 1i32;"));
    assert_rust_snippet_compiles("typed-ir-null-pointer-condition-comparison", &rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_readonly_pointer_truthiness_condition_with_strlen_in_nonnull_branch() {
    let usize_ty = ir_usize();
    let char_ty = ir_integer("const char", "char", true, 8);
    let ptr_ty = ir_pointer("const char *", "char *", ir_const(char_ty), false);
    let ir = IrFunction {
        name: "strlen_if_present".to_string(),
        return_type: usize_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: ptr_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::If {
                condition: ir_var("value", ptr_ty.clone()),
                then_body: vec![IrStmt::Return {
                    value: Some(IrExpr::Call {
                        callee: "strlen".to_string(),
                        args: vec![ir_var("value", ptr_ty.clone())],
                        ty: usize_ty.clone(),
                        source_span: None,
                    }),
                    source_span: None,
                }],
                else_body: vec![],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_lit(0, "0", usize_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit readonly pointer truthiness condition");
    let rust = &emitted.rust;

    assert!(
        rust.contains("pub fn strlen_if_present(value: Option<&[i8]>) -> usize"),
        "{rust}"
    );
    assert!(rust.contains("if value.is_some() {"), "{rust}");
    assert!(
        rust.contains("return value.unwrap().iter().position(|&byte| byte == 0).expect(\"C strlen precondition violated\");"),
        "{rust}"
    );
    assert!(rust.contains("return 0usize;"), "{rust}");
    assert_rust_snippet_compiles("typed-ir-pointer-truthiness-strlen", rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_readonly_pointer_truthiness_value_position() {
    let i32_ty = ir_i32();
    let char_ty = ir_integer("const char", "char", true, 8);
    let ptr_ty = ir_pointer("const char *", "char *", ir_const(char_ty), false);
    let ir = IrFunction {
        name: "bad_return_pointer_truthiness".to_string(),
        return_type: i32_ty,
        params: vec![IrParam {
            name: "value".to_string(),
            ty: ptr_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(ir_var("value", ptr_ty)),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("pointer truthiness is condition-only");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(error.reason.contains("return expr"));
    assert!(error
        .reason
        .contains("pointer type const char * is unsupported"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_comparison_condition_with_record_null_pointer_operand() {
    let i32_ty = ir_i32();
    let point_ty = ir_record_with_fields("point", vec![("x", i32_ty.clone())]);
    let ptr_ty = ir_pointer(
        "const struct point *",
        "const struct point *",
        ir_const(point_ty),
        false,
    );
    let ir = IrFunction {
        name: "zero_if_missing_point".to_string(),
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
                    ir_null_ptr(ptr_ty),
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
                value: Some(ir_lit(1, "1", i32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit record null pointer condition comparison");
    let rust = &emitted.rust;

    assert!(rust.contains("pub struct Point"), "{rust}");
    assert!(rust.contains("pub x: i32"), "{rust}");
    assert!(
        rust.contains("pub fn zero_if_missing_point(p: Option<&Point>) -> i32"),
        "{rust}"
    );
    assert!(rust.contains("if p.is_none() {"), "{rust}");
    assert!(rust.contains("return 0i32;"), "{rust}");
    assert!(rust.contains("return 1i32;"), "{rust}");
    assert_rust_snippet_compiles("typed-ir-record-null-pointer-condition-comparison", rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_null_guarded_nullable_record_pointer_arrow_field_read() {
    let i32_ty = ir_i32();
    let point_ty = ir_record_with_fields("point", vec![("x", i32_ty.clone())]);
    let ptr_ty = ir_pointer(
        "const struct point *",
        "const struct point *",
        ir_const(point_ty),
        false,
    );
    let ir = IrFunction {
        name: "point_x_or_zero".to_string(),
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

    let emitted =
        emit_rust_from_ir(&ir).expect("emit null-guarded nullable record pointer field read");
    let rust = &emitted.rust;

    assert!(rust.contains("pub struct Point"), "{rust}");
    assert!(rust.contains("pub x: i32"), "{rust}");
    assert!(
        rust.contains("pub fn point_x_or_zero(p: Option<&Point>) -> i32"),
        "{rust}"
    );
    assert!(rust.contains("if p.is_none() {"), "{rust}");
    assert!(rust.contains("return 0i32;"), "{rust}");
    assert!(rust.contains("return p.unwrap().x;"), "{rust}");
    assert_rust_snippet_compiles("typed-ir-null-guarded-record-pointer-field-read", rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_nullable_record_pointer_arrow_field_read_in_nonnull_branch() {
    let i32_ty = ir_i32();
    let point_ty = ir_record_with_fields("point", vec![("x", i32_ty.clone())]);
    let ptr_ty = ir_pointer(
        "const struct point *",
        "const struct point *",
        ir_const(point_ty),
        false,
    );
    let ir = IrFunction {
        name: "point_x_if_present".to_string(),
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
                    value: Some(IrExpr::Member {
                        base: Box::new(ir_var("p", ptr_ty)),
                        field: "x".to_string(),
                        ty: i32_ty.clone(),
                        is_arrow: true,
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

    let emitted =
        emit_rust_from_ir(&ir).expect("emit nullable record pointer field read in nonnull branch");
    let rust = &emitted.rust;

    assert!(
        rust.contains("pub fn point_x_if_present(p: Option<&Point>) -> i32"),
        "{rust}"
    );
    assert!(rust.contains("if p.is_some() {"), "{rust}");
    assert!(rust.contains("return p.unwrap().x;"), "{rust}");
    assert!(rust.contains("return 0i32;"), "{rust}");
    assert_rust_snippet_compiles(
        "typed-ir-nullable-record-pointer-nonnull-branch-field-read",
        rust,
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_nullable_record_pointer_arrow_field_read_without_null_guard() {
    let i32_ty = ir_i32();
    let point_ty = ir_record_with_fields("point", vec![("x", i32_ty.clone())]);
    let ptr_ty = ir_pointer(
        "const struct point *",
        "const struct point *",
        ir_const(point_ty),
        false,
    );
    let ir = IrFunction {
        name: "bad_point_x".to_string(),
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
                then_body: vec![],
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

    let error =
        emit_rust_from_ir(&ir).expect_err("nullable record pointer field read must need guard");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(error
        .reason
        .contains("nullable pointer param p is only supported in null comparisons"));
}
