#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_logical_not_value_with_readonly_pointer_deref_operand() {
    let i32_ty = ir_i32();
    let u8_ty = ir_u8();
    let const_u8_ty = ir_const(u8_ty.clone());
    let const_u8_ptr_ty = ir_pointer("const uint8_t *", "uint8_t *", const_u8_ty, false);
    let ir = IrFunction {
        name: "first_is_zero_not".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "p".to_string(),
            ty: const_u8_ptr_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(ir_not(
                ir_deref(ir_var("p", const_u8_ptr_ty), u8_ty),
                i32_ty,
            )),
            source_span: None,
        }],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit logical not deref value");
    let rust = &emitted.rust;

    assert!(rust.contains("pub fn first_is_zero_not(p: &[u8]) -> i32"));
    assert!(rust.contains("if p[0usize] == 0u8 { 1i32 } else { 0i32 }"));
    assert_rust_snippet_compiles("typed-ir-logical-not-deref-value", rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_logical_not_value_with_readonly_pointer_add_index_deref_operand() {
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
        name: "offset_is_zero_not".to_string(),
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
        body: vec![IrStmt::Return {
            value: Some(ir_not(ir_deref(ptr_plus_index, u8_ty), i32_ty)),
            source_span: None,
        }],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit logical not offset deref value");
    let rust = &emitted.rust;

    assert!(rust.contains("pub fn offset_is_zero_not(p: &[u8], i: usize) -> i32"));
    assert!(rust.contains("if p[i as usize] == 0u8 { 1i32 } else { 0i32 }"));
    assert_rust_snippet_compiles("typed-ir-logical-not-offset-deref-value", rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_logical_not_value_with_pointer_operand() {
    let i32_ty = ir_i32();
    let ptr_ty = ir_pointer("int *", "int *", i32_ty.clone(), false);
    let ir = IrFunction {
        name: "bad_logical_not_pointer".to_string(),
        return_type: i32_ty.clone(),
        params: vec![],
        body: vec![IrStmt::Return {
            value: Some(ir_not(ir_var("ptr", ptr_ty), i32_ty)),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("logical not pointer operand must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("return expr"));
    assert!(error.reason.contains("logical not operand zero"));
    assert!(error.reason.contains("pointer type int * is unsupported"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_logical_not_value_with_unsupported_operand_type() {
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
        name: "bad_logical_not_float".to_string(),
        return_type: i32_ty.clone(),
        params: vec![],
        body: vec![IrStmt::Return {
            value: Some(ir_not(ir_var("value", unsupported_ty), i32_ty)),
            source_span: None,
        }],
        source_span: None,
    };

    let error =
        emit_rust_from_ir(&ir).expect_err("logical not unsupported operand type must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("return expr"));
    assert!(error.reason.contains("logical not operand zero"));
    assert!(error
        .reason
        .contains("unsupported type float: floating type is outside typed IR subset"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_logical_not_value_with_non_int_result_type() {
    let i32_ty = ir_i32();
    let u32_ty = ir_u32();
    let ir = IrFunction {
        name: "bad_logical_not_result_type".to_string(),
        return_type: u32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(ir_not(ir_var("value", i32_ty), u32_ty)),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("logical not result type must be C int");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("return expr"));
    assert!(error
        .reason
        .contains("logical not result type must be C int"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_non_void_function_without_return_value_in_generic_emitter() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "missing_return".to_string(),
        return_type: i32_ty.clone(),
        params: vec![],
        body: vec![IrStmt::Expr {
            expr: ir_lit(1, "1", i32_ty),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("non-void function must return");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error
        .reason
        .contains("non-void function must end with a return value"));
}
