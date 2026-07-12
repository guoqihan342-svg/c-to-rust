#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_binary_arithmetic_with_integral_operand_cast() {
    let u32_ty = ir_u32();
    let u8_ty = ir_u8();
    let ir = IrFunction {
        name: "add_byte".to_string(),
        return_type: u32_ty.clone(),
        params: vec![
            IrParam {
                name: "acc".to_string(),
                ty: u32_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "byte".to_string(),
                ty: u8_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![IrStmt::Return {
            value: Some(ir_binary(
                IrBinOp::Add,
                ir_var("acc", u32_ty.clone()),
                IrExpr::Cast {
                    target: u32_ty.clone(),
                    expr: Box::new(ir_var("byte", u8_ty)),
                    implicit: true,
                    source_span: None,
                },
                u32_ty,
            )),
            source_span: None,
        }],
        source_span: None,
    };

    let rust = emit_rust_from_ir(&ir).expect("emit binary arithmetic integral cast");

    assert!(rust.contains("pub fn add_byte(acc: u32, byte: u8) -> u32"));
    assert!(rust.contains("return acc.wrapping_add((byte as u32));"));
    assert_rust_snippet_compiles("typed-ir-binary-integral-operand-cast", &rust);
}
#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_scalar_decl_init_and_integer_cast() {
    let i32_ty = ir_i32();
    let u32_ty = ir_u32();
    let ir = IrFunction {
        name: "widen".to_string(),
        return_type: u32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::Decl {
                name: "tmp".to_string(),
                ty: u32_ty.clone(),
                init: Some(IrExpr::Cast {
                    target: u32_ty.clone(),
                    expr: Box::new(ir_var("value", i32_ty.clone())),
                    implicit: false,
                    source_span: None,
                }),
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("tmp", u32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let rust = emit_rust_from_ir(&ir).expect("emit scalar decl and cast");

    assert!(rust.contains("pub fn widen(value: i32) -> u32"));
    assert!(rust.contains("let mut tmp: u32 = (value as u32);"));
    assert!(rust.contains("return tmp;"));
    assert_rust_snippet_compiles("typed-ir-scalar-decl-cast", &rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_scalar_while_with_integer_condition() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "countdown".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "count".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::While {
                condition: ir_var("count", i32_ty.clone()),
                body: vec![IrStmt::Assign {
                    target: ir_var("count", i32_ty.clone()),
                    value: ir_binary(
                        IrBinOp::Add,
                        ir_var("count", i32_ty.clone()),
                        ir_bitnot(ir_lit(0, "0", i32_ty.clone()), i32_ty.clone()),
                        i32_ty.clone(),
                    ),
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

    let rust = emit_rust_from_ir(&ir).expect("emit scalar while");

    assert!(rust.contains("pub fn countdown(mut count: i32) -> i32"));
    assert!(rust.contains("while count != 0i32 {"));
    assert!(rust.contains("count = count.checked_add(!0i32).expect(\"signed addition overflow\");"));
    assert!(rust.contains("return count;"));
    assert_rust_snippet_compiles("typed-ir-scalar-while", &rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_break_in_scalar_while_body() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "stop_at_limit".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::While {
                condition: ir_var("value", i32_ty.clone()),
                body: vec![IrStmt::If {
                    condition: ir_binary(
                        IrBinOp::Gt,
                        ir_var("value", i32_ty.clone()),
                        ir_lit(3, "3", i32_ty.clone()),
                        i32_ty.clone(),
                    ),
                    then_body: vec![IrStmt::Break { source_span: None }],
                    else_body: vec![],
                    source_span: None,
                }],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("value", i32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let rust = emit_rust_from_ir(&ir).expect("emit break in scalar while");

    assert!(rust.contains("pub fn stop_at_limit(value: i32) -> i32"));
    assert!(rust.contains("while value != 0i32 {"));
    assert!(rust.contains("if (value > 3i32) {"));
    assert!(rust.contains("break;"));
    assert!(rust.contains("return value;"));
    assert_rust_snippet_compiles("typed-ir-scalar-while-break", &rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_break_outside_loop() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "bad_break".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::Break { source_span: None },
            IrStmt::Return {
                value: Some(ir_var("value", i32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("top-level break must fail closed");

    assert!(error.reason.contains("break outside loop"));
}
