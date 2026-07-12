#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_scalar_if_with_logical_not_integer_condition() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "is_zero".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::If {
                condition: ir_not(ir_var("value", i32_ty.clone()), i32_ty.clone()),
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

    let rust = emit_rust_from_ir(&ir).expect("emit scalar if logical not condition");

    assert!(rust.contains("pub fn is_zero(value: i32) -> i32"));
    assert!(rust.contains("if value == 0i32 {"));
    assert!(rust.contains("return 1i32;"));
    assert!(rust.contains("return 0i32;"));
    assert_rust_snippet_compiles("typed-ir-scalar-if-logical-not", &rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_logical_not_condition_with_readonly_pointer_add_index_deref_operand() {
    let i32_ty = ir_i32();
    let usize_ty = ir_usize();
    let u8_ty = ir_u8();
    let const_u8_ty = ir_const(u8_ty.clone());
    let const_u8_ptr_ty = ir_pointer("const uint8_t *", "uint8_t *", const_u8_ty, false);
    let ptr_plus_index = ir_binary(
        IrBinOp::Add,
        ir_var("p", const_u8_ptr_ty.clone()),
        ir_var("i", usize_ty.clone()),
        const_u8_ptr_ty.clone(),
    );
    let ir = IrFunction {
        name: "offset_is_zero_not_condition".to_string(),
        return_type: i32_ty.clone(),
        params: vec![
            IrParam {
                name: "p".to_string(),
                ty: const_u8_ptr_ty,
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
                condition: ir_not(ir_deref(ptr_plus_index, u8_ty), i32_ty.clone()),
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

    let rust = emit_rust_from_ir(&ir).expect("emit logical not offset deref condition");

    assert!(rust.contains("pub fn offset_is_zero_not_condition(p: &[u8], i: usize) -> i32"));
    assert!(rust.contains("if p[i as usize] == 0u8 {"));
    assert!(rust.contains("return 1i32;"));
    assert!(rust.contains("return 0i32;"));
    assert_rust_snippet_compiles("typed-ir-offset-deref-logical-not-condition", &rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_logical_not_condition_with_readonly_pointer_add_compound_index_deref_operand() {
    let i32_ty = ir_i32();
    let usize_ty = ir_usize();
    let u8_ty = ir_u8();
    let const_u8_ty = ir_const(u8_ty.clone());
    let const_u8_ptr_ty = ir_pointer("const uint8_t *", "uint8_t *", const_u8_ty, false);
    let compound_index = ir_binary(
        IrBinOp::Add,
        ir_var("i", usize_ty.clone()),
        ir_lit(1, "1", usize_ty.clone()),
        usize_ty.clone(),
    );
    let ptr_plus_compound = ir_binary(
        IrBinOp::Add,
        ir_var("p", const_u8_ptr_ty.clone()),
        compound_index,
        const_u8_ptr_ty.clone(),
    );
    let ir = IrFunction {
        name: "bad_logical_not_offset_compound_index".to_string(),
        return_type: i32_ty.clone(),
        params: vec![
            IrParam {
                name: "p".to_string(),
                ty: const_u8_ptr_ty,
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
                condition: ir_not(ir_deref(ptr_plus_compound, u8_ty), i32_ty.clone()),
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
        emit_rust_from_ir(&ir).expect_err("compound index logical-not deref must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("stmt[0].if condition"));
    assert!(error.reason.contains("logical not operand"));
    assert!(error
        .reason
        .contains("deref pointer add index cannot use compound expression"));
}
