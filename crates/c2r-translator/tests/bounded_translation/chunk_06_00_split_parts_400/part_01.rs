#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_value_comparison_with_readonly_pointer_deref_operand_as_c_int() {
    let i32_ty = ir_i32();
    let const_i32_ty = ir_const(i32_ty.clone());
    let const_i32_ptr_ty = ir_pointer("const int *", "int *", const_i32_ty, false);
    let ir = IrFunction {
        name: "first_is_zero_value".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "p".to_string(),
            ty: const_i32_ptr_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(ir_binary(
                IrBinOp::Eq,
                ir_deref(ir_var("p", const_i32_ptr_ty), i32_ty.clone()),
                ir_lit(0, "0", i32_ty.clone()),
                i32_ty.clone(),
            )),
            source_span: None,
        }],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit deref value comparison");
    let rust = &emitted.rust;

    assert!(rust.contains("pub fn first_is_zero_value(p: &[i32]) -> i32"));
    assert!(rust.contains("if (p[0usize] == 0i32) { 1i32 } else { 0i32 }"));
    assert_rust_snippet_compiles("typed-ir-deref-value-comparison", rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_value_comparison_with_readonly_pointer_add_index_deref_operand_as_c_int() {
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
        name: "offset_is_zero_value".to_string(),
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
        body: vec![IrStmt::Return {
            value: Some(ir_binary(
                IrBinOp::Eq,
                ir_deref(ptr_plus_index, i32_ty.clone()),
                ir_lit(0, "0", i32_ty.clone()),
                i32_ty.clone(),
            )),
            source_span: None,
        }],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit offset deref value comparison");
    let rust = &emitted.rust;

    assert!(rust.contains("pub fn offset_is_zero_value(p: &[i32], i: usize) -> i32"));
    assert!(rust.contains("if (p[i as usize] == 0i32) { 1i32 } else { 0i32 }"));
    assert_rust_snippet_compiles("typed-ir-offset-deref-value-comparison", rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_value_comparison_with_pointer_operand() {
    let i32_ty = ir_i32();
    let ptr_ty = ir_pointer("int *", "int *", i32_ty.clone(), false);
    let ir = IrFunction {
        name: "bad_cmp_pointer_value".to_string(),
        return_type: i32_ty.clone(),
        params: vec![],
        body: vec![IrStmt::Return {
            value: Some(ir_binary(
                IrBinOp::Eq,
                ir_var("left", ptr_ty.clone()),
                ir_var("right", ptr_ty),
                i32_ty.clone(),
            )),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("comparison pointer operand must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("return expr"));
    assert!(error
        .reason
        .contains("comparison lhs has pointer type int * is unsupported"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_value_comparison_with_null_pointer_operand() {
    let i32_ty = ir_i32();
    let const_i32_ty = ir_const(i32_ty.clone());
    let ptr_ty = ir_pointer("const int *", "const int *", const_i32_ty, false);
    let ir = IrFunction {
        name: "has_values".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "values".to_string(),
            ty: ptr_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(ir_binary(
                IrBinOp::Neq,
                ir_var("values", ptr_ty.clone()),
                ir_null_ptr(ptr_ty),
                i32_ty.clone(),
            )),
            source_span: None,
        }],
        source_span: None,
    };

    let rust = emit_rust_from_ir(&ir).expect("emit null pointer value comparison");

    assert!(rust.contains("pub fn has_values(values: Option<&[i32]>) -> i32"));
    assert!(rust.contains("return (if values.is_some() { 1i32 } else { 0i32 });"));
    assert_rust_snippet_compiles("typed-ir-null-pointer-value-comparison", &rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_value_comparison_with_record_null_pointer_operand() {
    let i32_ty = ir_i32();
    let point_ty = ir_record_with_fields("point", vec![("x", i32_ty.clone())]);
    let ptr_ty = ir_pointer(
        "const struct point *",
        "const struct point *",
        ir_const(point_ty),
        false,
    );
    let ir = IrFunction {
        name: "has_point".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "p".to_string(),
            ty: ptr_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(ir_binary(
                IrBinOp::Neq,
                ir_var("p", ptr_ty.clone()),
                ir_null_ptr(ptr_ty),
                i32_ty.clone(),
            )),
            source_span: None,
        }],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit record null pointer value comparison");
    let rust = &emitted.rust;

    assert!(rust.contains("pub struct Point"), "{rust}");
    assert!(rust.contains("pub x: i32"), "{rust}");
    assert!(
        rust.contains("pub fn has_point(p: Option<&Point>) -> i32"),
        "{rust}"
    );
    assert!(
        rust.contains("return (if p.is_some() { 1i32 } else { 0i32 });"),
        "{rust}"
    );
    assert_rust_snippet_compiles("typed-ir-record-null-pointer-value-comparison", rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_value_comparison_with_unsupported_operand_type() {
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
        name: "bad_cmp_float_value".to_string(),
        return_type: i32_ty.clone(),
        params: vec![],
        body: vec![IrStmt::Return {
            value: Some(ir_binary(
                IrBinOp::Eq,
                ir_var("left", unsupported_ty.clone()),
                ir_var("right", unsupported_ty),
                i32_ty.clone(),
            )),
            source_span: None,
        }],
        source_span: None,
    };

    let error =
        emit_rust_from_ir(&ir).expect_err("comparison unsupported operand must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("return expr"));
    assert!(error.reason.contains(
        "comparison lhs has unsupported type float: floating type is outside typed IR subset"
    ));
}
