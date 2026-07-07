#[cfg(feature = "clang-frontend")]
#[test]
fn clang_dry_run_records_missing_libclang_environment_without_parsing() {
    let spec: SliceSpec = serde_json::from_value(serde_json::json!({
        "target_id": "flashdb",
        "slice_id": "real-fdb-calc-crc32",
        "source_commit": "93d1755",
        "function_name": "fdb_calc_crc32",
        "c_source": "uint32_t fdb_calc_crc32(uint32_t crc, const void *buf, size_t size) { return crc; }",
        "fixture_hash": "fixture-sha",
        "source_root": "C:/src/FlashDB",
        "source_file": "src/fdb_utils.c",
        "source_file_hashes": {
            "src/fdb_utils.c": "source-file-sha"
        },
        "function_source_span": {
            "file": "src/fdb_utils.c",
            "line_start": 77,
            "line_end": 89,
            "byte_start": 3818,
            "byte_end": 4075,
            "sha256": "function-span-sha"
        },
        "build_profile": {
            "include_paths": ["inc"],
            "defines": ["FDB_USING_FILE_POSIX_MODE"],
            "target_triple": "x86_64-unknown-linux-gnu",
            "abi": "linux-gnu",
            "compiler_command_source": "C:/src/FlashDB/CMakeLists.txt",
            "clang_available": false
        }
    }))
    .unwrap();
    let environment = std::collections::BTreeMap::new();

    let dry_run = ClangParseSpec::from_slice_spec(&spec)
        .expect("clang parse spec")
        .dry_run_with_environment(&environment);

    assert_eq!(dry_run.status, "diagnostic_only");
    assert_eq!(dry_run.claim_boundary.role, "diagnostic_only");
    assert_eq!(dry_run.active_frontend.kind, "clang_ast_dump_json");
    assert_eq!(dry_run.environment.status, "not_configured");
    assert_eq!(dry_run.environment.source.as_deref(), None);
    assert_eq!(dry_run.environment.observed_libclang_path.as_deref(), None);
    assert_eq!(dry_run.environment.role, "diagnostic_only");
    assert!(dry_run.environment.diagnostics.iter().any(|diagnostic| {
        diagnostic.contains("LIBCLANG_PATH is not set and is ignored for clang AST dump lowering")
    }));
    assert!(dry_run
        .diagnostics
        .contains(&"LIBCLANG_PATH is observed only as ignored legacy metadata; active lowering uses clang AST dump JSON via CLANG_PATH".to_string()));
}

#[cfg(feature = "clang-frontend")]
#[test]
fn clang_dry_run_records_configured_libclang_path_without_enabling_parse() {
    let spec: SliceSpec = serde_json::from_value(serde_json::json!({
        "target_id": "flashdb",
        "slice_id": "real-fdb-calc-crc32",
        "source_commit": "93d1755",
        "function_name": "fdb_calc_crc32",
        "c_source": "uint32_t fdb_calc_crc32(uint32_t crc, const void *buf, size_t size) { return crc; }",
        "fixture_hash": "fixture-sha",
        "source_root": "C:/src/FlashDB",
        "source_file": "src/fdb_utils.c",
        "source_file_hashes": {
            "src/fdb_utils.c": "source-file-sha"
        },
        "function_source_span": {
            "file": "src/fdb_utils.c",
            "line_start": 77,
            "line_end": 89,
            "byte_start": 3818,
            "byte_end": 4075,
            "sha256": "function-span-sha"
        },
        "build_profile": {
            "include_paths": ["inc"],
            "defines": ["FDB_USING_FILE_POSIX_MODE"],
            "target_triple": "x86_64-unknown-linux-gnu",
            "abi": "linux-gnu",
            "compiler_command_source": "C:/src/FlashDB/CMakeLists.txt",
            "clang_available": false
        }
    }))
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "LIBCLANG_PATH".to_string(),
        "C:/LLVM/bin/libclang.dll".to_string(),
    )]);

    let dry_run = ClangParseSpec::from_slice_spec(&spec)
        .expect("clang parse spec")
        .dry_run_with_environment(&environment);

    assert_eq!(dry_run.status, "diagnostic_only");
    assert_eq!(dry_run.active_frontend.kind, "clang_ast_dump_json");
    assert_eq!(dry_run.environment.status, "ignored_for_ast_dump");
    assert_eq!(dry_run.environment.source.as_deref(), Some("LIBCLANG_PATH"));
    assert_eq!(
        dry_run.environment.observed_libclang_path.as_deref(),
        Some("C:/LLVM/bin/libclang.dll")
    );
    assert!(dry_run.environment.diagnostics.iter().any(|diagnostic| {
        diagnostic.contains("LIBCLANG_PATH is configured but ignored for clang AST dump lowering")
    }));
    assert!(dry_run
        .diagnostics
        .contains(&"LIBCLANG_PATH is observed only as ignored legacy metadata; active lowering uses clang AST dump JSON via CLANG_PATH".to_string()));
}

