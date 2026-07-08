    #[test]
    fn expr_skeleton_from_ast_lowers_single_prefix_inc_dec_call_argument() {
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
                            "type": { "qualType": "int (int)" },
                            "referencedDecl": {
                                "kind": "FunctionDecl",
                                "name": "helper"
                            }
                        }
                    ]
                },
                {
                    "kind": "UnaryOperator",
                    "opcode": "++",
                    "isPostfix": false,
                    "type": { "qualType": "int" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "int" },
                            "referencedDecl": { "name": "i" }
                        }
                    ]
                }
            ]
        });

        let skeleton = expr_skeleton_from_ast(&expr).expect("call skeleton");

        let ClangExprSkeleton::Call { args, .. } = skeleton else {
            panic!("expected single prefix inc/dec call argument to lower, got {skeleton:?}");
        };
        let [ClangExprSkeleton::IncDec {
            target,
            prefix: true,
            ..
        }] = args.as_slice()
        else {
            panic!("expected one prefix inc/dec argument, got {args:?}");
        };
        assert!(
            matches!(target.as_ref(), ClangExprSkeleton::DeclRef { name, .. } if name == "i"),
            "unexpected target: {target:?}"
        );
    }

    #[test]
    fn expr_skeleton_from_ast_lowers_single_postfix_inc_dec_call_argument() {
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
                            "type": { "qualType": "int (int)" },
                            "referencedDecl": {
                                "kind": "FunctionDecl",
                                "name": "helper"
                            }
                        }
                    ]
                },
                {
                    "kind": "UnaryOperator",
                    "opcode": "++",
                    "isPostfix": true,
                    "type": { "qualType": "int" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "int" },
                            "referencedDecl": { "name": "i" }
                        }
                    ]
                }
            ]
        });

        let skeleton = expr_skeleton_from_ast(&expr).expect("call skeleton");

        let ClangExprSkeleton::Call { args, .. } = skeleton else {
            panic!("expected single postfix inc/dec call argument to lower, got {skeleton:?}");
        };
        let [ClangExprSkeleton::IncDec {
            target,
            prefix: false,
            ..
        }] = args.as_slice()
        else {
            panic!("expected one postfix inc/dec argument, got {args:?}");
        };
        assert!(
            matches!(target.as_ref(), ClangExprSkeleton::DeclRef { name, .. } if name == "i"),
            "unexpected target: {target:?}"
        );
    }

    #[test]
    fn expr_skeleton_from_ast_keeps_prefix_inc_dec_deref_operand_fail_closed() {
        let expr = serde_json::json!({
            "kind": "UnaryOperator",
            "opcode": "*",
            "type": { "qualType": "int" },
            "inner": [
                {
                    "kind": "UnaryOperator",
                    "opcode": "++",
                    "isPostfix": false,
                    "type": { "qualType": "int *" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "int *" },
                            "referencedDecl": { "name": "p" }
                        }
                    ]
                }
            ]
        });

        let skeleton = expr_skeleton_from_ast(&expr).expect("deref skeleton");

        let ClangExprSkeleton::Unsupported { reason, .. } = skeleton else {
            panic!("expected prefix inc/dec deref operand to fail closed, got {skeleton:?}");
        };
        assert!(
            reason.contains("deref pointer cannot use prefix increment/decrement value semantics"),
            "unexpected reason: {reason}"
        );
    }

    #[test]
    fn for_step_stmt_skeleton_from_ast_rejects_prefix_inc_dec_non_scalar_targets() {
        let cases = [
            (
                "prefix deref target",
                serde_json::json!({
                    "kind": "UnaryOperator",
                    "opcode": "++",
                    "isPostfix": false,
                    "type": { "qualType": "int" },
                    "inner": [
                        {
                            "kind": "UnaryOperator",
                            "opcode": "*",
                            "type": { "qualType": "int" },
                            "inner": [
                                {
                                    "kind": "DeclRefExpr",
                                    "type": { "qualType": "int *" },
                                    "referencedDecl": { "name": "p" }
                                }
                            ]
                        }
                    ]
                }),
                "simple variable",
            ),
            (
                "prefix pointer target",
                serde_json::json!({
                    "kind": "UnaryOperator",
                    "opcode": "++",
                    "isPostfix": false,
                    "type": { "qualType": "int *" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "int *" },
                            "referencedDecl": { "name": "p" }
                        }
                    ]
                }),
                "unsupported",
            ),
        ];

        for (label, stmt, expected_reason) in cases {
            let skeleton = for_step_stmt_skeleton_from_ast(&stmt).expect(label);

            let ClangStmtSkeleton::Unsupported { reason } = skeleton else {
                panic!("expected unsupported {label}, got {skeleton:?}");
            };
            assert!(
                reason.contains(expected_reason),
                "unexpected reason for {label}: {reason}"
            );
        }
    }

    #[test]
    fn for_step_stmt_skeleton_from_ast_rejects_inc_dec_without_explicit_bool_postfix_flag() {
        let cases = [
            (
                "missing postfix flag",
                serde_json::json!({
                    "kind": "UnaryOperator",
                    "opcode": "++",
                    "type": { "qualType": "int" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "int" },
                            "referencedDecl": { "name": "i" }
                        }
                    ]
                }),
            ),
            (
                "string postfix flag",
                serde_json::json!({
                    "kind": "UnaryOperator",
                    "opcode": "++",
                    "isPostfix": "false",
                    "type": { "qualType": "int" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "int" },
                            "referencedDecl": { "name": "i" }
                        }
                    ]
                }),
            ),
        ];

        for (label, stmt) in cases {
            let skeleton = for_step_stmt_skeleton_from_ast(&stmt).expect(label);

            let ClangStmtSkeleton::Unsupported { reason } = skeleton else {
                panic!("expected unsupported {label}, got {skeleton:?}");
            };
            assert!(
                reason.contains("explicit isPostfix flag"),
                "unexpected reason for {label}: {reason}"
            );
        }
    }

    #[test]
    fn type_from_qual_type_maps_fixed_width_integer_scalars() {
        let cases = [
            ("int8_t", "int8_t", true, 8),
            ("int16_t", "int16_t", true, 16),
            ("uint16_t", "uint16_t", false, 16),
            ("int32_t", "int32_t", true, 32),
            ("int64_t", "int64_t", true, 64),
            ("uint64_t", "uint64_t", false, 64),
        ];

        for (spelling, expected_canonical, expected_signed, expected_width) in cases {
            let ty = type_from_qual_type(spelling).expect("fixed-width integer type");

            assert_eq!(ty.spelled, spelling);
            assert_eq!(ty.canonical, expected_canonical);
            assert!(matches!(
                &ty.kind,
                ClangTypeKind::Integer { signed, width }
                    if *signed == expected_signed && *width == expected_width
            ));
        }
    }

    #[test]
    fn type_from_ast_type_object_keeps_supported_qual_type_before_fallbacks() {
        let type_object = serde_json::json!({
            "qualType": "uint32_t",
            "desugaredQualType": "unsigned int",
            "canonicalQualType": "unsigned int"
        });

        let ty = type_from_ast_type_object(&type_object, None).expect("type skeleton");

        assert_eq!(ty.spelled, "uint32_t");
        assert_eq!(ty.canonical, "uint32_t");
        assert!(matches!(
            ty.kind,
            ClangTypeKind::Integer {
                signed: false,
                width: 32
            }
        ));
    }

    #[test]
    fn type_from_ast_type_object_falls_back_to_desugared_qual_type() {
        let type_object = serde_json::json!({
            "qualType": "fdb_blob_t",
            "desugaredQualType": "struct fdb_blob *",
            "canonicalQualType": "struct fdb_blob *"
        });

        let ty = type_from_ast_type_object(&type_object, None).expect("type skeleton");

        assert_eq!(ty.spelled, "struct fdb_blob *");
        assert_eq!(ty.canonical, "struct fdb_blob *");
        assert!(matches!(ty.kind, ClangTypeKind::Pointer { .. }));
    }

    #[test]
    fn type_from_qual_type_rejects_multi_dimensional_array_before_dimension_reorder() {
        let err =
            type_from_qual_type("int[2][3]").expect_err("multi-dimensional array must fail closed");

        assert_eq!(err.kind, "invalid_array_type");
        assert!(err.message.contains("multi-dimensional array"));
        assert!(err.message.contains("int[2][3]"));
    }

    #[test]
    fn type_from_ast_type_object_rejects_fixed_width_typedef_desugared_width_mismatch() {
        let abi = TargetAbiProfile {
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
        let type_object = serde_json::json!({
            "qualType": "uint32_t",
            "desugaredQualType": "unsigned long",
            "canonicalQualType": "unsigned long"
        });

        let err = type_from_ast_type_object(&type_object, Some(&abi))
            .expect_err("mismatched fixed-width typedef desugaring must fail closed");

        assert_eq!(err.kind, "fixed_width_typedef_desugaring_mismatch");
        assert!(err.message.contains("uint32_t"));
        assert!(err.message.contains("desugaredQualType"));
        assert!(err.message.contains("unsigned long"));
        assert!(err.message.contains("32"));
        assert!(err.message.contains("64"));
    }

    #[test]
    fn type_from_ast_type_object_defers_target_dependent_fixed_width_desugaring_without_abi() {
        let type_object = serde_json::json!({
            "qualType": "uint64_t",
            "desugaredQualType": "unsigned long",
            "canonicalQualType": "unsigned long"
        });

        let ty = type_from_ast_type_object(&type_object, None)
            .expect("target-dependent fixed-width typedef desugaring should wait for ABI proof");

        assert_eq!(ty.spelled, "uint64_t");
        assert_eq!(ty.canonical, "uint64_t");
        assert!(matches!(
            ty.kind,
            ClangTypeKind::Integer {
                signed: false,
                width: 64
            }
        ));
    }

    #[test]
    fn function_return_type_from_type_object_falls_back_to_desugared_signature() {
        let type_object = serde_json::json!({
            "qualType": "fdb_blob_t (fdb_blob_t)",
            "desugaredQualType": "struct fdb_blob *(struct fdb_blob *)",
            "canonicalQualType": "struct fdb_blob *(struct fdb_blob *)"
        });

        let ty = function_return_type_from_type_object(&type_object).expect("return type");

        assert_eq!(ty.spelled, "struct fdb_blob *");
        assert!(matches!(ty.kind, ClangTypeKind::Pointer { .. }));
    }

    #[test]
    fn function_return_type_from_type_object_allows_function_pointer_parameter() {
        let type_object = serde_json::json!({
            "qualType": "int (int (*)(int), int)"
        });

        let ty = function_return_type_from_type_object(&type_object).expect(
            "function pointer parameter should not be mistaken for function pointer return",
        );

        assert_eq!(ty.spelled, "int");
        assert!(matches!(
            ty.kind,
            ClangTypeKind::Integer {
                signed: true,
                width: 32
            }
        ));
    }

    #[test]
    fn function_return_type_from_type_object_allows_simple_function_pointer_return() {
        let type_object = serde_json::json!({
            "qualType": "int (*(void))(int)"
        });

        let ty = function_return_type_from_type_object(&type_object)
            .expect("simple function pointer return should lower");

        assert_eq!(ty.spelled, "int (*)(int)");
        assert!(matches!(ty.kind, ClangTypeKind::Pointer { .. }));
    }

    #[test]
    fn type_from_qual_type_maps_signed_char_scalar() {
        let ty = type_from_qual_type("signed char").expect("signed char type");

        assert_eq!(ty.spelled, "signed char");
        assert_eq!(ty.canonical, "signed char");
        assert!(matches!(
            ty.kind,
            ClangTypeKind::Integer {
                signed: true,
                width: 8
            }
        ));
    }

    #[test]
    fn type_from_qual_type_keeps_target_dependent_integer_spellings_unsupported() {
        for spelling in [
            "char",
            "short",
            "unsigned short",
            "long",
            "unsigned long",
            "long long",
            "unsigned long long",
            "size_t",
        ] {
            let ty = type_from_qual_type(spelling).expect("type skeleton");

            assert!(matches!(
                ty.kind,
                ClangTypeKind::Unsupported { ref reason }
                    if reason.contains("requires target ABI width provenance")
            ));
        }
    }

    #[test]
    fn type_from_qual_type_with_target_abi_binds_lp64_integer_widths() {
        let abi = TargetAbiProfile {
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

        for (spelling, expected_signed, expected_width) in [
            ("char", true, 8),
            ("short", true, 16),
            ("unsigned short", false, 16),
            ("long", true, 64),
            ("unsigned long", false, 64),
            ("long long", true, 64),
            ("unsigned long long", false, 64),
            ("size_t", false, 64),
        ] {
            let ty =
                type_from_qual_type_with_target_abi(spelling, Some(&abi)).expect("type skeleton");

            assert_eq!(ty.spelled, spelling);
            assert!(matches!(
                ty.kind,
                ClangTypeKind::Integer { signed, width }
                    if signed == expected_signed && width == expected_width
            ));
        }
    }
