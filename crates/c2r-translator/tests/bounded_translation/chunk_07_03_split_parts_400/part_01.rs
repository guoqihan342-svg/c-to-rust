#[test]
fn slice_spec_legacy_compile_database_reference_blocks_translation() {
    let spec: SliceSpec = serde_json::from_value(serde_json::json!({
        "target_id": "demo",
        "slice_id": "add-one",
        "source_commit": "1234567",
        "function_name": "add_one",
        "c_source": "int add_one(int value) { return value + 1; }",
        "fixture_hash": "fixture-sha",
        "source_root": "C:/src/project",
        "source_file": "src/add_one.c",
        "source_files": [
            {
                "path": "src/add_one.c",
                "role": "source",
                "sha256": "source-file-sha"
            }
        ],
        "source_file_hashes": {
            "src/add_one.c": "source-file-sha"
        },
        "function_source_span": {
            "file": "src/add_one.c",
            "line_start": 10,
            "line_end": 12,
            "byte_start": 100,
            "byte_end": 160,
            "sha256": "function-span-sha"
        },
        "compile_commands": "build/compile_commands.json",
        "build_profile": {
            "include_paths": [],
            "defines": [],
            "target_triple": "x86_64-unknown-linux-gnu",
            "abi": "linux-gnu",
            "compiler_command_source": "compile_commands.json",
            "clang_available": true
        }
    }))
    .unwrap();

    assert_eq!(spec.source_root.as_deref(), Some("C:/src/project"));
    assert_eq!(spec.source_file.as_deref(), Some("src/add_one.c"));
    assert_eq!(spec.source_files[0].path, "src/add_one.c");
    assert_eq!(
        spec.source_file_hashes
            .get("src/add_one.c")
            .map(String::as_str),
        Some("source-file-sha")
    );
    assert_eq!(
        spec.function_source_span
            .as_ref()
            .map(|span| span.sha256.as_str()),
        Some("function-span-sha")
    );
    assert_eq!(
        spec.compile_commands.as_deref(),
        Some("build/compile_commands.json")
    );

    let out_dir = unique_out_dir("real-tu-metadata");

    write_translation_artifacts(&spec, &out_dir).unwrap();

    let plan = json_file(out_dir.join("l3-add-one-auto-translation-plan.json"));
    let plan_errors = plan["errors"].as_array().expect("plan errors");
    assert_eq!(plan_errors.len(), 1, "unexpected errors: {plan_errors:?}");
    assert_eq!(plan_errors[0]["kind"], "unhashed_compile_database");
    let rust_draft = fs::read_to_string(out_dir.join("l3-add-one-rust-draft.rs")).unwrap();
    assert!(rust_draft.is_empty(), "unhashed real-TU input emitted Rust");
}