#[cfg(feature = "clang-frontend")]
#[test]
fn clang_parse_spec_dry_run_prefers_compile_commands_over_synthesized_args() {
    let spec: SliceSpec = serde_json::from_value(serde_json::json!({
        "target_id": "flashdb",
        "slice_id": "real-fdb-calc-crc32",
        "source_commit": "93d1755",
        "function_name": "fdb_calc_crc32",
        "c_source": "uint32_t fdb_calc_crc32(uint32_t crc, const void *buf, size_t size) { return crc; }",
        "fixture_hash": "fixture-sha",
        "source_root": "C:/src/FlashDB",
        "source_file": "src/fdb_utils.c",
        "source_file_hashes": {
            "src/fdb_utils.c": "source-file-sha"
        },
        "function_source_span": {
            "file": "src/fdb_utils.c",
            "line_start": 77,
            "line_end": 89,
            "byte_start": 3818,
            "byte_end": 4075,
            "sha256": "function-span-sha"
        },
        "compile_commands": "build/compile_commands.json",
        "build_profile": {
            "include_paths": ["inc"],
            "defines": ["FDB_USING_FILE_POSIX_MODE"],
            "target_triple": "x86_64-unknown-linux-gnu",
            "abi": "linux-gnu",
            "compiler_command_source": "compile_commands.json",
            "clang_available": false
        }
    }))
    .unwrap();

    let dry_run = ClangParseSpec::from_slice_spec(&spec)
        .expect("clang parse spec")
        .dry_run();

    assert_eq!(dry_run.arguments, Vec::<String>::new());
    assert_eq!(
        dry_run.compile_commands.as_deref(),
        Some("build/compile_commands.json")
    );
}

#[cfg(feature = "clang-frontend")]
#[test]
fn clang_parse_spec_rejects_missing_source_hash_and_function_span() {
    let spec: SliceSpec = serde_json::from_value(serde_json::json!({
        "target_id": "flashdb",
        "slice_id": "real-fdb-calc-crc32",
        "source_commit": "93d1755",
        "function_name": "fdb_calc_crc32",
        "c_source": "uint32_t fdb_calc_crc32(uint32_t crc, const void *buf, size_t size) { return crc; }",
        "fixture_hash": "fixture-sha",
        "source_root": "C:/src/FlashDB",
        "source_file": "src/fdb_utils.c",
        "build_profile": {
            "include_paths": ["inc"],
            "defines": [],
            "target_triple": "x86_64-unknown-linux-gnu",
            "abi": "linux-gnu",
            "compiler_command_source": "C:/src/FlashDB/CMakeLists.txt",
            "clang_available": false
        }
    }))
    .unwrap();

    let error = ClangParseSpec::from_slice_spec(&spec)
        .expect_err("clang frontend must require source file hash coverage");

    assert_eq!(error.kind, "missing_source_file_hash");
    assert_eq!(
        error.to_string(),
        "clang frontend dry-run requires source_file_hashes entry for source_file"
    );
}

#[cfg(feature = "clang-frontend")]
#[test]
fn clang_parse_spec_rejects_function_span_for_a_different_source_file() {
    let spec: SliceSpec = serde_json::from_value(serde_json::json!({
        "target_id": "flashdb",
        "slice_id": "real-fdb-calc-crc32",
        "source_commit": "93d1755",
        "function_name": "fdb_calc_crc32",
        "c_source": "uint32_t fdb_calc_crc32(uint32_t crc, const void *buf, size_t size) { return crc; }",
        "fixture_hash": "fixture-sha",
        "source_root": "C:/src/FlashDB",
        "source_file": "src/fdb_utils.c",
        "source_file_hashes": {
            "src/fdb_utils.c": "source-file-sha"
        },
        "function_source_span": {
            "file": "src/other.c",
            "line_start": 77,
            "line_end": 89,
            "byte_start": 3818,
            "byte_end": 4075,
            "sha256": "function-span-sha"
        },
        "build_profile": {
            "include_paths": ["inc"],
            "defines": [],
            "target_triple": "x86_64-unknown-linux-gnu",
            "abi": "linux-gnu",
            "compiler_command_source": "C:/src/FlashDB/CMakeLists.txt",
            "clang_available": false
        }
    }))
    .unwrap();

    let error = ClangParseSpec::from_slice_spec(&spec)
        .expect_err("clang frontend must bind the span to source_file");

    assert_eq!(error.kind, "function_span_source_file_mismatch");
    assert!(error
        .to_string()
        .contains("function_source_span.file must match source_file"));
}

