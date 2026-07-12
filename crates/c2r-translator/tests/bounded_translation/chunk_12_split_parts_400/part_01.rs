#[cfg(feature = "clang-lowering-report")]
#[test]
fn clang_lowering_report_records_signed_left_shift_and_negation_preconditions() {
    let source_root = unique_out_dir("signed-shl-neg-source");
    fs::create_dir_all(&source_root).unwrap();
    fs::write(
        source_root.join("signed_shift_negation.c"),
        "int signed_shift_negation(int value, int count) { return (value << count) + (-value); }\n",
    )
    .unwrap();
    let source_root = source_root.to_string_lossy().replace('\\', "/");
    let spec: SliceSpec = serde_json::from_value(serde_json::json!({
        "target_id": "demo",
        "slice_id": "signed-shl-neg",
        "source_commit": "1234567",
        "function_name": "signed_shift_negation",
        "c_source": "int signed_shift_negation(int value, int count) { return (value << count) + (-value); }",
        "fixture_hash": "fixture-sha",
        "source_root": source_root,
        "source_file": "signed_shift_negation.c",
        "source_file_hashes": {
            "signed_shift_negation.c": "source-file-sha"
        },
        "function_source_span": {
            "file": "signed_shift_negation.c",
            "line_start": 1,
            "line_end": 1,
            "byte_start": 0,
            "byte_end": 90,
            "sha256": "function-span-sha"
        },
        "build_profile": {
            "include_paths": [],
            "defines": [],
            "clang_ast_fixture": "crates/c2r-translator/fixtures/clang_ast/signed_shift_negation_ast.json",
            "target_triple": "x86_64-pc-windows-msvc",
            "abi": "msvc",
            "compiler_command_source": "clang",
            "clang_available": true
        }
    }))
    .unwrap();
    let out_dir = unique_out_dir("signed-shl-neg-artifacts");

    write_translation_artifacts(&spec, &out_dir).unwrap();
    let report = json_file(out_dir.join("l3-signed-shl-neg-clang-lowering-report.json"));
    let pointer_graph = json_file(out_dir.join("l3-signed-shl-neg-pointer-graph.json"));

    assert_eq!(report["typed_ir_candidate"]["status"], "generated");
    let codes = report["typed_ir_candidate"]["runtime_preconditions"]
        .as_array()
        .expect("runtime precondition evidence")
        .iter()
        .map(|item| item["code"].as_str().unwrap().to_string())
        .collect::<Vec<_>>();
    assert!(
        codes.contains(&"shift_count_in_range".to_string()),
        "{codes:?}"
    );
    assert!(
        codes.contains(&"signed_left_shift_no_overflow".to_string()),
        "{codes:?}"
    );
    assert!(
        codes.contains(&"signed_negation_no_overflow".to_string()),
        "{codes:?}"
    );
    // Pointer analysis ran on the accepted typed IR and found no pointer
    // surface, so the scalar slice keeps the not_applicable claim.
    assert_eq!(pointer_graph["status"], "not_applicable");
    assert_eq!(
        pointer_graph["not_applicable_reason"],
        "slice has no pointer surface"
    );
}

#[cfg(feature = "clang-lowering-report")]
#[test]
fn clang_lowering_report_artifact_sanitizes_absolute_host_paths() {
    let source_root = unique_out_dir("sanitized-report-source");
    fs::create_dir_all(source_root.join("inc")).unwrap();
    fs::write(
        source_root.join("add_one.c"),
        "int add_one(int value) { return value + 1; }\n",
    )
    .unwrap();
    let source_root = source_root.to_string_lossy().replace('\\', "/");
    let spec: SliceSpec = serde_json::from_value(serde_json::json!({
        "target_id": "demo",
        "slice_id": "sanitized-add-one",
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
            "include_paths": ["inc"],
            "defines": [],
            "clang_ast_fixture": "crates/c2r-translator/fixtures/clang_ast/add_one_ast.json",
            "target_triple": "x86_64-pc-windows-msvc",
            "abi": "msvc",
            "compiler_command_source": "clang",
            "clang_available": true
        }
    }))
    .unwrap();
    let out_dir = unique_out_dir("sanitized-report-artifacts");

    write_translation_artifacts(&spec, &out_dir).unwrap();
    let report = json_file(out_dir.join("l3-sanitized-add-one-clang-lowering-report.json"));

    assert_no_absolute_host_path_strings(&report, "$");
    assert_eq!(report["source_file"], "<host>/add_one.c");
    assert_eq!(report["lowering_report"]["source_file"], "<host>/add_one.c");
    let arguments = report["lowering_report"]["arguments"]
        .as_array()
        .expect("lowering report arguments");
    assert!(
        arguments.iter().any(|argument| argument == "-I<host>/inc"),
        "{arguments:?}"
    );
    assert!(report["metadata"]["source_root"]
        .as_str()
        .expect("lowering report source_root metadata")
        .starts_with("<host>"));
}

