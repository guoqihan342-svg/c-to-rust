#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_runs_signed_add_with_checked_overflow_precondition() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "add_one_i32".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(ir_binary(
                IrBinOp::Add,
                ir_var("value", i32_ty.clone()),
                ir_lit(1, "1", i32_ty.clone()),
                i32_ty,
            )),
            source_span: None,
        }],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit signed checked add");
    assert!(
        emitted
            .rust
            .contains("return value.checked_add(1i32).expect(\"signed addition overflow\");"),
        "{}",
        emitted.rust
    );
    assert_rust_snippet_runs_with_overflow_checks(
        "typed-ir-signed-checked-add-defined-input",
        &emitted.rust,
        "assert_eq!(add_one_i32(41i32), 42i32);",
        false,
    );
    assert_rust_snippet_fails_with_overflow_checks(
        "typed-ir-signed-checked-add-overflow",
        &emitted.rust,
        "let _ = add_one_i32(i32::MAX);",
        false,
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_runs_signed_sub_with_checked_overflow_precondition() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "sub_one_i32".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(ir_binary(
                IrBinOp::Sub,
                ir_var("value", i32_ty.clone()),
                ir_lit(1, "1", i32_ty.clone()),
                i32_ty,
            )),
            source_span: None,
        }],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit signed checked sub");
    assert!(
        emitted
            .rust
            .contains("return value.checked_sub(1i32).expect(\"signed subtraction overflow\");"),
        "{}",
        emitted.rust
    );
    assert_rust_snippet_runs_with_overflow_checks(
        "typed-ir-signed-checked-sub-defined-input",
        &emitted.rust,
        "assert_eq!(sub_one_i32(42i32), 41i32);",
        false,
    );
    assert_rust_snippet_fails_with_overflow_checks(
        "typed-ir-signed-checked-sub-overflow",
        &emitted.rust,
        "let _ = sub_one_i32(i32::MIN);",
        false,
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_runs_signed_mul_with_checked_overflow_precondition() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "double_i32".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(ir_binary(
                IrBinOp::Mul,
                ir_var("value", i32_ty.clone()),
                ir_lit(2, "2", i32_ty.clone()),
                i32_ty,
            )),
            source_span: None,
        }],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit signed checked mul");
    assert!(
        emitted
            .rust
            .contains("return value.checked_mul(2i32).expect(\"signed multiplication overflow\");"),
        "{}",
        emitted.rust
    );
    assert_rust_snippet_runs_with_overflow_checks(
        "typed-ir-signed-checked-mul-defined-input",
        &emitted.rust,
        "assert_eq!(double_i32(21i32), 42i32);",
        false,
    );
    assert_rust_snippet_fails_with_overflow_checks(
        "typed-ir-signed-checked-mul-overflow",
        &emitted.rust,
        "let _ = double_i32(1_073_741_824i32);",
        false,
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_runs_nonliteral_signed_division_with_runtime_precondition() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "div_i32".to_string(),
        return_type: i32_ty.clone(),
        params: vec![
            IrParam {
                name: "value".to_string(),
                ty: i32_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "divisor".to_string(),
                ty: i32_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![IrStmt::Return {
            value: Some(ir_binary(
                IrBinOp::Div,
                ir_var("value", i32_ty.clone()),
                ir_var("divisor", i32_ty.clone()),
                i32_ty,
            )),
            source_span: None,
        }],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit signed checked division");
    assert!(
        emitted.rust.contains(
            "return value.checked_div(divisor).expect(\"division by zero or signed overflow\");"
        ),
        "{}",
        emitted.rust
    );
    assert_rust_snippet_runs_with_overflow_checks(
        "typed-ir-signed-checked-div-defined-input",
        &emitted.rust,
        "assert_eq!(div_i32(84i32, 2i32), 42i32);",
        false,
    );
    assert_rust_snippet_fails_with_overflow_checks(
        "typed-ir-signed-checked-div-zero-divisor",
        &emitted.rust,
        "let _ = div_i32(1i32, 0i32);",
        false,
    );
    assert_rust_snippet_fails_with_overflow_checks(
        "typed-ir-signed-checked-div-overflow",
        &emitted.rust,
        "let _ = div_i32(i32::MIN, -1i32);",
        false,
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_runs_nonliteral_signed_modulo_with_runtime_precondition() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "rem_i32".to_string(),
        return_type: i32_ty.clone(),
        params: vec![
            IrParam {
                name: "value".to_string(),
                ty: i32_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "divisor".to_string(),
                ty: i32_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![IrStmt::Return {
            value: Some(ir_binary(
                IrBinOp::Mod,
                ir_var("value", i32_ty.clone()),
                ir_var("divisor", i32_ty.clone()),
                i32_ty,
            )),
            source_span: None,
        }],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit signed checked modulo");
    assert!(
        emitted.rust.contains(
            "return value.checked_rem(divisor).expect(\"modulo by zero or signed overflow\");"
        ),
        "{}",
        emitted.rust
    );
    assert_rust_snippet_runs_with_overflow_checks(
        "typed-ir-signed-checked-rem-defined-input",
        &emitted.rust,
        "assert_eq!(rem_i32(85i32, 2i32), 1i32);",
        false,
    );
    assert_rust_snippet_fails_with_overflow_checks(
        "typed-ir-signed-checked-rem-zero-divisor",
        &emitted.rust,
        "let _ = rem_i32(1i32, 0i32);",
        false,
    );
    assert_rust_snippet_fails_with_overflow_checks(
        "typed-ir-signed-checked-rem-overflow",
        &emitted.rust,
        "let _ = rem_i32(i32::MIN, -1i32);",
        false,
    );
}
