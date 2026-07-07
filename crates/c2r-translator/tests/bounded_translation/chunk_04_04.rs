#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_deeper_nested_direct_call_arguments() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "deeper_nested_call_expression".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(IrExpr::Call {
                callee: "helper".to_string(),
                args: vec![IrExpr::Call {
                    callee: "other".to_string(),
                    args: vec![IrExpr::Call {
                        callee: "third".to_string(),
                        args: vec![ir_var("value", i32_ty.clone())],
                        ty: i32_ty.clone(),
                        source_span: None,
                    }],
                    ty: i32_ty.clone(),
                    source_span: None,
                }],
                ty: i32_ty.clone(),
                source_span: None,
            }),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("deeper nested call arg must fail closed");

    assert!(error
        .reason
        .contains("nested call expressions are outside the bounded call subset"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_multiple_nested_direct_call_arguments() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "multiple_nested_call_expression".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(IrExpr::Call {
                callee: "helper".to_string(),
                args: vec![
                    IrExpr::Call {
                        callee: "left".to_string(),
                        args: vec![ir_var("value", i32_ty.clone())],
                        ty: i32_ty.clone(),
                        source_span: None,
                    },
                    IrExpr::Call {
                        callee: "right".to_string(),
                        args: vec![ir_var("value", i32_ty.clone())],
                        ty: i32_ty.clone(),
                        source_span: None,
                    },
                ],
                ty: i32_ty.clone(),
                source_span: None,
            }),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("multiple nested call args must fail closed");

    assert!(error
        .reason
        .contains("multiple nested call arguments are outside the bounded call subset"));
}
