#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_readonly_index_add_pointer_deref_read() {
    let u8_ty = ir_u8();
    let usize_ty = ir_usize();
    let const_u8_ty = ir_const(u8_ty.clone());
    let const_u8_ptr_ty = ir_pointer("const uint8_t *", "uint8_t *", const_u8_ty, false);
    let index_plus_ptr = ir_binary(
        IrBinOp::Add,
        ir_var("i", usize_ty.clone()),
        ir_var("p", const_u8_ptr_ty.clone()),
        const_u8_ptr_ty.clone(),
    );
    let ir = IrFunction {
        name: "read_byte_at_commuted".to_string(),
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
            value: Some(ir_deref(index_plus_ptr, u8_ty)),
            source_span: None,
        }],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit readonly index-add-pointer deref read");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub fn read_byte_at_commuted(p: &[u8], i: usize) -> u8"));
    assert!(rust.contains("return p[i as usize];"));
    assert_rust_snippet_compiles("typed-ir-readonly-index-add-pointer-deref-read", rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_readonly_pointer_add_literal_deref_read() {
    let u8_ty = ir_u8();
    let i32_ty = ir_i32();
    let const_u8_ty = ir_const(u8_ty.clone());
    let const_u8_ptr_ty = ir_pointer("const uint8_t *", "uint8_t *", const_u8_ty, false);
    let ptr_plus_one = ir_binary(
        IrBinOp::Add,
        ir_var("p", const_u8_ptr_ty.clone()),
        ir_lit(1, "1", i32_ty),
        const_u8_ptr_ty.clone(),
    );
    let ir = IrFunction {
        name: "read_second_byte".to_string(),
        return_type: u8_ty.clone(),
        params: vec![IrParam {
            name: "p".to_string(),
            ty: const_u8_ptr_ty,
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(ir_deref(ptr_plus_one, u8_ty)),
            source_span: None,
        }],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit readonly pointer add-literal deref read");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub fn read_second_byte(p: &[u8]) -> u8"));
    assert!(rust.contains("return p[1i32 as usize];"));
    assert_rust_snippet_compiles("typed-ir-readonly-pointer-add-literal-deref-read", rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_mutable_pointer_add_index_deref_read() {
    let u8_ty = ir_u8();
    let usize_ty = ir_usize();
    let mutable_u8_ptr_ty = ir_pointer("uint8_t *", "uint8_t *", u8_ty.clone(), false);
    let ptr_plus_index = ir_binary(
        IrBinOp::Add,
        ir_var("p", mutable_u8_ptr_ty.clone()),
        ir_var("i", usize_ty.clone()),
        mutable_u8_ptr_ty.clone(),
    );
    let ir = IrFunction {
        name: "bad_mut_ptr_offset_read".to_string(),
        return_type: u8_ty.clone(),
        params: vec![
            IrParam {
                name: "p".to_string(),
                ty: mutable_u8_ptr_ty,
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

    let error = emit_rust_from_ir(&ir).expect_err("mutable pointer offset deref must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("param p"));
    assert!(error.reason.contains("pointer type"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_readonly_pointer_add_call_index_deref_read() {
    let u8_ty = ir_u8();
    let usize_ty = ir_usize();
    let const_u8_ty = ir_const(u8_ty.clone());
    let const_u8_ptr_ty = ir_pointer("const uint8_t *", "uint8_t *", const_u8_ty, false);
    let ptr_plus_call = ir_binary(
        IrBinOp::Add,
        ir_var("p", const_u8_ptr_ty.clone()),
        IrExpr::Call {
            callee: "next_index".to_string(),
            args: vec![],
            ty: usize_ty,
            source_span: None,
        },
        const_u8_ptr_ty.clone(),
    );
    let ir = IrFunction {
        name: "bad_call_index_offset_read".to_string(),
        return_type: u8_ty.clone(),
        params: vec![IrParam {
            name: "p".to_string(),
            ty: const_u8_ptr_ty,
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(ir_deref(ptr_plus_call, u8_ty)),
            source_span: None,
        }],
        source_span: None,
    };

    let error =
        emit_rust_from_ir(&ir).expect_err("call index pointer offset deref must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("return expr"));
    assert!(error
        .reason
        .contains("deref pointer add index call expression next_index is unsupported"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_readonly_pointer_add_compound_index_deref_read() {
    let u8_ty = ir_u8();
    let usize_ty = ir_usize();
    let const_u8_ty = ir_const(u8_ty.clone());
    let const_u8_ptr_ty = ir_pointer("const uint8_t *", "uint8_t *", const_u8_ty, false);
    let compound_index = ir_binary(
        IrBinOp::Add,
        ir_var("i", usize_ty.clone()),
        ir_lit(1, "1", usize_ty.clone()),
        usize_ty.clone(),
    );
    let ptr_plus_compound = ir_binary(
        IrBinOp::Add,
        ir_var("p", const_u8_ptr_ty.clone()),
        compound_index,
        const_u8_ptr_ty.clone(),
    );
    let ir = IrFunction {
        name: "bad_compound_index_offset_read".to_string(),
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
            value: Some(ir_deref(ptr_plus_compound, u8_ty)),
            source_span: None,
        }],
        source_span: None,
    };

    let error =
        emit_rust_from_ir(&ir).expect_err("compound index pointer offset deref must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("return expr"));
    assert!(error
        .reason
        .contains("deref pointer add index cannot use compound expression"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_nullable_readonly_pointer_add_index_deref_read() {
    let i32_ty = ir_i32();
    let const_i32_ty = ir_const(i32_ty.clone());
    let const_i32_ptr_ty = ir_pointer("const int *", "const int *", const_i32_ty, false);
    let ptr_plus_index = ir_binary(
        IrBinOp::Add,
        ir_var("p", const_i32_ptr_ty.clone()),
        ir_var("i", i32_ty.clone()),
        const_i32_ptr_ty.clone(),
    );
    let ir = IrFunction {
        name: "bad_nullable_offset_read".to_string(),
        return_type: i32_ty.clone(),
        params: vec![
            IrParam {
                name: "p".to_string(),
                ty: const_i32_ptr_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "i".to_string(),
                ty: i32_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![
            IrStmt::If {
                condition: ir_binary(
                    IrBinOp::Eq,
                    ir_var("p", const_i32_ptr_ty.clone()),
                    ir_null_ptr(const_i32_ptr_ty.clone()),
                    i32_ty.clone(),
                ),
                then_body: vec![IrStmt::Return {
                    value: Some(ir_lit(0, "0", i32_ty.clone())),
                    source_span: None,
                }],
                else_body: vec![],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_deref(ptr_plus_index, i32_ty)),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("nullable offset deref must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error
        .reason
        .contains("nullable pointer param p is only supported in null comparisons"));
}

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

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_readonly_pointer_add_deref_result_type_mismatch() {
    let i32_ty = ir_i32();
    let u8_ty = ir_u8();
    let usize_ty = ir_usize();
    let const_u8_ty = ir_const(u8_ty);
    let const_u8_ptr_ty = ir_pointer("const uint8_t *", "uint8_t *", const_u8_ty, false);
    let ptr_plus_index = ir_binary(
        IrBinOp::Add,
        ir_var("p", const_u8_ptr_ty.clone()),
        ir_var("i", usize_ty.clone()),
        const_u8_ptr_ty.clone(),
    );
    let ir = IrFunction {
        name: "bad_deref_result_type".to_string(),
        return_type: i32_ty.clone(),
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
            value: Some(ir_deref(ptr_plus_index, i32_ty)),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("deref result type mismatch must fail closed");

    assert!(error
        .reason
        .contains("deref result type i32 does not match pointer element type u8"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_local_fixed_array_index_assignment() {
    let u32_ty = ir_u32();
    let usize_ty = ir_usize();
    let table_ty = ir_array(u32_ty.clone(), 3);
    let table_var = || ir_var("table", table_ty.clone());
    let index_var = || ir_var("i", usize_ty.clone());
    let ir = IrFunction {
        name: "replace_local_table_slot".to_string(),
        return_type: u32_ty.clone(),
        params: vec![
            IrParam {
                name: "i".to_string(),
                ty: usize_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "value".to_string(),
                ty: u32_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![
            IrStmt::Decl {
                name: "table".to_string(),
                ty: table_ty.clone(),
                init: Some(IrExpr::ArrayLiteral {
                    elements: vec![
                        ir_lit(1, "1U", u32_ty.clone()),
                        ir_lit(2, "2U", u32_ty.clone()),
                        ir_lit(3, "3U", u32_ty.clone()),
                    ],
                    ty: table_ty.clone(),
                    source_span: None,
                }),
                source_span: None,
            },
            IrStmt::Assign {
                target: IrExpr::Index {
                    base: Box::new(table_var()),
                    index: Box::new(index_var()),
                    ty: u32_ty.clone(),
                    source_span: None,
                },
                value: ir_var("value", u32_ty.clone()),
                source_span: None,
            },
            IrStmt::Return {
                value: Some(IrExpr::Index {
                    base: Box::new(table_var()),
                    index: Box::new(index_var()),
                    ty: u32_ty,
                    source_span: None,
                }),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit local fixed array index assignment");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("let mut table: [u32; 3] = [1u32, 2u32, 3u32];"));
    assert!(rust.contains("table[i as usize] = value;"));
    assert!(rust.contains("return table[i as usize];"));
    assert_rust_snippet_compiles("typed-ir-local-fixed-array-index-assignment", rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_readonly_global_array_index_assignment() {
    let u32_ty = ir_u32();
    let usize_ty = ir_usize();
    let global = ir_u32_global_array("table", 3, vec![1, 2, 3]);
    let ir = IrFunction {
        name: "write_global_table".to_string(),
        return_type: u32_ty.clone(),
        params: vec![IrParam {
            name: "i".to_string(),
            ty: usize_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::Assign {
                target: IrExpr::Index {
                    base: Box::new(ir_var("table", global.ty.clone())),
                    index: Box::new(ir_var("i", usize_ty)),
                    ty: u32_ty.clone(),
                    source_span: None,
                },
                value: ir_lit(0, "0U", u32_ty.clone()),
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_lit(0, "0U", u32_ty)),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error = emit_rust_from_ir_with_globals(&ir, &[global])
        .expect_err("readonly global array assignment must fail closed");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(error.reason.contains("assign index base table"));
    assert!(error.reason.contains("readonly global"));
}
