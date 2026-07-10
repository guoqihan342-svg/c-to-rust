from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from validation.tools._translation_carrier_reporter import emit_reports
from validation.tools._translation_carrier_reporter.contract import ReporterError, U32_MAX


class TranslationCarrierReporterTests(unittest.TestCase):
    def test_renamed_non_project_fixture_emits_name_independent_reports(self) -> None:
        with tempfile.TemporaryDirectory(prefix="carrier-reporter-") as tmp:
            layout = build_renamed_layout(Path(tmp))
            paths = emit_reports(**layout["emit_args"])

            self.assertEqual(set(paths), {"c_oracle", "rust_report", "diff", "negative_diff"})
            reports = {name: load_json(path) for name, path in paths.items()}
            for report in reports.values():
                self.assertEqual(report["target_id"], "orbit-store")
                self.assertEqual(report["slice_id"], "reserve-slot-sentinel")
                self.assertEqual(report["case_count"], 4)
                self.assertEqual(report["claim_boundary"]["scope"], "source_fragment_only")
                self.assertFalse(report["claim_boundary"]["whole_function_semantics_verified"])
                self.assertFalse(report["claim_boundary"]["external_callee_semantics_verified"])

            c_oracle = reports["c_oracle"]
            self.assertEqual(c_oracle["status"], "passed")
            self.assertEqual(c_oracle["provenance"]["binding_mode"], "executed_harness")
            self.assertEqual(c_oracle["cases"][0]["is_exhausted"], True)
            self.assertEqual(c_oracle["cases"][3]["assigned_slot"], 9001)
            self.assertEqual(c_oracle["cases"][3]["forwarded_values"], [77, 88, 144])

            self.assertEqual(reports["rust_report"]["status"], "passed")
            self.assertEqual(reports["diff"]["status"], "passed")
            self.assertIsNone(reports["diff"]["first_mismatch"])
            negative = reports["negative_diff"]
            self.assertEqual(negative["status"], "expected_failed")
            self.assertTrue(negative["mutation_detected"])
            self.assertEqual(
                negative["partition_detection"]["comparison_true_case_ids"],
                ["capacity-marker"],
            )
            self.assertEqual(
                negative["partition_detection"]["comparison_false_case_ids"],
                ["zero-slot", "small-slot", "wide-inputs"],
            )
            emitted_text = "\n".join(
                path.read_text(encoding="utf-8", errors="replace")
                for path in sorted(output_dir_files(layout["emit_args"]["output_dir"]))
            )
            self.assertNotIn(str(Path(tmp).resolve()), emitted_text)
            self.assertNotIn("/tmp/", emitted_text)
            self.assertNotRegex(emitted_text, r"[A-Za-z]:[\\/]")

    def test_missing_runtime_artifact_fails_before_writing_reports(self) -> None:
        with tempfile.TemporaryDirectory(prefix="carrier-reporter-") as tmp:
            layout = build_renamed_layout(Path(tmp))
            layout["lowering_path"].unlink()
            with self.assertRaisesRegex(ReporterError, "required runtime artifact is missing"):
                emit_reports(**layout["emit_args"])
            self.assertFalse(layout["emit_args"]["output_dir"].exists())

    def test_generated_rust_replay_tampering_fails_closed(self) -> None:
        mutations = (
            "generated_draft_replay_pass",
            "rust_draft_sha",
            "rust_draft_path",
            "rust_check_external_semantics",
            "run_returncode",
            "replay_host_path",
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory(
                prefix="carrier-reporter-"
            ) as tmp:
                layout = build_renamed_layout(Path(tmp))
                apply_replay_mutation(layout, mutation)
                with self.assertRaises((ReporterError, OSError)):
                    emit_reports(**layout["emit_args"])
                self.assertFalse(layout["emit_args"]["output_dir"].exists())

    def test_reporter_implementation_contains_no_project_or_function_name_switches(self) -> None:
        tool_dir = Path(__file__).parent / "_translation_carrier_reporter"
        implementation = "\n".join(
            path.read_text(encoding="utf-8") for path in sorted(tool_dir.glob("*.py"))
        )
        implementation += (Path(__file__).parent / "translation_carrier_reporter.py").read_text(
            encoding="utf-8"
        )
        for forbidden in ("flashdb", "new_kv", "alloc_kv", "real-fdb"):
            self.assertNotIn(forbidden, implementation.lower())


def build_renamed_layout(root: Path) -> dict[str, object]:
    fixture_path = root / "fixtures" / "reservation-cases.json"
    source_path = root / "upstream" / "src" / "reservation.c"
    spec_path = root / "specs" / "reservation-slice.json"
    auto_dir = root / "evidence" / "auto" / "reserve-slot-sentinel"
    output_dir = root / "evidence" / "accepted"
    for directory in (fixture_path.parent, source_path.parent, spec_path.parent, auto_dir):
        directory.mkdir(parents=True, exist_ok=True)

    fields = ["is_exhausted", "assigned_slot", "invocation_count", "forwarded_values"]
    raw_cases = [
        ("capacity-marker", 11, 22, 33, U32_MAX),
        ("zero-slot", 2, 4, 0, 0),
        ("small-slot", 9, 7, 128, 41),
        ("wide-inputs", 77, 88, 144, 9001),
    ]
    cases = []
    for case_id, store_token, zone_token, payload_bytes, scripted_value in raw_cases:
        cases.append(
            {
                "id": case_id,
                "store_token": store_token,
                "zone_token": zone_token,
                "payload_bytes": payload_bytes,
                "script_value": scripted_value,
                "expected_outputs": {
                    "is_exhausted": scripted_value == U32_MAX,
                    "assigned_slot": scripted_value,
                    "invocation_count": 1,
                    "forwarded_values": [store_token, zone_token, payload_bytes],
                },
                "status": "ok",
            }
        )
    fixture = {
        "schema_version": 1,
        "level": "L3",
        "target_id": "orbit-store",
        "slice_id": "reserve-slot-sentinel",
        "source_commit": "source-commit-17",
        "source_boundary": {"files": ["src/reservation.c"]},
        "compared_fields": fields,
        "case_count": len(cases),
        "cases": cases,
    }
    write_json(fixture_path, fixture)
    fixture_sha = sha256_file(fixture_path)

    fragment = "    if ((slot = claim_slot(store_token, zone_token, payload_bytes)) == NO_SLOT) {\n"
    function_source = (
        "static bool reserve_slot_probe(\n"
        "    uint32_t store_token, uint32_t zone_token, size_t payload_bytes, uint32_t *slot_out)\n"
        "{\n"
        "    uint32_t slot = NO_SLOT;\n"
        "    bool exhausted = false;\n"
        "\n"
        f"{fragment}"
        "        exhausted = true;\n"
        "    }\n"
        "    *slot_out = slot;\n"
        "    return exhausted;\n"
        "}\n"
    )
    source_path.write_text(function_source, encoding="utf-8")
    carrier_source = (
        "#define NO_SLOT ((uint32_t)-1)\n"
        "uint32_t claim_slot(uint32_t store_token, uint32_t zone_token, size_t payload_bytes);\n"
        f"{function_source.rstrip()}"
    )
    carrier = {
        "kind": "exact_source_fragment_wrapper",
        "carrier_function": "reserve_slot_probe",
        "carrier_source_sha256": sha256_text(carrier_source),
        "embedding_mode": "verbatim_once",
        "frontend_contract": "live_clang_slice_source",
        "source_text_normalization": "utf8_universal_newlines",
        "source_file_hash_mode": "raw_bytes",
        "artifact_source_hash_mode": "lf_stable_text",
        "real_source": {
            "file": "src/reservation.c",
            "containing_function": {
                "name": "reserve_slot_probe",
                "line_start": 1,
                "line_end": len(function_source.splitlines()),
                "sha256": sha256_text(function_source.strip()),
                "hash_mode": "trimmed_normalized_span",
                "declaration_text": "static bool reserve_slot_probe(",
            },
            "fragment": {
                "kind": "if_condition_header",
                "line_start": 7,
                "line_end": 7,
                "sha256": sha256_text(fragment),
                "hash_mode": "normalized_line_span_with_newline",
                "text": fragment,
            },
        },
        "claim_boundary": {
            "scope": "source_fragment_only",
            "whole_function_semantics_verified": False,
            "external_callee_semantics_verified": False,
            "excluded_semantics": [
                "containing function control flow outside the exact fragment",
                "real external implementation behavior and side effects",
            ],
        },
    }
    replay_contract = {
        "schema_version": 1,
        "kind": "scripted_external_u32_call_bool_out",
        "external_callee": {
            "name": "claim_slot",
            "return_fixture_field": "script_value",
            "call_count_output": "invocation_count",
            "call_args_output": "forwarded_values",
        },
        "inputs": [
            {"parameter": "store_token", "fixture_field": "store_token", "rust_type": "u32"},
            {"parameter": "zone_token", "fixture_field": "zone_token", "rust_type": "u32"},
            {"parameter": "payload_bytes", "fixture_field": "payload_bytes", "rust_type": "usize"},
        ],
        "output_pointer": {
            "parameter": "slot_out",
            "fixture_field": "assigned_slot",
            "rust_type": "u32",
        },
        "return": {"fixture_field": "is_exhausted", "rust_type": "bool"},
    }
    spec = {
        "schema_version": 1,
        "target_id": "orbit-store",
        "slice_id": "reserve-slot-sentinel",
        "level": "L3",
        "status": "draft",
        "function_name": "reserve_slot_probe",
        "c_source": carrier_source,
        "source_commit": "source-commit-17",
        "fixture_hash": fixture_sha,
        "source_root": "upstream",
        "source_file": "src/reservation.c",
        "source_file_hashes": {"src/reservation.c": sha256_file(source_path)},
        "translation_carrier": carrier,
        "build_profile": {"clang_available": True},
        "fixture_contract": {
            "path": "fixtures/reservation-cases.json",
            "hash": fixture_sha,
            "cases": [
                {"id": case["id"], "expected_outputs": case["expected_outputs"]} for case in cases
            ],
            "behavior_fields": fields,
        },
        "replay_contract": replay_contract,
    }
    write_json(spec_path, spec)

    prefix = "l3-reserve-slot-sentinel"
    artifact_source_hashes = {"src/reservation.c": sha256_text(function_source)}
    translator_input = {
        **spec,
        "fixture_hash": fixture_sha,
        "source_file_hashes": artifact_source_hashes,
    }
    plan = {
        "target_id": spec["target_id"],
        "slice_id": spec["slice_id"],
        "source_commit": spec["source_commit"],
        "status": "generated",
        "fixture_hash": fixture_sha,
        "translation_carrier": carrier,
        "translation_source": {"selected": "clang-lowered-typed-ir"},
    }
    rust_draft_path = auto_dir / f"{prefix}-rust-draft.rs"
    rust_draft_path.write_text(
        "std::thread_local! {\n"
        "    static SCRIPTED_RETURN: std::cell::Cell<u32> = std::cell::Cell::new(0);\n"
        "    static CALL_COUNT: std::cell::Cell<usize> = std::cell::Cell::new(0);\n"
        "    static ARG0: std::cell::Cell<u32> = std::cell::Cell::new(0);\n"
        "    static ARG1: std::cell::Cell<u32> = std::cell::Cell::new(0);\n"
        "    static ARG2: std::cell::Cell<usize> = std::cell::Cell::new(0);\n"
        "}\n"
        "fn __c2r_scripted_external_set_return(value: u32) { SCRIPTED_RETURN.with(|v| v.set(value)); }\n"
        "fn __c2r_scripted_external_reset_calls() { CALL_COUNT.with(|v| v.set(0)); }\n"
        "fn __c2r_scripted_external_call_count() -> usize { CALL_COUNT.with(std::cell::Cell::get) }\n"
        "fn __c2r_scripted_external_call_args() -> (u32, u32, usize) {\n"
        "    (ARG0.with(std::cell::Cell::get), ARG1.with(std::cell::Cell::get), ARG2.with(std::cell::Cell::get))\n"
        "}\n"
        "fn claim_slot(store_token: u32, zone_token: u32, payload_bytes: usize) -> u32 {\n"
        "    ARG0.with(|v| v.set(store_token));\n"
        "    ARG1.with(|v| v.set(zone_token));\n"
        "    ARG2.with(|v| v.set(payload_bytes));\n"
        "    CALL_COUNT.with(|v| v.set(v.get() + 1));\n"
        "    SCRIPTED_RETURN.with(std::cell::Cell::get)\n"
        "}\n"
        "pub fn reserve_slot_probe(\n"
        "    store_token: u32, zone_token: u32, payload_bytes: usize, slot_out: &mut [u32],\n"
        ") -> bool {\n"
        "    let slot = claim_slot(store_token, zone_token, payload_bytes);\n"
        "    slot_out[0] = slot;\n"
        "    slot == u32::MAX\n"
        "}\n",
        encoding="utf-8",
    )
    rust_draft_sha = sha256_file(rust_draft_path)
    lowering = {
        "target_id": spec["target_id"],
        "slice_id": spec["slice_id"],
        "source_commit": spec["source_commit"],
        "status": "lowered",
        "function_name": spec["function_name"],
        "fixture_hash": fixture_sha,
        "translation_carrier": carrier,
        "lowering_report": {"frontend": "clang_slice_source"},
        "metadata": {
            "clang_ast_fixture": None,
            "source_root": spec["source_root"],
            "logical_source_file": spec["source_file"],
            "source_file_hashes": artifact_source_hashes,
        },
        "typed_ir_candidate": {
            "status": "generated",
            "rust_draft_generated": True,
            "semantic_pass": False,
            "rust_draft_sha256": rust_draft_sha,
        },
    }
    write_json(auto_dir / f"{prefix}-translator-input.json", translator_input)
    write_json(auto_dir / f"{prefix}-auto-translation-plan.json", plan)
    lowering_path = auto_dir / f"{prefix}-clang-lowering-report.json"
    write_json(lowering_path, lowering)

    markers = [f"fixture case {case['id']} {field} matched" for case in cases for field in fields]
    harness_path = auto_dir / f"{prefix}-c-oracle-harness-draft.c"
    harness_path.write_text(
        "/* generated fixture harness */\n"
        + carrier_source
        + "\nint main(void) {\n"
        + "".join(f'  puts("{marker}");\n' for marker in markers)
        + "  return 0;\n}\n",
        encoding="utf-8",
    )
    status = {
        "schema_version": 1,
        "target_id": spec["target_id"],
        "slice_id": spec["slice_id"],
        "source_commit": spec["source_commit"],
        "status": "DRAFT_GENERATED",
        "semantic_pass": False,
        "fixture": "fixtures/reservation-cases.json",
        "harness_draft_ref": {
            "path": harness_path.relative_to(root).as_posix(),
            "sha256": sha256_file(harness_path),
            "status": "draft",
        },
        "compile_execution": {
            "status": "compile_succeeded_not_oracle",
            "attempted": True,
            "returncode": 0,
            "argv": ["cc", "reservation-harness.c", "-o", "reservation-harness.exe"],
            "execution_argv": [
                "/tmp/private-toolchain/cc",
                str(harness_path),
                "-o",
                "/tmp/private-build/reservation-harness.exe",
            ],
            "compiler_name": "cc",
            "compiler_path": "/tmp/private-toolchain/cc",
            "harness_execution": {
                "status": "exited_zero_not_oracle",
                "returncode": 0,
                "argv": ["evidence/auto/reservation-harness.exe"],
                "execution_argv": ["/tmp/private-build/reservation-harness.exe"],
                "executable_path": "/tmp/private-build/reservation-harness.exe",
                "output_gate": {
                    "status": "matched_not_oracle",
                    "matched_stdout_fragments": markers,
                    "missing_stdout_fragments": [],
                },
            },
        },
    }
    write_json(auto_dir / f"{prefix}-c-oracle-status.json", status)

    rust_check_path = auto_dir / "rust-check.json"
    write_json(
        rust_check_path,
        {
            "schema_version": 1,
            "status": "passed",
            "external_callee_context": {
                "declared_callees": [
                    {"name": "claim_slot", "semantics_verified": False}
                ]
            },
            "rust_check_harness_only_bindings": {
                "status": "emitted",
                "semantics_verified": False,
                "bindings": [
                    {
                        "name": "claim_slot",
                        "fixture_only": True,
                        "semantics_verified": False,
                        "replay_contract_kind": "scripted_external_u32_call_bool_out",
                    }
                ],
            },
        },
    )
    replay_test_path = auto_dir / f"{prefix}-rust-replay-test-draft.rs"
    replay_case_literals = "\n".join(
        (
            f"        ({case['store_token']}u32, {case['zone_token']}u32, "
            f"{case['payload_bytes']}usize, {case['script_value']}u32, "
            f"{str(case['expected_outputs']['is_exhausted']).lower()}, "
            f"{case['expected_outputs']['assigned_slot']}u32, "
            f"({case['expected_outputs']['forwarded_values'][0]}u32, "
            f"{case['expected_outputs']['forwarded_values'][1]}u32, "
            f"{case['expected_outputs']['forwarded_values'][2]}usize)),"
        )
        for case in cases
    )
    replay_test_path.write_text(
        "#[test]\n"
        "fn replay_declared_fixture_contract() {\n"
        "    let cases = [\n"
        + replay_case_literals
        + "\n    ];\n"
        "    for (arg0, arg1, arg2, scripted, expected_return, expected_out, expected_args) in cases {\n"
        "        __c2r_scripted_external_set_return(scripted);\n"
        "        __c2r_scripted_external_reset_calls();\n"
        "        let mut out = [0u32; 1];\n"
        "        let actual = reserve_slot_probe(arg0, arg1, arg2, &mut out);\n"
        "        assert_eq!(actual, expected_return);\n"
        "        assert_eq!(out[0], expected_out);\n"
        "        assert_eq!(__c2r_scripted_external_call_count(), 1usize);\n"
        "        assert_eq!(__c2r_scripted_external_call_args(), expected_args);\n"
        "    }\n"
        "}\n",
        encoding="utf-8",
    )
    stdout_path = auto_dir / "generated-rust-replay.stdout.log"
    stderr_path = auto_dir / "generated-rust-replay.stderr.log"
    stdout_path.write_text("test result: ok. 4 passed\n", encoding="utf-8")
    stderr_path.write_text("", encoding="utf-8")
    replay_execution = {
        "status": "passed",
        "compile_returncode": 0,
        "run_returncode": 0,
        "stdout_log": stdout_path.relative_to(root).as_posix(),
        "stderr_log": stderr_path.relative_to(root).as_posix(),
    }
    test_translation = {
        "schema_version": 1,
        "target_id": spec["target_id"],
        "slice_id": spec["slice_id"],
        "source_commit": spec["source_commit"],
        "status": "passed",
        "behavior_fields": fields,
        "generated_draft_replay_pass": True,
        "generated_draft_semantic_pass": False,
        "fixture_external_stub": {
            "kind": "scripted_external_u32_call_bool_out",
            "scope": "fixture_only",
            "semantics_verified": False,
        },
        "replay_execution": replay_execution,
        "test_draft": replay_test_path.relative_to(root).as_posix(),
        "rust_tests": [
            {
                "file": replay_test_path.relative_to(root).as_posix(),
                "file_hash": sha256_file(replay_test_path),
            }
        ],
        "source_test_inputs": {
            "fixtures": [
                {
                    "path": fixture_path.relative_to(root).as_posix(),
                    "hash": fixture_sha,
                    "operation_count": len(cases),
                }
            ]
        },
    }
    test_translation_path = auto_dir / f"{prefix}-test-translation-generated.json"
    write_json(test_translation_path, test_translation)
    candidate_report_path = auto_dir / f"{prefix}-rust-report.json"
    write_json(
        candidate_report_path,
        {
            "schema_version": 1,
            "target_id": spec["target_id"],
            "slice_id": spec["slice_id"],
            "source_commit": spec["source_commit"],
            "status": "passed",
            "generated_draft_replay_pass": True,
            "generated_draft_semantic_pass": False,
            "generated_draft": {
                "path": rust_draft_path.relative_to(root).as_posix(),
                "sha256": rust_draft_sha,
                "status": "candidate",
            },
            "replay": test_translation,
        },
    )
    return {
        "emit_args": {
            "slice_spec": spec_path,
            "auto_evidence_dir": auto_dir,
            "output_dir": output_dir,
            "repo_root": root,
        },
        "lowering_path": lowering_path,
        "test_translation_path": test_translation_path,
        "candidate_report_path": candidate_report_path,
        "rust_check_path": rust_check_path,
        "rust_draft_path": rust_draft_path,
        "replay_test_path": replay_test_path,
    }


def output_dir_files(output_dir: Path) -> list[Path]:
    return [path for path in output_dir.rglob("*") if path.is_file()]


def apply_replay_mutation(layout: dict[str, object], mutation: str) -> None:
    if mutation == "generated_draft_replay_pass":
        payload = load_json(layout["test_translation_path"])
        payload["generated_draft_replay_pass"] = False
        write_json(layout["test_translation_path"], payload)
    elif mutation == "rust_draft_sha":
        payload = load_json(layout["candidate_report_path"])
        payload["generated_draft"]["sha256"] = "0" * 64
        write_json(layout["candidate_report_path"], payload)
    elif mutation == "rust_draft_path":
        payload = load_json(layout["candidate_report_path"])
        payload["generated_draft"]["path"] = layout["replay_test_path"].relative_to(
            layout["emit_args"]["repo_root"]
        ).as_posix()
        write_json(layout["candidate_report_path"], payload)
    elif mutation == "rust_check_external_semantics":
        payload = load_json(layout["rust_check_path"])
        payload["rust_check_harness_only_bindings"]["semantics_verified"] = True
        write_json(layout["rust_check_path"], payload)
    elif mutation == "run_returncode":
        payload = load_json(layout["test_translation_path"])
        payload["replay_execution"]["run_returncode"] = 17
        write_json(layout["test_translation_path"], payload)
    elif mutation == "replay_host_path":
        payload = load_json(layout["test_translation_path"])
        payload["replay_execution"]["compile_command"] = (
            "rustc /tmp/private-build/generated.rs"
        )
        write_json(layout["test_translation_path"], payload)
    else:
        raise AssertionError(f"unknown test mutation: {mutation}")


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


if __name__ == "__main__":
    unittest.main()
