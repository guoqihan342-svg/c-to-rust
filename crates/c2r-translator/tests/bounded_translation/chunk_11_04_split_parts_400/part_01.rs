#[test]
fn missing_clang_profile_records_type_uncertainty() {
    let spec = SliceSpec {
        target_id: "demo".to_string(),
        slice_id: "ambiguous".to_string(),
        source_commit: "1234567".to_string(),
        function_name: "uses_alias".to_string(),
        c_source: "alias_t uses_alias(alias_t value) { return value; }".to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(false),
        ..SliceSpec::default()
    };
    let out_dir = unique_out_dir("ambiguous");

    let manifest = write_translation_artifacts(&spec, &out_dir).unwrap();

    assert_eq!(manifest.status, "blocked");
    let rust_draft = fs::read_to_string(out_dir.join("l3-ambiguous-rust-draft.rs")).unwrap();
    assert!(rust_draft.is_empty(), "{rust_draft}");
    let type_map = json_file(out_dir.join("l3-ambiguous-type-map.json"));
    assert_eq!(type_map["status"], "uncertain");
    assert!(
        type_map["type_map"]["uncertainties"]
            .as_array()
            .expect("type map uncertainties")
            .iter()
            .any(|item| item["reason"]
                .as_str()
                .expect("uncertainty reason")
                .contains("clang-backed type extraction")),
        "{:?}",
        type_map["type_map"]["uncertainties"]
    );
    let plan = json_file(out_dir.join("l3-ambiguous-auto-translation-plan.json"));
    assert_eq!(plan["status"], "blocked");
    assert!(
        plan["errors"]
            .as_array()
            .expect("plan errors")
            .iter()
            .any(|error| error["kind"] == "type_uncertainty"),
        "{:?}",
        plan["errors"]
    );
    let events =
        fs::read_to_string(out_dir.join("l3-ambiguous-auto-translation-events.jsonl")).unwrap();
    assert!(!events.contains("\"event\":\"translation_generated\""));
}

#[test]
fn writes_translation_artifacts_for_l3_manifest_binding() {
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
    let out_dir = unique_out_dir("add-one");

    let manifest = write_translation_artifacts(&spec, &out_dir).unwrap();

    assert_eq!(manifest.target_id, "demo");
    assert_eq!(manifest.slice_id, "add-one");
    for path in [
        "l3-add-one-auto-translation-plan.json",
        "l3-add-one-auto-translation-events.jsonl",
        "l3-add-one-type-map.json",
        "l3-add-one-cfg.json",
        "l3-add-one-pointer-graph.json",
        "l3-add-one-ai-candidate-manifest.json",
        "l3-add-one-blocked-repairs.json",
        "l3-add-one-rust-draft.rs",
    ] {
        assert!(out_dir.join(path).exists(), "{path}");
    }
    let plan = fs::read_to_string(out_dir.join("l3-add-one-auto-translation-plan.json")).unwrap();
    assert!(plan.contains("\"status\": \"blocked\""));
    assert!(plan.contains("\"kind\": \"legacy_"));
    assert!(plan.contains("_retired\""));
    let events =
        fs::read_to_string(out_dir.join("l3-add-one-auto-translation-events.jsonl")).unwrap();
    assert!(!events.contains("\"event\":\"translation_generated\""));
}

#[cfg(not(feature = "clang-frontend"))]
#[test]
fn default_translation_artifacts_do_not_emit_clang_dry_run() {
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
    let out_dir = unique_out_dir("no-clang-dry-run");

    let manifest = write_translation_artifacts(&spec, &out_dir).unwrap();

    assert!(!out_dir
        .join("l3-real-fdb-calc-crc32-clang-dry-run.json")
        .exists());
    assert!(!out_dir
        .join("l3-real-fdb-calc-crc32-clang-lowering-report.json")
        .exists());
    assert!(!manifest
        .artifact_paths
        .iter()
        .any(|path| path.ends_with("l3-real-fdb-calc-crc32-clang-dry-run.json")));
    assert!(!manifest
        .artifact_paths
        .iter()
        .any(|path| path.ends_with("l3-real-fdb-calc-crc32-clang-lowering-report.json")));
}
