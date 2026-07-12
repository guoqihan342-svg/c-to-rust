#[cfg(feature = "clang-lowering-report")]
#[test]
fn clang_lowering_report_reuses_translation_report_without_second_clang_invocation() {
    let source_root = unique_out_dir("clang-lowering-single-run-source");
    fs::create_dir_all(&source_root).unwrap();
    fs::write(
        source_root.join("add_one.c"),
        "int add_one(int value) { return value + 1; }\n",
    )
    .unwrap();
    let out_dir = unique_out_dir("clang-lowering-single-run");
    fs::create_dir_all(&out_dir).unwrap();
    let (fake_clang, count_file) = write_one_shot_fake_clang(&out_dir);
    let _clang_path_guard = EnvVarGuard::set_path("CLANG_PATH", &fake_clang);
    let source_root = source_root.to_string_lossy().replace('\\', "/");
    let spec: SliceSpec = serde_json::from_value(serde_json::json!({
        "target_id": "demo",
        "slice_id": "add-one-single-run",
        "source_commit": "1234567",
        "function_name": "add_one",
        "c_source": "int add_one(int value) { return value + 1; }",
        "fixture_hash": "fixture-sha",
        "source_root": source_root,
        "source_file": "add_one.c",
        "source_file_hashes": {
            "add_one.c": "source-file-sha"
        },
        "function_source_span": {
            "file": "add_one.c",
            "line_start": 1,
            "line_end": 1,
            "byte_start": 0,
            "byte_end": 43,
            "sha256": "function-span-sha"
        },
        "build_profile": {
            "include_paths": [],
            "defines": [],
            "target_triple": "x86_64-unknown-linux-gnu",
            "abi": "linux-gnu",
            "compiler_command_source": "clang",
            "clang_available": true
        }
    }))
    .unwrap();

    let manifest = write_translation_artifacts(&spec, &out_dir).unwrap();
    let invocation_count = fs::read_to_string(&count_file).unwrap();
    let report = json_file(out_dir.join("l3-add-one-single-run-clang-lowering-report.json"));
    let rust = fs::read_to_string(out_dir.join("l3-add-one-single-run-rust-draft.rs")).unwrap();

    assert_eq!(
        invocation_count.trim(),
        "1",
        "clang lowering report must reuse the translation lowering instead of launching clang twice"
    );
    assert_eq!(manifest.status, "generated");
    assert!(manifest
        .artifact_paths
        .iter()
        .any(|path| path.ends_with("l3-add-one-single-run-clang-lowering-report.json")));
    assert_eq!(report["status"], "lowered");
    assert_eq!(report["typed_ir_candidate"]["status"], "generated");
    assert!(rust.contains("pub fn add_one(value: i32) -> i32"));
}

