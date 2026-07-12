#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_readonly_pointer_add_incdec_index_deref_read() {
    let u8_ty = ir_u8();
    let usize_ty = ir_usize();
    let const_u8_ty = ir_const(u8_ty.clone());
    let const_u8_ptr_ty = ir_pointer("const uint8_t *", "uint8_t *", const_u8_ty, false);
    let inc_index = IrExpr::IncDec {
        target: Box::new(ir_var("i", usize_ty.clone())),
        op: IrIncDecOp::Inc,
        prefix: false,
        ty: usize_ty.clone(),
        source_span: None,
    };
    let ptr_plus_inc = ir_binary(
        IrBinOp::Add,
        ir_var("p", const_u8_ptr_ty.clone()),
        inc_index,
        const_u8_ptr_ty.clone(),
    );
    let ir = IrFunction {
        name: "bad_incdec_index_offset_read".to_string(),
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
            value: Some(ir_deref(ptr_plus_inc, u8_ty)),
            source_span: None,
        }],
        source_span: None,
    };

    let error =
        emit_rust_from_ir(&ir).expect_err("inc/dec index pointer offset deref must fail closed");

    assert!(error
        .reason
        .contains("deref pointer add index cannot use increment/decrement"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_readonly_pointer_add_deref_index_deref_read() {
    let u8_ty = ir_u8();
    let usize_ty = ir_usize();
    let const_u8_ty = ir_const(u8_ty.clone());
    let const_usize_ty = ir_const(usize_ty.clone());
    let const_u8_ptr_ty = ir_pointer("const uint8_t *", "uint8_t *", const_u8_ty, false);
    let const_usize_ptr_ty = ir_pointer("const size_t *", "size_t *", const_usize_ty, false);
    let deref_index = ir_deref(ir_var("idx", const_usize_ptr_ty.clone()), usize_ty.clone());
    let ptr_plus_deref = ir_binary(
        IrBinOp::Add,
        ir_var("p", const_u8_ptr_ty.clone()),
        deref_index,
        const_u8_ptr_ty.clone(),
    );
    let ir = IrFunction {
        name: "bad_deref_index_offset_read".to_string(),
        return_type: u8_ty.clone(),
        params: vec![
            IrParam {
                name: "p".to_string(),
                ty: const_u8_ptr_ty,
                source_span: None,
            },
            IrParam {
                name: "idx".to_string(),
                ty: const_usize_ptr_ty,
                source_span: None,
            },
        ],
        body: vec![IrStmt::Return {
            value: Some(ir_deref(ptr_plus_deref, u8_ty)),
            source_span: None,
        }],
        source_span: None,
    };

    let error =
        emit_rust_from_ir(&ir).expect_err("deref index pointer offset deref must fail closed");

    assert!(error
        .reason
        .contains("deref pointer add index cannot use dereference"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_readonly_pointer_add_unsupported_index_deref_read() {
    let u8_ty = ir_u8();
    let usize_ty = ir_usize();
    let const_u8_ty = ir_const(u8_ty.clone());
    let const_u8_ptr_ty = ir_pointer("const uint8_t *", "uint8_t *", const_u8_ty, false);
    let unsupported_index = IrExpr::Cast {
        target: usize_ty,
        expr: Box::new(IrExpr::Unsupported {
            node: "RecoveryExpr".to_string(),
            reason: "clang could not recover index expression".to_string(),
            source_span: None,
        }),
        implicit: false,
        source_span: None,
    };
    let ptr_plus_unsupported = ir_binary(
        IrBinOp::Add,
        ir_var("p", const_u8_ptr_ty.clone()),
        unsupported_index,
        const_u8_ptr_ty.clone(),
    );
    let ir = IrFunction {
        name: "bad_unsupported_index_offset_read".to_string(),
        return_type: u8_ty.clone(),
        params: vec![IrParam {
            name: "p".to_string(),
            ty: const_u8_ptr_ty,
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(ir_deref(ptr_plus_unsupported, u8_ty)),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir)
        .expect_err("unsupported index pointer offset deref must fail closed");

    assert!(error
        .reason
        .contains("deref pointer add index unsupported expression RecoveryExpr"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_readonly_pointer_add_result_type_mismatch() {
    let u8_ty = ir_u8();
    let usize_ty = ir_usize();
    let const_u8_ty = ir_const(u8_ty.clone());
    let const_u8_ptr_ty = ir_pointer("const uint8_t *", "uint8_t *", const_u8_ty, false);
    let ptr_plus_index_with_bad_ty = ir_binary(
        IrBinOp::Add,
        ir_var("p", const_u8_ptr_ty.clone()),
        ir_var("i", usize_ty.clone()),
        u8_ty.clone(),
    );
    let ir = IrFunction {
        name: "bad_pointer_add_result_type".to_string(),
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
            value: Some(ir_deref(ptr_plus_index_with_bad_ty, u8_ty)),
            source_span: None,
        }],
        source_span: None,
    };

    let error =
        emit_rust_from_ir(&ir).expect_err("pointer add result type mismatch must fail closed");

    assert!(error
        .reason
        .contains("deref pointer add result type uint8_t does not match base type"));
}