#[cfg(feature = "clang-frontend")]
#[test]
fn clang_parse_spec_dry_run_uses_real_tu_metadata_without_libclang() {
    let spec: SliceSpec = serde_json::from_value(serde_json::json!({
        "target_id": "flashdb",
        "slice_id": "real-fdb-calc-crc32",
        "source_commit": "93d1755",
        "function_name": "fdb_calc_crc32",
        "c_source": "uint32_t fdb_calc_crc32(uint32_t crc, const void *buf, size_t size) { return crc; }",
        "fixture_hash": "fixture-sha",
        "source_root": "C:/src/FlashDB",
        "source_file": "src/fdb_utils.c",
        "source_files": [
            {
                "path": "src/fdb_utils.c",
                "role": "source",
                "sha256": "source-file-sha"
            }
        ],
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
            "include_paths": ["inc", "tests"],
            "defines": ["FDB_USING_FILE_POSIX_MODE"],
            "target_triple": "x86_64-unknown-linux-gnu",
            "abi": "linux-gnu",
            "compiler_command_source": "C:/src/FlashDB/CMakeLists.txt",
            "clang_available": false
        }
    }))
    .unwrap();

    let parse_spec = ClangParseSpec::from_slice_spec(&spec).expect("clang parse spec");
    let dry_run = parse_spec.dry_run();

    assert_eq!(parse_spec.source_root, PathBuf::from("C:/src/FlashDB"));
    assert_eq!(parse_spec.source_file, PathBuf::from("src/fdb_utils.c"));
    assert_eq!(parse_spec.function_name, "fdb_calc_crc32");
    assert_eq!(
        parse_spec.source_file_hashes["src/fdb_utils.c"],
        "source-file-sha"
    );
    assert_eq!(
        parse_spec
            .function_source_span
            .as_ref()
            .map(|span| span.sha256.as_str()),
        Some("function-span-sha")
    );
    assert!(parse_spec.compile_commands.is_none());
    assert_eq!(dry_run.status, "diagnostic_only");
    assert_eq!(dry_run.claim_boundary.role, "diagnostic_only");
    assert_eq!(dry_run.active_frontend.kind, "clang_ast_dump_json");
    assert_eq!(
        dry_run.active_frontend.command,
        "clang -Xclang -ast-dump=json -fsyntax-only"
    );
    assert_eq!(dry_run.active_frontend.required_env, vec!["CLANG_PATH"]);
    assert!(!dry_run.active_frontend.uses_libclang);
    assert_eq!(
        dry_run.arguments,
        vec![
            "-IC:/src/FlashDB/inc".to_string(),
            "-IC:/src/FlashDB/tests".to_string(),
            "-DFDB_USING_FILE_POSIX_MODE".to_string(),
        ]
    );
    assert!(dry_run
        .diagnostics
        .contains(&"LIBCLANG_PATH is observed only as ignored legacy metadata; active lowering uses clang AST dump JSON via CLANG_PATH".to_string()));
}
#[cfg(feature = "clang-frontend")]
#[test]
fn clang_parse_spec_preserves_target_abi_profile() {
    let spec: SliceSpec = serde_json::from_value(serde_json::json!({
        "target_id": "demo",
        "slice_id": "target-abi-width",
        "source_commit": "1234567",
        "function_name": "identity_size",
        "c_source": "size_t identity_size(size_t value) { return value; }",
        "fixture_hash": "fixture-sha",
        "source_root": "C:/src/project",
        "source_file": "src/size.c",
        "source_file_hashes": {
            "src/size.c": "source-file-sha"
        },
        "function_source_span": {
            "file": "src/size.c",
            "line_start": 1,
            "line_end": 1,
            "byte_start": 0,
            "byte_end": 48,
            "sha256": "function-span-sha"
        },
        "build_profile": {
            "include_paths": [],
            "defines": [],
            "target": {
                "triple_or_abi": "x86_64-unknown-linux-gnu",
                "endianness": "little",
                "int_width": 32,
                "int_align": 32,
                "char_width": 8,
                "char_align": 8,
                "plain_char_signed": true,
                "short_width": 16,
                "short_align": 16,
                "long_width": 64,
                "long_align": 64,
                "long_long_width": 64,
                "long_long_align": 64,
                "pointer_width": 64,
                "pointer_align": 64
            },
            "target_triple": "x86_64-unknown-linux-gnu",
            "abi": "x86_64-unknown-linux-gnu",
            "compiler_command_source": "unit-test",
            "clang_available": true
        }
    }))
    .unwrap();

    let parse_spec = ClangParseSpec::from_slice_spec(&spec).expect("clang parse spec");
    let target_abi = parse_spec.target_abi.expect("target ABI profile");

    assert_eq!(target_abi.triple_or_abi, "x86_64-unknown-linux-gnu");
    assert_eq!(target_abi.int_width, 32);
    assert_eq!(target_abi.int_align, 32);
    assert_eq!(target_abi.char_width, 8);
    assert_eq!(target_abi.char_align, 8);
    assert_eq!(target_abi.plain_char_signed, Some(true));
    assert_eq!(target_abi.short_width, 16);
    assert_eq!(target_abi.short_align, 16);
    assert_eq!(target_abi.long_width, 64);
    assert_eq!(target_abi.long_align, 64);
    assert_eq!(target_abi.long_long_width, 64);
    assert_eq!(target_abi.long_long_align, 64);
    assert_eq!(target_abi.pointer_width, 64);
    assert_eq!(target_abi.pointer_align, 64);
}

#[cfg(feature = "clang-frontend")]
#[test]
fn clang_parse_spec_resolves_known_target_abi_profile_from_build_metadata() {
    let spec: SliceSpec = serde_json::from_value(serde_json::json!({
        "target_id": "demo",
        "slice_id": "target-abi-from-triple",
        "source_commit": "1234567",
        "function_name": "identity_size",
        "c_source": "size_t identity_size(size_t value) { return value; }",
        "fixture_hash": "fixture-sha",
        "source_root": "C:/src/project",
        "source_file": "src/size.c",
        "source_file_hashes": {
            "src/size.c": "source-file-sha"
        },
        "function_source_span": {
            "file": "src/size.c",
            "line_start": 1,
            "line_end": 1,
            "byte_start": 0,
            "byte_end": 48,
            "sha256": "function-span-sha"
        },
        "build_profile": {
            "include_paths": [],
            "defines": [],
            "target_triple": "x86_64-pc-windows-msvc",
            "abi": "msvc",
            "compiler_command_source": "unit-test",
            "clang_available": true
        }
    }))
    .unwrap();

    let parse_spec = ClangParseSpec::from_slice_spec(&spec).expect("clang parse spec");
    let target_abi = parse_spec
        .target_abi
        .expect("known target metadata should resolve to ABI profile");

    assert_eq!(target_abi.triple_or_abi, "x86_64-pc-windows-msvc");
    assert_eq!(target_abi.int_width, 32);
    assert_eq!(target_abi.long_width, 32);
    assert_eq!(target_abi.long_long_width, 64);
    assert_eq!(target_abi.pointer_width, 64);
    assert_eq!(target_abi.endianness.as_deref(), Some("little"));
}