#[cfg(feature = "clang-lowering-report")]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_lowering_report_feature_can_drive_rust_draft_from_clang_lowered_ir_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let _clang_path_guard = EnvVarGuard::set_path("CLANG_PATH", &clang_path);
    let source_root = unique_out_dir("clang-lowered-rust-draft-source");
    fs::create_dir_all(source_root.join("src")).unwrap();
    fs::create_dir_all(source_root.join("inc")).unwrap();
    let table_values = repeated_c_u32_initializer(256, "0U");
    fs::write(
        source_root.join("src/fdb_utils.c"),
        format!(
            "#include <stdint.h>\n#include <stddef.h>\nstatic const uint32_t crc32_table[256] = {{ {table_values} }};\nuint32_t fdb_calc_crc32(uint32_t crc, const void *buf, size_t size) {{\n    const uint8_t *p;\n    p = (const uint8_t *)buf;\n    crc = crc ^ ~0U;\n    while (size--) {{\n        crc = crc32_table[(crc ^ *p++) & 0xFF] ^ (crc >> 8);\n    }}\n    return crc ^ ~0U;\n}}\n"
        ),
    )
    .unwrap();
    let source_root = source_root.to_string_lossy().replace('\\', "/");
    let spec: SliceSpec = serde_json::from_value(serde_json::json!({
        "target_id": "flashdb",
        "slice_id": "real-fdb-calc-crc32",
        "source_commit": "93d1755",
        "function_name": "fdb_calc_crc32",
        "c_source": "uint32_t fdb_calc_crc32(uint32_t crc, const void *buf, size_t size) { return crc; }",
        "fixture_hash": "fixture-sha",
        "source_root": source_root,
        "source_file": "src/fdb_utils.c",
        "source_file_hashes": {
            "src/fdb_utils.c": "source-file-sha"
        },
        "function_source_span": {
            "file": "src/fdb_utils.c",
            "line_start": 4,
            "line_end": 12,
            "byte_start": 86,
            "byte_end": 357,
            "sha256": "function-span-sha"
        },
        "build_profile": {
            "include_paths": ["inc"],
            "defines": [],
            "target_triple": "x86_64-pc-windows-msvc",
            "abi": "msvc",
            "compiler_command_source": "clang",
            "clang_available": true
        }
    }))
    .unwrap();
    let out_dir = unique_out_dir("clang-lowered-rust-draft");

    let manifest = write_translation_artifacts(&spec, &out_dir).unwrap();
    let plan = json_file(out_dir.join("l3-real-fdb-calc-crc32-auto-translation-plan.json"));
    let type_map = json_file(out_dir.join("l3-real-fdb-calc-crc32-type-map.json"));
    let cfg = json_file(out_dir.join("l3-real-fdb-calc-crc32-cfg.json"));
    let pointer_graph = json_file(out_dir.join("l3-real-fdb-calc-crc32-pointer-graph.json"));
    let report = json_file(out_dir.join("l3-real-fdb-calc-crc32-clang-lowering-report.json"));
    let rust = fs::read_to_string(out_dir.join("l3-real-fdb-calc-crc32-rust-draft.rs")).unwrap();

    assert_eq!(manifest.status, "generated");
    assert_eq!(report["typed_ir_candidate"]["status"], "generated");
    assert_eq!(
        report["typed_ir_candidate"]["candidate_route"]["route"],
        "GenericTypedIr"
    );
    assert_eq!(
        report["typed_ir_candidate"]["candidate_route"]["candidate_generator"],
        "GenericTypedIrEmitter"
    );
    assert_eq!(report["typed_ir_candidate"]["semantic_pass"], false);
    assert_eq!(
        report["typed_ir_candidate"]["readonly_globals"][0]["name"],
        "crc32_table"
    );
    assert_eq!(
        report["typed_ir_candidate"]["readonly_globals"][0]["array_len"],
        256
    );
    assert_eq!(
        report["typed_ir_candidate"]["readonly_globals"][0]["init_kind"],
        "integer_array"
    );
    assert_eq!(
        report["typed_ir_candidate"]["readonly_globals"][0]["value_count"],
        256
    );
    assert!(report["typed_ir_candidate"]["runtime_preconditions"]
        .as_array()
        .unwrap()
        .iter()
        .any(|precondition| precondition["code"] == "shift_count_in_range"));
    assert!(rust.contains("const CRC32_TABLE: [u32; 256] = [0u32, 0u32"));
    assert!(
        rust.contains("pub fn fdb_calc_crc32(mut crc: u32, buf: &[u8], mut size: usize) -> u32")
    );
    assert!(rust.contains("CRC32_TABLE[((crc ^ (byte0 as u32)) &"));
    assert!(rust.contains("(255i32 as u32)") || rust.contains("255u32"));
    assert!(rust.contains("^ crc.checked_shr("));
    assert!(!rust.contains("crc32_update_byte"));
    assert!(!rust.contains("return crc;"));
    assert!(plan["plan"]["translation_rule_ids"]
        .as_array()
        .unwrap()
        .contains(&serde_json::json!("clang-lowered-typed-ir")));
    assert!(plan["plan"]["translation_rule_ids"]
        .as_array()
        .unwrap()
        .contains(&serde_json::json!("byte-cursor-loop")));
    assert!(!plan["plan"]["translation_rule_ids"]
        .as_array()
        .unwrap()
        .contains(&serde_json::json!("crc32-byte-cursor-loop")));
    assert!(type_map["type_map"]["mappings"]
        .as_array()
        .unwrap()
        .iter()
        .any(|mapping| mapping["symbol"] == "buf" && mapping["rust_type"] == "&[u8]"));
    assert!(cfg["cfg"]["functions"][0]["blocks"][0]["statement_kinds"]
        .as_array()
        .unwrap()
        .contains(&serde_json::json!("while")));
    assert_eq!(pointer_graph["status"], "recorded");
    assert!(pointer_graph["pointer_graph"]["nodes"]
        .as_array()
        .unwrap()
        .iter()
        .any(|node| {
            node["id"] == "buf"
                && node["role"] == "borrowed_input"
                && node["rust_boundary"] == "&[u8]"
                && node["read_effects"]
                    .as_array()
                    .unwrap()
                    .contains(&serde_json::json!("*p++"))
                && node["boundary_decisions"]
                    .as_array()
                    .unwrap()
                    .contains(&serde_json::json!("byte_cursor_post_increment_read"))
        }));
}

