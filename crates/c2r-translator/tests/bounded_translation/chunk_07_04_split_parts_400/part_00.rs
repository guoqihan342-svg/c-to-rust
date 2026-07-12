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
