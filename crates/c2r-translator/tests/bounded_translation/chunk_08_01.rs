#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_replays_renamed_record_field_rhs_integer_read_conversion_without_clang() {
    let ast: Value = serde_json::from_str(
        r#"{
        "kind": "TranslationUnitDecl",
        "inner": [
            {
                "kind": "RecordDecl",
                "tagUsed": "struct",
                "name": "quota_window",
                "completeDefinition": true,
                "inner": [
                    {
                        "kind": "FieldDecl",
                        "name": "capacity_left",
                        "type": { "qualType": "size_t" }
                    }
                ]
            },
            {
                "kind": "RecordDecl",
                "tagUsed": "struct",
                "name": "packet_measure",
                "completeDefinition": true,
                "inner": [
                    {
                        "kind": "FieldDecl",
                        "name": "units_used",
                        "type": { "qualType": "uint32_t" }
                    }
                ]
            },
            {
                "kind": "FunctionDecl",
                "name": "consume_packet_measure",
                "type": {
                    "qualType": "void (struct quota_window *, struct packet_measure)"
                },
                "inner": [
                    {
                        "kind": "ParmVarDecl",
                        "name": "window",
                        "type": { "qualType": "struct quota_window *" }
                    },
                    {
                        "kind": "ParmVarDecl",
                        "name": "measure",
                        "type": { "qualType": "struct packet_measure" }
                    },
                    {
                        "kind": "CompoundStmt",
                        "inner": [
                            {
                                "kind": "CompoundAssignOperator",
                                "opcode": "-=",
                                "type": {
                                    "qualType": "size_t",
                                    "desugaredQualType": "uint64_t"
                                },
                                "computeLHSType": {
                                    "qualType": "size_t",
                                    "desugaredQualType": "uint64_t"
                                },
                                "computeResultType": {
                                    "qualType": "size_t",
                                    "desugaredQualType": "uint64_t"
                                },
                                "inner": [
                                    {
                                        "kind": "MemberExpr",
                                        "name": "capacity_left",
                                        "isArrow": true,
                                        "type": {
                                            "qualType": "size_t",
                                            "desugaredQualType": "uint64_t"
                                        },
                                        "inner": [
                                            {
                                                "kind": "DeclRefExpr",
                                                "type": { "qualType": "struct quota_window *" },
                                                "referencedDecl": {
                                                    "kind": "ParmVarDecl",
                                                    "name": "window"
                                                }
                                            }
                                        ]
                                    },
                                    {
                                        "kind": "ImplicitCastExpr",
                                        "castKind": "IntegralCast",
                                        "type": {
                                            "qualType": "size_t",
                                            "desugaredQualType": "uint64_t"
                                        },
                                        "inner": [
                                            {
                                                "kind": "ImplicitCastExpr",
                                                "castKind": "LValueToRValue",
                                                "type": { "qualType": "uint32_t" },
                                                "inner": [
                                                    {
                                                        "kind": "MemberExpr",
                                                        "name": "units_used",
                                                        "isArrow": false,
                                                        "type": { "qualType": "uint32_t" },
                                                        "inner": [
                                                            {
                                                                "kind": "DeclRefExpr",
                                                                "type": {
                                                                    "qualType": "struct packet_measure"
                                                                },
                                                                "referencedDecl": {
                                                                    "kind": "ParmVarDecl",
                                                                    "name": "measure"
                                                                }
                                                            }
                                                        ]
                                                    }
                                                ]
                                            }
                                        ]
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        ]
    }"#,
    )
    .expect("inline AST JSON");
    let target_abi = TargetAbiProfile {
        triple_or_abi: "x86_64-unknown-linux-gnu".to_string(),
        endianness: Some("little".to_string()),
        int_width: 32,
        char_width: 8,
        plain_char_signed: Some(true),
        short_width: 16,
        long_width: 64,
        long_long_width: 64,
        pointer_width: 64,
        ..TargetAbiProfile::default()
    };

    let lowered = lower_function_and_globals_from_clang_ast_json_value_with_target_abi(
        &ast,
        "consume_packet_measure",
        Some(&target_abi),
    )
    .expect("lower renamed record field RHS conversion without invoking clang");
    let [IrStmt::Assign {
        value: IrExpr::Binary { rhs, .. },
        ..
    }] = lowered.function_ir.body.as_slice()
    else {
        panic!(
            "expected one compound assignment desugar, got {:?}",
            lowered.function_ir.body
        );
    };
    let IrExpr::Cast {
        target: cast_target,
        expr: cast_expr,
        implicit: true,
        ..
    } = rhs.as_ref()
    else {
        panic!("expected preserved outer integral cast, got {rhs:?}");
    };
    assert!(matches!(
        cast_target.kind,
        IrTypeKind::Integer {
            signed: false,
            width: 64
        }
    ));
    let IrExpr::LValueToRValue {
        target: read_target,
        expr: read_expr,
        ..
    } = cast_expr.as_ref()
    else {
        panic!("expected preserved integer lvalue-to-rvalue read, got {cast_expr:?}");
    };
    assert!(matches!(
        read_target.kind,
        IrTypeKind::Integer {
            signed: false,
            width: 32
        }
    ));
    assert!(matches!(
        read_expr.as_ref(),
        IrExpr::Member {
            base,
            field,
            ty: IrType {
                kind: IrTypeKind::Integer {
                    signed: false,
                    width: 32
                },
                ..
            },
            is_arrow: false,
            ..
        } if field == "units_used"
            && matches!(base.as_ref(), IrExpr::Var { name, .. } if name == "measure")
    ));
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_lowering_skeleton_maps_record_field_compound_assignment_literal_and_cast_rhs() {
    let int_ty = ClangTypeSkeleton {
        spelled: "int".to_string(),
        canonical: "int".to_string(),
        kind: ClangTypeKind::Integer {
            signed: true,
            width: 32,
        },
    };
    let uint8_ty = ClangTypeSkeleton {
        spelled: "uint8_t".to_string(),
        canonical: "uint8_t".to_string(),
        kind: ClangTypeKind::Integer {
            signed: false,
            width: 8,
        },
    };
    let point_ty = ClangTypeSkeleton {
        spelled: "struct point".to_string(),
        canonical: "struct point".to_string(),
        kind: ClangTypeKind::Record {
            name: "point".to_string(),
        },
    };
    let field_target = ClangExprSkeleton::Member {
        base: Box::new(ClangExprSkeleton::DeclRef {
            name: "p".to_string(),
            ty: point_ty.clone(),
        }),
        field: "x".to_string(),
        ty: int_ty.clone(),
        is_arrow: false,
    };
    let skeleton = ClangFunctionSkeleton {
        name: "add_point_literals".to_string(),
        return_type: int_ty.clone(),
        params: vec![
            ClangParamSkeleton {
                name: "p".to_string(),
                ty: point_ty.clone(),
            },
            ClangParamSkeleton {
                name: "byte".to_string(),
                ty: uint8_ty.clone(),
            },
        ],
        body: vec![
            ClangStmtSkeleton::CompoundAssign {
                target: field_target.clone(),
                op: ClangBinaryOperator::Add,
                value: ClangExprSkeleton::IntegerLiteral {
                    value: 1,
                    spelling: "1".to_string(),
                    ty: int_ty.clone(),
                },
                result_ty: int_ty.clone(),
                compute_lhs_ty: int_ty.clone(),
                compute_result_ty: int_ty.clone(),
            },
            ClangStmtSkeleton::CompoundAssign {
                target: field_target.clone(),
                op: ClangBinaryOperator::Add,
                value: ClangExprSkeleton::Cast {
                    target: int_ty.clone(),
                    expr: Box::new(ClangExprSkeleton::DeclRef {
                        name: "byte".to_string(),
                        ty: uint8_ty,
                    }),
                    implicit: true,
                },
                result_ty: int_ty.clone(),
                compute_lhs_ty: int_ty.clone(),
                compute_result_ty: int_ty.clone(),
            },
            ClangStmtSkeleton::Return {
                value: Some(field_target),
            },
        ],
    };

    let ir = lower_function_skeleton(&skeleton)
        .expect("lower by-value record field compound assignment literal/cast RHS");

    let rust = emit_rust_from_ir(&ir).expect("emit record field compound assignment literal/cast");
    assert!(rust.contains("p.x = p.x.checked_add(1i32).expect(\"signed addition overflow\");"));
    assert!(
        rust.contains("p.x = p.x.checked_add((byte as i32)).expect(\"signed addition overflow\");")
    );
    assert_rust_snippet_compiles("typed-ir-clang-record-field-compound-literal-cast", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_lowering_skeleton_rejects_record_field_compound_assignment_complex_rhs() {
    let int_ty = ClangTypeSkeleton {
        spelled: "int".to_string(),
        canonical: "int".to_string(),
        kind: ClangTypeKind::Integer {
            signed: true,
            width: 32,
        },
    };
    let point_ty = ClangTypeSkeleton {
        spelled: "struct point".to_string(),
        canonical: "struct point".to_string(),
        kind: ClangTypeKind::Record {
            name: "point".to_string(),
        },
    };
    let skeleton = ClangFunctionSkeleton {
        name: "bad_record_field_compound_rhs".to_string(),
        return_type: int_ty.clone(),
        params: vec![
            ClangParamSkeleton {
                name: "p".to_string(),
                ty: point_ty.clone(),
            },
            ClangParamSkeleton {
                name: "value".to_string(),
                ty: int_ty.clone(),
            },
        ],
        body: vec![ClangStmtSkeleton::CompoundAssign {
            target: ClangExprSkeleton::Member {
                base: Box::new(ClangExprSkeleton::DeclRef {
                    name: "p".to_string(),
                    ty: point_ty,
                }),
                field: "x".to_string(),
                ty: int_ty.clone(),
                is_arrow: false,
            },
            op: ClangBinaryOperator::Add,
            value: ClangExprSkeleton::Binary {
                op: ClangBinaryOperator::Add,
                lhs: Box::new(ClangExprSkeleton::DeclRef {
                    name: "value".to_string(),
                    ty: int_ty.clone(),
                }),
                rhs: Box::new(ClangExprSkeleton::IntegerLiteral {
                    value: 1,
                    spelling: "1".to_string(),
                    ty: int_ty.clone(),
                }),
                ty: int_ty.clone(),
            },
            result_ty: int_ty.clone(),
            compute_lhs_ty: int_ty.clone(),
            compute_result_ty: int_ty.clone(),
        }],
    };

    let error = lower_function_skeleton(&skeleton)
        .expect_err("record field compound assignment must reject complex RHS");

    assert_eq!(error.kind, "unsupported_compound_assignment_value");
    assert!(error
        .message
        .contains("record field compound assignment RHS"));
}
#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_lowering_skeleton_rejects_record_field_compound_assignment_call_rhs() {
    let int_ty = ClangTypeSkeleton {
        spelled: "int".to_string(),
        canonical: "int".to_string(),
        kind: ClangTypeKind::Integer {
            signed: true,
            width: 32,
        },
    };
    let point_ty = ClangTypeSkeleton {
        spelled: "struct point".to_string(),
        canonical: "struct point".to_string(),
        kind: ClangTypeKind::Record {
            name: "point".to_string(),
        },
    };
    let skeleton = ClangFunctionSkeleton {
        name: "bad_record_field_compound_call_rhs".to_string(),
        return_type: int_ty.clone(),
        params: vec![ClangParamSkeleton {
            name: "p".to_string(),
            ty: point_ty.clone(),
        }],
        body: vec![ClangStmtSkeleton::CompoundAssign {
            target: ClangExprSkeleton::Member {
                base: Box::new(ClangExprSkeleton::DeclRef {
                    name: "p".to_string(),
                    ty: point_ty,
                }),
                field: "x".to_string(),
                ty: int_ty.clone(),
                is_arrow: false,
            },
            op: ClangBinaryOperator::Add,
            value: ClangExprSkeleton::Call {
                callee: "helper".to_string(),
                args: Vec::new(),
                ty: int_ty.clone(),
            },
            result_ty: int_ty.clone(),
            compute_lhs_ty: int_ty.clone(),
            compute_result_ty: int_ty.clone(),
        }],
    };

    let error = lower_function_skeleton(&skeleton)
        .expect_err("record field compound assignment must reject call RHS");

    assert_eq!(error.kind, "unsupported_compound_assignment_value");
    assert!(error
        .message
        .contains("record field compound assignment RHS"));
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_lowering_skeleton_rejects_record_field_compound_assignment_inc_dec_rhs() {
    let int_ty = ClangTypeSkeleton {
        spelled: "int".to_string(),
        canonical: "int".to_string(),
        kind: ClangTypeKind::Integer {
            signed: true,
            width: 32,
        },
    };
    let counter_ty = ClangTypeSkeleton {
        spelled: "struct renamed_counter".to_string(),
        canonical: "struct renamed_counter".to_string(),
        kind: ClangTypeKind::Record {
            name: "renamed_counter".to_string(),
        },
    };
    let skeleton = ClangFunctionSkeleton {
        name: "reject_counter_step_rhs".to_string(),
        return_type: int_ty.clone(),
        params: vec![
            ClangParamSkeleton {
                name: "counter".to_string(),
                ty: counter_ty.clone(),
            },
            ClangParamSkeleton {
                name: "step".to_string(),
                ty: int_ty.clone(),
            },
        ],
        body: vec![ClangStmtSkeleton::CompoundAssign {
            target: ClangExprSkeleton::Member {
                base: Box::new(ClangExprSkeleton::DeclRef {
                    name: "counter".to_string(),
                    ty: counter_ty,
                }),
                field: "total".to_string(),
                ty: int_ty.clone(),
                is_arrow: false,
            },
            op: ClangBinaryOperator::Add,
            value: ClangExprSkeleton::IncDec {
                target: Box::new(ClangExprSkeleton::DeclRef {
                    name: "step".to_string(),
                    ty: int_ty.clone(),
                }),
                op: ClangIncDecOperator::Inc,
                prefix: false,
                ty: int_ty.clone(),
            },
            result_ty: int_ty.clone(),
            compute_lhs_ty: int_ty.clone(),
            compute_result_ty: int_ty,
        }],
    };

    let error = lower_function_skeleton(&skeleton)
        .expect_err("record field compound assignment must reject inc/dec RHS");

    assert_eq!(error.kind, "unsupported_compound_assignment_value");
    assert!(error
        .message
        .contains("record field compound assignment RHS"));
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_lowering_skeleton_rejects_record_field_compound_assignment_member_rhs() {
    let int_ty = ClangTypeSkeleton {
        spelled: "int".to_string(),
        canonical: "int".to_string(),
        kind: ClangTypeKind::Integer {
            signed: true,
            width: 32,
        },
    };
    let point_ty = ClangTypeSkeleton {
        spelled: "struct point".to_string(),
        canonical: "struct point".to_string(),
        kind: ClangTypeKind::Record {
            name: "point".to_string(),
        },
    };
    let skeleton = ClangFunctionSkeleton {
        name: "bad_record_field_compound_member_rhs".to_string(),
        return_type: int_ty.clone(),
        params: vec![ClangParamSkeleton {
            name: "p".to_string(),
            ty: point_ty.clone(),
        }],
        body: vec![ClangStmtSkeleton::CompoundAssign {
            target: ClangExprSkeleton::Member {
                base: Box::new(ClangExprSkeleton::DeclRef {
                    name: "p".to_string(),
                    ty: point_ty.clone(),
                }),
                field: "x".to_string(),
                ty: int_ty.clone(),
                is_arrow: false,
            },
            op: ClangBinaryOperator::Add,
            value: ClangExprSkeleton::Member {
                base: Box::new(ClangExprSkeleton::DeclRef {
                    name: "p".to_string(),
                    ty: point_ty,
                }),
                field: "y".to_string(),
                ty: int_ty.clone(),
                is_arrow: false,
            },
            result_ty: int_ty.clone(),
            compute_lhs_ty: int_ty.clone(),
            compute_result_ty: int_ty.clone(),
        }],
    };

    let error = lower_function_skeleton(&skeleton)
        .expect_err("record field compound assignment must reject member RHS");

    assert_eq!(error.kind, "unsupported_compound_assignment_value");
    assert!(error
        .message
        .contains("record field compound assignment RHS"));
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_lowering_skeleton_rejects_record_field_compound_assignment_index_rhs() {
    let int_ty = ClangTypeSkeleton {
        spelled: "int".to_string(),
        canonical: "int".to_string(),
        kind: ClangTypeKind::Integer {
            signed: true,
            width: 32,
        },
    };
    let int_array_ty = ClangTypeSkeleton {
        spelled: "int[4]".to_string(),
        canonical: "int[4]".to_string(),
        kind: ClangTypeKind::Array {
            element: Box::new(int_ty.clone()),
            len: Some(4),
        },
    };
    let point_ty = ClangTypeSkeleton {
        spelled: "struct point".to_string(),
        canonical: "struct point".to_string(),
        kind: ClangTypeKind::Record {
            name: "point".to_string(),
        },
    };
    let skeleton = ClangFunctionSkeleton {
        name: "bad_record_field_compound_index_rhs".to_string(),
        return_type: int_ty.clone(),
        params: vec![
            ClangParamSkeleton {
                name: "p".to_string(),
                ty: point_ty.clone(),
            },
            ClangParamSkeleton {
                name: "values".to_string(),
                ty: int_array_ty.clone(),
            },
        ],
        body: vec![ClangStmtSkeleton::CompoundAssign {
            target: ClangExprSkeleton::Member {
                base: Box::new(ClangExprSkeleton::DeclRef {
                    name: "p".to_string(),
                    ty: point_ty,
                }),
                field: "x".to_string(),
                ty: int_ty.clone(),
                is_arrow: false,
            },
            op: ClangBinaryOperator::Add,
            value: ClangExprSkeleton::Index {
                base: Box::new(ClangExprSkeleton::DeclRef {
                    name: "values".to_string(),
                    ty: int_array_ty,
                }),
                index: Box::new(ClangExprSkeleton::IntegerLiteral {
                    value: 0,
                    spelling: "0".to_string(),
                    ty: int_ty.clone(),
                }),
                ty: int_ty.clone(),
            },
            result_ty: int_ty.clone(),
            compute_lhs_ty: int_ty.clone(),
            compute_result_ty: int_ty.clone(),
        }],
    };

    let error = lower_function_skeleton(&skeleton)
        .expect_err("record field compound assignment must reject index RHS");

    assert_eq!(error.kind, "unsupported_compound_assignment_value");
    assert!(error
        .message
        .contains("record field compound assignment RHS"));
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_lowering_skeleton_rejects_record_field_compound_assignment_non_integer_rhs() {
    let int_ty = ClangTypeSkeleton {
        spelled: "int".to_string(),
        canonical: "int".to_string(),
        kind: ClangTypeKind::Integer {
            signed: true,
            width: 32,
        },
    };
    let int_ptr_ty = ClangTypeSkeleton {
        spelled: "int *".to_string(),
        canonical: "int *".to_string(),
        kind: ClangTypeKind::Pointer {
            pointee: Box::new(int_ty.clone()),
            width: None,
        },
    };
    let point_ty = ClangTypeSkeleton {
        spelled: "struct point".to_string(),
        canonical: "struct point".to_string(),
        kind: ClangTypeKind::Record {
            name: "point".to_string(),
        },
    };
    let skeleton = ClangFunctionSkeleton {
        name: "reject_non_integer_record_field_read".to_string(),
        return_type: int_ty.clone(),
        params: vec![ClangParamSkeleton {
            name: "p".to_string(),
            ty: point_ty.clone(),
        }],
        body: vec![ClangStmtSkeleton::CompoundAssign {
            target: ClangExprSkeleton::Member {
                base: Box::new(ClangExprSkeleton::DeclRef {
                    name: "p".to_string(),
                    ty: point_ty.clone(),
                }),
                field: "x".to_string(),
                ty: int_ty.clone(),
                is_arrow: false,
            },
            op: ClangBinaryOperator::Add,
            value: ClangExprSkeleton::LValueToRValue {
                target: int_ptr_ty.clone(),
                expr: Box::new(ClangExprSkeleton::Member {
                    base: Box::new(ClangExprSkeleton::DeclRef {
                        name: "p".to_string(),
                        ty: point_ty,
                    }),
                    field: "next".to_string(),
                    ty: int_ptr_ty,
                    is_arrow: false,
                }),
            },
            result_ty: int_ty.clone(),
            compute_lhs_ty: int_ty.clone(),
            compute_result_ty: int_ty.clone(),
        }],
    };

    let error = lower_function_skeleton(&skeleton)
        .expect_err("record field compound assignment must reject non-integer RHS");

    assert_eq!(error.kind, "unsupported_compound_assignment_value");
    assert!(error
        .message
        .contains("lvalue-to-rvalue target must be an integer"));
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_lowering_skeleton_rejects_record_field_compound_assignment_cast_and_compute_mismatch() {
    let int_ty = ClangTypeSkeleton {
        spelled: "int".to_string(),
        canonical: "int".to_string(),
        kind: ClangTypeKind::Integer {
            signed: true,
            width: 32,
        },
    };
    let uint_ty = ClangTypeSkeleton {
        spelled: "unsigned int".to_string(),
        canonical: "unsigned int".to_string(),
        kind: ClangTypeKind::Integer {
            signed: false,
            width: 32,
        },
    };
    let int_ptr_ty = ClangTypeSkeleton {
        spelled: "int *".to_string(),
        canonical: "int *".to_string(),
        kind: ClangTypeKind::Pointer {
            pointee: Box::new(int_ty.clone()),
            width: None,
        },
    };
    let bucket_ty = ClangTypeSkeleton {
        spelled: "struct renamed_bucket".to_string(),
        canonical: "struct renamed_bucket".to_string(),
        kind: ClangTypeKind::Record {
            name: "renamed_bucket".to_string(),
        },
    };
    let target = ClangExprSkeleton::Member {
        base: Box::new(ClangExprSkeleton::DeclRef {
            name: "bucket".to_string(),
            ty: bucket_ty.clone(),
        }),
        field: "count".to_string(),
        ty: int_ty.clone(),
        is_arrow: false,
    };
    let cast_mismatch = ClangFunctionSkeleton {
        name: "reject_pointer_cast_rhs".to_string(),
        return_type: int_ty.clone(),
        params: vec![ClangParamSkeleton {
            name: "bucket".to_string(),
            ty: bucket_ty.clone(),
        }],
        body: vec![ClangStmtSkeleton::CompoundAssign {
            target: target.clone(),
            op: ClangBinaryOperator::Add,
            value: ClangExprSkeleton::Cast {
                target: int_ptr_ty,
                expr: Box::new(ClangExprSkeleton::IntegerLiteral {
                    value: 1,
                    spelling: "1".to_string(),
                    ty: int_ty.clone(),
                }),
                implicit: false,
            },
            result_ty: int_ty.clone(),
            compute_lhs_ty: int_ty.clone(),
            compute_result_ty: int_ty.clone(),
        }],
    };
    let cast_error = lower_function_skeleton(&cast_mismatch)
        .expect_err("record field compound assignment must reject non-integer cast target");
    assert_eq!(cast_error.kind, "unsupported_compound_assignment_value");
    assert!(cast_error
        .message
        .contains("RHS cast target must be an integer"));

    let compute_mismatch = ClangFunctionSkeleton {
        name: "reject_compute_type_mismatch".to_string(),
        return_type: int_ty.clone(),
        params: vec![ClangParamSkeleton {
            name: "bucket".to_string(),
            ty: bucket_ty,
        }],
        body: vec![ClangStmtSkeleton::CompoundAssign {
            target,
            op: ClangBinaryOperator::Add,
            value: ClangExprSkeleton::IntegerLiteral {
                value: 1,
                spelling: "1".to_string(),
                ty: int_ty.clone(),
            },
            result_ty: int_ty.clone(),
            compute_lhs_ty: int_ty,
            compute_result_ty: uint_ty,
        }],
    };
    let compute_error = lower_function_skeleton(&compute_mismatch)
        .expect_err("record field compound assignment must reject compute type mismatch");
    assert_eq!(compute_error.kind, "unsupported_compound_assignment_type");
    assert!(compute_error
        .message
        .contains("compute lhs/result types must match"));
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_lowering_skeleton_rejects_record_field_compound_assignment_deref_target() {
    let int_ty = ClangTypeSkeleton {
        spelled: "int".to_string(),
        canonical: "int".to_string(),
        kind: ClangTypeKind::Integer {
            signed: true,
            width: 32,
        },
    };
    let int_ptr_ty = ClangTypeSkeleton {
        spelled: "int *".to_string(),
        canonical: "int *".to_string(),
        kind: ClangTypeKind::Pointer {
            pointee: Box::new(int_ty.clone()),
            width: None,
        },
    };
    let skeleton = ClangFunctionSkeleton {
        name: "bad_record_field_compound_deref_target".to_string(),
        return_type: int_ty.clone(),
        params: vec![ClangParamSkeleton {
            name: "p".to_string(),
            ty: int_ptr_ty.clone(),
        }],
        body: vec![ClangStmtSkeleton::CompoundAssign {
            target: ClangExprSkeleton::Deref {
                ptr: Box::new(ClangExprSkeleton::DeclRef {
                    name: "p".to_string(),
                    ty: int_ptr_ty,
                }),
                ty: int_ty.clone(),
            },
            op: ClangBinaryOperator::Add,
            value: ClangExprSkeleton::IntegerLiteral {
                value: 1,
                spelling: "1".to_string(),
                ty: int_ty.clone(),
            },
            result_ty: int_ty.clone(),
            compute_lhs_ty: int_ty.clone(),
            compute_result_ty: int_ty.clone(),
        }],
    };

    let error = lower_function_skeleton(&skeleton)
        .expect_err("record field compound assignment must reject deref target");

    assert_eq!(error.kind, "unsupported_compound_assignment_target");
    assert!(error
        .message
        .contains("simple variable or by-value record field"));
}
