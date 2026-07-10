#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_lowering_skeleton_rejects_compound_assignment_index_record_member_base() {
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
    let holder_ty = ClangTypeSkeleton {
        spelled: "struct holder".to_string(),
        canonical: "struct holder".to_string(),
        kind: ClangTypeKind::Record {
            name: "holder".to_string(),
        },
    };
    let skeleton = ClangFunctionSkeleton {
        name: "reject_member_index_base".to_string(),
        return_type: int_ty.clone(),
        params: vec![ClangParamSkeleton {
            name: "state".to_string(),
            ty: holder_ty.clone(),
        }],
        body: vec![ClangStmtSkeleton::CompoundAssign {
            target: ClangExprSkeleton::Index {
                base: Box::new(ClangExprSkeleton::Member {
                    base: Box::new(ClangExprSkeleton::DeclRef {
                        name: "state".to_string(),
                        ty: holder_ty,
                    }),
                    field: "slots".to_string(),
                    ty: int_array_ty,
                    is_arrow: false,
                }),
                index: Box::new(ClangExprSkeleton::IntegerLiteral {
                    value: 0,
                    spelling: "0".to_string(),
                    ty: int_ty.clone(),
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
        .expect_err("compound assignment index must reject record member base");

    assert_eq!(error.kind, "unsupported_compound_assignment_target");
    assert!(error
        .message
        .contains("direct pointer parameter or local fixed array"));
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_lowering_skeleton_maps_mutable_record_pointer_field_compound_assignment() {
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
    let point_ptr_ty = ClangTypeSkeleton {
        spelled: "struct point *".to_string(),
        canonical: "struct point *".to_string(),
        kind: ClangTypeKind::Pointer {
            pointee: Box::new(point_ty.clone()),
            width: None,
        },
    };
    let void_ty = ClangTypeSkeleton {
        spelled: "void".to_string(),
        canonical: "void".to_string(),
        kind: ClangTypeKind::Void,
    };
    let skeleton = ClangFunctionSkeleton {
        name: "add_point_x".to_string(),
        return_type: void_ty,
        params: vec![
            ClangParamSkeleton {
                name: "p".to_string(),
                ty: point_ptr_ty.clone(),
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
                    ty: point_ptr_ty,
                }),
                field: "x".to_string(),
                ty: int_ty.clone(),
                is_arrow: true,
            },
            op: ClangBinaryOperator::Add,
            value: ClangExprSkeleton::DeclRef {
                name: "value".to_string(),
                ty: int_ty.clone(),
            },
            result_ty: int_ty.clone(),
            compute_lhs_ty: int_ty.clone(),
            compute_result_ty: int_ty.clone(),
        }],
    };

    let ir = lower_function_skeleton(&skeleton)
        .expect("lower mutable record pointer field compound assignment");

    let [IrStmt::Assign { target, value, .. }] = ir.body.as_slice() else {
        panic!(
            "expected mutable arrow field compound assignment, got {:?}",
            ir.body
        );
    };
    assert!(
        matches!(target, IrExpr::Member { field, is_arrow: true, .. } if field == "x"),
        "expected arrow member target, got {target:?}"
    );
    let IrExpr::Binary { op, lhs, rhs, .. } = value else {
        panic!("expected binary compound value, got {value:?}");
    };
    assert_eq!(op, &IrBinOp::Add);
    assert!(
        matches!(lhs.as_ref(), IrExpr::Member { field, is_arrow: true, .. } if field == "x"),
        "expected arrow member lhs, got {lhs:?}"
    );
    assert!(matches!(rhs.as_ref(), IrExpr::Var { name, .. } if name == "value"));

    let rust = emit_rust_from_ir(&ir)
        .expect("emit mutable record pointer field compound assignment skeleton");
    assert!(rust.contains("pub fn add_point_x(mut p: &mut Point, value: i32)"));
    assert!(rust.contains("p.x = p.x.checked_add(value).expect(\"signed addition overflow\");"));
    assert_rust_snippet_compiles(
        "typed-ir-clang-mutable-record-pointer-field-compound",
        &rust,
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_lowering_skeleton_rejects_record_field_compound_assignment_nested_base() {
    let int_ty = ClangTypeSkeleton {
        spelled: "int".to_string(),
        canonical: "int".to_string(),
        kind: ClangTypeKind::Integer {
            signed: true,
            width: 32,
        },
    };
    let outer_ty = ClangTypeSkeleton {
        spelled: "struct outer".to_string(),
        canonical: "struct outer".to_string(),
        kind: ClangTypeKind::Record {
            name: "outer".to_string(),
        },
    };
    let inner_ty = ClangTypeSkeleton {
        spelled: "struct inner".to_string(),
        canonical: "struct inner".to_string(),
        kind: ClangTypeKind::Record {
            name: "inner".to_string(),
        },
    };
    let skeleton = ClangFunctionSkeleton {
        name: "bad_record_field_compound_nested_base".to_string(),
        return_type: int_ty.clone(),
        params: vec![ClangParamSkeleton {
            name: "p".to_string(),
            ty: outer_ty.clone(),
        }],
        body: vec![ClangStmtSkeleton::CompoundAssign {
            target: ClangExprSkeleton::Member {
                base: Box::new(ClangExprSkeleton::Member {
                    base: Box::new(ClangExprSkeleton::DeclRef {
                        name: "p".to_string(),
                        ty: outer_ty,
                    }),
                    field: "inner".to_string(),
                    ty: inner_ty,
                    is_arrow: false,
                }),
                field: "x".to_string(),
                ty: int_ty.clone(),
                is_arrow: false,
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
        .expect_err("record field compound assignment must reject nested base");

    assert_eq!(error.kind, "unsupported_compound_assignment_target");
    assert!(error.message.contains("direct record variable base"));
}
#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_lowering_skeleton_maps_compound_assignment_integer_promotion() {
    let uint8_ty = ClangTypeSkeleton {
        spelled: "uint8_t".to_string(),
        canonical: "uint8_t".to_string(),
        kind: ClangTypeKind::Integer {
            signed: false,
            width: 8,
        },
    };
    let int_ty = ClangTypeSkeleton {
        spelled: "int".to_string(),
        canonical: "int".to_string(),
        kind: ClangTypeKind::Integer {
            signed: true,
            width: 32,
        },
    };
    let skeleton = ClangFunctionSkeleton {
        name: "inc8".to_string(),
        return_type: uint8_ty.clone(),
        params: vec![ClangParamSkeleton {
            name: "value".to_string(),
            ty: uint8_ty.clone(),
        }],
        body: vec![
            ClangStmtSkeleton::CompoundAssign {
                target: ClangExprSkeleton::DeclRef {
                    name: "value".to_string(),
                    ty: uint8_ty.clone(),
                },
                op: ClangBinaryOperator::Add,
                value: ClangExprSkeleton::IntegerLiteral {
                    value: 1,
                    spelling: "1".to_string(),
                    ty: int_ty.clone(),
                },
                result_ty: uint8_ty.clone(),
                compute_lhs_ty: int_ty.clone(),
                compute_result_ty: int_ty.clone(),
            },
            ClangStmtSkeleton::Return {
                value: Some(ClangExprSkeleton::DeclRef {
                    name: "value".to_string(),
                    ty: uint8_ty.clone(),
                }),
            },
        ],
    };

    let ir =
        lower_function_skeleton(&skeleton).expect("lower promoted compound assignment skeleton");

    let [IrStmt::Assign { target, value, .. }, IrStmt::Return { .. }] = ir.body.as_slice() else {
        panic!(
            "expected promoted compound assignment followed by return, got {:?}",
            ir.body
        );
    };
    assert!(matches!(target, IrExpr::Var { name, .. } if name == "value"));
    let IrExpr::Cast {
        target: cast_target,
        expr,
        implicit: true,
        ..
    } = value
    else {
        panic!("expected final truncation cast, got {value:?}");
    };
    assert!(matches!(
        &cast_target.kind,
        IrTypeKind::Integer {
            signed: false,
            width: 8
        }
    ));
    let IrExpr::Binary {
        op, lhs, rhs, ty, ..
    } = expr.as_ref()
    else {
        panic!("expected promoted binary, got {expr:?}");
    };
    assert_eq!(op, &IrBinOp::Add);
    assert!(matches!(
        &ty.kind,
        IrTypeKind::Integer {
            signed: true,
            width: 32
        }
    ));
    assert!(matches!(
        lhs.as_ref(),
        IrExpr::Cast {
            target,
            expr,
            implicit: true,
            ..
        } if matches!(&target.kind, IrTypeKind::Integer { signed: true, width: 32 })
            && matches!(expr.as_ref(), IrExpr::Var { name, .. } if name == "value")
    ));
    assert!(matches!(rhs.as_ref(), IrExpr::LitInt { value: 1, .. }));

    let rust =
        emit_rust_from_ir(&ir).expect("emit promoted compound assignment from lowered skeleton");
    assert!(rust.contains("pub fn inc8(mut value: u8) -> u8"));
    assert!(rust.contains(
        "value = ((value as i32).checked_add(1i32).expect(\"signed addition overflow\") as u8);"
    ));
    assert!(rust.contains("return value;"));
    assert_rust_snippet_compiles("typed-ir-clang-compound-promotion", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_replays_compound_assignment_integer_promotion_without_clang() {
    let ast: Value = serde_json::from_str(include_str!(
        "../../fixtures/clang_ast/compound_assignment_promotion_ast.json"
    ))
    .expect("fixture JSON");

    let lowered = lower_function_and_globals_from_clang_ast_json_value(
        &ast,
        "compound_assignment_integer_promotion",
    )
    .expect("compound assignment integer promotion fixture should lower");

    let [IrStmt::Assign { target, value, .. }, IrStmt::Return { .. }] =
        lowered.function_ir.body.as_slice()
    else {
        panic!(
            "expected promoted compound assignment followed by return, got {:?}",
            lowered.function_ir.body
        );
    };
    assert!(matches!(target, IrExpr::Var { name, .. } if name == "value"));
    let IrExpr::Cast {
        target: cast_target,
        expr,
        implicit: true,
        ..
    } = value
    else {
        panic!("expected final truncation cast, got {value:?}");
    };
    assert!(matches!(
        &cast_target.kind,
        IrTypeKind::Integer {
            signed: false,
            width: 8
        }
    ));
    assert!(matches!(
        expr.as_ref(),
        IrExpr::Binary {
            op: IrBinOp::Add,
            ty,
            ..
        } if matches!(&ty.kind, IrTypeKind::Integer { signed: true, width: 32 })
    ));

    let emitted = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect("emit promoted compound assignment from fixture typed IR");
    let rust = &emitted.rust;
    assert!(rust.contains("pub fn compound_assignment_integer_promotion(mut value: u8) -> u8"));
    assert!(rust.contains(
        "value = ((value as i32).checked_add(1i32).expect(\"signed addition overflow\") as u8);"
    ));
    assert!(rust.contains("return value;"));
    assert_rust_snippet_compiles("typed-ir-clang-ast-compound-promotion", rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_replays_pointer_index_compound_assignments_without_clang() {
    let decl_ref = |name: &str, qual_type: &str| {
        serde_json::json!({
            "kind": "DeclRefExpr",
            "type": { "qualType": qual_type },
            "referencedDecl": { "kind": "ParmVarDecl", "name": name }
        })
    };
    let lvalue = |name: &str, qual_type: &str| {
        serde_json::json!({
            "kind": "ImplicitCastExpr",
            "castKind": "LValueToRValue",
            "type": { "qualType": qual_type },
            "inner": [decl_ref(name, qual_type)]
        })
    };
    let pointer_base = || lvalue("data", "unsigned char *");
    let position = || lvalue("position", "int");
    let index_target = |index: Value| {
        serde_json::json!({
            "kind": "ArraySubscriptExpr",
            "type": { "qualType": "unsigned char" },
            "inner": [pointer_base(), index]
        })
    };
    let cast_position = serde_json::json!({
        "kind": "CStyleCastExpr",
        "castKind": "NoOp",
        "type": { "qualType": "int" },
        "inner": [position()]
    });
    let keep_mask = serde_json::json!({
        "kind": "BinaryOperator",
        "opcode": "|",
        "type": { "qualType": "int" },
        "inner": [
            lvalue("keep", "int"),
            {
                "kind": "IntegerLiteral",
                "type": { "qualType": "int" },
                "value": "3"
            }
        ]
    });
    let bit_and = serde_json::json!({
        "kind": "CompoundAssignOperator",
        "opcode": "&=",
        "type": { "qualType": "unsigned char" },
        "computeLHSType": { "qualType": "int" },
        "computeResultType": { "qualType": "int" },
        "inner": [index_target(cast_position), keep_mask]
    });
    let bit_or = serde_json::json!({
        "kind": "CompoundAssignOperator",
        "opcode": "|=",
        "type": { "qualType": "unsigned char" },
        "computeLHSType": { "qualType": "int" },
        "computeResultType": { "qualType": "int" },
        "inner": [index_target(position()), lvalue("set", "int")]
    });
    let return_slot = serde_json::json!({
        "kind": "ReturnStmt",
        "inner": [{
            "kind": "CStyleCastExpr",
            "castKind": "IntegralCast",
            "type": { "qualType": "unsigned char" },
            "inner": [{
                "kind": "IntegerLiteral",
                "type": { "qualType": "int" },
                "value": "0"
            }]
        }]
    });
    let ast = serde_json::json!({
        "kind": "TranslationUnitDecl",
        "inner": [{
            "kind": "FunctionDecl",
            "name": "transform_slot",
            "type": {
                "qualType": "unsigned char (unsigned char *, int, int, int)"
            },
            "inner": [
                { "kind": "ParmVarDecl", "name": "data", "type": { "qualType": "unsigned char *" } },
                { "kind": "ParmVarDecl", "name": "position", "type": { "qualType": "int" } },
                { "kind": "ParmVarDecl", "name": "keep", "type": { "qualType": "int" } },
                { "kind": "ParmVarDecl", "name": "set", "type": { "qualType": "int" } },
                { "kind": "CompoundStmt", "inner": [bit_and, bit_or, return_slot] }
            ]
        }]
    });

    let lowered = lower_function_and_globals_from_clang_ast_json_value(&ast, "transform_slot")
        .expect("pointer index compound assignment AST should lower");
    let [IrStmt::Assign { value: first, .. }, IrStmt::Assign { value: second, .. }, IrStmt::Return { .. }] =
        lowered.function_ir.body.as_slice()
    else {
        panic!(
            "expected two index assignments and return, got {:?}",
            lowered.function_ir.body
        );
    };
    assert!(matches!(
        first,
        IrExpr::Cast {
            expr,
            target,
            implicit: true,
            ..
        } if matches!(&target.kind, IrTypeKind::Integer { signed: false, width: 8 })
            && matches!(expr.as_ref(), IrExpr::Binary { op: IrBinOp::BitAnd, .. })
    ));
    let IrExpr::Cast {
        expr: first_binary, ..
    } = first
    else {
        unreachable!("first compound assignment must narrow the binary result");
    };
    let IrExpr::Binary { lhs: first_lhs, .. } = first_binary.as_ref() else {
        unreachable!("first compound assignment must contain a binary operation");
    };
    let IrExpr::Cast {
        expr: first_read, ..
    } = first_lhs.as_ref()
    else {
        unreachable!("pointer element read must promote to the compute type");
    };
    let IrExpr::Index {
        base: first_base, ..
    } = first_read.as_ref()
    else {
        unreachable!("compound lhs must read the indexed element");
    };
    let IrExpr::Var {
        ty: first_base_ty, ..
    } = first_base.as_ref()
    else {
        unreachable!("compound index base must remain a direct variable");
    };
    let IrTypeKind::Pointer { pointee } = &first_base_ty.kind else {
        unreachable!("compound index base must remain a pointer");
    };
    assert!(pointee.is_const, "compound read must use a readonly view");
    assert!(matches!(
        second,
        IrExpr::Cast {
            expr,
            target,
            implicit: true,
            ..
        } if matches!(&target.kind, IrTypeKind::Integer { signed: false, width: 8 })
            && matches!(expr.as_ref(), IrExpr::Binary { op: IrBinOp::BitOr, .. })
    ));

    let emitted = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect("emit pointer index compound assignments");
    let rust = &emitted.rust;
    assert!(rust.contains(
        "pub fn transform_slot(mut data: &mut [u8], position: i32, keep: i32, set: i32) -> u8"
    ));
    assert!(rust.contains("data[(position as i32) as usize] ="));
    assert!(rust.contains("& (keep | 3i32)"));
    assert!(rust.contains("data[position as usize] ="));
    assert!(rust.contains("| set"));
    assert_rust_snippet_runs(
        "typed-ir-clang-ast-pointer-index-compound-assignment",
        rust,
        r#"
    let mut data = [0u8, 0xf0u8];
    let result = transform_slot(&mut data, 1, 0xacu32 as i32, 0x03);
    assert_eq!(result, 0u8);
    assert_eq!(data[1], 0xa3u8);
"#,
    );
}
