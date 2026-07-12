#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_runs_nonliteral_unsigned_division_and_modulo_with_runtime_precondition() {
    let u32_ty = ir_u32();
    let div_ir = IrFunction {
        name: "div_u32".to_string(),
        return_type: u32_ty.clone(),
        params: vec![
            IrParam {
                name: "value".to_string(),
                ty: u32_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "divisor".to_string(),
                ty: u32_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![IrStmt::Return {
            value: Some(ir_binary(
                IrBinOp::Div,
                ir_var("value", u32_ty.clone()),
                ir_var("divisor", u32_ty.clone()),
                u32_ty.clone(),
            )),
            source_span: None,
        }],
        source_span: None,
    };
    let rem_ir = IrFunction {
        name: "rem_u32".to_string(),
        return_type: u32_ty.clone(),
        params: vec![
            IrParam {
                name: "value".to_string(),
                ty: u32_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "divisor".to_string(),
                ty: u32_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![IrStmt::Return {
            value: Some(ir_binary(
                IrBinOp::Mod,
                ir_var("value", u32_ty.clone()),
                ir_var("divisor", u32_ty.clone()),
                u32_ty,
            )),
            source_span: None,
        }],
        source_span: None,
    };

    let div = emit_rust_from_ir(&div_ir).expect("emit unsigned checked division");
    let rem = emit_rust_from_ir(&rem_ir).expect("emit unsigned checked modulo");
    assert!(
        div.rust
            .contains("return value.checked_div(divisor).expect(\"division by zero\");"),
        "{}",
        div.rust
    );
    assert!(
        rem.rust
            .contains("return value.checked_rem(divisor).expect(\"modulo by zero\");"),
        "{}",
        rem.rust
    );
    assert_rust_snippet_runs_with_overflow_checks(
        "typed-ir-unsigned-checked-div-defined-input",
        &div.rust,
        "assert_eq!(div_u32(84u32, 2u32), 42u32);",
        false,
    );
    assert_rust_snippet_runs_with_overflow_checks(
        "typed-ir-unsigned-checked-rem-defined-input",
        &rem.rust,
        "assert_eq!(rem_u32(85u32, 2u32), 1u32);",
        false,
    );
    assert_rust_snippet_fails_with_overflow_checks(
        "typed-ir-unsigned-checked-div-zero-divisor",
        &div.rust,
        "let _ = div_u32(1u32, 0u32);",
        false,
    );
    assert_rust_snippet_fails_with_overflow_checks(
        "typed-ir-unsigned-checked-rem-zero-divisor",
        &rem.rust,
        "let _ = rem_u32(1u32, 0u32);",
        false,
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_runs_nonliteral_shift_with_runtime_precondition() {
    let u32_ty = ir_u32();
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "shift_left_u32".to_string(),
        return_type: u32_ty.clone(),
        params: vec![
            IrParam {
                name: "value".to_string(),
                ty: u32_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "count".to_string(),
                ty: i32_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![IrStmt::Return {
            value: Some(ir_binary(
                IrBinOp::Shl,
                ir_var("value", u32_ty.clone()),
                ir_var("count", i32_ty),
                u32_ty,
            )),
            source_span: None,
        }],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit checked shift");
    assert!(
        emitted.rust.contains("return value.checked_shl(core::convert::TryFrom::try_from(count).expect(\"shift count must be nonnegative and fit u32\")).expect(\"shift count out of range\");"),
        "{}",
        emitted.rust
    );
    assert_rust_snippet_runs_with_overflow_checks(
        "typed-ir-checked-shift-defined-input",
        &emitted.rust,
        "assert_eq!(shift_left_u32(1u32, 4i32), 16u32);",
        false,
    );
    assert_rust_snippet_fails_with_overflow_checks(
        "typed-ir-checked-shift-negative-count",
        &emitted.rust,
        "let _ = shift_left_u32(1u32, -1i32);",
        false,
    );
    assert_rust_snippet_fails_with_overflow_checks(
        "typed-ir-checked-shift-width-count",
        &emitted.rust,
        "let _ = shift_left_u32(1u32, 32i32);",
        false,
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_runs_unsigned_add_with_wrapping_semantics() {
    let u32_ty = ir_u32();
    let ir = IrFunction {
        name: "add_one".to_string(),
        return_type: u32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: u32_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(ir_binary(
                IrBinOp::Add,
                ir_var("value", u32_ty.clone()),
                ir_lit(1, "1U", u32_ty.clone()),
                u32_ty,
            )),
            source_span: None,
        }],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit unsigned wrapping add");

    assert_rust_snippet_runs(
        "typed-ir-unsigned-wrapping-add",
        &emitted.rust,
        "assert_eq!(add_one(u32::MAX), 0u32);",
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_runs_unsigned_sub_with_wrapping_semantics() {
    let u32_ty = ir_u32();
    let ir = IrFunction {
        name: "sub_one_u32".to_string(),
        return_type: u32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: u32_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(ir_binary(
                IrBinOp::Sub,
                ir_var("value", u32_ty.clone()),
                ir_lit(1, "1U", u32_ty.clone()),
                u32_ty,
            )),
            source_span: None,
        }],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit unsigned wrapping sub");

    assert_rust_snippet_runs(
        "typed-ir-unsigned-wrapping-sub",
        &emitted.rust,
        "assert_eq!(sub_one_u32(0u32), u32::MAX);",
    );
}
