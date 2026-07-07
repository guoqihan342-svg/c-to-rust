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
