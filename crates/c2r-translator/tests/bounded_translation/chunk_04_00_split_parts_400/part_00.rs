#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_signed_right_shift_with_explicit_contract_policy() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "signed_rshift_contract".to_string(),
        return_type: i32_ty.clone(),
        params: vec![
            IrParam {
                name: "value".to_string(),
                ty: i32_ty.clone(),
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
                IrBinOp::Shr,
                ir_var("value", i32_ty.clone()),
                ir_var("count", i32_ty.clone()),
                i32_ty,
            )),
            source_span: None,
        }],
        source_span: None,
    };
    let policy = EmitPolicy {
        signed_right_shift: SignedRightShiftPolicy::ImplementationDefinedArithmetic,
        ..Default::default()
    };

    let emitted = emit_rust_from_ir_with_globals_and_policy(&ir, &[], policy)
        .expect("explicit contract policy should allow signed right shift");

    assert!(emitted.rust.contains("pub fn signed_rshift_contract"));
    assert!(emitted.rust.contains(".checked_shr("));
    assert_rust_snippet_compiles("typed-ir-signed-rshift-contract", &emitted.rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_scalar_mul_div_mod() {
    let i32_ty = ir_i32();
    let mul = ir_binary(
        IrBinOp::Mul,
        ir_var("value", i32_ty.clone()),
        ir_lit(3, "3", i32_ty.clone()),
        i32_ty.clone(),
    );
    let div = ir_binary(
        IrBinOp::Div,
        mul,
        ir_lit(2, "2", i32_ty.clone()),
        i32_ty.clone(),
    );
    let rem = ir_binary(
        IrBinOp::Mod,
        div,
        ir_lit(5, "5", i32_ty.clone()),
        i32_ty.clone(),
    );
    let ir = IrFunction {
        name: "mul_div_mod".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty,
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(rem),
            source_span: None,
        }],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit scalar mul/div/mod");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub fn mul_div_mod(value: i32) -> i32"));
    assert!(rust.contains("return value.checked_mul(3i32).expect(\"signed multiplication overflow\").checked_div(2i32).expect(\"division by zero or signed overflow\").checked_rem(5i32).expect(\"modulo by zero or signed overflow\");"));
    assert_rust_snippet_compiles("typed-ir-scalar-mul-div-mod", rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_scalar_bit_or_and_left_shift() {
    let u32_ty = ir_u32();
    let shifted = ir_binary(
        IrBinOp::Shl,
        ir_var("value", u32_ty.clone()),
        ir_lit(4, "4U", u32_ty.clone()),
        u32_ty.clone(),
    );
    let mask = ir_binary(
        IrBinOp::BitOr,
        shifted,
        ir_lit(3, "3U", u32_ty.clone()),
        u32_ty.clone(),
    );
    let ir = IrFunction {
        name: "pack_flags".to_string(),
        return_type: u32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: u32_ty,
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(mask),
            source_span: None,
        }],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit scalar bit-or and left shift");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub fn pack_flags(value: u32) -> u32"));
    assert!(rust.contains("return (value.checked_shl(core::convert::TryFrom::try_from(4u32).expect(\"shift count must be nonnegative and fit u32\")).expect(\"shift count out of range\") | 3u32);"));
    assert!(!rust.contains("crc32_update_byte"));
    assert_rust_snippet_compiles("typed-ir-scalar-bit-or-left-shift", rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_signed_unary_minus() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "neg_value".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(ir_neg(ir_var("value", i32_ty.clone()), i32_ty)),
            source_span: None,
        }],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit signed unary minus");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub fn neg_value(value: i32) -> i32"));
    assert!(rust.contains("return (-value);"));
    assert!(!rust.contains("crc32_update_byte"));
    assert_rust_snippet_compiles("typed-ir-signed-unary-minus", rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_direct_identifier_call_expressions() {
    let i32_ty = ir_i32();
    let helper_call = |arg: IrExpr| IrExpr::Call {
        callee: "helper".to_string(),
        args: vec![arg],
        ty: i32_ty.clone(),
        source_span: None,
    };
    let ir = IrFunction {
        name: "call_expression".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::Decl {
                name: "first".to_string(),
                ty: i32_ty.clone(),
                init: Some(helper_call(ir_var("value", i32_ty.clone()))),
                source_span: None,
            },
            IrStmt::Assign {
                target: ir_var("value", i32_ty.clone()),
                value: helper_call(ir_var("first", i32_ty.clone())),
                source_span: None,
            },
            IrStmt::Return {
                value: Some(helper_call(ir_var("value", i32_ty.clone()))),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit direct call expressions");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub fn call_expression(mut value: i32) -> i32"));
    assert!(rust.contains("let mut first: i32 = helper(value);"));
    assert!(rust.contains("value = helper(first);"));
    assert!(rust.contains("return helper(value);"));
    assert_rust_snippet_compiles(
        "typed-ir-direct-call-expressions",
        &format!("fn helper(value: i32) -> i32 {{ value }}\n{rust}"),
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_direct_identifier_call_statement() {
    let i32_ty = ir_i32();
    let void_ty = ir_void();
    let ir = IrFunction {
        name: "call_hook".to_string(),
        return_type: void_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Expr {
            expr: IrExpr::Call {
                callee: "observe".to_string(),
                args: vec![ir_var("value", i32_ty)],
                ty: void_ty,
                source_span: None,
            },
            source_span: None,
        }],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit direct call statement");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub fn call_hook(value: i32)"));
    assert!(rust.contains("observe(value);"));
    assert_rust_snippet_compiles(
        "typed-ir-direct-call-statement",
        &format!("fn observe(_: i32) {{}}\n{rust}"),
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_direct_call_argument_integral_cast() {
    let u8_ty = ir_u8();
    let u32_ty = ir_u32();
    let void_ty = ir_void();
    let ir = IrFunction {
        name: "call_hook_cast".to_string(),
        return_type: void_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: u8_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Expr {
            expr: IrExpr::Call {
                callee: "observe".to_string(),
                args: vec![IrExpr::Cast {
                    target: u32_ty,
                    expr: Box::new(ir_var("value", u8_ty)),
                    implicit: true,
                    source_span: None,
                }],
                ty: void_ty,
                source_span: None,
            },
            source_span: None,
        }],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit direct call argument cast");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub fn call_hook_cast(value: u8)"));
    assert!(rust.contains("observe((value as u32));"));
    assert_rust_snippet_compiles(
        "typed-ir-direct-call-argument-integral-cast",
        &format!("fn observe(_: u32) {{}}\n{rust}"),
    );
}
