#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_pointer_value_direct_call_arguments_with_explicit_boundary() {
    let i32_ty = ir_i32();
    let ptr_ty = ir_pointer("const int *", "const int *", ir_const(i32_ty.clone()), true);
    let ir = IrFunction {
        name: "call_take_ptr".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "values".to_string(),
            ty: ptr_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(IrExpr::Call {
                callee: "take_ptr".to_string(),
                args: vec![ir_var("values", ptr_ty)],
                ty: i32_ty,
                source_span: None,
            }),
            source_span: None,
        }],
        source_span: None,
    };

    let error =
        emit_rust_from_ir(&ir).expect_err("pointer value direct call arguments must fail closed");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(
        error.reason.contains("call arg[0] pointer value argument"),
        "{:?}",
        error.reason
    );
    assert!(error.reason.contains("const int *"), "{:?}", error.reason);
    assert!(
        error
            .reason
            .contains("explicit ownership/lifetime/ABI lowering"),
        "{:?}",
        error.reason
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_pointer_value_return_with_explicit_boundary() {
    let i32_ty = ir_i32();
    let ptr_ty = ir_pointer("const int *", "const int *", ir_const(i32_ty), true);
    let ir = IrFunction {
        name: "return_pointer".to_string(),
        return_type: ptr_ty.clone(),
        params: vec![IrParam {
            name: "values".to_string(),
            ty: ptr_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(ir_var("values", ptr_ty)),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("pointer value returns must fail closed");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(
        error.reason.contains("pointer value return"),
        "{:?}",
        error.reason
    );
    assert!(error.reason.contains("const int *"), "{:?}", error.reason);
    assert!(
        error
            .reason
            .contains("explicit ownership/lifetime/ABI lowering"),
        "{:?}",
        error.reason
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_nested_direct_call_argument() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "nested_call_expression".to_string(),
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
                    args: vec![ir_var("value", i32_ty.clone())],
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

    let emitted = emit_rust_from_ir(&ir).expect("emit one-level nested direct call arg");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub fn nested_call_expression(value: i32) -> i32"));
    assert!(rust.contains("return helper(other(value));"));
    assert_rust_snippet_compiles(
        "typed-ir-nested-direct-call-argument",
        &format!(
            "fn other(value: i32) -> i32 {{ value + 1 }}\nfn helper(value: i32) -> i32 {{ value }}\n{rust}"
        ),
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_single_prefix_inc_direct_call_argument() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "prefix_inc_call_argument".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(IrExpr::Call {
                callee: "helper".to_string(),
                args: vec![IrExpr::IncDec {
                    target: Box::new(ir_var("value", i32_ty.clone())),
                    op: IrIncDecOp::Inc,
                    prefix: true,
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

    let emitted = emit_rust_from_ir(&ir).expect("emit prefix inc direct call arg");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub fn prefix_inc_call_argument(mut value: i32) -> i32"));
    assert!(rust.contains("value = value.checked_add(1i32).expect(\"signed addition overflow\");"));
    assert!(rust.contains("return helper(value);"));
    assert_rust_snippet_runs(
        "typed-ir-prefix-inc-direct-call-arg",
        &format!("fn helper(value: i32) -> i32 {{ value * 2 }}\n{rust}"),
        "    assert_eq!(prefix_inc_call_argument(5), 12);",
    );
}
