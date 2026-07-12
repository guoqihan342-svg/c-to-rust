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
