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
