    #[test]
    fn stmt_skeleton_from_ast_accepts_compound_assignment_integer_promotion() {
        let stmt = serde_json::json!({
            "kind": "CompoundAssignOperator",
            "opcode": "+=",
            "type": { "qualType": "unsigned char" },
            "computeLHSType": { "qualType": "int" },
            "computeResultType": { "qualType": "int" },
            "inner": [
                {
                    "kind": "DeclRefExpr",
                    "type": { "qualType": "unsigned char" },
                    "referencedDecl": {
                        "kind": "ParmVarDecl",
                        "name": "x"
                    }
                },
                {
                    "kind": "ImplicitCastExpr",
                    "castKind": "LValueToRValue",
                    "type": { "qualType": "int" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "int" },
                            "referencedDecl": {
                                "kind": "ParmVarDecl",
                                "name": "y"
                            }
                        }
                    ]
                }
            ]
        });

        let skeleton = stmt_skeleton_from_ast(&stmt).expect("compound assignment skeleton");

        let ClangStmtSkeleton::CompoundAssign {
            result_ty,
            compute_lhs_ty,
            compute_result_ty,
            value,
            ..
        } = skeleton
        else {
            panic!("expected promoted compound assignment skeleton, got {skeleton:?}");
        };
        assert!(matches!(
            result_ty.kind,
            ClangTypeKind::Integer {
                signed: false,
                width: 8
            }
        ));
        assert!(matches!(
            compute_lhs_ty.kind,
            ClangTypeKind::Integer {
                signed: true,
                width: 32
            }
        ));
        assert_eq!(compute_lhs_ty, compute_result_ty);
        assert_lvalue_to_rvalue_decl_ref(&value, "y", true, 32);
    }

    #[test]
    fn stmt_skeleton_from_ast_accepts_inc_dec_statement_as_assignment() {
        for (case_name, opcode, is_postfix, expected_op) in [
            ("postfix increment", "++", true, ClangBinaryOperator::Add),
            ("prefix increment", "++", false, ClangBinaryOperator::Add),
            ("postfix decrement", "--", true, ClangBinaryOperator::Sub),
            ("prefix decrement", "--", false, ClangBinaryOperator::Sub),
        ] {
            let stmt = serde_json::json!({
                "kind": "UnaryOperator",
                "opcode": opcode,
                "isPostfix": is_postfix,
                "type": { "qualType": "int" },
                "inner": [
                    {
                        "kind": "DeclRefExpr",
                        "type": { "qualType": "int" },
                        "referencedDecl": { "name": "value" }
                    }
                ]
            });

            let skeleton = stmt_skeleton_from_ast(&stmt).expect(case_name);
            let ClangStmtSkeleton::Assign { target, value } = skeleton else {
                panic!("{case_name}: expected assignment statement, got {skeleton:?}");
            };
            assert!(matches!(target, ClangExprSkeleton::DeclRef { name, .. } if name == "value"));
            let ClangExprSkeleton::Binary { op, lhs, rhs, .. } = value else {
                panic!("{case_name}: expected binary assignment value, got {value:?}");
            };
            assert_eq!(op, expected_op);
            assert!(
                matches!(lhs.as_ref(), ClangExprSkeleton::DeclRef { name, .. } if name == "value")
            );
            assert!(matches!(
                rhs.as_ref(),
                ClangExprSkeleton::IntegerLiteral { value: 1, .. }
            ));
        }
    }

    #[test]
    fn stmt_skeleton_from_ast_accepts_record_field_inc_dec_statement_as_assignment() {
        let stmt = serde_json::json!({
            "kind": "UnaryOperator",
            "opcode": "++",
            "isPostfix": true,
            "type": { "qualType": "int" },
            "inner": [
                {
                    "kind": "MemberExpr",
                    "name": "x",
                    "isArrow": false,
                    "type": { "qualType": "int" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "struct point" },
                            "referencedDecl": { "name": "p" }
                        }
                    ]
                }
            ]
        });

        let skeleton = stmt_skeleton_from_ast(&stmt).expect("record field inc/dec skeleton");

        let ClangStmtSkeleton::Assign { target, value } = skeleton else {
            panic!("expected record field inc/dec assignment, got {skeleton:?}");
        };
        assert!(
            matches!(&target, ClangExprSkeleton::Member { field, is_arrow: false, .. } if field == "x"),
            "expected dot-field assignment target, got {target:?}"
        );
        let ClangExprSkeleton::Binary { op, lhs, rhs, .. } = value else {
            panic!("expected binary assignment value, got {value:?}");
        };
        assert_eq!(op, ClangBinaryOperator::Add);
        assert!(
            matches!(lhs.as_ref(), ClangExprSkeleton::Member { field, is_arrow: false, .. } if field == "x"),
            "expected dot-field binary lhs, got {lhs:?}"
        );
        assert!(matches!(
            rhs.as_ref(),
            ClangExprSkeleton::IntegerLiteral { value: 1, .. }
        ));
    }

    #[test]
    fn stmt_skeleton_from_ast_accepts_mutable_record_pointer_field_inc_dec_statement_as_assignment()
    {
        let stmt = serde_json::json!({
            "kind": "UnaryOperator",
            "opcode": "++",
            "isPostfix": true,
            "type": { "qualType": "int" },
            "inner": [
                {
                    "kind": "MemberExpr",
                    "name": "x",
                    "isArrow": true,
                    "type": { "qualType": "int" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "struct point *" },
                            "referencedDecl": { "name": "p" }
                        }
                    ]
                }
            ]
        });

        let skeleton = stmt_skeleton_from_ast(&stmt).expect("record arrow inc/dec skeleton");

        let ClangStmtSkeleton::Assign { target, value } = skeleton else {
            panic!("expected arrow field inc/dec assignment, got {skeleton:?}");
        };
        assert!(
            matches!(&target, ClangExprSkeleton::Member { field, is_arrow: true, .. } if field == "x"),
            "expected arrow-field assignment target, got {target:?}"
        );
        let ClangExprSkeleton::Binary { op, lhs, rhs, .. } = value else {
            panic!("expected binary assignment value, got {value:?}");
        };
        assert_eq!(op, ClangBinaryOperator::Add);
        assert!(
            matches!(lhs.as_ref(), ClangExprSkeleton::Member { field, is_arrow: true, .. } if field == "x"),
            "expected arrow-field binary lhs, got {lhs:?}"
        );
        assert!(matches!(
            rhs.as_ref(),
            ClangExprSkeleton::IntegerLiteral { value: 1, .. }
        ));
    }

    #[test]
    fn stmt_skeleton_from_ast_rejects_const_record_pointer_field_inc_dec_statement() {
        let stmt = serde_json::json!({
            "kind": "UnaryOperator",
            "opcode": "++",
            "isPostfix": true,
            "type": { "qualType": "int" },
            "inner": [
                {
                    "kind": "MemberExpr",
                    "name": "x",
                    "isArrow": true,
                    "type": { "qualType": "int" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "const struct point *" },
                            "referencedDecl": { "name": "p" }
                        }
                    ]
                }
            ]
        });

        let skeleton = stmt_skeleton_from_ast(&stmt).expect("const arrow inc/dec skeleton");

        let ClangStmtSkeleton::Unsupported { reason } = skeleton else {
            panic!("expected const arrow field inc/dec to be unsupported, got {skeleton:?}");
        };
        assert!(reason.contains("non-const record pointer variable"));
    }

    #[test]
    fn for_step_stmt_skeleton_from_ast_accepts_record_field_inc_dec_step_as_assignment() {
        let stmt = serde_json::json!({
            "kind": "UnaryOperator",
            "opcode": "++",
            "isPostfix": true,
            "type": { "qualType": "int" },
            "inner": [
                {
                    "kind": "MemberExpr",
                    "name": "x",
                    "isArrow": false,
                    "type": { "qualType": "int" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "struct point" },
                            "referencedDecl": { "name": "p" }
                        }
                    ]
                }
            ]
        });

        let skeleton = inc_dec_for_step_skeleton_from_ast(&stmt).expect("record field for step");

        let ClangStmtSkeleton::Assign { target, value } = skeleton else {
            panic!("expected record field inc/dec for step assignment, got {skeleton:?}");
        };
        assert!(
            matches!(&target, ClangExprSkeleton::Member { field, is_arrow: false, .. } if field == "x"),
            "expected dot-field step assignment target, got {target:?}"
        );
        let ClangExprSkeleton::Binary { op, lhs, rhs, .. } = value else {
            panic!("expected binary step assignment value, got {value:?}");
        };
        assert_eq!(op, ClangBinaryOperator::Add);
        assert!(
            matches!(lhs.as_ref(), ClangExprSkeleton::Member { field, is_arrow: false, .. } if field == "x"),
            "expected dot-field binary lhs, got {lhs:?}"
        );
        assert!(matches!(
            rhs.as_ref(),
            ClangExprSkeleton::IntegerLiteral { value: 1, .. }
        ));
    }

    #[test]
    fn for_step_stmt_skeleton_from_ast_accepts_record_pointer_field_inc_dec_step_as_assignment() {
        let stmt = serde_json::json!({
            "kind": "UnaryOperator",
            "opcode": "++",
            "isPostfix": true,
            "type": { "qualType": "int" },
            "inner": [
                {
                    "kind": "MemberExpr",
                    "name": "x",
                    "isArrow": true,
                    "type": { "qualType": "int" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "struct point *" },
                            "referencedDecl": { "name": "p" }
                        }
                    ]
                }
            ]
        });

        let skeleton =
            inc_dec_for_step_skeleton_from_ast(&stmt).expect("record pointer field for step");

        let ClangStmtSkeleton::Assign { target, value } = skeleton else {
            panic!(
                "expected record pointer field inc/dec for step assignment, got {skeleton:?}"
            );
        };
        assert!(
            matches!(&target, ClangExprSkeleton::Member { field, is_arrow: true, .. } if field == "x"),
            "expected arrow-field step assignment target, got {target:?}"
        );
        let ClangExprSkeleton::Binary { op, lhs, rhs, .. } = value else {
            panic!("expected binary step assignment value, got {value:?}");
        };
        assert_eq!(op, ClangBinaryOperator::Add);
        assert!(
            matches!(lhs.as_ref(), ClangExprSkeleton::Member { field, is_arrow: true, .. } if field == "x"),
            "expected arrow-field binary lhs, got {lhs:?}"
        );
        assert!(matches!(
            rhs.as_ref(),
            ClangExprSkeleton::IntegerLiteral { value: 1, .. }
        ));
    }

    #[test]
    fn for_step_stmt_skeleton_from_ast_rejects_const_record_pointer_field_inc_dec_step() {
        let stmt = serde_json::json!({
            "kind": "UnaryOperator",
            "opcode": "++",
            "isPostfix": true,
            "type": { "qualType": "int" },
            "inner": [
                {
                    "kind": "MemberExpr",
                    "name": "x",
                    "isArrow": true,
                    "type": { "qualType": "int" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "const struct point *" },
                            "referencedDecl": { "name": "p" }
                        }
                    ]
                }
            ]
        });

        let skeleton =
            inc_dec_for_step_skeleton_from_ast(&stmt).expect("const record pointer field for step");

        let ClangStmtSkeleton::Unsupported { reason } = skeleton else {
            panic!("expected const record pointer field inc/dec step to be unsupported, got {skeleton:?}");
        };
        assert!(reason.contains("non-const record pointer variable"));
    }

    #[test]
    fn stmt_skeleton_from_ast_rejects_record_field_inc_dec_nested_base() {
        let stmt = serde_json::json!({
            "kind": "UnaryOperator",
            "opcode": "++",
            "isPostfix": true,
            "type": { "qualType": "int" },
            "inner": [
                {
                    "kind": "MemberExpr",
                    "name": "x",
                    "isArrow": false,
                    "type": { "qualType": "int" },
                    "inner": [
                        {
                            "kind": "MemberExpr",
                            "name": "inner",
                            "isArrow": false,
                            "type": { "qualType": "struct inner" },
                            "inner": [
                                {
                                    "kind": "DeclRefExpr",
                                    "type": { "qualType": "struct outer" },
                                    "referencedDecl": { "name": "p" }
                                }
                            ]
                        }
                    ]
                }
            ]
        });

        let skeleton = stmt_skeleton_from_ast(&stmt).expect("nested record field inc/dec");

        let ClangStmtSkeleton::Unsupported { reason } = skeleton else {
            panic!("expected nested record field inc/dec to be unsupported, got {skeleton:?}");
        };
        assert!(reason.contains("must have a direct record variable base"));
    }

    #[test]
    fn stmt_skeleton_from_ast_rejects_compound_assignment_compute_type_mismatch() {
        let stmt = serde_json::json!({
            "kind": "CompoundAssignOperator",
            "opcode": "+=",
            "type": { "qualType": "unsigned char" },
            "computeLHSType": { "qualType": "int" },
            "computeResultType": { "qualType": "unsigned int" },
            "inner": [
                {
                    "kind": "DeclRefExpr",
                    "type": { "qualType": "unsigned char" },
                    "referencedDecl": {
                        "kind": "ParmVarDecl",
                        "name": "x"
                    }
                },
                {
                    "kind": "IntegerLiteral",
                    "type": { "qualType": "int" },
                    "value": "1"
                }
            ]
        });

        let skeleton = stmt_skeleton_from_ast(&stmt).expect("compound assignment skeleton");

        let ClangStmtSkeleton::Unsupported { reason } = skeleton else {
            panic!("expected compute-type mismatch to be unsupported, got {skeleton:?}");
        };
        assert!(reason.contains("compound assignment integer promotion types are unsupported"));
    }

    #[test]
    fn expr_skeleton_from_ast_lowers_function_pointer_direct_call_expr() {
        let expr = serde_json::json!({
            "kind": "CallExpr",
            "type": { "qualType": "int" },
            "inner": [
                {
                    "kind": "ImplicitCastExpr",
                    "castKind": "FunctionToPointerDecay",
                    "type": { "qualType": "int (*)(int)" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "int (*)(int)" },
                            "referencedDecl": {
                                "kind": "ParmVarDecl",
                                "name": "fp"
                            }
                        }
                    ]
                },
                {
                    "kind": "ImplicitCastExpr",
                    "castKind": "LValueToRValue",
                    "type": { "qualType": "int" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "int" },
                            "referencedDecl": { "name": "value" }
                        }
                    ]
                }
            ]
        });

        let skeleton = expr_skeleton_from_ast(&expr).expect("function pointer call skeleton");
        let lowered =
            lower_expr(&skeleton).expect("function pointer direct call should lower to IR call");

        let IrExpr::Call {
            callee, args, ty, ..
        } = lowered
        else {
            panic!("expected function pointer direct call IR, got {lowered:?}");
        };
        assert_eq!(callee, "fp");
        assert_eq!(ty.spelled, "int");
        assert_eq!(args.len(), 1);
        assert!(matches!(args[0], IrExpr::LValueToRValue { .. }));
    }

    #[test]
    fn expr_skeleton_from_ast_preserves_function_to_pointer_decay_as_explicit_ir() {
        let expr = serde_json::json!({
            "kind": "ImplicitCastExpr",
            "castKind": "FunctionToPointerDecay",
            "type": { "qualType": "int (*)(int)" },
            "inner": [
                {
                    "kind": "DeclRefExpr",
                    "type": { "qualType": "int (int)" },
                    "referencedDecl": {
                        "kind": "FunctionDecl",
                        "name": "helper"
                    }
                }
            ]
        });

        let skeleton =
            expr_skeleton_from_ast(&expr).expect("function-to-pointer decay value skeleton");

        let lowered =
            lower_expr(&skeleton).expect("function-to-pointer decay should lower to explicit IR");
        let lowered_json =
            serde_json::to_value(&lowered).expect("serialize function-to-pointer decay IR");
        let Some(decay) = lowered_json.get("FunctionToPointerDecay") else {
            panic!("expected FunctionToPointerDecay IR node, got {lowered_json}");
        };
        assert_eq!(decay["target"]["spelled"], "int (*)(int)");
        assert_eq!(decay["expr"]["Var"]["name"], "helper");
    }
