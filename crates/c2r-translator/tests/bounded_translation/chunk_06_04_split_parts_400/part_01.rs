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