#[cfg(feature = "clang-frontend")]
#[test]
fn clang_parse_spec_rejects_missing_real_tu_metadata() {
    let spec = SliceSpec {
        target_id: "flashdb".to_string(),
        slice_id: "real-fdb-calc-crc32".to_string(),
        source_commit: "93d1755".to_string(),
        function_name: "fdb_calc_crc32".to_string(),
        c_source:
            "uint32_t fdb_calc_crc32(uint32_t crc, const void *buf, size_t size) { return crc; }"
                .to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(true),
        ..SliceSpec::default()
    };

    let error = ClangParseSpec::from_slice_spec(&spec)
        .expect_err("clang frontend must require real TU metadata");

    assert_eq!(error.kind, "missing_source_root");
    assert_eq!(
        error.to_string(),
        "clang frontend dry-run requires source_root"
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_lowering_skeleton_builds_typed_ir_for_add_one_fixture() {
    let int_ty = ClangTypeSkeleton {
        spelled: "int".to_string(),
        canonical: "int".to_string(),
        kind: ClangTypeKind::Integer {
            signed: true,
            width: 32,
        },
    };
    let skeleton = ClangFunctionSkeleton {
        name: "add_one".to_string(),
        return_type: int_ty.clone(),
        params: vec![ClangParamSkeleton {
            name: "value".to_string(),
            ty: int_ty.clone(),
        }],
        body: vec![ClangStmtSkeleton::Return {
            value: Some(ClangExprSkeleton::Binary {
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
            }),
        }],
    };

    let ir = lower_function_skeleton(&skeleton).expect("lower add_one skeleton");

    assert_eq!(ir.name, "add_one");
    assert!(matches!(
        ir.return_type.kind,
        IrTypeKind::Integer {
            signed: true,
            width: 32
        }
    ));
    assert_eq!(ir.params.len(), 1);
    assert_eq!(ir.params[0].name, "value");
    let [IrStmt::Return {
        value:
            Some(IrExpr::Binary {
                op: IrBinOp::Add,
                lhs,
                rhs,
                ty,
                ..
            }),
        ..
    }] = ir.body.as_slice()
    else {
        panic!("expected single return-add statement");
    };
    assert!(matches!(ty.kind, IrTypeKind::Integer { width: 32, .. }));
    assert!(matches!(
        lhs.as_ref(),
        IrExpr::Var { name, .. } if name == "value"
    ));
    assert!(matches!(
        rhs.as_ref(),
        IrExpr::LitInt { value: 1, spelling, .. } if spelling == "1"
    ));
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn typed_ir_emits_add_one_from_clang_lowered_ir() {
    let int_ty = ClangTypeSkeleton {
        spelled: "int".to_string(),
        canonical: "int".to_string(),
        kind: ClangTypeKind::Integer {
            signed: true,
            width: 32,
        },
    };
    let skeleton = ClangFunctionSkeleton {
        name: "add_one".to_string(),
        return_type: int_ty.clone(),
        params: vec![ClangParamSkeleton {
            name: "value".to_string(),
            ty: int_ty.clone(),
        }],
        body: vec![ClangStmtSkeleton::Return {
            value: Some(ClangExprSkeleton::Binary {
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
                ty: int_ty,
            }),
        }],
    };
    let ir = lower_function_skeleton(&skeleton).expect("lower add_one skeleton");

    let rust = emit_rust_from_ir(&ir).expect("emit add_one from lowered typed IR");

    assert!(rust.contains("pub fn add_one(value: i32) -> i32"));
    assert!(rust.contains("return value.checked_add(1i32).expect(\"signed addition overflow\");"));
    assert!(!rust.contains("crc32_update_byte"));
    assert_rust_snippet_compiles("typed-ir-add-one", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn typed_ir_emits_scalar_subtraction_from_clang_lowered_ir() {
    let int_ty = ClangTypeSkeleton {
        spelled: "int".to_string(),
        canonical: "int".to_string(),
        kind: ClangTypeKind::Integer {
            signed: true,
            width: 32,
        },
    };
    let skeleton = ClangFunctionSkeleton {
        name: "sub_one".to_string(),
        return_type: int_ty.clone(),
        params: vec![ClangParamSkeleton {
            name: "value".to_string(),
            ty: int_ty.clone(),
        }],
        body: vec![ClangStmtSkeleton::Return {
            value: Some(ClangExprSkeleton::Binary {
                op: ClangBinaryOperator::Sub,
                lhs: Box::new(ClangExprSkeleton::DeclRef {
                    name: "value".to_string(),
                    ty: int_ty.clone(),
                }),
                rhs: Box::new(ClangExprSkeleton::IntegerLiteral {
                    value: 1,
                    spelling: "1".to_string(),
                    ty: int_ty.clone(),
                }),
                ty: int_ty,
            }),
        }],
    };
    let ir = lower_function_skeleton(&skeleton).expect("lower sub_one skeleton");

    let [IrStmt::Return {
        value:
            Some(IrExpr::Binary {
                op: IrBinOp::Sub,
                lhs,
                rhs,
                ..
            }),
        ..
    }] = ir.body.as_slice()
    else {
        panic!("expected single return-sub statement");
    };
    assert!(matches!(
        lhs.as_ref(),
        IrExpr::Var { name, .. } if name == "value"
    ));
    assert!(matches!(
        rhs.as_ref(),
        IrExpr::LitInt { value: 1, spelling, .. } if spelling == "1"
    ));

    let rust = emit_rust_from_ir(&ir).expect("emit sub_one from lowered typed IR");

    assert!(rust.contains("pub fn sub_one(value: i32) -> i32"));
    assert!(
        rust.contains("return value.checked_sub(1i32).expect(\"signed subtraction overflow\");")
    );
    assert!(!rust.contains("crc32_update_byte"));
    assert_rust_snippet_compiles("typed-ir-sub-one", &rust);
}
