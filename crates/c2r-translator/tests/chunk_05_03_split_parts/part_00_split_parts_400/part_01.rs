#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_for_nested_while_continue_does_not_emit_outer_step() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "nested_continue".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "limit".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
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
                    target: ir_var("i", i32_ty.clone()),
                    value: ir_binary(
                        IrBinOp::Add,
                        ir_var("i", i32_ty.clone()),
                        ir_lit(1, "1", i32_ty.clone()),
                        i32_ty.clone(),
                    ),
                    source_span: None,
                })),
                body: vec![IrStmt::While {
                    condition: ir_var("limit", i32_ty.clone()),
                    body: vec![IrStmt::Continue { source_span: None }],
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

    let rust = emit_rust_from_ir(&ir).expect("emit nested while continue in for body");

    assert_eq!(
        rust.matches("i = i.checked_add(1i32).expect(\"signed addition overflow\");")
            .count(),
        1,
        "{rust:?}"
    );
    assert!(
        rust.contains("while limit != 0i32 {\n                continue;\n            }"),
        "{rust:?}"
    );
    assert_rust_snippet_compiles("typed-ir-for-nested-while-continue", &rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_continue_outside_loop() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "bad_continue".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::Continue { source_span: None },
            IrStmt::Return {
                value: Some(ir_var("value", i32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("top-level continue must fail closed");

    assert!(error.reason.contains("continue outside loop"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_while_with_unsupported_condition_expr() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "bad_while_call".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "count".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::While {
                condition: IrExpr::Call {
                    callee: "helper".to_string(),
                    args: vec![],
                    ty: i32_ty.clone(),
                    source_span: None,
                },
                body: vec![IrStmt::Assign {
                    target: ir_var("count", i32_ty.clone()),
                    value: ir_var("count", i32_ty.clone()),
                    source_span: None,
                }],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("count", i32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("while call condition must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("stmt[0].while condition"));
    assert!(error
        .reason
        .contains("call expression helper is unsupported"));
}
