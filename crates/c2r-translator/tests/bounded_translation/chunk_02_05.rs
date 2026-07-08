#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_unused_readonly_pointer_param_without_slice_evidence() {
    let i32_ty = ir_i32();
    let const_i32_ty = ir_const(i32_ty.clone());
    let const_i32_ptr_ty = ir_pointer("const int *", "const int *", const_i32_ty, false);
    let ir = IrFunction {
        name: "ignore_values".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "values".to_string(),
            ty: const_i32_ptr_ty,
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(ir_lit(0, "0", i32_ty)),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir)
        .expect_err("readonly pointer params need explicit slice lowering evidence");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(
        error.reason.contains("pointer-to-slice lowering evidence"),
        "{:?}",
        error.reason
    );
    assert!(error.reason.contains("values"), "{:?}", error.reason);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_unused_readonly_8_bit_pointer_param_as_raw_candidate() {
    let i32_ty = ir_i32();
    let char_ty = ir_integer("char", "char", true, 8);
    let const_char_ptr_ty = ir_pointer("const char *", "char *", ir_const(char_ty), false);
    let ir = IrFunction {
        name: "ignore_name".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "name".to_string(),
            ty: const_char_ptr_ty,
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(ir_lit(0, "0", i32_ty)),
            source_span: None,
        }],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit unused readonly 8-bit pointer raw candidate");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub fn ignore_name(name: *const core::ffi::c_void) -> i32"));
    assert!(rust.contains("return 0i32;"));
    assert_rust_snippet_compiles("typed-ir-unused-readonly-8-bit-pointer-param", rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_readonly_pointer_deref_read_as_slice_zero_index() {
    let u8_ty = ir_u8();
    let const_u8_ty = ir_const(u8_ty.clone());
    let const_u8_ptr_ty = ir_pointer("const uint8_t *", "uint8_t *", const_u8_ty, false);
    let ir = IrFunction {
        name: "read_first_byte".to_string(),
        return_type: u8_ty.clone(),
        params: vec![IrParam {
            name: "p".to_string(),
            ty: const_u8_ptr_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(ir_deref(ir_var("p", const_u8_ptr_ty), u8_ty)),
            source_span: None,
        }],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit readonly pointer deref read");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub fn read_first_byte(p: &[u8]) -> u8"));
    assert!(rust.contains("return p[0usize];"));
    assert_rust_snippet_compiles("typed-ir-readonly-pointer-deref-read", rust);
}
#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_readonly_pointer_add_index_deref_read() {
    let u8_ty = ir_u8();
    let usize_ty = ir_usize();
    let const_u8_ty = ir_const(u8_ty.clone());
    let const_u8_ptr_ty = ir_pointer("const uint8_t *", "uint8_t *", const_u8_ty, false);
    let ptr_plus_index = ir_binary(
        IrBinOp::Add,
        ir_var("p", const_u8_ptr_ty.clone()),
        ir_var("i", usize_ty.clone()),
        const_u8_ptr_ty.clone(),
    );
    let ir = IrFunction {
        name: "read_byte_at".to_string(),
        return_type: u8_ty.clone(),
        params: vec![
            IrParam {
                name: "p".to_string(),
                ty: const_u8_ptr_ty,
                source_span: None,
            },
            IrParam {
                name: "i".to_string(),
                ty: usize_ty,
                source_span: None,
            },
        ],
        body: vec![IrStmt::Return {
            value: Some(ir_deref(ptr_plus_index, u8_ty)),
            source_span: None,
        }],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit readonly pointer add-index deref read");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub fn read_byte_at(p: &[u8], i: usize) -> u8"));
    assert!(rust.contains("return p[i as usize];"));
    assert_rust_snippet_compiles("typed-ir-readonly-pointer-add-index-deref-read", rust);
}
