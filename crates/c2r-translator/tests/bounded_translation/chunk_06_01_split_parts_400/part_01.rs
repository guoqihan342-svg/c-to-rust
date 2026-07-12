#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_short_circuit_value_with_call_operand() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "bad_short_circuit_value_call".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(ir_binary(
                IrBinOp::LogOr,
                IrExpr::Call {
                    callee: "helper".to_string(),
                    args: vec![ir_var("value", i32_ty.clone())],
                    ty: i32_ty.clone(),
                    source_span: None,
                },
                ir_var("value", i32_ty.clone()),
                i32_ty.clone(),
            )),
            source_span: None,
        }],
        source_span: None,
    };

    let error =
        emit_rust_from_ir(&ir).expect_err("short-circuit value call operand must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("return expr"));
    assert!(error
        .reason
        .contains("lhs call expression helper is unsupported"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_value_comparison_with_integral_cast_operand_as_c_int() {
    let i32_ty = ir_i32();
    let u32_ty = ir_u32();
    let ir = IrFunction {
        name: "cmp_value_cast".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: u32_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(ir_binary(
                IrBinOp::Gt,
                ir_var("value", u32_ty.clone()),
                IrExpr::Cast {
                    target: u32_ty,
                    expr: Box::new(ir_lit(0, "0", i32_ty.clone())),
                    implicit: true,
                    source_span: None,
                },
                i32_ty,
            )),
            source_span: None,
        }],
        source_span: None,
    };

    let rust = emit_rust_from_ir(&ir).expect("emit value comparison integral cast operand");

    assert!(rust.contains("pub fn cmp_value_cast(value: u32) -> i32"));
    assert!(rust.contains("return (if (value > (0i32 as u32)) { 1i32 } else { 0i32 });"));
    assert_rust_snippet_compiles("typed-ir-comparison-value-cast", &rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_comparison_with_non_integer_cast_operand() {
    let i32_ty = ir_i32();
    let u32_ty = ir_u32();
    let float_ty = IrType {
        spelled: "float".to_string(),
        canonical: "float".to_string(),
        kind: IrTypeKind::Unsupported {
            reason: "floating type is outside typed IR subset".to_string(),
        },
        is_const: false,
        width_bits: Some(32),
        source_span: None,
    };
    let ir = IrFunction {
        name: "bad_cmp_non_integer_cast".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: u32_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(ir_binary(
                IrBinOp::Gt,
                ir_var("value", u32_ty.clone()),
                IrExpr::Cast {
                    target: u32_ty,
                    expr: Box::new(ir_lit(0, "0.0", float_ty)),
                    implicit: true,
                    source_span: None,
                },
                i32_ty,
            )),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("non-integer comparison cast must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("return expr"));
    assert!(error
        .reason
        .contains("comparison rhs cast source float is unsupported"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_value_comparison_with_post_increment_byte_read_operand() {
    let i32_ty = ir_i32();
    let u8_ty = ir_u8();
    let const_u8_ptr = ir_pointer(
        "const uint8_t *",
        "const unsigned char *",
        ir_const(u8_ty.clone()),
        false,
    );
    let byte_read = IrExpr::Deref {
        ptr: Box::new(IrExpr::IncDec {
            target: Box::new(ir_var("p", const_u8_ptr.clone())),
            op: IrIncDecOp::Inc,
            prefix: false,
            ty: const_u8_ptr.clone(),
            source_span: None,
        }),
        ty: u8_ty.clone(),
        source_span: None,
    };
    let ir = IrFunction {
        name: "bad_cmp_byte_read_value".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "p".to_string(),
            ty: const_u8_ptr,
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(ir_binary(
                IrBinOp::Eq,
                byte_read,
                ir_lit(0, "0", u8_ty),
                i32_ty,
            )),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("comparison byte-read operand must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("return expr"));
    assert!(error.reason.contains("comparison lhs"));
    assert!(error.reason.contains("deref pointer must be Var"));
}
