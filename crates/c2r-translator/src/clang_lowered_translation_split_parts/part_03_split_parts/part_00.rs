    use super::*;
    use crate::{
        AcceptedNamedSliceEvidence, CBoundary, CDirectDependency, CParameter, CSignature,
        ExternalDirectCallee,
    };
    use crate::typed_ir::{
        IrBinOp, IrExpr, IrFunction, IrIncDecOp, IrParam, IrStmt, IrType, IrTypeKind, SourceSpan,
    };

    fn test_profile() -> BuildProfile {
        BuildProfile {
            include_paths: Vec::new(),
            defines: Vec::new(),
            target: None,
            clang_ast_fixture: None,
            target_triple: None,
            abi: None,
            compiler_command_source: "unit-test".to_string(),
            clang_available: true,
        }
    }

    fn unsigned_ty(spelled: &str, canonical: &str, width: u16) -> IrType {
        IrType {
            spelled: spelled.to_string(),
            canonical: canonical.to_string(),
            kind: IrTypeKind::Integer {
                signed: false,
                width,
            },
            is_const: false,
            width_bits: Some(width),
            source_span: None,
        }
    }

    fn signed_ty(spelled: &str, canonical: &str, width: u16) -> IrType {
        IrType {
            spelled: spelled.to_string(),
            canonical: canonical.to_string(),
            kind: IrTypeKind::Integer {
                signed: true,
                width,
            },
            is_const: false,
            width_bits: Some(width),
            source_span: None,
        }
    }

    fn void_ty(is_const: bool) -> IrType {
        IrType {
            spelled: "void".to_string(),
            canonical: "void".to_string(),
            kind: IrTypeKind::Void,
            is_const,
            width_bits: None,
            source_span: None,
        }
    }

    fn pointer_ty(spelled: &str, canonical: &str, pointee: IrType, is_const: bool) -> IrType {
        IrType {
            spelled: spelled.to_string(),
            canonical: canonical.to_string(),
            kind: IrTypeKind::Pointer {
                pointee: Box::new(pointee),
            },
            is_const,
            width_bits: Some(64),
            source_span: None,
        }
    }

    fn record_ty(name: &str) -> IrType {
        IrType {
            spelled: name.to_string(),
            canonical: name.to_string(),
            kind: IrTypeKind::Record {
                name: name.to_string(),
                fields: None,
            },
            is_const: false,
            width_bits: None,
            source_span: None,
        }
    }

    fn param(name: &str, ty: IrType) -> IrParam {
        IrParam {
            name: name.to_string(),
            ty,
            source_span: None,
        }
    }

    fn var(name: &str, ty: IrType) -> IrExpr {
        IrExpr::Var {
            name: name.to_string(),
            ty,
            source_span: None,
        }
    }

    fn call(callee: &str, args: Vec<IrExpr>, ty: IrType) -> IrExpr {
        IrExpr::Call {
            callee: callee.to_string(),
            args,
            ty,
            source_span: None,
        }
    }

    #[test]
    fn clang_ast_fixture_is_preferred_over_available_clang_path() {
        let parse_spec = clang_frontend::ClangParseSpec {
            source_root: PathBuf::from("."),
            source_file: PathBuf::from("add_one.c"),
            function_name: "add_one".to_string(),
            include_paths: Vec::new(),
            defines: Vec::new(),
            target_abi: None,
            compile_commands: None,
            source_file_hashes: std::collections::BTreeMap::new(),
            function_source_span: None,
        };
        let environment = std::collections::BTreeMap::from([(
            "CLANG_PATH".to_string(),
            std::env::current_exe()
                .unwrap()
                .to_string_lossy()
                .into_owned(),
        )]);

        let report = lower_parse_spec_report_with_optional_ast_fixture(
            &environment,
            &parse_spec,
            Some("crates/c2r-translator/fixtures/clang_ast/add_one_ast.json"),
        );

        assert_eq!(report.status, "lowered");
        assert_eq!(report.frontend, "clang_ast_json_fixture");
        assert_eq!(report.clang_path, None);
        assert_eq!(
            report
                .function_ir
                .as_ref()
                .map(|function| function.name.as_str()),
            Some("add_one")
        );
        assert!(report
            .diagnostics
            .iter()
            .any(|diagnostic| diagnostic.contains("external clang AST dump was not invoked")));
    }

    #[test]
    fn slice_source_translation_unit_declares_external_boundaries_without_project_macros() {
        let spec = SliceSpec {
            target_id: "flashdb".to_string(),
            slice_id: "real-fdb-kv-del".to_string(),
            function_name: "fdb_kv_del".to_string(),
            c_source: "fdb_err_t fdb_kv_del(fdb_kvdb_t db, const char *key) { fdb_err_t result = FDB_NO_ERR; if (!db_init_ok(db)) { FDB_INFO(\"bad %s\\n\", db_name(db)); return FDB_INIT_FAILED; } return result; }".to_string(),
            c_boundary: CBoundary {
                signatures: vec![
                    CSignature {
                        function: "fdb_kv_del".to_string(),
                        return_type: "fdb_err_t".to_string(),
                        parameters: vec![
                            CParameter {
                                name: "db".to_string(),
                                c_type: "fdb_kvdb_t".to_string(),
                                ..CParameter::default()
                            },
                            CParameter {
                                name: "key".to_string(),
                                c_type: "const char *".to_string(),
                                ..CParameter::default()
                            },
                        ],
                        ..CSignature::default()
                    },
                    CSignature {
                        role: "external_direct_callee".to_string(),
                        function: "db_init_ok".to_string(),
                        return_type: "bool".to_string(),
                        parameters: vec![CParameter {
                            name: "db".to_string(),
                            c_type: "fdb_kvdb_t".to_string(),
                            ..CParameter::default()
                        }],
                        ..CSignature::default()
                    },
                    CSignature {
                        role: "external_direct_callee".to_string(),
                        function: "FDB_INFO".to_string(),
                        return_type: "void".to_string(),
                        parameters: vec![
                            CParameter {
                                name: "fmt".to_string(),
                                c_type: "const char *".to_string(),
                                ..CParameter::default()
                            },
                            CParameter {
                                name: "name".to_string(),
                                c_type: "const char *".to_string(),
                                ..CParameter::default()
                            },
                        ],
                        ..CSignature::default()
                    },
                    CSignature {
                        role: "external_direct_callee".to_string(),
                        function: "db_name".to_string(),
                        return_type: "const char *".to_string(),
                        parameters: vec![CParameter {
                            name: "db".to_string(),
                            c_type: "fdb_kvdb_t".to_string(),
                            ..CParameter::default()
                        }],
                        ..CSignature::default()
                    },
                ],
                direct_dependencies: vec![CDirectDependency {
                    kind: "constant".to_string(),
                    name: "FDB_INIT_FAILED".to_string(),
                    value: Some(serde_json::json!(7)),
                    ..CDirectDependency::default()
                }],
                ..CBoundary::default()
            },
            ..SliceSpec::default()
        };

        let source = slice_source_translation_unit(&spec);

        assert!(source.contains("typedef int fdb_err_t;"), "{source}");
        assert!(source.contains("typedef void *fdb_kvdb_t;"), "{source}");
        assert!(source.contains("enum { FDB_INIT_FAILED = 7 };"), "{source}");
        assert!(source.contains("enum { FDB_NO_ERR = 0 };"), "{source}");
        assert!(source.contains("bool db_init_ok(fdb_kvdb_t db);"), "{source}");
        assert!(
            source.contains("void FDB_INFO(const char * fmt, const char * name);"),
            "{source}"
        );
        assert!(!source.contains("flashdb.h"), "{source}");
    }

    #[test]
    fn slice_source_translation_unit_binds_record_pointer_typedef_alias_when_struct_is_known() {
        let spec = SliceSpec {
            target_id: "flashdb".to_string(),
            slice_id: "record-constructor".to_string(),
            function_name: "set_blob".to_string(),
            c_source: "int set_blob(struct fdb_blob *slot, const char *value) { struct fdb_blob blob; return consume_blob(fdb_blob_make(&blob, value, strlen(value))); }".to_string(),
            c_boundary: CBoundary {
                signatures: vec![
                    CSignature {
                        function: "set_blob".to_string(),
                        return_type: "int".to_string(),
                        parameters: vec![
                            CParameter {
                                name: "slot".to_string(),
                                c_type: "struct fdb_blob *".to_string(),
                                ..CParameter::default()
                            },
                            CParameter {
                                name: "value".to_string(),
                                c_type: "const char *".to_string(),
                                ..CParameter::default()
                            },
                        ],
                        ..CSignature::default()
                    },
                    CSignature {
                        role: "external_direct_callee".to_string(),
                        function: "fdb_blob_make".to_string(),
                        return_type: "fdb_blob_t".to_string(),
                        parameters: vec![
                            CParameter {
                                name: "blob".to_string(),
                                c_type: "fdb_blob_t".to_string(),
                                ..CParameter::default()
                            },
                            CParameter {
                                name: "value".to_string(),
                                c_type: "const void *".to_string(),
                                ..CParameter::default()
                            },
                            CParameter {
                                name: "len".to_string(),
                                c_type: "size_t".to_string(),
                                ..CParameter::default()
                            },
                        ],
                        ..CSignature::default()
                    },
                ],
                ..CBoundary::default()
            },
            ..SliceSpec::default()
        };

        let source = slice_source_translation_unit(&spec);

        assert!(source.contains("struct fdb_blob { unsigned char _c2r_opaque; };"), "{source}");
        assert!(source.contains("typedef struct fdb_blob *fdb_blob_t;"), "{source}");
        assert!(!source.contains("typedef void *fdb_blob_t;"), "{source}");
    }

    #[test]
    fn slice_source_translation_unit_enriches_record_fields_from_accepted_named_slice_evidence() {
        let spec = SliceSpec {
            target_id: "flashdb".to_string(),
            slice_id: "record-constructor".to_string(),
            function_name: "set_blob".to_string(),
            c_source: "int set_blob(struct fdb_blob *slot, const char *value) { struct fdb_blob blob; return consume_blob(fdb_blob_make(&blob, value, strlen(value))); }".to_string(),
            c_boundary: CBoundary {
                signatures: vec![
                    CSignature {
                        function: "set_blob".to_string(),
                        return_type: "int".to_string(),
                        parameters: vec![
                            CParameter {
                                name: "slot".to_string(),
                                c_type: "struct fdb_blob *".to_string(),
                                ..CParameter::default()
                            },
                            CParameter {
                                name: "value".to_string(),
                                c_type: "const char *".to_string(),
                                ..CParameter::default()
                            },
                        ],
                        ..CSignature::default()
                    },
                    CSignature {
                        role: "external_direct_callee".to_string(),
                        function: "fdb_blob_make".to_string(),
                        return_type: "fdb_blob_t".to_string(),
                        parameters: vec![
                            CParameter {
                                name: "blob".to_string(),
                                c_type: "fdb_blob_t".to_string(),
                                ..CParameter::default()
                            },
                            CParameter {
                                name: "value".to_string(),
                                c_type: "const void *".to_string(),
                                ..CParameter::default()
                            },
                            CParameter {
                                name: "len".to_string(),
                                c_type: "size_t".to_string(),
                                ..CParameter::default()
                            },
                        ],
                        ..CSignature::default()
                    },
                ],
                external_direct_callees: vec![ExternalDirectCallee {
                    name: "fdb_blob_make".to_string(),
                    accepted_named_slice_evidence: Some(AcceptedNamedSliceEvidence {
                        target_id: "flashdb".to_string(),
                        slice_id: "real-fdb-blob-make".to_string(),
                        final_verification: "validation/evidence/flashdb/auto-translation/real-fdb-blob-make/l3-real-fdb-blob-make-final-verification.json".to_string(),
                        ..AcceptedNamedSliceEvidence::default()
                    }),
                    ..ExternalDirectCallee::default()
                }],
                ..CBoundary::default()
            },
            ..SliceSpec::default()
        };

        let source = slice_source_translation_unit(&spec);

        assert!(
            source.contains("struct fdb_blob {\n    void * buf;\n    size_t size;\n};"),
            "{source}"
        );
        assert!(!source.contains("struct fdb_blob { unsigned char _c2r_opaque; };"), "{source}");
        assert!(source.contains("typedef struct fdb_blob *fdb_blob_t;"), "{source}");
    }

    #[test]
    fn slice_source_translation_unit_ignores_unaccepted_named_slice_record_fields() {
        let spec = SliceSpec {
            target_id: "flashdb".to_string(),
            slice_id: "record-constructor".to_string(),
            function_name: "set_blob".to_string(),
            c_source: "int set_blob(struct fdb_blob *slot, const char *value) { struct fdb_blob blob; return consume_blob(fdb_blob_make(&blob, value, strlen(value))); }".to_string(),
            c_boundary: CBoundary {
                signatures: vec![
                    CSignature {
                        function: "set_blob".to_string(),
                        return_type: "int".to_string(),
                        parameters: vec![CParameter {
                            name: "slot".to_string(),
                            c_type: "struct fdb_blob *".to_string(),
                            ..CParameter::default()
                        }],
                        ..CSignature::default()
                    },
                    CSignature {
                        role: "external_direct_callee".to_string(),
                        function: "fdb_blob_make".to_string(),
                        return_type: "fdb_blob_t".to_string(),
                        parameters: vec![CParameter {
                            name: "blob".to_string(),
                            c_type: "fdb_blob_t".to_string(),
                            ..CParameter::default()
                        }],
                        ..CSignature::default()
                    },
                ],
                external_direct_callees: vec![ExternalDirectCallee {
                    name: "fdb_blob_make".to_string(),
                    accepted_named_slice_evidence: Some(AcceptedNamedSliceEvidence {
                        target_id: "flashdb".to_string(),
                        slice_id: "real-fdb-kv-set".to_string(),
                        final_verification: "validation/evidence/flashdb/auto-translation/real-fdb-kv-set/l3-real-fdb-kv-set-route-decision.json".to_string(),
                        ..AcceptedNamedSliceEvidence::default()
                    }),
                    ..ExternalDirectCallee::default()
                }],
                ..CBoundary::default()
            },
            ..SliceSpec::default()
        };

        let source = slice_source_translation_unit(&spec);

        assert!(
            source.contains("struct fdb_blob { unsigned char _c2r_opaque; };"),
            "{source}"
        );
        assert!(!source.contains("void * buf"), "{source}");
        assert!(!source.contains("size_t size"), "{source}");
    }

    #[test]
    fn slice_source_translation_unit_declares_signature_pointer_member_fields() {
        let spec = SliceSpec {
            target_id: "libuv".to_string(),
            slice_id: "ip4-addr".to_string(),
            function_name: "uv_ip4_addr".to_string(),
            c_source: "int uv_ip4_addr(const char* ip, int port, struct sockaddr_in* addr) { addr->sin_family = AF_INET; return 0; }".to_string(),
            c_boundary: CBoundary {
                signatures: vec![CSignature {
                    function: "uv_ip4_addr".to_string(),
                    return_type: "int".to_string(),
                    parameters: vec![
                        CParameter {
                            name: "ip".to_string(),
                            c_type: "const char*".to_string(),
                            ..CParameter::default()
                        },
                        CParameter {
                            name: "port".to_string(),
                            c_type: "int".to_string(),
                            ..CParameter::default()
                        },
                        CParameter {
                            name: "addr".to_string(),
                            c_type: "struct sockaddr_in*".to_string(),
                            ..CParameter::default()
                        },
                    ],
                    ..CSignature::default()
                }],
                direct_dependencies: vec![CDirectDependency {
                    kind: "constant".to_string(),
                    name: "AF_INET".to_string(),
                    value: Some(serde_json::json!(2)),
                    ..CDirectDependency::default()
                }],
                ..CBoundary::default()
            },
            ..SliceSpec::default()
        };

        let source = slice_source_translation_unit(&spec);

        assert!(
            source.contains("struct sockaddr_in {\n    int sin_family;\n    unsigned char _c2r_opaque;\n};"),
            "{source}"
        );
        assert!(source.contains("enum { AF_INET = 2 };"), "{source}");
    }

    #[test]
    fn slice_source_translation_unit_does_not_redeclare_build_profile_defines() {
        let spec = SliceSpec {
            target_id: "libuv".to_string(),
            slice_id: "ip4-addr".to_string(),
            function_name: "uv_ip4_addr".to_string(),
            c_source: "int uv_ip4_addr(const char* ip, int port, struct sockaddr_in* addr) { addr->sin_family = AF_INET; return 0; }".to_string(),
            c_boundary: CBoundary {
                signatures: vec![CSignature {
                    function: "uv_ip4_addr".to_string(),
                    return_type: "int".to_string(),
                    parameters: vec![CParameter {
                        name: "addr".to_string(),
                        c_type: "struct sockaddr_in*".to_string(),
                        ..CParameter::default()
                    }],
                    ..CSignature::default()
                }],
                ..CBoundary::default()
            },
            build_profile: BuildProfile {
                defines: vec!["AF_INET=2".to_string()],
                ..test_profile()
            },
            ..SliceSpec::default()
        };

        let source = slice_source_translation_unit(&spec);

        assert!(!source.contains("enum { AF_INET"), "{source}");
        assert!(source.contains("addr->sin_family = AF_INET"), "{source}");
    }

    #[test]
    fn slice_source_constant_scan_ignores_null_strings_and_comments() {
        let names = collect_object_like_uppercase_identifiers(
            "int sample(void) { /* SKIP_COMMENT */ const char *msg = \"KV OK\"; return VALUE + (NULL == 0); }",
        );

        assert!(names.contains("VALUE"));
        assert!(!names.contains("NULL"));
        assert!(!names.contains("KV"));
        assert!(!names.contains("OK"));
        assert!(!names.contains("SKIP_COMMENT"));
    }

    #[test]
    fn clang_lowered_ir_records_direct_call_expression_evidence() {
        let i32_ty = signed_ty("int", "int", 32);
        let function = IrFunction {
            name: "call_expression".to_string(),
            return_type: i32_ty.clone(),
            params: vec![param("value", i32_ty.clone())],
            body: vec![
                IrStmt::Decl {
                    name: "first".to_string(),
                    ty: i32_ty.clone(),
                    init: Some(call(
                        "helper",
                        vec![var("value", i32_ty.clone())],
                        i32_ty.clone(),
                    )),
                    source_span: None,
                },
                IrStmt::Assign {
                    target: var("value", i32_ty.clone()),
                    value: call("helper", vec![var("first", i32_ty.clone())], i32_ty.clone()),
                    source_span: None,
                },
                IrStmt::Return {
                    value: Some(call("helper", vec![var("value", i32_ty.clone())], i32_ty)),
                    source_span: None,
                },
            ],
            source_span: None,
        };
        let spec = SliceSpec {
            target_id: "demo".to_string(),
            slice_id: "call-expression".to_string(),
            source_commit: "1234567".to_string(),
            function_name: "call_expression".to_string(),
            build_profile: test_profile(),
            ..SliceSpec::default()
        };
        let mut result = TranslationResult::default();

        record_clang_lowered_ir_evidence(&spec, &function, &mut result);

        assert_eq!(result.plan.call_expressions.len(), 3);
        assert!(result
            .plan
            .translation_rule_ids
            .contains(&"bounded-call-expression".to_string()));
        assert_eq!(result.plan.call_expressions[0].callee, "helper");
        assert_eq!(result.plan.call_expressions[0].arguments, vec!["value"]);
        assert_eq!(
            result.plan.call_expressions[0].source_expression,
            "helper(value)"
        );
        assert_eq!(
            result.plan.call_expressions[0].statement_context,
            "declaration_initializer"
        );
        assert_eq!(
            result.plan.call_expressions[1].source_expression,
            "helper(first)"
        );
        assert_eq!(
            result.plan.call_expressions[1].statement_context,
            "assignment"
        );
        assert_eq!(result.plan.call_expressions[2].statement_context, "return");
    }

    #[test]
    fn clang_lowered_ir_parenthesizes_complex_member_source_text() {
        let i32_ty = signed_ty("int", "int", 32);
        let ptr_ty = pointer_ty(
            "struct point *",
            "struct point *",
            record_ty("point"),
            false,
        );
        let member = IrExpr::Member {
            base: Box::new(IrExpr::Deref {
                ptr: Box::new(var("p", ptr_ty)),
                ty: record_ty("point"),
                source_span: None,
            }),
            field: "x".to_string(),
            ty: i32_ty,
            is_arrow: false,
            source_span: None,
        };

        assert_eq!(ir_expr_source_text(&member), "(*p).x");
    }

    #[test]
    fn clang_lowered_ir_records_call_inside_member_base() {
        let i32_ty = signed_ty("int", "int", 32);
        let point_ty = record_ty("point");
        let function = IrFunction {
            name: "member_call".to_string(),
            return_type: i32_ty.clone(),
            params: vec![param("value", i32_ty.clone())],
            body: vec![IrStmt::Return {
                value: Some(call(
                    "helper",
                    vec![IrExpr::Member {
                        base: Box::new(call("obj_factory", Vec::new(), point_ty)),
                        field: "x".to_string(),
                        ty: i32_ty.clone(),
                        is_arrow: false,
                        source_span: None,
                    }],
                    i32_ty,
                )),
                source_span: None,
            }],
            source_span: None,
        };
        let spec = SliceSpec {
            target_id: "demo".to_string(),
            slice_id: "member-call".to_string(),
            source_commit: "1234567".to_string(),
            function_name: "member_call".to_string(),
            build_profile: test_profile(),
            ..SliceSpec::default()
        };
        let mut result = TranslationResult::default();

        record_clang_lowered_ir_evidence(&spec, &function, &mut result);

        assert_eq!(result.plan.call_expressions.len(), 2);
        assert_eq!(result.plan.call_expressions[0].callee, "helper");
        assert_eq!(
            result.plan.call_expressions[0].source_expression,
            "helper(obj_factory().x)"
        );
        assert_eq!(result.plan.call_expressions[1].callee, "obj_factory");
        assert_eq!(
            result.plan.call_expressions[1].source_expression,
            "obj_factory()"
        );
    }

    #[test]
    fn clang_lowered_ir_preserves_repeated_direct_call_sites_in_same_context() {
        let i32_ty = signed_ty("int", "int", 32);
        let function = IrFunction {
            name: "repeat_call".to_string(),
            return_type: i32_ty.clone(),
            params: vec![param("value", i32_ty.clone())],
            body: vec![
                IrStmt::Assign {
                    target: var("value", i32_ty.clone()),
                    value: call("helper", vec![var("value", i32_ty.clone())], i32_ty.clone()),
                    source_span: None,
                },
                IrStmt::Assign {
                    target: var("value", i32_ty.clone()),
                    value: call("helper", vec![var("value", i32_ty.clone())], i32_ty.clone()),
                    source_span: None,
                },
                IrStmt::Return {
                    value: Some(var("value", i32_ty)),
                    source_span: None,
                },
            ],
            source_span: None,
        };
        let spec = SliceSpec {
            target_id: "demo".to_string(),
            slice_id: "repeat-call".to_string(),
            source_commit: "1234567".to_string(),
            function_name: "repeat_call".to_string(),
            build_profile: test_profile(),
            ..SliceSpec::default()
        };
        let mut result = TranslationResult::default();

        record_clang_lowered_ir_evidence(&spec, &function, &mut result);

        assert_eq!(result.plan.call_expressions.len(), 2);
        assert!(result
            .plan
            .call_expressions
            .iter()
            .all(|call| call.source_expression == "helper(value)"));
        assert!(result
            .plan
            .call_expressions
            .iter()
            .all(|call| call.statement_context == "assignment"));
    }

    #[test]
    fn clang_lowered_ir_does_not_record_condition_call_as_success_evidence() {
        let i32_ty = signed_ty("int", "int", 32);
        let function = IrFunction {
            name: "condition_call".to_string(),
            return_type: i32_ty.clone(),
            params: vec![param("value", i32_ty.clone())],
            body: vec![
                IrStmt::If {
                    condition: call("helper", vec![var("value", i32_ty.clone())], i32_ty.clone()),
                    then_body: vec![IrStmt::Return {
                        value: Some(var("value", i32_ty.clone())),
                        source_span: None,
                    }],
                    else_body: Vec::new(),
                    source_span: None,
                },
                IrStmt::Return {
                    value: Some(var("value", i32_ty)),
                    source_span: None,
                },
            ],
            source_span: None,
        };
        let spec = SliceSpec {
            target_id: "demo".to_string(),
            slice_id: "condition-call".to_string(),
            source_commit: "1234567".to_string(),
            function_name: "condition_call".to_string(),
            build_profile: test_profile(),
            ..SliceSpec::default()
        };
        let mut result = TranslationResult::default();

        record_clang_lowered_ir_evidence(&spec, &function, &mut result);

        assert!(result.plan.call_expressions.is_empty());
        assert!(!result
            .plan
            .translation_rule_ids
            .contains(&"bounded-call-expression".to_string()));
    }

    #[test]
    fn clang_lowered_ir_records_for_statement_evidence_recursively() {
        let i32_ty = signed_ty("int", "int", 32);
        let function = IrFunction {
            name: "for_evidence".to_string(),
            return_type: i32_ty.clone(),
            params: vec![param("limit", i32_ty.clone())],
            body: vec![
                IrStmt::Decl {
                    name: "total".to_string(),
                    ty: i32_ty.clone(),
                    init: Some(var("limit", i32_ty.clone())),
                    source_span: None,
                },
                IrStmt::For {
                    init: vec![IrStmt::Decl {
                        name: "i".to_string(),
                        ty: i32_ty.clone(),
                        init: Some(var("limit", i32_ty.clone())),
                        source_span: None,
                    }],
                    condition: Some(IrExpr::Binary {
                        op: IrBinOp::Lt,
                        lhs: Box::new(var("i", i32_ty.clone())),
                        rhs: Box::new(var("limit", i32_ty.clone())),
                        ty: i32_ty.clone(),
                        source_span: None,
                    }),
                    step: Some(Box::new(IrStmt::Assign {
                        target: var("i", i32_ty.clone()),
                        value: call(
                            "step_helper",
                            vec![var("i", i32_ty.clone())],
                            i32_ty.clone(),
                        ),
                        source_span: None,
                    })),
                    body: vec![IrStmt::Decl {
                        name: "next".to_string(),
                        ty: i32_ty.clone(),
                        init: Some(call(
                            "body_helper",
                            vec![var("total", i32_ty.clone())],
                            i32_ty.clone(),
                        )),
                        source_span: None,
                    }],
                    source_span: None,
                },
                IrStmt::Return {
                    value: Some(var("total", i32_ty.clone())),
                    source_span: None,
                },
            ],
            source_span: None,
        };
        let spec = SliceSpec {
            target_id: "demo".to_string(),
            slice_id: "for-evidence".to_string(),
            source_commit: "1234567".to_string(),
            function_name: "for_evidence".to_string(),
            build_profile: test_profile(),
            ..SliceSpec::default()
        };
        let mut result = TranslationResult::default();

        record_clang_lowered_ir_evidence(&spec, &function, &mut result);

        let block = &result.cfg.functions[0].blocks[0];
        assert!(block.statement_kinds.contains(&"for".to_string()));
        assert!(block.edges.contains(&"entry->for-1".to_string()));
        assert!(result
            .type_map
            .mappings
            .iter()
            .any(|mapping| mapping.symbol == "i"));
        assert!(result
            .type_map
            .mappings
            .iter()
            .any(|mapping| mapping.symbol == "next"));
        assert_eq!(result.plan.call_expressions.len(), 2);
        assert_eq!(
            result.plan.call_expressions[0].source_expression,
            "body_helper(total)"
        );
        assert_eq!(
            result.plan.call_expressions[0].statement_context,
            "declaration_initializer"
        );
        assert_eq!(
            result.plan.call_expressions[1].source_expression,
            "step_helper(i)"
        );
        assert_eq!(
            result.plan.call_expressions[1].statement_context,
            "assignment"
        );
    }

    #[test]
    fn clang_lowered_pointer_graph_does_not_infer_byte_cursor_from_buf_name_only() {
        let u32_ty = unsigned_ty("uint32_t", "unsigned int", 32);
        let usize_ty = unsigned_ty("size_t", "unsigned long", 64);
        let const_void_ptr = pointer_ty("const void *", "const void *", void_ty(true), true);
        let function = IrFunction {
            name: "fdb_calc_crc32".to_string(),
            return_type: u32_ty.clone(),
            params: vec![
                param("crc", u32_ty.clone()),
                param("buf", const_void_ptr),
                param("size", usize_ty),
            ],
            body: vec![IrStmt::Return {
                value: Some(IrExpr::Var {
                    name: "crc".to_string(),
                    ty: u32_ty,
                    source_span: None::<SourceSpan>,
                }),
                source_span: None,
            }],
            source_span: None,
        };
        let spec = SliceSpec {
            target_id: "flashdb".to_string(),
            slice_id: "real-fdb-calc-crc32".to_string(),
            source_commit: "93d1755".to_string(),
            function_name: "fdb_calc_crc32".to_string(),
            build_profile: test_profile(),
            ..SliceSpec::default()
        };
        let mut result = TranslationResult::default();

        record_clang_lowered_ir_evidence(&spec, &function, &mut result);

        let buf = result
            .pointer_graph
            .nodes
            .iter()
            .find(|node| node.id == "buf")
            .expect("buf pointer node");
        assert!(buf.read_effects.is_empty(), "{:?}", buf.read_effects);
        assert!(
            !buf.boundary_decisions
                .contains(&"byte_cursor_post_increment_read".to_string()),
            "{:?}",
            buf.boundary_decisions
        );
    }

    #[test]
    fn clang_lowered_type_map_records_unused_readonly_8_bit_pointer_as_raw_candidate() {
        let i32_ty = signed_ty("int", "int", 32);
        let mut const_char_ty = signed_ty("char", "char", 8);
        const_char_ty.is_const = true;
        let const_char_ptr = pointer_ty("const char *", "const char *", const_char_ty, false);
        let sockaddr_ptr = pointer_ty(
            "struct sockaddr_in *",
            "struct sockaddr_in *",
            record_ty("sockaddr_in"),
            false,
        );
        let function = IrFunction {
            name: "uv_ip4_addr".to_string(),
            return_type: i32_ty.clone(),
            params: vec![
                param("ip", const_char_ptr),
                param("port", i32_ty.clone()),
                param("addr", sockaddr_ptr.clone()),
            ],
            body: vec![
                IrStmt::Assign {
                    target: IrExpr::Member {
                        base: Box::new(var("addr", sockaddr_ptr)),
                        field: "sin_family".to_string(),
                        ty: i32_ty.clone(),
                        is_arrow: true,
                        source_span: None,
                    },
                    value: IrExpr::LitInt {
                        value: 2,
                        spelling: "2".to_string(),
                        ty: i32_ty.clone(),
                        source_span: None,
                    },
                    source_span: None,
                },
                IrStmt::Return {
                    value: Some(IrExpr::LitInt {
                        value: 0,
                        spelling: "0".to_string(),
                        ty: i32_ty,
                        source_span: None,
                    }),
                    source_span: None,
                },
            ],
            source_span: None,
        };
        let spec = SliceSpec {
            target_id: "libuv".to_string(),
            slice_id: "ip4-addr".to_string(),
            source_commit: "5e7d51a".to_string(),
            function_name: "uv_ip4_addr".to_string(),
            build_profile: test_profile(),
            ..SliceSpec::default()
        };
        let mut result = TranslationResult::default();

        record_clang_lowered_ir_evidence(&spec, &function, &mut result);

        let ip_mapping = result
            .type_map
            .mappings
            .iter()
            .find(|mapping| mapping.symbol == "ip")
            .expect("ip type mapping");
        assert_eq!(ip_mapping.rust_type, "*const core::ffi::c_void");
        let ip_pointer = result
            .pointer_graph
            .nodes
            .iter()
            .find(|node| node.id == "ip")
            .expect("ip pointer node");
        assert_eq!(ip_pointer.rust_boundary, "*const core::ffi::c_void");
        assert!(ip_pointer.read_effects.is_empty());
        assert!(ip_pointer
            .boundary_decisions
            .contains(&"unused_readonly_8_bit_pointer_raw_candidate".to_string()));
    }