#[cfg(feature = "clang-lowering-report")]
#[test]
fn clang_lowering_report_uses_slice_spec_noalias_contract_for_copy_slice() {
    let spec: SliceSpec = serde_json::from_value(serde_json::json!({
        "target_id": "demo",
        "slice_id": "copy-i32-ptr-arith-policy",
        "source_commit": "demo-copy-i32-ptr-arith-20260625",
        "function_name": "copy_i32_ptr_arith",
        "c_source": "int copy_i32_ptr_arith(const int* values, int len, int* out) { for (int i = 0; i < len; i++) { *(out + i) = *(values + i); } return 0; }",
        "fixture_hash": "copy-i32-ptr-arith-fixture",
        "source_root": ".",
        "source_file": "validation/l2_slices/fixtures/copy-i32-ptr-arith.c",
        "source_file_hashes": {
            "validation/l2_slices/fixtures/copy-i32-ptr-arith.c": "91e829b92a6b5fe4f2872e9b27660e5914c56e301234a6fc0d525641dbf79c75"
        },
        "function_source_span": {
            "file": "validation/l2_slices/fixtures/copy-i32-ptr-arith.c",
            "line_start": 1,
            "line_end": 1,
            "byte_start": 0,
            "byte_end": 136,
            "sha256": "91e829b92a6b5fe4f2872e9b27660e5914c56e301234a6fc0d525641dbf79c75"
        },
        "c_boundary": {
            "pointer_contract": {
                "input_buffers": [
                    {"name": "values"}
                ],
                "output_pointers": [
                    {"name": "out"}
                ],
                "noalias_required": [
                    ["values", "out"]
                ]
            }
        },
        "build_profile": {
            "include_paths": [],
            "defines": [],
            "clang_ast_fixture": "crates/c2r-translator/fixtures/clang_ast/copy_i32_ptr_arith_ast.json",
            "target_triple": "x86_64-unknown-linux-gnu",
            "abi": "linux-gnu",
            "compiler_command_source": "clang",
            "clang_available": true
        }
    }))
    .unwrap();
    let out_dir = unique_out_dir("copy-i32-ptr-arith-noalias-policy");

    let manifest = write_translation_artifacts(&spec, &out_dir).unwrap();
    let report = json_file(out_dir.join(
        "l3-copy-i32-ptr-arith-policy-clang-lowering-report.json",
    ));
    let plan = json_file(out_dir.join(
        "l3-copy-i32-ptr-arith-policy-auto-translation-plan.json",
    ));
    let rust_draft = fs::read_to_string(
        out_dir.join("l3-copy-i32-ptr-arith-policy-rust-draft.rs"),
    )
    .unwrap();

    assert_eq!(manifest.status, "generated");
    assert_eq!(plan["status"], "generated");
    assert_eq!(report["typed_ir_candidate"]["status"], "generated");
    assert_eq!(
        report["typed_ir_candidate"]["candidate_route"]["route"],
        "GenericTypedIr"
    );
    assert!(rust_draft.contains(
        "pub fn copy_i32_ptr_arith(values: &[i32], len: i32, mut out: &mut [i32]) -> i32"
    ));
    assert!(rust_draft.contains("out[i as usize] = values[i as usize];"));
}

#[test]
fn blocked_translation_marks_pointer_graph_artifact_not_evaluated() {
    let spec = SliceSpec {
        target_id: "demo".to_string(),
        slice_id: "blocked-pointer-slice".to_string(),
        source_commit: "1234567".to_string(),
        function_name: "classify".to_string(),
        c_source:
            "int classify(int *value) { switch (*value) { case 0: return 0; default: return 1; } }"
                .to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(true),
        ..SliceSpec::default()
    };
    let out_dir = unique_out_dir("blocked-pointer-graph");

    let manifest = write_translation_artifacts(&spec, &out_dir).unwrap();
    let pointer_graph = json_file(out_dir.join("l3-blocked-pointer-slice-pointer-graph.json"));

    assert_eq!(manifest.status, "blocked");
    // Translation is blocked before pointer analysis runs, so the artifact
    // must not claim "no pointer surface" for a slice with pointer parameters.
    assert_eq!(pointer_graph["status"], "not_evaluated");
    assert_eq!(
        pointer_graph["not_evaluated_reason"],
        "pointer analysis did not run (translation blocked)"
    );
    assert_eq!(pointer_graph["not_applicable_reason"], Value::Null);
    assert!(pointer_graph["pointer_graph"]["nodes"]
        .as_array()
        .unwrap()
        .is_empty());
}
