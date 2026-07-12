#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_memcmp_direct_call_for_readonly_byte_slices() {
    let i32_ty = ir_i32();
    let usize_ty = ir_usize();
    let const_u8_ptr_ty = ir_pointer(
        "const uint8_t *",
        "const unsigned char *",
        ir_const(ir_u8()),
        true,
    );
    let ir = IrFunction {
        name: "compare_prefix".to_string(),
        return_type: i32_ty.clone(),
        params: vec![
            IrParam {
                name: "left".to_string(),
                ty: const_u8_ptr_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "right".to_string(),
                ty: const_u8_ptr_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "count".to_string(),
                ty: usize_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![IrStmt::Return {
            value: Some(IrExpr::Call {
                callee: "memcmp".to_string(),
                args: vec![
                    ir_var("left", const_u8_ptr_ty.clone()),
                    ir_var("right", const_u8_ptr_ty),
                    ir_var("count", usize_ty),
                ],
                ty: i32_ty,
                source_span: None,
            }),
            source_span: None,
        }],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit modeled C memcmp");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(
        rust.contains("pub fn compare_prefix(left: &[u8], right: &[u8], count: usize) -> i32"),
        "{rust}"
    );
    assert!(rust.contains(".get(..(count as usize))"), "{rust}");
    assert!(rust.contains("C memcmp precondition violated"), "{rust}");
    assert!(!rust.contains("memcmp(left, right, count)"), "{rust}");
    assert_rust_snippet_runs(
        "typed-ir-memcmp-model",
        rust,
        r#"
    let left = [1u8, 2, 3, 4];
    let equal = [1u8, 2, 9, 9];
    let greater = [1u8, 3, 0, 0];
    let shorter = [1u8, 2, 3, 4];
    assert_eq!(compare_prefix(&left, &equal, 2), 0);
    assert!(compare_prefix(&left, &greater, 3) < 0);
    assert_eq!(compare_prefix(&left, &shorter, 4), 0);
"#,
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_memcmp_treats_signed_byte_slices_as_unsigned_bytes() {
    let i32_ty = ir_i32();
    let usize_ty = ir_usize();
    let i8_ty = ir_integer("int8_t", "signed char", true, 8);
    let const_i8_ptr_ty = ir_pointer(
        "const int8_t *",
        "const signed char *",
        ir_const(i8_ty),
        true,
    );
    let ir = IrFunction {
        name: "compare_signed_prefix".to_string(),
        return_type: i32_ty.clone(),
        params: vec![
            IrParam {
                name: "left".to_string(),
                ty: const_i8_ptr_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "right".to_string(),
                ty: const_i8_ptr_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "count".to_string(),
                ty: usize_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![IrStmt::Return {
            value: Some(IrExpr::Call {
                callee: "memcmp".to_string(),
                args: vec![
                    ir_var("left", const_i8_ptr_ty.clone()),
                    ir_var("right", const_i8_ptr_ty),
                    ir_var("count", usize_ty),
                ],
                ty: i32_ty,
                source_span: None,
            }),
            source_span: None,
        }],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit signed-byte C memcmp");
    assert_rust_snippet_runs(
        "typed-ir-memcmp-signed-byte-model",
        &emitted.rust,
        r#"
    let high = [-1i8];
    let low = [1i8];
    assert!(compare_signed_prefix(&high, &low, 1) > 0);
"#,
    );
}
