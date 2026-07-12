#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_value_comparison_with_mismatched_operand_types() {
    let i32_ty = ir_i32();
    let u32_ty = ir_u32();
    let ir = IrFunction {
        name: "bad_cmp_mismatch_value".to_string(),
        return_type: i32_ty.clone(),
        params: vec![
            IrParam {
                name: "left".to_string(),
                ty: i32_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "right".to_string(),
                ty: u32_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![IrStmt::Return {
            value: Some(ir_binary(
                IrBinOp::Eq,
                ir_var("left", i32_ty.clone()),
                ir_var("right", u32_ty),
                i32_ty.clone(),
            )),
            source_span: None,
        }],
        source_span: None,
    };

    let error =
        emit_rust_from_ir(&ir).expect_err("comparison mismatched operands must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("return expr"));
    assert!(error
        .reason
        .contains("comparison operand types must match for =="));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_value_comparison_with_mismatched_operand_widths() {
    let i16_ty = ir_integer("short", "short", true, 16);
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "bad_cmp_width_value".to_string(),
        return_type: i32_ty.clone(),
        params: vec![
            IrParam {
                name: "left".to_string(),
                ty: i32_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "right".to_string(),
                ty: i16_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![IrStmt::Return {
            value: Some(ir_binary(
                IrBinOp::Eq,
                ir_var("left", i32_ty.clone()),
                ir_var("right", i16_ty),
                i32_ty.clone(),
            )),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("comparison width mismatch must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("return expr"));
    assert!(error
        .reason
        .contains("comparison operand types must match for =="));
    assert!(error.reason.contains("lhs=i32"));
    assert!(error.reason.contains("rhs=i16"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_value_comparison_with_non_int_result_type() {
    let i32_ty = ir_i32();
    let u32_ty = ir_u32();
    let ir = IrFunction {
        name: "bad_cmp_result_value".to_string(),
        return_type: u32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(ir_binary(
                IrBinOp::Eq,
                ir_var("value", i32_ty.clone()),
                ir_lit(0, "0", i32_ty.clone()),
                u32_ty,
            )),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("comparison result type must be C int");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("return expr"));
    assert!(error
        .reason
        .contains("comparison result type must be C int"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_short_circuit_return_value_as_c_int() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "both_nonzero_value".to_string(),
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
        body: vec![IrStmt::Return {
            value: Some(ir_binary(
                IrBinOp::LogAnd,
                ir_var("left", i32_ty.clone()),
                ir_var("right", i32_ty.clone()),
                i32_ty.clone(),
            )),
            source_span: None,
        }],
        source_span: None,
    };

    let rust = emit_rust_from_ir(&ir).expect("emit short-circuit return value as C int");

    assert!(rust.contains("pub fn both_nonzero_value(left: i32, right: i32) -> i32"));
    assert!(rust.contains("return (if (left != 0i32 && right != 0i32) { 1i32 } else { 0i32 });"));
    assert!(!rust.contains("return (left && right);"));
    assert_rust_snippet_compiles("typed-ir-short-circuit-return-value", &rust);
}
#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_short_circuit_assignment_value_as_c_int() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "either_nonzero_assign".to_string(),
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
            IrStmt::Assign {
                target: ir_var("left", i32_ty.clone()),
                value: ir_binary(
                    IrBinOp::LogOr,
                    ir_var("left", i32_ty.clone()),
                    ir_var("right", i32_ty.clone()),
                    i32_ty.clone(),
                ),
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("left", i32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let rust = emit_rust_from_ir(&ir).expect("emit short-circuit assignment value as C int");

    assert!(rust.contains("pub fn either_nonzero_assign(mut left: i32, right: i32) -> i32"));
    assert!(rust.contains("left = (if (left != 0i32 || right != 0i32) { 1i32 } else { 0i32 });"));
    assert!(rust.contains("return left;"));
    assert_rust_snippet_compiles("typed-ir-short-circuit-assignment-value", &rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_short_circuit_decl_initializer_as_c_int() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "either_comparison_init".to_string(),
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
            IrStmt::Decl {
                name: "out".to_string(),
                ty: i32_ty.clone(),
                init: Some(ir_binary(
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
                )),
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("out", i32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let rust = emit_rust_from_ir(&ir).expect("emit short-circuit decl initializer as C int");

    assert!(rust.contains("pub fn either_comparison_init(left: i32, right: i32) -> i32"));
    assert!(rust.contains(
        "let mut out: i32 = (if ((left < 3i32) || (right != 0i32)) { 1i32 } else { 0i32 });"
    ));
    assert!(rust.contains("return out;"));
    assert_rust_snippet_compiles("typed-ir-short-circuit-decl-initializer", &rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_short_circuit_value_with_non_int_result_type() {
    let i32_ty = ir_i32();
    let u32_ty = ir_u32();
    let ir = IrFunction {
        name: "bad_short_circuit_value_result".to_string(),
        return_type: u32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(ir_binary(
                IrBinOp::LogAnd,
                ir_var("value", i32_ty.clone()),
                ir_var("value", i32_ty.clone()),
                u32_ty,
            )),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("short-circuit value result must be C int");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("return expr"));
    assert!(error
        .reason
        .contains("short-circuit result type must be C int"));
}
