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

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_const_pointer_index_assignment() {
    let u32_ty = ir_u32();
    let usize_ty = ir_usize();
    let const_u32_ptr = ir_pointer(
        "const uint32_t *",
        "const unsigned int *",
        ir_const(u32_ty.clone()),
        false,
    );
    let ir = IrFunction {
        name: "write_const_pointer_slot".to_string(),
        return_type: u32_ty.clone(),
        params: vec![
            IrParam {
                name: "table".to_string(),
                ty: const_u32_ptr.clone(),
                source_span: None,
            },
            IrParam {
                name: "i".to_string(),
                ty: usize_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![
            IrStmt::Assign {
                target: IrExpr::Index {
                    base: Box::new(ir_var("table", const_u32_ptr)),
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

    let error =
        emit_rust_from_ir(&ir).expect_err("const pointer index assignment must fail closed");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(error.reason.contains("assign index base table"));
    assert!(error.reason.contains("unsupported type"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_mutable_pointer_deref_assignment_as_mut_slice_zero_index() {
    let i32_ty = ir_i32();
    let mutable_i32_ptr = ir_pointer("int *", "int *", i32_ty.clone(), false);
    let ir = IrFunction {
        name: "store_first".to_string(),
        return_type: ir_void(),
        params: vec![
            IrParam {
                name: "out".to_string(),
                ty: mutable_i32_ptr.clone(),
                source_span: None,
            },
            IrParam {
                name: "value".to_string(),
                ty: i32_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![
            IrStmt::Assign {
                target: ir_deref(ir_var("out", mutable_i32_ptr), i32_ty.clone()),
                value: ir_var("value", i32_ty),
                source_span: None,
            },
            IrStmt::Return {
                value: None,
                source_span: None,
            },
        ],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit mutable pointer deref assignment");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub fn store_first(mut out: &mut [i32], value: i32)"));
    assert!(rust.contains("out[0usize] = value;"));
    assert_rust_snippet_compiles("typed-ir-mutable-pointer-deref-assignment", rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_mutable_pointer_index_assignment() {
    let i32_ty = ir_i32();
    let usize_ty = ir_usize();
    let mutable_i32_ptr = ir_pointer("int *", "int *", i32_ty.clone(), false);
    let ir = IrFunction {
        name: "store_at".to_string(),
        return_type: ir_void(),
        params: vec![
            IrParam {
                name: "out".to_string(),
                ty: mutable_i32_ptr.clone(),
                source_span: None,
            },
            IrParam {
                name: "i".to_string(),
                ty: usize_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "value".to_string(),
                ty: i32_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![
            IrStmt::Assign {
                target: IrExpr::Index {
                    base: Box::new(ir_var("out", mutable_i32_ptr)),
                    index: Box::new(ir_var("i", usize_ty)),
                    ty: i32_ty.clone(),
                    source_span: None,
                },
                value: ir_var("value", i32_ty),
                source_span: None,
            },
            IrStmt::Return {
                value: None,
                source_span: None,
            },
        ],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit mutable pointer index assignment");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub fn store_at(mut out: &mut [i32], i: usize, value: i32)"));
    assert!(rust.contains("out[i as usize] = value;"));
    assert_rust_snippet_compiles("typed-ir-mutable-pointer-index-assignment", rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_nullable_mutable_pointer_index_assignment() {
    let i32_ty = ir_i32();
    let mutable_i32_ptr = ir_pointer("int *", "int *", i32_ty.clone(), false);
    let ir = IrFunction {
        name: "bad_nullable_out_write".to_string(),
        return_type: i32_ty.clone(),
        params: vec![
            IrParam {
                name: "out".to_string(),
                ty: mutable_i32_ptr.clone(),
                source_span: None,
            },
            IrParam {
                name: "value".to_string(),
                ty: i32_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![
            IrStmt::If {
                condition: ir_binary(
                    IrBinOp::Eq,
                    ir_var("out", mutable_i32_ptr.clone()),
                    ir_null_ptr(mutable_i32_ptr.clone()),
                    i32_ty.clone(),
                ),
                then_body: vec![IrStmt::Return {
                    value: Some(ir_lit(-1i64 as u64, "-1", i32_ty.clone())),
                    source_span: None,
                }],
                else_body: vec![],
                source_span: None,
            },
            IrStmt::Assign {
                target: IrExpr::Index {
                    base: Box::new(ir_var("out", mutable_i32_ptr)),
                    index: Box::new(ir_lit(0, "0", i32_ty.clone())),
                    ty: i32_ty.clone(),
                    source_span: None,
                },
                value: ir_var("value", i32_ty.clone()),
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_lit(0, "0", i32_ty)),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error =
        emit_rust_from_ir(&ir).expect_err("nullable mutable pointer write must fail closed");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(
        error
            .reason
            .contains("nullable mutable pointer param out cannot be lowered to &mut [T]"),
        "unexpected reason: {}",
        error.reason
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_multiple_mutable_pointer_index_assignments_without_alias_proof() {
    let i32_ty = ir_i32();
    let mutable_i32_ptr = ir_pointer("int *", "int *", i32_ty.clone(), false);
    let ir = IrFunction {
        name: "bad_two_out_writes".to_string(),
        return_type: ir_void(),
        params: vec![
            IrParam {
                name: "left".to_string(),
                ty: mutable_i32_ptr.clone(),
                source_span: None,
            },
            IrParam {
                name: "right".to_string(),
                ty: mutable_i32_ptr.clone(),
                source_span: None,
            },
        ],
        body: vec![
            IrStmt::Assign {
                target: IrExpr::Index {
                    base: Box::new(ir_var("left", mutable_i32_ptr.clone())),
                    index: Box::new(ir_lit(0, "0", i32_ty.clone())),
                    ty: i32_ty.clone(),
                    source_span: None,
                },
                value: ir_lit(1, "1", i32_ty.clone()),
                source_span: None,
            },
            IrStmt::Assign {
                target: IrExpr::Index {
                    base: Box::new(ir_var("right", mutable_i32_ptr)),
                    index: Box::new(ir_lit(0, "0", i32_ty.clone())),
                    ty: i32_ty.clone(),
                    source_span: None,
                },
                value: ir_lit(2, "2", i32_ty.clone()),
                source_span: None,
            },
            IrStmt::Return {
                value: None,
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error =
        emit_rust_from_ir(&ir).expect_err("multiple mutable pointer writes need alias proof");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(
        error
            .reason
            .contains("mutable pointer write requires exactly one pointer param for alias proof"),
        "unexpected reason: {}",
        error.reason
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_readonly_input_and_mutable_output_index_assignment_without_noalias_proof() {
    let i32_ty = ir_i32();
    let usize_ty = ir_usize();
    let const_i32_ptr = ir_pointer(
        "const int *",
        "const int *",
        ir_const(i32_ty.clone()),
        false,
    );
    let mutable_i32_ptr = ir_pointer("int *", "int *", i32_ty.clone(), false);
    let ir = IrFunction {
        name: "copy_one".to_string(),
        return_type: i32_ty.clone(),
        params: vec![
            IrParam {
                name: "values".to_string(),
                ty: const_i32_ptr.clone(),
                source_span: None,
            },
            IrParam {
                name: "out".to_string(),
                ty: mutable_i32_ptr.clone(),
                source_span: None,
            },
            IrParam {
                name: "i".to_string(),
                ty: usize_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![
            IrStmt::Assign {
                target: IrExpr::Index {
                    base: Box::new(ir_var("out", mutable_i32_ptr)),
                    index: Box::new(ir_var("i", usize_ty.clone())),
                    ty: i32_ty.clone(),
                    source_span: None,
                },
                value: IrExpr::Index {
                    base: Box::new(ir_var("values", const_i32_ptr)),
                    index: Box::new(ir_var("i", usize_ty)),
                    ty: i32_ty.clone(),
                    source_span: None,
                },
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_lit(0, "0", i32_ty)),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error =
        emit_rust_from_ir(&ir).expect_err("readonly input plus mutable output needs noalias proof");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(
        error
            .reason
            .contains("mutable pointer write with readonly pointer read requires noalias proof"),
        "unexpected reason: {}",
        error.reason
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_readonly_input_and_mutable_output_index_assignment_with_restrict_noalias_proof() {
    let i32_ty = ir_i32();
    let usize_ty = ir_usize();
    let const_i32_ptr = ir_pointer(
        "const int *restrict",
        "const int *restrict",
        ir_const(i32_ty.clone()),
        false,
    );
    let mutable_i32_ptr = ir_pointer("int *restrict", "int *restrict", i32_ty.clone(), false);
    let ir = IrFunction {
        name: "copy_one_restrict".to_string(),
        return_type: i32_ty.clone(),
        params: vec![
            IrParam {
                name: "values".to_string(),
                ty: const_i32_ptr.clone(),
                source_span: None,
            },
            IrParam {
                name: "out".to_string(),
                ty: mutable_i32_ptr.clone(),
                source_span: None,
            },
            IrParam {
                name: "i".to_string(),
                ty: usize_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![
            IrStmt::Assign {
                target: IrExpr::Index {
                    base: Box::new(ir_var("out", mutable_i32_ptr)),
                    index: Box::new(ir_var("i", usize_ty.clone())),
                    ty: i32_ty.clone(),
                    source_span: None,
                },
                value: IrExpr::Index {
                    base: Box::new(ir_var("values", const_i32_ptr)),
                    index: Box::new(ir_var("i", usize_ty)),
                    ty: i32_ty.clone(),
                    source_span: None,
                },
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_lit(0, "0", i32_ty)),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("restrict params provide noalias proof");

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(emitted.rust.contains(
        "pub fn copy_one_restrict(values: &[i32], mut out: &mut [i32], i: usize) -> i32"
    ));
    assert!(emitted
        .rust
        .contains("out[i as usize] = values[i as usize];"));
    assert_rust_snippet_compiles("typed-ir-readonly-mutable-restrict-copy-one", &emitted.rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_readonly_input_and_mutable_output_index_assignment_with_policy_noalias_pair() {
    let i32_ty = ir_i32();
    let usize_ty = ir_usize();
    let const_i32_ptr = ir_pointer(
        "const int *",
        "const int *",
        ir_const(i32_ty.clone()),
        false,
    );
    let mutable_i32_ptr = ir_pointer("int *", "int *", i32_ty.clone(), false);
    let ir = IrFunction {
        name: "copy_one_policy_noalias".to_string(),
        return_type: i32_ty.clone(),
        params: vec![
            IrParam {
                name: "values".to_string(),
                ty: const_i32_ptr.clone(),
                source_span: None,
            },
            IrParam {
                name: "out".to_string(),
                ty: mutable_i32_ptr.clone(),
                source_span: None,
            },
            IrParam {
                name: "i".to_string(),
                ty: usize_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![
            IrStmt::Assign {
                target: IrExpr::Index {
                    base: Box::new(ir_var("out", mutable_i32_ptr)),
                    index: Box::new(ir_var("i", usize_ty.clone())),
                    ty: i32_ty.clone(),
                    source_span: None,
                },
                value: IrExpr::Index {
                    base: Box::new(ir_var("values", const_i32_ptr)),
                    index: Box::new(ir_var("i", usize_ty)),
                    ty: i32_ty.clone(),
                    source_span: None,
                },
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_lit(0, "0", i32_ty)),
                source_span: None,
            },
        ],
        source_span: None,
    };
    let policy = EmitPolicy {
        noalias_param_pairs: vec![NoAliasParamPair {
            readonly_param: "values".to_string(),
            mutable_param: "out".to_string(),
        }],
        ..Default::default()
    };

    let emitted = emit_rust_from_ir_with_globals_and_policy(&ir, &[], policy)
        .expect("explicit policy noalias pair should allow safe slice lowering");

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(emitted.rust.contains(
        "pub fn copy_one_policy_noalias(values: &[i32], mut out: &mut [i32], i: usize) -> i32"
    ));
    assert!(emitted
        .rust
        .contains("out[i as usize] = values[i as usize];"));
    assert_rust_snippet_compiles(
        "typed-ir-readonly-mutable-policy-noalias-copy-one",
        &emitted.rust,
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_readonly_deref_and_mutable_output_assignment_without_noalias_proof() {
    let i32_ty = ir_i32();
    let const_i32_ptr = ir_pointer(
        "const int *",
        "const int *",
        ir_const(i32_ty.clone()),
        false,
    );
    let mutable_i32_ptr = ir_pointer("int *", "int *", i32_ty.clone(), false);
    let ir = IrFunction {
        name: "copy_first".to_string(),
        return_type: ir_void(),
        params: vec![
            IrParam {
                name: "values".to_string(),
                ty: const_i32_ptr.clone(),
                source_span: None,
            },
            IrParam {
                name: "out".to_string(),
                ty: mutable_i32_ptr.clone(),
                source_span: None,
            },
        ],
        body: vec![
            IrStmt::Assign {
                target: IrExpr::Index {
                    base: Box::new(ir_var("out", mutable_i32_ptr)),
                    index: Box::new(ir_lit(0, "0", i32_ty.clone())),
                    ty: i32_ty.clone(),
                    source_span: None,
                },
                value: ir_deref(ir_var("values", const_i32_ptr), i32_ty),
                source_span: None,
            },
            IrStmt::Return {
                value: None,
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error =
        emit_rust_from_ir(&ir).expect_err("readonly deref plus mutable output needs noalias proof");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(
        error
            .reason
            .contains("mutable pointer write with readonly pointer read requires noalias proof"),
        "unexpected reason: {}",
        error.reason
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_readonly_deref_and_mutable_output_assignment_with_restrict_noalias_proof() {
    let i32_ty = ir_i32();
    let const_i32_ptr = ir_pointer(
        "const int *restrict",
        "const int *restrict",
        ir_const(i32_ty.clone()),
        false,
    );
    let mutable_i32_ptr = ir_pointer("int *restrict", "int *restrict", i32_ty.clone(), false);
    let ir = IrFunction {
        name: "copy_first_restrict".to_string(),
        return_type: ir_void(),
        params: vec![
            IrParam {
                name: "values".to_string(),
                ty: const_i32_ptr.clone(),
                source_span: None,
            },
            IrParam {
                name: "out".to_string(),
                ty: mutable_i32_ptr.clone(),
                source_span: None,
            },
        ],
        body: vec![
            IrStmt::Assign {
                target: IrExpr::Index {
                    base: Box::new(ir_var("out", mutable_i32_ptr)),
                    index: Box::new(ir_lit(0, "0", i32_ty.clone())),
                    ty: i32_ty.clone(),
                    source_span: None,
                },
                value: ir_deref(ir_var("values", const_i32_ptr), i32_ty),
                source_span: None,
            },
            IrStmt::Return {
                value: None,
                source_span: None,
            },
        ],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("restrict params provide noalias proof");

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(emitted
        .rust
        .contains("pub fn copy_first_restrict(values: &[i32], mut out: &mut [i32])"));
    assert!(emitted
        .rust
        .contains("out[0i32 as usize] = values[0usize];"));
    assert_rust_snippet_compiles(
        "typed-ir-readonly-deref-mutable-restrict-copy-first",
        &emitted.rust,
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_mutable_pointer_add_index_deref_assignment() {
    let i32_ty = ir_i32();
    let usize_ty = ir_usize();
    let mutable_i32_ptr = ir_pointer("int *", "int *", i32_ty.clone(), false);
    let ptr_plus_index = ir_binary(
        IrBinOp::Add,
        ir_var("out", mutable_i32_ptr.clone()),
        ir_var("i", usize_ty.clone()),
        mutable_i32_ptr.clone(),
    );
    let ir = IrFunction {
        name: "store_at_offset".to_string(),
        return_type: ir_void(),
        params: vec![
            IrParam {
                name: "out".to_string(),
                ty: mutable_i32_ptr,
                source_span: None,
            },
            IrParam {
                name: "i".to_string(),
                ty: usize_ty,
                source_span: None,
            },
            IrParam {
                name: "value".to_string(),
                ty: i32_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![
            IrStmt::Assign {
                target: ir_deref(ptr_plus_index, i32_ty.clone()),
                value: ir_var("value", i32_ty),
                source_span: None,
            },
            IrStmt::Return {
                value: None,
                source_span: None,
            },
        ],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit mutable pointer add-index deref assignment");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub fn store_at_offset(mut out: &mut [i32], i: usize, value: i32)"));
    assert!(rust.contains("out[i as usize] = value;"));
    assert_rust_snippet_compiles("typed-ir-mutable-pointer-add-index-deref-assignment", rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_const_pointer_deref_assignment() {
    let i32_ty = ir_i32();
    let const_i32_ptr = ir_pointer(
        "const int *",
        "const int *",
        ir_const(i32_ty.clone()),
        false,
    );
    let ir = IrFunction {
        name: "bad_const_store".to_string(),
        return_type: ir_void(),
        params: vec![IrParam {
            name: "out".to_string(),
            ty: const_i32_ptr.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Assign {
            target: ir_deref(ir_var("out", const_i32_ptr), i32_ty.clone()),
            value: ir_lit(1, "1", i32_ty),
            source_span: None,
        }],
        source_span: None,
    };

    let error =
        emit_rust_from_ir(&ir).expect_err("const pointer deref assignment must fail closed");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(error.reason.contains("deref assignment pointer out"));
    assert!(error.reason.contains("unsupported type"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_mutable_pointer_complex_offset_assignment() {
    let i32_ty = ir_i32();
    let usize_ty = ir_usize();
    let mutable_i32_ptr = ir_pointer("int *", "int *", i32_ty.clone(), false);
    let complex_index = ir_binary(
        IrBinOp::Add,
        ir_var("i", usize_ty.clone()),
        ir_lit(1, "1", usize_ty.clone()),
        usize_ty.clone(),
    );
    let ptr_plus_complex_index = ir_binary(
        IrBinOp::Add,
        ir_var("out", mutable_i32_ptr.clone()),
        complex_index,
        mutable_i32_ptr.clone(),
    );
    let ir = IrFunction {
        name: "bad_complex_store".to_string(),
        return_type: ir_void(),
        params: vec![
            IrParam {
                name: "out".to_string(),
                ty: mutable_i32_ptr,
                source_span: None,
            },
            IrParam {
                name: "i".to_string(),
                ty: usize_ty,
                source_span: None,
            },
        ],
        body: vec![IrStmt::Assign {
            target: ir_deref(ptr_plus_complex_index, i32_ty.clone()),
            value: ir_lit(1, "1", i32_ty),
            source_span: None,
        }],
        source_span: None,
    };

    let error =
        emit_rust_from_ir(&ir).expect_err("complex pointer offset assignment must fail closed");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(error
        .reason
        .contains("deref pointer add index cannot use compound expression"));
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn typed_ir_emits_local_fixed_array_index_read_from_clang_lowered_ir() {
    let int_ty = ClangTypeSkeleton {
        spelled: "int".to_string(),
        canonical: "int".to_string(),
        kind: ClangTypeKind::Integer {
            signed: true,
            width: 32,
        },
    };
    let u32_ty = ClangTypeSkeleton {
        spelled: "uint32_t".to_string(),
        canonical: "uint32_t".to_string(),
        kind: ClangTypeKind::Integer {
            signed: false,
            width: 32,
        },
    };
    let usize_ty = ClangTypeSkeleton {
        spelled: "size_t".to_string(),
        canonical: "size_t".to_string(),
        kind: ClangTypeKind::Integer {
            signed: false,
            width: 64,
        },
    };
    let table_ty = ClangTypeSkeleton {
        spelled: "uint32_t[3]".to_string(),
        canonical: "uint32_t[3]".to_string(),
        kind: ClangTypeKind::Array {
            element: Box::new(u32_ty.clone()),
            len: Some(3),
        },
    };
    let skeleton = ClangFunctionSkeleton {
        name: "lookup_local_table".to_string(),
        return_type: u32_ty.clone(),
        params: vec![ClangParamSkeleton {
            name: "i".to_string(),
            ty: usize_ty.clone(),
        }],
        body: vec![
            ClangStmtSkeleton::Decl {
                name: "table".to_string(),
                ty: table_ty.clone(),
                init: Some(ClangExprSkeleton::ArrayLiteral {
                    elements: vec![
                        ClangExprSkeleton::Cast {
                            target: u32_ty.clone(),
                            expr: Box::new(ClangExprSkeleton::IntegerLiteral {
                                value: 1,
                                spelling: "1".to_string(),
                                ty: int_ty,
                            }),
                            implicit: true,
                        },
                        ClangExprSkeleton::IntegerLiteral {
                            value: 2,
                            spelling: "2U".to_string(),
                            ty: u32_ty.clone(),
                        },
                        ClangExprSkeleton::IntegerLiteral {
                            value: 3,
                            spelling: "3U".to_string(),
                            ty: u32_ty.clone(),
                        },
                    ],
                    ty: table_ty.clone(),
                }),
            },
            ClangStmtSkeleton::Return {
                value: Some(ClangExprSkeleton::Index {
                    base: Box::new(ClangExprSkeleton::DeclRef {
                        name: "table".to_string(),
                        ty: table_ty,
                    }),
                    index: Box::new(ClangExprSkeleton::DeclRef {
                        name: "i".to_string(),
                        ty: usize_ty,
                    }),
                    ty: u32_ty,
                }),
            },
        ],
    };

    let ir = lower_function_skeleton(&skeleton).expect("lower local fixed array skeleton");
    let emitted = emit_rust_from_ir(&ir).expect("emit local fixed array from clang-lowered IR");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("let table: [u32; 3] = [(1i32 as u32), 2u32, 3u32];"));
    assert!(rust.contains("return table[i as usize];"));
    assert_rust_snippet_compiles("clang-lowered-local-fixed-array-index-read", rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn typed_ir_emits_local_fixed_array_index_assignment_from_clang_lowered_ir() {
    let u32_ty = ClangTypeSkeleton {
        spelled: "uint32_t".to_string(),
        canonical: "uint32_t".to_string(),
        kind: ClangTypeKind::Integer {
            signed: false,
            width: 32,
        },
    };
    let usize_ty = ClangTypeSkeleton {
        spelled: "size_t".to_string(),
        canonical: "size_t".to_string(),
        kind: ClangTypeKind::Integer {
            signed: false,
            width: 64,
        },
    };
    let table_ty = ClangTypeSkeleton {
        spelled: "uint32_t[3]".to_string(),
        canonical: "uint32_t[3]".to_string(),
        kind: ClangTypeKind::Array {
            element: Box::new(u32_ty.clone()),
            len: Some(3),
        },
    };
    let table_ref = || ClangExprSkeleton::DeclRef {
        name: "table".to_string(),
        ty: table_ty.clone(),
    };
    let index_ref = || ClangExprSkeleton::DeclRef {
        name: "i".to_string(),
        ty: usize_ty.clone(),
    };
    let skeleton = ClangFunctionSkeleton {
        name: "replace_local_table_slot".to_string(),
        return_type: u32_ty.clone(),
        params: vec![
            ClangParamSkeleton {
                name: "i".to_string(),
                ty: usize_ty.clone(),
            },
            ClangParamSkeleton {
                name: "value".to_string(),
                ty: u32_ty.clone(),
            },
        ],
        body: vec![
            ClangStmtSkeleton::Decl {
                name: "table".to_string(),
                ty: table_ty.clone(),
                init: Some(ClangExprSkeleton::ArrayLiteral {
                    elements: vec![
                        ClangExprSkeleton::IntegerLiteral {
                            value: 1,
                            spelling: "1U".to_string(),
                            ty: u32_ty.clone(),
                        },
                        ClangExprSkeleton::IntegerLiteral {
                            value: 2,
                            spelling: "2U".to_string(),
                            ty: u32_ty.clone(),
                        },
                        ClangExprSkeleton::IntegerLiteral {
                            value: 3,
                            spelling: "3U".to_string(),
                            ty: u32_ty.clone(),
                        },
                    ],
                    ty: table_ty.clone(),
                }),
            },
            ClangStmtSkeleton::Assign {
                target: ClangExprSkeleton::Index {
                    base: Box::new(table_ref()),
                    index: Box::new(index_ref()),
                    ty: u32_ty.clone(),
                },
                value: ClangExprSkeleton::DeclRef {
                    name: "value".to_string(),
                    ty: u32_ty.clone(),
                },
            },
            ClangStmtSkeleton::Return {
                value: Some(ClangExprSkeleton::Index {
                    base: Box::new(table_ref()),
                    index: Box::new(index_ref()),
                    ty: u32_ty.clone(),
                }),
            },
        ],
    };

    let ir = lower_function_skeleton(&skeleton).expect("lower local array assignment skeleton");
    let [IrStmt::Decl { .. }, IrStmt::Assign { target, .. }, IrStmt::Return { .. }] =
        ir.body.as_slice()
    else {
        panic!(
            "expected local array declaration, assignment, and return, got {:?}",
            ir.body
        );
    };
    assert!(matches!(target, IrExpr::Index { .. }));

    let emitted =
        emit_rust_from_ir(&ir).expect("emit local array assignment from clang-lowered IR");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("let mut table: [u32; 3] = [1u32, 2u32, 3u32];"));
    assert!(rust.contains("table[i as usize] = value;"));
    assert!(rust.contains("return table[i as usize];"));
    assert_rust_snippet_compiles("clang-lowered-local-fixed-array-index-assignment", rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn typed_ir_emits_mutable_pointer_index_assignment_from_clang_lowered_ir() {
    let i32_ty = ClangTypeSkeleton {
        spelled: "int".to_string(),
        canonical: "int".to_string(),
        kind: ClangTypeKind::Integer {
            signed: true,
            width: 32,
        },
    };
    let usize_ty = ClangTypeSkeleton {
        spelled: "size_t".to_string(),
        canonical: "size_t".to_string(),
        kind: ClangTypeKind::Integer {
            signed: false,
            width: 64,
        },
    };
    let mutable_i32_ptr = ClangTypeSkeleton {
        spelled: "int *".to_string(),
        canonical: "int *".to_string(),
        kind: ClangTypeKind::Pointer {
            pointee: Box::new(i32_ty.clone()),
            width: None,
        },
    };
    let out_ref = || ClangExprSkeleton::DeclRef {
        name: "out".to_string(),
        ty: mutable_i32_ptr.clone(),
    };
    let index_ref = || ClangExprSkeleton::DeclRef {
        name: "i".to_string(),
        ty: usize_ty.clone(),
    };
    let skeleton = ClangFunctionSkeleton {
        name: "store_at".to_string(),
        return_type: ClangTypeSkeleton {
            spelled: "void".to_string(),
            canonical: "void".to_string(),
            kind: ClangTypeKind::Void,
        },
        params: vec![
            ClangParamSkeleton {
                name: "out".to_string(),
                ty: mutable_i32_ptr.clone(),
            },
            ClangParamSkeleton {
                name: "i".to_string(),
                ty: usize_ty.clone(),
            },
            ClangParamSkeleton {
                name: "value".to_string(),
                ty: i32_ty.clone(),
            },
        ],
        body: vec![ClangStmtSkeleton::Assign {
            target: ClangExprSkeleton::Index {
                base: Box::new(out_ref()),
                index: Box::new(index_ref()),
                ty: i32_ty.clone(),
            },
            value: ClangExprSkeleton::DeclRef {
                name: "value".to_string(),
                ty: i32_ty.clone(),
            },
        }],
    };

    let ir = lower_function_skeleton(&skeleton).expect("lower mutable pointer index assignment");
    let [IrStmt::Assign { target, .. }] = ir.body.as_slice() else {
        panic!("expected pointer index assignment, got {:?}", ir.body);
    };
    assert!(matches!(target, IrExpr::Index { .. }));

    let emitted = emit_rust_from_ir(&ir)
        .expect("emit mutable pointer index assignment from clang-lowered IR");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub fn store_at(mut out: &mut [i32], i: usize, value: i32)"));
    assert!(rust.contains("out[i as usize] = value;"));
    assert_rust_snippet_compiles("clang-lowered-mutable-pointer-index-assignment", rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn typed_ir_emits_mutable_pointer_add_index_deref_assignment_from_clang_lowered_ir() {
    let i32_ty = ClangTypeSkeleton {
        spelled: "int".to_string(),
        canonical: "int".to_string(),
        kind: ClangTypeKind::Integer {
            signed: true,
            width: 32,
        },
    };
    let usize_ty = ClangTypeSkeleton {
        spelled: "size_t".to_string(),
        canonical: "size_t".to_string(),
        kind: ClangTypeKind::Integer {
            signed: false,
            width: 64,
        },
    };
    let mutable_i32_ptr = ClangTypeSkeleton {
        spelled: "int *".to_string(),
        canonical: "int *".to_string(),
        kind: ClangTypeKind::Pointer {
            pointee: Box::new(i32_ty.clone()),
            width: None,
        },
    };
    let out_ref = || ClangExprSkeleton::DeclRef {
        name: "out".to_string(),
        ty: mutable_i32_ptr.clone(),
    };
    let index_ref = || ClangExprSkeleton::DeclRef {
        name: "i".to_string(),
        ty: usize_ty.clone(),
    };
    let skeleton = ClangFunctionSkeleton {
        name: "store_at_offset".to_string(),
        return_type: ClangTypeSkeleton {
            spelled: "void".to_string(),
            canonical: "void".to_string(),
            kind: ClangTypeKind::Void,
        },
        params: vec![
            ClangParamSkeleton {
                name: "out".to_string(),
                ty: mutable_i32_ptr.clone(),
            },
            ClangParamSkeleton {
                name: "i".to_string(),
                ty: usize_ty.clone(),
            },
            ClangParamSkeleton {
                name: "value".to_string(),
                ty: i32_ty.clone(),
            },
        ],
        body: vec![ClangStmtSkeleton::Assign {
            target: ClangExprSkeleton::Deref {
                ptr: Box::new(ClangExprSkeleton::Binary {
                    op: ClangBinaryOperator::Add,
                    lhs: Box::new(out_ref()),
                    rhs: Box::new(index_ref()),
                    ty: mutable_i32_ptr.clone(),
                }),
                ty: i32_ty.clone(),
            },
            value: ClangExprSkeleton::DeclRef {
                name: "value".to_string(),
                ty: i32_ty.clone(),
            },
        }],
    };

    let ir =
        lower_function_skeleton(&skeleton).expect("lower mutable pointer add-deref assignment");
    let [IrStmt::Assign { target, .. }] = ir.body.as_slice() else {
        panic!("expected pointer add-deref assignment, got {:?}", ir.body);
    };
    assert!(matches!(target, IrExpr::Deref { .. }));

    let emitted = emit_rust_from_ir(&ir)
        .expect("emit mutable pointer add-deref assignment from clang-lowered IR");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub fn store_at_offset(mut out: &mut [i32], i: usize, value: i32)"));
    assert!(rust.contains("out[i as usize] = value;"));
    assert_rust_snippet_compiles(
        "clang-lowered-mutable-pointer-add-index-deref-assignment",
        rust,
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_does_not_use_deprecated_crc32_route_for_no_globals_crc32() {
    let error = emit_rust_from_ir(&flashdb_crc32_typed_ir())
        .expect_err("no-globals crc32 must not be emitted through a canned legacy route");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert_eq!(error.route.candidate_generator, CandidateGenerator::None);
    assert!(!error.route.deprecated);
    assert!(error.route.delete_when.is_empty());
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_reports_generic_candidate_route_for_scalar_emit() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "add_one_route".to_string(),
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

    let emitted = emit_rust_from_ir(&ir).expect("emit scalar route");

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert_eq!(
        emitted.route.candidate_generator,
        CandidateGenerator::GenericTypedIrEmitter
    );
    assert!(!emitted.route.deprecated);
    assert!(emitted.rust.contains("pub fn add_one_route"));
    assert!(!emitted.rust.contains("crc32_update_byte"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_scalar_subtraction() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "sub_one".to_string(),
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

    let emitted = emit_rust_from_ir(&ir).expect("emit scalar subtraction");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub fn sub_one(value: i32) -> i32"));
    assert!(
        rust.contains("return value.checked_sub(1i32).expect(\"signed subtraction overflow\");")
    );
    assert!(!rust.contains("crc32_update_byte"));
    assert_rust_snippet_compiles("typed-ir-scalar-subtraction", rust);
}

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

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_runs_unsigned_mul_with_wrapping_semantics() {
    let u32_ty = ir_u32();
    let ir = IrFunction {
        name: "mul_two".to_string(),
        return_type: u32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: u32_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(ir_binary(
                IrBinOp::Mul,
                ir_var("value", u32_ty.clone()),
                ir_lit(2, "2U", u32_ty.clone()),
                u32_ty,
            )),
            source_span: None,
        }],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit unsigned wrapping mul");

    assert_rust_snippet_runs(
        "typed-ir-unsigned-wrapping-mul",
        &emitted.rust,
        "assert_eq!(mul_two(u32::MAX), 0xFFFF_FFFEu32);",
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_division_by_zero_literal() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "bad_div_zero".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(ir_binary(
                IrBinOp::Div,
                ir_var("value", i32_ty.clone()),
                ir_lit(0, "0", i32_ty.clone()),
                i32_ty,
            )),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("division by zero must fail closed");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(error.reason.contains("division by zero literal"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_modulo_by_zero_literal() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "bad_mod_zero".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(ir_binary(
                IrBinOp::Mod,
                ir_var("value", i32_ty.clone()),
                ir_lit(0, "0", i32_ty.clone()),
                i32_ty,
            )),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("modulo by zero must fail closed");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(error.reason.contains("modulo by zero literal"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_shift_count_equal_to_integer_width_literal() {
    let u32_ty = ir_u32();
    let ir = IrFunction {
        name: "bad_shift_width".to_string(),
        return_type: u32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: u32_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(ir_binary(
                IrBinOp::Shl,
                ir_var("value", u32_ty.clone()),
                ir_lit(32, "32U", u32_ty.clone()),
                u32_ty,
            )),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("invalid shift count must fail closed");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(error.reason.contains("shift count literal 32"));
    assert!(error.reason.contains("width 32"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_negative_shift_count_literal() {
    let u32_ty = ir_u32();
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "bad_shift_negative".to_string(),
        return_type: u32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: u32_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(ir_binary(
                IrBinOp::Shr,
                ir_var("value", u32_ty.clone()),
                ir_neg(ir_lit(1, "1", i32_ty.clone()), i32_ty),
                u32_ty,
            )),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("negative shift count must fail closed");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(error.reason.contains("negative shift count literal"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_signed_right_shift_without_contract() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "bad_signed_rshift".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(ir_binary(
                IrBinOp::Shr,
                ir_var("value", i32_ty.clone()),
                ir_lit(1, "1", i32_ty.clone()),
                i32_ty,
            )),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("signed right shift must fail closed");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(error.reason.contains("signed right shift"));
    assert!(error.reason.contains("implementation-defined"));
}
