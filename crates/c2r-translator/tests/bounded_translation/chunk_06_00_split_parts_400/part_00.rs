#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_comparison_assignment_value_as_c_int() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "cmp_assign".to_string(),
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
                    IrBinOp::Neq,
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

    let rust = emit_rust_from_ir(&ir).expect("emit comparison assignment value as C int");

    assert!(rust.contains("pub fn cmp_assign(mut left: i32, right: i32) -> i32"));
    assert!(rust.contains("left = (if (left != right) { 1i32 } else { 0i32 });"));
    assert!(rust.contains("return left;"));
    assert_rust_snippet_compiles("typed-ir-comparison-assignment-value", &rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_comparison_decl_initializer_as_c_int() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "cmp_init".to_string(),
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
                    IrBinOp::Eq,
                    ir_var("left", i32_ty.clone()),
                    ir_var("right", i32_ty.clone()),
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

    let rust = emit_rust_from_ir(&ir).expect("emit comparison decl initializer as C int");

    assert!(rust.contains("pub fn cmp_init(left: i32, right: i32) -> i32"));
    assert!(rust.contains("let mut out: i32 = (if (left == right) { 1i32 } else { 0i32 });"));
    assert!(rust.contains("return out;"));
    assert_rust_snippet_compiles("typed-ir-comparison-decl-initializer", &rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_u8_comparison_return_value_as_c_int() {
    let i32_ty = ir_i32();
    let u8_ty = ir_u8();
    let ir = IrFunction {
        name: "byte_is_above".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: u8_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(ir_binary(
                IrBinOp::Gt,
                ir_var("value", u8_ty.clone()),
                ir_lit(127, "127", u8_ty.clone()),
                i32_ty.clone(),
            )),
            source_span: None,
        }],
        source_span: None,
    };

    let rust = emit_rust_from_ir(&ir).expect("emit u8 comparison return value as C int");

    assert!(rust.contains("pub fn byte_is_above(value: u8) -> i32"));
    assert!(rust.contains("return (if (value > 127u8) { 1i32 } else { 0i32 });"));
    assert_rust_snippet_compiles("typed-ir-u8-comparison-return-value", &rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_value_comparison_with_call_operand() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "bad_cmp_call".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(ir_binary(
                IrBinOp::Eq,
                IrExpr::Call {
                    callee: "helper".to_string(),
                    args: vec![ir_var("value", i32_ty.clone())],
                    ty: i32_ty.clone(),
                    source_span: None,
                },
                ir_lit(0, "0", i32_ty.clone()),
                i32_ty.clone(),
            )),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("comparison call operand must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("return expr"));
    assert!(error
        .reason
        .contains("comparison operand call expression helper is unsupported"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_value_comparison_with_incdec_operand_ordered_prelude() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "cmp_post_inc_value".to_string(),
        return_type: i32_ty.clone(),
        params: vec![
            IrParam {
                name: "value".to_string(),
                ty: i32_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "limit".to_string(),
                ty: i32_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![
            IrStmt::Decl {
                name: "result".to_string(),
                ty: i32_ty.clone(),
                init: Some(ir_binary(
                    IrBinOp::Lt,
                    IrExpr::IncDec {
                        target: Box::new(ir_var("value", i32_ty.clone())),
                        op: IrIncDecOp::Inc,
                        prefix: false,
                        ty: i32_ty.clone(),
                        source_span: None,
                    },
                    ir_var("limit", i32_ty.clone()),
                    i32_ty.clone(),
                )),
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_binary(
                    IrBinOp::Add,
                    ir_binary(
                        IrBinOp::Mul,
                        ir_var("value", i32_ty.clone()),
                        ir_lit(10, "10", i32_ty.clone()),
                        i32_ty.clone(),
                    ),
                    ir_var("result", i32_ty.clone()),
                    i32_ty.clone(),
                )),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit comparison incdec ordered prelude");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub fn cmp_post_inc_value(mut value: i32, limit: i32) -> i32"));
    assert!(rust.contains("let post_inc_value: i32 = value;"));
    assert!(rust.contains("value = value.checked_add(1i32).expect(\"signed addition overflow\");"));
    assert!(rust.contains(
        "let mut result: i32 = (if (post_inc_value < limit) { 1i32 } else { 0i32 });"
    ));
    assert_rust_snippet_runs(
        "typed-ir-comparison-incdec-ordered-prelude",
        rust,
        "    assert_eq!(cmp_post_inc_value(4, 5), 51);\n    assert_eq!(cmp_post_inc_value(5, 5), 60);",
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_value_comparison_incdec_with_same_scalar_sibling_read() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "bad_cmp_incdec_sibling_read".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(ir_binary(
                IrBinOp::Eq,
                IrExpr::IncDec {
                    target: Box::new(ir_var("value", i32_ty.clone())),
                    op: IrIncDecOp::Inc,
                    prefix: false,
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

    let error = emit_rust_from_ir(&ir)
        .expect_err("comparison incdec plus same-scalar read must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("return expr"));
    assert!(error
        .reason
        .contains("binary rhs reads variable value modified by lhs side-effect expression"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_value_comparison_with_deref_operand() {
    let i32_ty = ir_i32();
    let ptr_ty = ir_pointer("int *", "int *", i32_ty.clone(), false);
    let ir = IrFunction {
        name: "bad_cmp_deref_value".to_string(),
        return_type: i32_ty.clone(),
        params: vec![],
        body: vec![IrStmt::Return {
            value: Some(ir_binary(
                IrBinOp::Eq,
                IrExpr::Deref {
                    ptr: Box::new(ir_var("ptr", ptr_ty)),
                    ty: i32_ty.clone(),
                    source_span: None,
                },
                ir_lit(0, "0", i32_ty.clone()),
                i32_ty.clone(),
            )),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("comparison deref operand must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("return expr"));
    assert!(error.reason.contains("comparison lhs"));
    assert!(error.reason.contains("deref pointer ptr is not declared"));
}
