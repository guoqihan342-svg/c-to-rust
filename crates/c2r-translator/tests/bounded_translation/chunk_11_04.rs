#[cfg(feature = "clang-lowering-report")]
#[test]
fn clang_lowering_report_feature_blocks_retired_legacy_fallback_when_unavailable() {
    let source_root = unique_out_dir("clang-lowering-source");
    fs::create_dir_all(&source_root).unwrap();
    fs::write(
        source_root.join("add_one.c"),
        "int add_one(int value) { return value + 1; }\n",
    )
    .unwrap();
    let source_root = source_root.to_string_lossy().replace('\\', "/");
    let spec: SliceSpec = serde_json::from_value(serde_json::json!({
        "target_id": "demo",
        "slice_id": "add-one",
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
            "target_triple": "x86_64-pc-windows-msvc",
            "abi": "msvc",
            "compiler_command_source": "clang",
            "clang_available": true
        }
    }))
    .unwrap();
    let out_dir = unique_out_dir("clang-lowering-report");

    let manifest = write_translation_artifacts(&spec, &out_dir).unwrap();
    let report = json_file(out_dir.join("l3-add-one-clang-lowering-report.json"));

    if report["typed_ir_candidate"]["status"] == "generated" {
        assert_eq!(manifest.status, "generated");
    } else {
        assert_eq!(manifest.status, "blocked");
        let plan = json_file(out_dir.join("l3-add-one-auto-translation-plan.json"));
        assert_eq!(plan["errors"][0]["kind"], "legacy_fallback_retired");
        let events =
            fs::read_to_string(out_dir.join("l3-add-one-auto-translation-events.jsonl")).unwrap();
        assert!(events.contains("\"event\":\"translation_fallback\""));
        assert!(!events.contains("\"event\":\"translation_generated\""));
    }
    assert!(manifest
        .artifact_paths
        .iter()
        .any(|path| path.ends_with("l3-add-one-clang-lowering-report.json")));
    assert_eq!(report["schema_version"], 1);
    assert_eq!(report["artifact_kind"], "clang-lowering-report");
    assert_eq!(report["frontend"], "clang");
    assert_eq!(report["function_name"], "add_one");
    assert_eq!(report["claim_boundary"]["role"], "diagnostic_only");
    assert_eq!(report["claim_boundary"]["affects_manifest_status"], false);
    assert_eq!(report["claim_boundary"]["affects_semantic_pass"], false);
    assert_eq!(report["claim_boundary"]["authoritative_evidence"], false);
    assert!(["lowered", "unavailable", "blocked", "unsupported"]
        .contains(&report["status"].as_str().unwrap()));
    assert_eq!(report["lowering_report"]["function_name"], "add_one");
    assert_eq!(
        report["lowering_report"]["source_file"],
        report["source_file"]
    );
    assert!(report["typed_ir_candidate"].is_object());
    assert_eq!(report["typed_ir_candidate"]["semantic_pass"], false);
    assert!(report["typed_ir_candidate"]["readonly_globals"]
        .as_array()
        .is_some());
    if report["typed_ir_candidate"]["status"] == "generated" {
        assert_eq!(
            report["typed_ir_candidate"]["candidate_route"]["route"],
            "GenericTypedIr"
        );
        assert_eq!(
            report["typed_ir_candidate"]["candidate_route"]["candidate_generator"],
            "GenericTypedIrEmitter"
        );
    }
    assert_eq!(
        report["metadata"]["logical_source_file"],
        serde_json::json!("add_one.c")
    );
    assert!(report["diagnostics"].as_array().is_some());
    assert!(report["errors"].as_array().is_some());
    assert!(out_dir.join("l3-add-one-rust-draft.rs").exists());
}

#[cfg(feature = "clang-lowering-report")]
fn write_one_shot_fake_clang(out_dir: &std::path::Path) -> (PathBuf, PathBuf) {
    let fake_clang = out_dir.join(if cfg!(windows) {
        "fake-clang.cmd"
    } else {
        "fake-clang"
    });
    let count_file = out_dir.join("fake-clang-count.txt");
    let ast_file = out_dir.join("add_one_ast.json");
    fs::write(
        &ast_file,
        include_str!("../../fixtures/clang_ast/add_one_ast.json"),
    )
    .unwrap();

    if cfg!(windows) {
        fs::write(
            &fake_clang,
            format!(
                "@echo off\r\n\
if not exist \"{count}\" (\r\n\
  >\"{count}\" echo 1\r\n\
  type \"{ast}\"\r\n\
  exit /b 0\r\n\
)\r\n\
set /p CURRENT=<\"{count}\"\r\n\
set /a NEXT=%CURRENT%+1\r\n\
>\"{count}\" echo %NEXT%\r\n\
echo fake clang invoked more than once 1>&2\r\n\
exit /b 1\r\n",
                count = count_file.display(),
                ast = ast_file.display()
            ),
        )
        .unwrap();
    } else {
        fs::write(
            &fake_clang,
            format!(
                "#!/bin/sh\n\
if [ ! -f '{count}' ]; then\n\
  echo 1 > '{count}'\n\
  cat '{ast}'\n\
  exit 0\n\
fi\n\
current=$(cat '{count}')\n\
echo $((current + 1)) > '{count}'\n\
echo 'fake clang invoked more than once' >&2\n\
exit 1\n",
                count = count_file.display(),
                ast = ast_file.display()
            ),
        )
        .unwrap();
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            fs::set_permissions(&fake_clang, fs::Permissions::from_mode(0o755)).unwrap();
        }
    }

    (fake_clang, count_file)
}
