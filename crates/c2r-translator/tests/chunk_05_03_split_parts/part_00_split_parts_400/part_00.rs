#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_continue_in_scalar_while_body() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "skip_large".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::While {
                condition: ir_var("value", i32_ty.clone()),
                body: vec![
                    IrStmt::If {
                        condition: ir_binary(
                            IrBinOp::Gt,
                            ir_var("value", i32_ty.clone()),
                            ir_lit(3, "3", i32_ty.clone()),
                            i32_ty.clone(),
                        ),
                        then_body: vec![IrStmt::Continue { source_span: None }],
                        else_body: vec![],
                        source_span: None,
                    },
                    IrStmt::Assign {
                        target: ir_var("value", i32_ty.clone()),
                        value: ir_binary(
                            IrBinOp::Sub,
                            ir_var("value", i32_ty.clone()),
                            ir_lit(1, "1", i32_ty.clone()),
                            i32_ty.clone(),
                        ),
                        source_span: None,
                    },
                ],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("value", i32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let rust = emit_rust_from_ir(&ir).expect("emit continue in scalar while");

    assert!(rust.contains("pub fn skip_large(mut value: i32) -> i32"));
    assert!(rust.contains("while value != 0i32 {"));
    assert!(rust.contains("continue;"));
    assert!(
        rust.contains("value = value.checked_sub(1i32).expect(\"signed subtraction overflow\");")
    );
    assert_rust_snippet_compiles("typed-ir-scalar-while-continue", &rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_scalar_do_while_with_condition_check_after_body() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "do_countdown".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::DoWhile {
                body: vec![IrStmt::Assign {
                    target: ir_var("value", i32_ty.clone()),
                    value: ir_binary(
                        IrBinOp::Sub,
                        ir_var("value", i32_ty.clone()),
                        ir_lit(1, "1", i32_ty.clone()),
                        i32_ty.clone(),
                    ),
                    source_span: None,
                }],
                condition: ir_var("value", i32_ty.clone()),
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("value", i32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let rust = emit_rust_from_ir(&ir).expect("emit scalar do-while");

    assert!(rust.contains("pub fn do_countdown(mut value: i32) -> i32"));
    assert!(rust.contains("loop {"));
    assert!(
        rust.contains("value = value.checked_sub(1i32).expect(\"signed subtraction overflow\");")
    );
    assert!(rust.contains("if !(value != 0i32) {"));
    assert!(rust.contains("break;"));
    assert!(rust.contains("return value;"));
    assert_rust_snippet_compiles("typed-ir-scalar-do-while", &rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_do_while_continue_checks_condition_before_continuing() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "do_skip_large".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::DoWhile {
                body: vec![
                    IrStmt::Assign {
                        target: ir_var("value", i32_ty.clone()),
                        value: ir_binary(
                            IrBinOp::Sub,
                            ir_var("value", i32_ty.clone()),
                            ir_lit(1, "1", i32_ty.clone()),
                            i32_ty.clone(),
                        ),
                        source_span: None,
                    },
                    IrStmt::If {
                        condition: ir_binary(
                            IrBinOp::Gt,
                            ir_var("value", i32_ty.clone()),
                            ir_lit(3, "3", i32_ty.clone()),
                            i32_ty.clone(),
                        ),
                        then_body: vec![IrStmt::Continue { source_span: None }],
                        else_body: vec![],
                        source_span: None,
                    },
                    IrStmt::Assign {
                        target: ir_var("value", i32_ty.clone()),
                        value: ir_binary(
                            IrBinOp::Sub,
                            ir_var("value", i32_ty.clone()),
                            ir_lit(1, "1", i32_ty.clone()),
                            i32_ty.clone(),
                        ),
                        source_span: None,
                    },
                ],
                condition: ir_var("value", i32_ty.clone()),
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("value", i32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let rust = emit_rust_from_ir(&ir).expect("emit do-while continue");

    assert!(rust.contains("pub fn do_skip_large(mut value: i32) -> i32"));
    assert!(rust.contains(
        "if (value > 3i32) {\n            if !(value != 0i32) {\n                break;\n            }\n            continue;"
    ));
    assert_eq!(rust.matches("if !(value != 0i32) {").count(), 2, "{rust:?}");
    assert_rust_snippet_compiles("typed-ir-do-while-continue", &rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_for_emits_continue_after_step_in_body() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "sum_skip".to_string(),
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
                body: vec![
                    IrStmt::If {
                        condition: ir_binary(
                            IrBinOp::Gt,
                            ir_var("i", i32_ty.clone()),
                            ir_lit(3, "3", i32_ty.clone()),
                            i32_ty.clone(),
                        ),
                        then_body: vec![IrStmt::Continue { source_span: None }],
                        else_body: vec![],
                        source_span: None,
                    },
                    IrStmt::Assign {
                        target: ir_var("total", i32_ty.clone()),
                        value: ir_binary(
                            IrBinOp::Add,
                            ir_var("total", i32_ty.clone()),
                            ir_var("i", i32_ty.clone()),
                            i32_ty.clone(),
                        ),
                        source_span: None,
                    },
                ],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("total", i32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let rust = emit_rust_from_ir(&ir).expect("emit for continue with step");

    assert!(rust.contains("pub fn sum_skip(limit: i32) -> i32"));
    assert!(rust.contains("if (i > 3i32) {"));
    assert!(
        rust.contains("            if (i > 3i32) {\n                i = i.checked_add(1i32).expect(\"signed addition overflow\");\n                continue;\n            }"),
        "{rust:?}"
    );
    assert_eq!(
        rust.matches("i = i.checked_add(1i32).expect(\"signed addition overflow\");")
            .count(),
        2,
        "{rust:?}"
    );
    assert_rust_snippet_compiles("typed-ir-for-continue-step", &rust);
}