#[cfg(feature = "clang-frontend")]
#[test]
fn clang_frontend_dry_run_artifact_records_metadata_errors_and_legacy_retired_status() {
    let spec = SliceSpec {
        target_id: "demo".to_string(),
        slice_id: "add-one".to_string(),
        source_commit: "1234567".to_string(),
        function_name: "add_one".to_string(),
        c_source: "int add_one(int value) { return value + 1; }".to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(true),
        ..SliceSpec::default()
    };
    let out_dir = unique_out_dir("clang-dry-run-blocked");

    let manifest = write_translation_artifacts(&spec, &out_dir).unwrap();
    let dry_run = json_file(out_dir.join("l3-add-one-clang-dry-run.json"));

    assert_eq!(manifest.status, "blocked");
    assert_eq!(dry_run["status"], "blocked");
    assert_eq!(dry_run["errors"][0]["kind"], "missing_source_root");
    assert_eq!(
        dry_run["errors"][0]["message"],
        "clang frontend dry-run requires source_root"
    );
    assert!(out_dir.join("l3-add-one-rust-draft.rs").exists());
    let plan = json_file(out_dir.join("l3-add-one-auto-translation-plan.json"));
    assert!(plan["errors"][0]["kind"]
        .as_str()
        .unwrap()
        .starts_with("legacy_"));
}

#[cfg(feature = "clang-lowering-report")]
fn assert_no_absolute_host_path_strings(value: &Value, json_path: &str) {
    match value {
        Value::String(text) => {
            let bytes = text.as_bytes();
            let has_drive_path = (0..bytes.len().saturating_sub(2)).any(|index| {
                bytes[index].is_ascii_alphabetic()
                    && bytes[index + 1] == b':'
                    && (bytes[index + 2] == b'/' || bytes[index + 2] == b'\\')
            });
            assert!(
                !has_drive_path,
                "absolute Windows host path leaked at {json_path}: {text}"
            );
            assert!(
                !text.starts_with('/'),
                "absolute POSIX host path leaked at {json_path}: {text}"
            );
        }
        Value::Array(items) => {
            for (index, item) in items.iter().enumerate() {
                assert_no_absolute_host_path_strings(item, &format!("{json_path}[{index}]"));
            }
        }
        Value::Object(entries) => {
            for (key, item) in entries {
                assert_no_absolute_host_path_strings(item, &format!("{json_path}.{key}"));
            }
        }
        _ => {}
    }
}
