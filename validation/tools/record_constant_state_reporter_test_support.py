from __future__ import annotations

from pathlib import Path
from typing import Any

from validation.tools.record_constant_state_test_support import (
    REPO_ROOT,
    build_constant_state_spec,
    load_auto_migrate_module,
    renamed_rust_draft,
    sha256_file,
    translation_carrier,
    write_json,
)


def build_reporter_layout(workspace: Path) -> dict[str, object]:
    relative_prefix = workspace.relative_to(REPO_ROOT).as_posix() + "/"
    spec, fixture = build_constant_state_spec(path_prefix=relative_prefix)
    fixture_path = workspace / "fixtures" / "constant-state-cases.json"
    source_root = workspace / "upstream"
    source_path = source_root / "routing.c"
    spec_path = workspace / "specs" / "constant-state.json"
    auto_dir = workspace / "evidence" / "auto"
    output_dir = workspace / "evidence" / "accepted"
    for directory in (fixture_path.parent, source_root, spec_path.parent, auto_dir):
        directory.mkdir(parents=True, exist_ok=True)
    write_json(fixture_path, fixture)
    source_path.write_bytes(spec["c_source"].encode("utf-8"))
    spec["fixture_hash"] = sha256_file(fixture_path)
    spec["fixture_contract"]["hash"] = spec["fixture_hash"]
    spec["source_root"] = source_root.relative_to(REPO_ROOT).as_posix()
    spec["source_file"] = source_path.name
    spec["source_file_hashes"] = {source_path.name: sha256_file(source_path)}
    spec["translation_carrier"] = translation_carrier(spec["c_source"], source_path.name)
    write_json(spec_path, spec)

    module = load_auto_migrate_module()
    oracle = module.generate_oracle_harness_draft(spec, auto_dir, False)
    if oracle["compile_execution"]["status"] != "compile_succeeded_not_oracle":
        raise AssertionError(oracle["compile_execution"])
    draft_path = auto_dir / "l3-clear-nested-marker-rust-draft.rs"
    draft_path.write_text(renamed_rust_draft(), encoding="utf-8")
    write_json(auto_dir / "l3-clear-nested-marker-auto-translation-plan.json", plan_payload(spec))
    replay = module.generate_rust_replay_test_draft(spec, auto_dir, spec_path)
    rust_check, _ = module.run_rust_check(auto_dir, False, spec)
    if rust_check["status"] != "passed":
        raise AssertionError(rust_check)
    replay = module.run_generated_rust_replay(spec, auto_dir, replay, rust_check)
    if replay["status"] != "passed":
        raise AssertionError(replay)

    source_hash = sha256_file(source_path)
    common = {
        "schema_version": 1,
        "target_id": spec["target_id"],
        "slice_id": spec["slice_id"],
        "source_commit": spec["source_commit"],
        "fixture_hash": spec["fixture_hash"],
        "translation_carrier": spec["translation_carrier"],
    }
    write_json(
        auto_dir / "l3-clear-nested-marker-translator-input.json",
        {
            **common, "c_source": spec["c_source"], "function_name": spec["function_name"],
            "source_root": spec["source_root"], "source_file": spec["source_file"],
            "source_file_hashes": {source_path.name: source_hash},
            "build_profile": {"clang_ast_fixture": None},
        },
    )
    write_json(
        auto_dir / "l3-clear-nested-marker-clang-lowering-report.json",
        {
            **common, "status": "lowered", "function_name": spec["function_name"],
            "lowering_report": {"frontend": "clang_slice_source"},
            "metadata": {
                "source_root": spec["source_root"], "logical_source_file": spec["source_file"],
                "source_file_hashes": {source_path.name: source_hash}, "clang_ast_fixture": None,
            },
            "typed_ir_candidate": {
                "status": "generated", "rust_draft_generated": True, "semantic_pass": False,
                "rust_draft_sha256": sha256_file(draft_path),
            },
        },
    )
    return {
        "emit_args": {
            "slice_spec": spec_path, "auto_evidence_dir": auto_dir,
            "output_dir": output_dir, "repo_root": REPO_ROOT,
        },
        "output_dir": output_dir,
    }


def plan_payload(spec: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1, "target_id": spec["target_id"], "slice_id": spec["slice_id"],
        "source_commit": spec["source_commit"], "fixture_hash": spec["fixture_hash"],
        "translation_carrier": spec["translation_carrier"], "status": "generated",
        "translation_source": {"selected": "clang-lowered-typed-ir"},
        "translation_summary": {
            "translation_rule_ids": ["clang-lowered-typed-ir"], "call_expressions": []
        },
    }
