#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_scalar_while_with_logical_not_integer_condition() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "bump_until_nonzero".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::While {
                condition: ir_not(ir_var("value", i32_ty.clone()), i32_ty.clone()),
                body: vec![IrStmt::Assign {
                    target: ir_var("value", i32_ty.clone()),
                    value: ir_binary(
                        IrBinOp::Add,
                        ir_var("value", i32_ty.clone()),
                        ir_lit(1, "1", i32_ty.clone()),
                        i32_ty.clone(),
                    ),
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

    let rust = emit_rust_from_ir(&ir).expect("emit scalar while logical not condition");

    assert!(rust.contains("pub fn bump_until_nonzero(mut value: i32) -> i32"));
    assert!(rust.contains("while value == 0i32 {"));
    assert!(rust.contains("value = value.checked_add(1i32).expect(\"signed addition overflow\");"));
    assert!(rust.contains("return value;"));
    assert_rust_snippet_compiles("typed-ir-scalar-while-logical-not", &rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_scalar_if_with_logical_not_comparison_condition() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "clamp_nonpositive".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::If {
                condition: ir_not(
                    ir_binary(
                        IrBinOp::Gt,
                        ir_var("value", i32_ty.clone()),
                        ir_lit(0, "0", i32_ty.clone()),
                        i32_ty.clone(),
                    ),
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
                value: Some(ir_var("value", i32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let rust = emit_rust_from_ir(&ir).expect("emit scalar if logical not comparison condition");

    assert!(rust.contains("pub fn clamp_nonpositive(value: i32) -> i32"));
    assert!(rust.contains("if (value <= 0i32) {"));
    assert!(!rust.contains("!(value > 0i32)"));
    assert!(!rust.contains("(value > 0i32) == 0i32"));
    assert!(rust.contains("return 0i32;"));
    assert!(rust.contains("return value;"));
    assert_rust_snippet_compiles("typed-ir-scalar-if-logical-not-comparison", &rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_comparison_return_value_as_c_int() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "positive_as_int".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(ir_binary(
                IrBinOp::Gt,
                ir_var("value", i32_ty.clone()),
                ir_lit(0, "0", i32_ty.clone()),
                i32_ty.clone(),
            )),
            source_span: None,
        }],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit comparison return value as C int");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub fn positive_as_int(value: i32) -> i32"));
    assert!(rust.contains("return (if (value > 0i32) { 1i32 } else { 0i32 });"));
    assert!(!rust.contains("return (value > 0i32);"));
    assert_rust_snippet_compiles("typed-ir-comparison-return-value", rust);
}
