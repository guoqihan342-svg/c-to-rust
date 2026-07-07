    #[test]
    fn sizeof_integer_type_lowers_to_profile_bound_size_t_literal() {
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
        let expr = serde_json::json!({
            "kind": "UnaryExprOrTypeTraitExpr",
            "type": {"qualType": "size_t"},
            "valueCategory": "prvalue",
            "name": "sizeof",
            "argType": {"qualType": "int"}
        });

        let mut skeleton =
            expr_skeleton_from_ast(&expr).expect("sizeof integer skeleton should parse");
        bind_target_abi_to_expr(&mut skeleton, &abi);
        let ir = lower_expr(&skeleton).expect("sizeof integer should lower");

        let IrExpr::LitInt { value, ty, .. } = ir else {
            panic!("expected sizeof to lower to LitInt, got {ir:?}");
        };
        assert_eq!(value, 4);
        assert_eq!(ty.spelled, "size_t");
        assert!(matches!(
            ty.kind,
            IrTypeKind::Integer {
                signed: false,
                width: 64
            }
        ));
    }

    #[test]
    fn sizeof_int_lowers_from_target_int_width_profile() {
        let abi = TargetAbiProfile {
            triple_or_abi: "small-int-test-abi".to_string(),
            endianness: Some("little".to_string()),
            int_width: 16,
            char_width: 8,
            plain_char_signed: Some(true),
            short_width: 16,
            long_width: 32,
            long_long_width: 64,
            pointer_width: 64,
            ..TargetAbiProfile::default()
        };
        let expr = serde_json::json!({
            "kind": "UnaryExprOrTypeTraitExpr",
            "type": {"qualType": "size_t"},
            "valueCategory": "prvalue",
            "name": "sizeof",
            "argType": {"qualType": "int"}
        });

        let mut skeleton =
            expr_skeleton_from_ast(&expr).expect("sizeof(int) skeleton should parse");
        bind_target_abi_to_expr(&mut skeleton, &abi);
        let ir = lower_expr(&skeleton).expect("sizeof(int) should lower with ABI profile");

        let IrExpr::LitInt { value, .. } = ir else {
            panic!("expected sizeof(int) to lower to LitInt, got {ir:?}");
        };
        assert_eq!(value, 2);
    }

    #[test]
    fn sizeof_size_t_lowers_from_target_pointer_width_profile() {
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
        let expr = serde_json::json!({
            "kind": "UnaryExprOrTypeTraitExpr",
            "type": {"qualType": "size_t"},
            "valueCategory": "prvalue",
            "name": "sizeof",
            "argType": {"qualType": "size_t"}
        });

        let mut skeleton =
            expr_skeleton_from_ast(&expr).expect("sizeof size_t skeleton should parse");
        bind_target_abi_to_expr(&mut skeleton, &abi);
        let ir = lower_expr(&skeleton).expect("sizeof size_t should lower");

        let IrExpr::LitInt { value, ty, .. } = ir else {
            panic!("expected sizeof(size_t) to lower to LitInt, got {ir:?}");
        };
        assert_eq!(value, 8);
        assert_eq!(ty.spelled, "size_t");
    }

    #[test]
    fn type_from_qual_type_binds_double_underscore_size_t_with_target_profile() {
        let abi = TargetAbiProfile {
            triple_or_abi: "x86_64-pc-windows-msvc".to_string(),
            endianness: Some("little".to_string()),
            int_width: 32,
            char_width: 8,
            plain_char_signed: Some(true),
            short_width: 16,
            long_width: 32,
            long_long_width: 64,
            pointer_width: 64,
            ..TargetAbiProfile::default()
        };

        let ty = type_from_qual_type_with_target_abi("__size_t", Some(&abi))
            .expect("__size_t should parse with target ABI profile");
        assert_eq!(ty.spelled, "__size_t");
        assert!(matches!(
            ty.kind,
            ClangTypeKind::Integer {
                signed: false,
                width: 64
            }
        ));

        let unbound = type_from_qual_type("__size_t").expect("__size_t should parse as unbound");
        assert!(matches!(unbound.kind, ClangTypeKind::Unsupported { .. }));
    }

    #[test]
    fn sizeof_pointer_type_lowers_from_target_pointer_width_profile() {
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
        let expr = serde_json::json!({
            "kind": "UnaryExprOrTypeTraitExpr",
            "type": {"qualType": "size_t"},
            "valueCategory": "prvalue",
            "name": "sizeof",
            "argType": {"qualType": "const int *"}
        });

        let mut skeleton =
            expr_skeleton_from_ast(&expr).expect("sizeof pointer skeleton should parse");
        bind_target_abi_to_expr(&mut skeleton, &abi);
        let ir = lower_expr(&skeleton).expect("sizeof pointer should lower with ABI profile");

        let IrExpr::LitInt { value, ty, .. } = ir else {
            panic!("expected sizeof(pointer) to lower to LitInt, got {ir:?}");
        };
        assert_eq!(value, 8);
        assert_eq!(ty.spelled, "size_t");
    }

    #[test]
    fn sizeof_pointer_type_stays_fail_closed_without_pointer_width_profile() {
        let expr = serde_json::json!({
            "kind": "UnaryExprOrTypeTraitExpr",
            "type": {"qualType": "size_t"},
            "valueCategory": "prvalue",
            "name": "sizeof",
            "argType": {"qualType": "const int *"}
        });

        let skeleton = expr_skeleton_from_ast(&expr).expect("sizeof pointer skeleton should parse");
        let error = lower_expr(&skeleton).expect_err("sizeof pointer requires target profile");

        assert_eq!(error.kind, "unsupported_sizeof_type");
        assert!(
            error.message.contains("pointer-width provenance"),
            "unexpected error: {error:?}"
        );
    }

    #[test]
    fn sizeof_long_lowers_from_target_long_width_profile() {
        for (abi_name, long_width, expected_size) in [
            ("x86_64-unknown-linux-gnu", 64, 8),
            ("x86_64-pc-windows-msvc", 32, 4),
        ] {
            let abi = TargetAbiProfile {
                triple_or_abi: abi_name.to_string(),
                endianness: Some("little".to_string()),
                int_width: 32,
                char_width: 8,
                plain_char_signed: Some(true),
                short_width: 16,
                long_width,
                long_long_width: 64,
                pointer_width: 64,
                ..TargetAbiProfile::default()
            };
            let expr = serde_json::json!({
                "kind": "UnaryExprOrTypeTraitExpr",
                "type": {"qualType": "size_t"},
                "valueCategory": "prvalue",
                "name": "sizeof",
                "argType": {"qualType": "long"}
            });

            let mut skeleton =
                expr_skeleton_from_ast(&expr).expect("sizeof(long) skeleton should parse");
            bind_target_abi_to_expr(&mut skeleton, &abi);
            let ir = lower_expr(&skeleton).expect("sizeof(long) should lower with ABI profile");

            let IrExpr::LitInt { value, ty, .. } = ir else {
                panic!("expected sizeof(long) to lower to LitInt, got {ir:?}");
            };
            assert_eq!(value, expected_size, "{abi_name}");
            assert_eq!(ty.spelled, "size_t");
        }
    }

    #[test]
    fn sizeof_fixed_integer_array_type_lowers_to_total_byte_size() {
        let abi = TargetAbiProfile {
            triple_or_abi: "small-int-test-abi".to_string(),
            endianness: Some("little".to_string()),
            int_width: 16,
            char_width: 8,
            plain_char_signed: Some(true),
            short_width: 16,
            long_width: 32,
            long_long_width: 64,
            pointer_width: 64,
            ..TargetAbiProfile::default()
        };
        let expr = serde_json::json!({
            "kind": "UnaryExprOrTypeTraitExpr",
            "type": {"qualType": "size_t"},
            "valueCategory": "prvalue",
            "name": "sizeof",
            "argType": {"qualType": "int[3]"}
        });

        let mut skeleton =
            expr_skeleton_from_ast(&expr).expect("sizeof(int[3]) skeleton should parse");
        bind_target_abi_to_expr(&mut skeleton, &abi);
        let ir = lower_expr(&skeleton).expect("sizeof(int[3]) should lower with ABI profile");

        let IrExpr::LitInt { value, ty, .. } = ir else {
            panic!("expected sizeof(int[3]) to lower to LitInt, got {ir:?}");
        };
        assert_eq!(value, 6);
        assert_eq!(ty.spelled, "size_t");
    }

    #[test]
    fn sizeof_incomplete_array_type_stays_fail_closed() {
        let expr = serde_json::json!({
            "kind": "UnaryExprOrTypeTraitExpr",
            "type": {"qualType": "size_t"},
            "valueCategory": "prvalue",
            "name": "sizeof",
            "argType": {"qualType": "int[]"}
        });

        let skeleton = expr_skeleton_from_ast(&expr).expect("sizeof(int[]) skeleton should parse");
        let error = lower_expr(&skeleton).expect_err("sizeof incomplete array must fail closed");

        assert_eq!(error.kind, "unsupported_sizeof_type");
        assert!(
            error.message.contains("complete array bound"),
            "unexpected error: {error:?}"
        );
    }

    #[test]
    fn sizeof_vla_like_array_type_stays_fail_closed() {
        let expr = serde_json::json!({
            "kind": "UnaryExprOrTypeTraitExpr",
            "type": {"qualType": "size_t"},
            "valueCategory": "prvalue",
            "name": "sizeof",
            "argType": {"qualType": "int[n]"}
        });

        let error = expr_skeleton_from_ast(&expr).expect_err("VLA-like sizeof must fail closed");

        assert_eq!(error.kind, "invalid_array_type");
        assert!(
            error.message.contains("array length is not usize"),
            "unexpected error: {error:?}"
        );
    }

    #[test]
    fn sizeof_array_result_exceeding_target_size_t_stays_fail_closed() {
        let abi = TargetAbiProfile {
            triple_or_abi: "small-size-t-test-abi".to_string(),
            endianness: Some("little".to_string()),
            int_width: 16,
            char_width: 8,
            plain_char_signed: Some(true),
            short_width: 16,
            long_width: 32,
            long_long_width: 64,
            pointer_width: 16,
            ..TargetAbiProfile::default()
        };
        let expr = serde_json::json!({
            "kind": "UnaryExprOrTypeTraitExpr",
            "type": {"qualType": "size_t"},
            "valueCategory": "prvalue",
            "name": "sizeof",
            "argType": {"qualType": "int[40000]"}
        });

        let mut skeleton =
            expr_skeleton_from_ast(&expr).expect("sizeof(int[40000]) skeleton should parse");
        bind_target_abi_to_expr(&mut skeleton, &abi);
        let error = lower_expr(&skeleton).expect_err("oversized sizeof result must fail closed");

        assert_eq!(error.kind, "unsupported_sizeof_type");
        assert!(
            error.message.contains("does not fit target result type"),
            "unexpected error: {error:?}"
        );
    }

    #[test]
    fn sizeof_target_dependent_integer_stays_fail_closed_without_profile() {
        let expr = serde_json::json!({
            "kind": "UnaryExprOrTypeTraitExpr",
            "type": {"qualType": "size_t"},
            "valueCategory": "prvalue",
            "name": "sizeof",
            "argType": {"qualType": "long"}
        });

        let skeleton = expr_skeleton_from_ast(&expr).expect("sizeof(long) skeleton should parse");
        let error = lower_expr(&skeleton).expect_err("sizeof(long) without ABI must fail closed");

        assert_eq!(error.kind, "unsupported_sizeof_type");
        assert!(
            error
                .message
                .contains("requires target ABI width provenance"),
            "unexpected error: {error:?}"
        );
    }

    #[test]
    fn sizeof_expression_operand_stays_fail_closed_without_arg_type() {
        let expr = serde_json::json!({
            "kind": "UnaryExprOrTypeTraitExpr",
            "type": {"qualType": "size_t"},
            "valueCategory": "prvalue",
            "name": "sizeof",
            "inner": [
                {
                    "kind": "DeclRefExpr",
                    "referencedDecl": {
                        "kind": "VarDecl",
                        "name": "value"
                    },
                    "type": {"qualType": "int"}
                }
            ]
        });

        let error =
            expr_skeleton_from_ast(&expr).expect_err("sizeof expression operand must fail closed");

        assert_eq!(error.kind, "unsupported_sizeof_operand");
        assert!(
            error.message.contains("expression operand"),
            "unexpected error: {error:?}"
        );
    }

    #[test]
    fn sizeof_expression_operand_lowers_with_arg_type_profile() {
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
        let expr = serde_json::json!({
            "kind": "UnaryExprOrTypeTraitExpr",
            "type": {"qualType": "size_t"},
            "valueCategory": "prvalue",
            "name": "sizeof",
            "argType": {"qualType": "int"},
            "inner": [
                {
                    "kind": "DeclRefExpr",
                    "referencedDecl": {
                        "kind": "VarDecl",
                        "name": "value"
                    },
                    "type": {"qualType": "int"}
                }
            ]
        });

        let mut skeleton =
            expr_skeleton_from_ast(&expr).expect("sizeof expression argType should parse");
        bind_target_abi_to_expr(&mut skeleton, &abi);
        let ir = lower_expr(&skeleton).expect("sizeof(value) should lower through argType");

        let IrExpr::LitInt { value, ty, .. } = ir else {
            panic!("expected sizeof(value) to lower to LitInt, got {ir:?}");
        };
        assert_eq!(value, 4);
        assert_eq!(ty.spelled, "size_t");
    }

    #[test]
    fn sizeof_record_type_stays_fail_closed_without_layout_provenance() {
        let expr = serde_json::json!({
            "kind": "UnaryExprOrTypeTraitExpr",
            "type": {"qualType": "size_t"},
            "valueCategory": "prvalue",
            "name": "sizeof",
            "argType": {"qualType": "struct point"}
        });

        let error = expr_skeleton_from_ast(&expr).expect_err("record sizeof must fail closed");

        assert!(
            error.message.contains("sizeof") && error.message.contains("layout"),
            "unexpected error: {error:?}"
        );
    }

    #[test]
    fn alignof_type_trait_lowers_only_with_alignment_profile() {
        let expr = serde_json::json!({
            "kind": "UnaryExprOrTypeTraitExpr",
            "type": {"qualType": "size_t"},
            "valueCategory": "prvalue",
            "name": "_Alignof",
            "argType": {"qualType": "int"}
        });

        let skeleton = expr_skeleton_from_ast(&expr).expect("_Alignof skeleton should parse");
        let ClangExprSkeleton::AlignOfType {
            arg_type,
            alignment_bits,
            ..
        } = &skeleton
        else {
            panic!("expected _Alignof type skeleton, got {skeleton:?}");
        };
        assert_eq!(arg_type.spelled, "int");
        assert_eq!(*alignment_bits, None);

        let error = lower_expr(&skeleton).expect_err("_Alignof must fail closed");
        assert_eq!(error.kind, "unsupported_alignof_type");
        assert!(
            error.message.contains("_Alignof") && error.message.contains("alignment"),
            "unexpected error: {error:?}"
        );

        let mut bound = skeleton.clone();
        let target_abi = TargetAbiProfile {
            triple_or_abi: "x86_64-unknown-linux-gnu".to_string(),
            endianness: Some("little".to_string()),
            int_width: 32,
            int_align: 32,
            long_width: 64,
            pointer_width: 64,
            ..TargetAbiProfile::default()
        };
        bind_target_abi_to_expr(&mut bound, &target_abi);

        let ir = lower_expr(&bound).expect("_Alignof(int) lowers with target alignment profile");
        let IrExpr::LitInt { value, ty, .. } = ir else {
            panic!("expected literal _Alignof result, got {ir:?}");
        };
        assert_eq!(value, 4);
        assert!(matches!(
            ty.kind,
            IrTypeKind::Integer {
                signed: false,
                width: 64
            }
        ));
    }

    #[test]
    fn type_from_qual_type_maps_fixed_array() {
        let ty = type_from_qual_type("uint32_t[256]").expect("array type");

        assert_eq!(ty.spelled, "uint32_t[256]");
        assert_eq!(ty.canonical, "uint32_t[256]");
        let ClangTypeKind::Array { element, len } = ty.kind else {
            panic!("expected array type, got {:?}", ty.kind);
        };
        assert_eq!(len, Some(256));
        assert!(matches!(
            element.kind,
            ClangTypeKind::Integer {
                signed: false,
                width: 32
            }
        ));
    }

    #[test]
    fn type_from_qual_type_maps_const_fixed_array() {
        let ty = type_from_qual_type("const uint32_t[256]").expect("const array type");

        assert_eq!(ty.spelled, "const uint32_t[256]");
        assert_eq!(ty.canonical, "uint32_t[256]");
        assert!(clang_type_is_const(&ty));
        let ClangTypeKind::Array { element, len } = ty.kind else {
            panic!("expected array type, got {:?}", ty.kind);
        };
        assert_eq!(len, Some(256));
        assert!(matches!(
            element.kind,
            ClangTypeKind::Integer {
                signed: false,
                width: 32
            }
        ));
    }

    #[test]
    fn type_from_qual_type_maps_incomplete_array() {
        let ty = type_from_qual_type("uint32_t[]").expect("incomplete array type");

        assert_eq!(ty.spelled, "uint32_t[]");
        assert_eq!(ty.canonical, "uint32_t[]");
        let ClangTypeKind::Array { element, len } = ty.kind else {
            panic!("expected array type, got {:?}", ty.kind);
        };
        assert_eq!(len, None);
        assert!(matches!(
            element.kind,
            ClangTypeKind::Integer {
                signed: false,
                width: 32
            }
        ));
    }

    #[test]
    fn readonly_globals_from_ast_maps_static_const_integer_array_initializer() {
        let ast = serde_json::json!({
            "kind": "TranslationUnitDecl",
            "inner": [
                {
                    "kind": "VarDecl",
                    "name": "table",
                    "storageClass": "static",
                    "type": { "qualType": "const uint32_t[4]" },
                    "init": "c",
                    "inner": [
                        {
                            "kind": "InitListExpr",
                            "type": { "qualType": "const uint32_t[4]" },
                            "inner": [
                                {
                                    "kind": "ImplicitCastExpr",
                                    "castKind": "IntegralCast",
                                    "type": { "qualType": "uint32_t" },
                                    "inner": [
                                        {
                                            "kind": "IntegerLiteral",
                                            "type": { "qualType": "int" },
                                            "value": "1"
                                        }
                                    ]
                                },
                                {
                                    "kind": "IntegerLiteral",
                                    "type": { "qualType": "unsigned int" },
                                    "value": "2"
                                },
                                {
                                    "kind": "IntegerLiteral",
                                    "type": { "qualType": "unsigned int" },
                                    "value": "3988292384"
                                },
                                {
                                    "kind": "IntegerLiteral",
                                    "type": { "qualType": "unsigned int" },
                                    "value": "4"
                                }
                            ]
                        }
                    ]
                }
            ]
        });

        let globals = readonly_globals_from_ast(&ast).expect("readonly globals");

        assert_eq!(globals.len(), 1);
        let global = &globals[0];
        assert_eq!(global.name, "table");
        assert!(global.ty.is_const);
        assert!(matches!(
            global.ty.kind,
            IrTypeKind::Array { len: Some(4), .. }
        ));
        assert_eq!(
            global.init,
            IrGlobalInit::IntegerArray(vec![1, 2, 0xEDB8_8320, 4])
        );
    }

    #[test]
    fn readonly_globals_from_ast_maps_static_const_sparse_array_filler_initializer() {
        let ast = serde_json::json!({
            "kind": "TranslationUnitDecl",
            "inner": [
                {
                    "kind": "VarDecl",
                    "name": "table",
                    "storageClass": "static",
                    "type": { "qualType": "const int[3]" },
                    "init": "c",
                    "inner": [
                        {
                            "kind": "InitListExpr",
                            "type": { "qualType": "const int[3]" },
                            "array_filler": [
                                {
                                    "kind": "ImplicitValueInitExpr",
                                    "type": { "qualType": "const int" }
                                },
                                {
                                    "kind": "ImplicitValueInitExpr",
                                    "type": { "qualType": "const int" }
                                },
                                {
                                    "kind": "IntegerLiteral",
                                    "type": { "qualType": "int" },
                                    "value": "7"
                                }
                            ]
                        }
                    ]
                }
            ]
        });

        let globals = readonly_globals_from_ast(&ast).expect("readonly globals");

        assert_eq!(globals.len(), 1);
        let global = &globals[0];
        assert_eq!(global.name, "table");
        assert!(global.ty.is_const);
        assert!(matches!(
            global.ty.kind,
            IrTypeKind::Array { len: Some(3), .. }
        ));
        assert_eq!(global.init, IrGlobalInit::IntegerArray(vec![0, 7, 0]));
    }

    #[test]
    fn readonly_globals_from_ast_maps_static_const_all_zero_array_filler_initializer() {
        let ast = serde_json::json!({
            "kind": "TranslationUnitDecl",
            "inner": [
                {
                    "kind": "VarDecl",
                    "name": "table",
                    "storageClass": "static",
                    "type": { "qualType": "const int[3]" },
                    "init": "c",
                    "inner": [
                        {
                            "kind": "InitListExpr",
                            "type": { "qualType": "const int[3]" },
                            "array_filler": [
                                {
                                    "kind": "ImplicitValueInitExpr",
                                    "type": { "qualType": "const int" }
                                }
                            ]
                        }
                    ]
                }
            ]
        });

        let globals = readonly_globals_from_ast(&ast).expect("readonly globals");

        assert_eq!(globals.len(), 1);
        assert_eq!(globals[0].name, "table");
        assert_eq!(globals[0].init, IrGlobalInit::IntegerArray(vec![0, 0, 0]));
    }

    #[test]
    fn readonly_globals_from_ast_rejects_malformed_static_const_array_filler_initializer() {
        let ast = serde_json::json!({
            "kind": "TranslationUnitDecl",
            "inner": [
                {
                    "kind": "VarDecl",
                    "name": "bad_filler_sentinel",
                    "storageClass": "static",
                    "type": { "qualType": "const int[3]" },
                    "init": "c",
                    "inner": [
                        {
                            "kind": "InitListExpr",
                            "type": { "qualType": "const int[3]" },
                            "array_filler": [
                                {
                                    "kind": "IntegerLiteral",
                                    "type": { "qualType": "int" },
                                    "value": "0"
                                }
                            ]
                        }
                    ]
                },
                {
                    "kind": "VarDecl",
                    "name": "bad_filler_length",
                    "storageClass": "static",
                    "type": { "qualType": "const int[3]" },
                    "init": "c",
                    "inner": [
                        {
                            "kind": "InitListExpr",
                            "type": { "qualType": "const int[3]" },
                            "array_filler": [
                                {
                                    "kind": "ImplicitValueInitExpr",
                                    "type": { "qualType": "const int" }
                                },
                                {
                                    "kind": "IntegerLiteral",
                                    "type": { "qualType": "int" },
                                    "value": "1"
                                },
                                {
                                    "kind": "IntegerLiteral",
                                    "type": { "qualType": "int" },
                                    "value": "2"
                                },
                                {
                                    "kind": "IntegerLiteral",
                                    "type": { "qualType": "int" },
                                    "value": "3"
                                },
                                {
                                    "kind": "IntegerLiteral",
                                    "type": { "qualType": "int" },
                                    "value": "4"
                                }
                            ]
                        }
                    ]
                },
                {
                    "kind": "VarDecl",
                    "name": "bad_filler_side_effect",
                    "storageClass": "static",
                    "type": { "qualType": "const int[3]" },
                    "init": "c",
                    "inner": [
                        {
                            "kind": "InitListExpr",
                            "type": { "qualType": "const int[3]" },
                            "array_filler": [
                                {
                                    "kind": "ImplicitValueInitExpr",
                                    "type": { "qualType": "const int" }
                                },
                                {
                                    "kind": "CallExpr",
                                    "type": { "qualType": "int" }
                                }
                            ]
                        }
                    ]
                }
            ]
        });

        let globals = readonly_globals_from_ast(&ast).expect("readonly globals");

        assert!(
            globals.is_empty(),
            "malformed array_filler globals must stay fail-closed: {globals:?}"
        );
    }

    #[test]
    fn readonly_globals_from_ast_maps_static_const_integer_array_enum_constant_initializer() {
        let ast = serde_json::json!({
            "kind": "TranslationUnitDecl",
            "inner": [
                {
                    "kind": "EnumDecl",
                    "name": "status",
                    "completeDefinition": true,
                    "inner": [
                        {
                            "id": "0x1001",
                            "kind": "EnumConstantDecl",
                            "name": "STATUS_OK",
                            "type": { "qualType": "int" },
                            "inner": [
                                {
                                    "kind": "ConstantExpr",
                                    "type": { "qualType": "int" },
                                    "value": "7",
                                    "inner": [
                                        {
                                            "kind": "IntegerLiteral",
                                            "type": { "qualType": "int" },
                                            "value": "7"
                                        }
                                    ]
                                }
                            ]
                        }
                    ]
                },
                {
                    "kind": "VarDecl",
                    "name": "table",
                    "storageClass": "static",
                    "type": { "qualType": "const int[2]" },
                    "init": "c",
                    "inner": [
                        {
                            "kind": "InitListExpr",
                            "type": { "qualType": "const int[2]" },
                            "inner": [
                                {
                                    "kind": "DeclRefExpr",
                                    "type": { "qualType": "int" },
                                    "referencedDecl": {
                                        "id": "0x1001",
                                        "kind": "EnumConstantDecl",
                                        "name": "STATUS_OK"
                                    }
                                },
                                {
                                    "kind": "IntegerLiteral",
                                    "type": { "qualType": "int" },
                                    "value": "0"
                                }
                            ]
                        }
                    ]
                }
            ]
        });

        let globals = readonly_globals_from_ast(&ast).expect("readonly globals");

        assert_eq!(globals.len(), 1);
        assert_eq!(globals[0].name, "table");
        assert_eq!(globals[0].init, IrGlobalInit::IntegerArray(vec![7, 0]));
    }

    #[test]
    fn readonly_globals_from_ast_rejects_implicit_enum_constant_initializer() {
        let ast = serde_json::json!({
            "kind": "TranslationUnitDecl",
            "inner": [
                {
                    "kind": "EnumDecl",
                    "name": "status",
                    "completeDefinition": true,
                    "inner": [
                        {
                            "id": "0x1001",
                            "kind": "EnumConstantDecl",
                            "name": "STATUS_PENDING",
                            "type": { "qualType": "int" }
                        }
                    ]
                },
                {
                    "kind": "VarDecl",
                    "name": "table",
                    "storageClass": "static",
                    "type": { "qualType": "const int[1]" },
                    "init": "c",
                    "inner": [
                        {
                            "kind": "InitListExpr",
                            "type": { "qualType": "const int[1]" },
                            "inner": [
                                {
                                    "kind": "DeclRefExpr",
                                    "type": { "qualType": "int" },
                                    "referencedDecl": {
                                        "id": "0x1001",
                                        "kind": "EnumConstantDecl",
                                        "name": "STATUS_PENDING"
                                    }
                                }
                            ]
                        }
                    ]
                }
            ]
        });

        let globals = readonly_globals_from_ast(&ast).expect("readonly globals");

        assert!(
            globals.is_empty(),
            "implicit enum global initializer must stay fail-closed: {globals:?}"
        );
    }

    #[test]
    fn record_inventory_from_ast_maps_opaque_void_pointer_fields() {
        let ast = serde_json::json!({
            "kind": "TranslationUnitDecl",
            "inner": [
                {
                    "kind": "RecordDecl",
                    "tagUsed": "struct",
                    "name": "blob",
                    "completeDefinition": true,
                    "inner": [
                        {
                            "kind": "FieldDecl",
                            "name": "buf",
                            "type": { "qualType": "void *" }
                        },
                        {
                            "kind": "FieldDecl",
                            "name": "readonly",
                            "type": { "qualType": "const void *" }
                        },
                        {
                            "kind": "FieldDecl",
                            "name": "size",
                            "type": { "qualType": "size_t" }
                        }
                    ]
                }
            ]
        });

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
        let inventory = record_inventory_from_ast_with_target_abi(&ast, Some(&abi));
        let fields = inventory.get("blob").expect("blob record inventory");

        assert_eq!(fields.len(), 3);
        assert_eq!(fields[0].name, "buf");
        assert!(matches!(fields[0].ty.kind, IrTypeKind::Pointer { .. }));
        assert_eq!(fields[1].name, "readonly");
        let IrTypeKind::Pointer { pointee } = &fields[1].ty.kind else {
            panic!("expected const void pointer field, got {:?}", fields[1].ty);
        };
        assert!(pointee.is_const);
        assert_eq!(fields[2].name, "size");
        assert_eq!(fields[2].ty.spelled, "size_t");
        assert_eq!(fields[2].ty.width_bits, Some(64));
    }

    #[test]
    fn record_inventory_from_ast_keeps_duplicate_complete_record_definitions_with_same_fields() {
        let record_decl = serde_json::json!({
            "kind": "RecordDecl",
            "tagUsed": "struct",
            "name": "fdb_blob",
            "completeDefinition": true,
            "inner": [
                {
                    "kind": "FieldDecl",
                    "name": "buf",
                    "type": { "qualType": "void *" }
                },
                {
                    "kind": "FieldDecl",
                    "name": "size",
                    "type": { "qualType": "size_t" }
                }
            ]
        });
        let ast = serde_json::json!({
            "kind": "TranslationUnitDecl",
            "inner": [
                record_decl.clone(),
                record_decl
            ]
        });

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
        let inventory = record_inventory_from_ast_with_target_abi(&ast, Some(&abi));
        let fields = inventory
            .get("fdb_blob")
            .expect("identical duplicate record definitions keep inventory");

        assert_eq!(fields.len(), 2);
        assert_eq!(fields[0].name, "buf");
        assert_eq!(fields[1].name, "size");
    }
