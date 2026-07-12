from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from validation.tools import ai_candidate_harness


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class AiFreshOracleTests(unittest.TestCase):
    def make_case(self, root: Path) -> tuple[dict[str, object], dict[str, object], Path]:
        project = root / "project"
        source = project / "src" / "unit.c"
        include = project / "include"
        fixture = root / "fixtures" / "cases.json"
        harness = root / "run" / "harness.c"
        source.parent.mkdir(parents=True)
        include.mkdir(parents=True)
        fixture.parent.mkdir(parents=True)
        harness.parent.mkdir(parents=True)
        function = b"int transform(int value) { return value + FEATURE; }\n"
        source.write_bytes(b"/* prefix */\n" + function + b"int other(void) { return 0; }\n")
        fixture.write_text(json.dumps({"cases": [{"value": 1, "expected": 3}]}), encoding="utf-8")
        harness.write_text("int main(void) { return 0; }\n", encoding="utf-8", newline="\n")
        start = source.read_bytes().index(function)
        source_hash = sha256(source)
        fixture_hash = sha256(fixture)
        spec: dict[str, object] = {
            "schema_version": 1,
            "target_id": "renamable-project",
            "slice_id": "renamable-slice",
            "source_root": "project",
            "source_file_hashes": {"src/unit.c": source_hash},
            "function_source_span": {
                "file": "src/unit.c",
                "line_start": 2,
                "line_end": 2,
                "byte_start": start,
                "byte_end": start + len(function),
                "sha256": hashlib.sha256(function).hexdigest(),
            },
            "fixture_hash": fixture_hash,
            "fixture_contract": {
                "path": "fixtures/cases.json",
                "hash": fixture_hash,
                "sha256": fixture_hash,
                "c_oracle": "history/oracle.json",
                "rust_report": "history/rust.json",
                "diff": "history/diff.json",
                "final_verification": "history/final.json",
            },
            "build_profile": {
                "profile_id": "generic-c99",
                "compiler_command_source": "build/compile_commands.json",
                "include_paths": ["include"],
                "defines": ["FEATURE=2"],
                "preprocessing_mode": "compile_commands",
                "target": {
                    "triple_or_abi": "x86_64-unknown-linux-gnu",
                    "endianness": "little",
                    "int_width": 32,
                    "long_width": 64,
                    "pointer_width": 64,
                },
            },
            "c_boundary": {
                "files": [{"path": "src/unit.c", "sha256": source_hash}],
                "target_abi_contract": {"calling_convention": "C", "pointer_width": 64},
            },
        }
        argv = ["cc", "-std=c99", "-DFEATURE=2", "harness.c", "-o", "harness.exe"]
        payload: dict[str, object] = {
            "schema_version": 1,
            "status": "DRAFT_GENERATED",
            "toolchain_status": "COMPILE_SUCCEEDED_NOT_ORACLE",
            "semantic_pass": False,
            "harness_draft": "run/harness.c",
            "harness_draft_ref": {"path": "run/harness.c", "sha256": sha256(harness), "status": "draft"},
            "fixture": "fixtures/cases.json",
            "fixture_binding": {
                "path": "fixtures/cases.json",
                "case_count": 1,
                "behavior_fields": ["return_value"],
                "case_bindings": [
                    {
                        "id": "one",
                        "input_ref": "cases[0]",
                        "expected_outputs": {"return_value": 3},
                        "missing_observable_outputs": [],
                    }
                ],
            },
            "harness_contract": {"source_files": copy.deepcopy(spec["c_boundary"]["files"])},
            "compile_command_draft": {
                "status": "draft_not_executed",
                "argv": argv,
                "defines": ["FEATURE=2"],
                "resolved_include_paths": ["project/include"],
                "link_source_files": [],
            },
            "compile_execution": {
                "status": "compile_succeeded_not_oracle",
                "toolchain_status_after_attempt": "COMPILE_SUCCEEDED_NOT_ORACLE",
                "attempted": True,
                "returncode": 0,
                "argv": argv,
                "execution_argv": ["/usr/bin/cc", *argv[1:]],
                "compiler_name": "cc",
                "toolchain_adapter": "local",
                "harness_execution": {
                    "status": "exited_zero_not_oracle",
                    "attempted": True,
                    "returncode": 0,
                    "execution_argv": ["run/harness.exe"],
                    "output_gate": {
                        "status": "matched_not_oracle",
                        "matched_stdout_fragments": ["fixture case one return_value matched"],
                        "missing_stdout_fragments": [],
                    },
                },
            },
        }
        return spec, payload, harness

    def prove(self, root: Path, spec: object, payload: object, harness: Path) -> dict[str, object]:
        return ai_candidate_harness.prove_fresh_oracle(spec, payload, harness, source_root=root)

    def test_fresh_hash_bound_run_passes_without_granting_semantic_status(self) -> None:
        with tempfile.TemporaryDirectory(prefix="fresh-oracle-") as tmp:
            root = Path(tmp)
            spec, payload, harness = self.make_case(root)

            result = self.prove(root, spec, payload, harness)

            self.assertEqual(result["status"], "passed")
            self.assertEqual(result["failures"], [])
            self.assertEqual(len(result["oracle_run_sha256"]), 64)
            self.assertEqual(len(result["reuse_key_sha256"]), 64)
            self.assertNotIn("semantic_pass", result)
            self.assertNotIn(str(root), json.dumps(result, sort_keys=True))

    def test_crlf_checkout_matches_lf_source_bindings_without_hiding_content_drift(self) -> None:
        with tempfile.TemporaryDirectory(prefix="fresh-oracle-crlf-") as tmp:
            root = Path(tmp)
            spec, payload, harness = self.make_case(root)
            source = root / "project/src/unit.c"
            source.write_bytes(source.read_bytes().replace(b"\n", b"\r\n"))

            result = self.prove(root, spec, payload, harness)

            self.assertEqual(result["status"], "passed")
            source_binding = result["bindings"]["source_files"][0]
            span_binding = result["bindings"]["source_span"]
            self.assertEqual(source_binding["hash_match_mode"], "newline_equivalent")
            self.assertEqual(span_binding["hash_match_mode"], "newline_equivalent")
            self.assertEqual(source_binding["declared_sha256"], spec["source_file_hashes"]["src/unit.c"])
            self.assertEqual(span_binding["declared_sha256"], spec["function_source_span"]["sha256"])
            self.assertEqual(source_binding["sha256"], sha256(source))

    def test_span_byte_coordinates_cannot_fall_back_to_matching_lines(self) -> None:
        with tempfile.TemporaryDirectory(prefix="fresh-oracle-coordinate-drift-") as tmp:
            root = Path(tmp)
            spec, payload, harness = self.make_case(root)
            spec["function_source_span"]["byte_start"] += 1
            spec["function_source_span"]["byte_end"] += 1

            result = self.prove(root, spec, payload, harness)

            self.assertEqual(result["status"], "failed")
            self.assertIn("source_span_invalid", self.kinds(result))

    def test_declared_invalid_byte_coordinates_cannot_be_treated_as_line_only(self) -> None:
        with tempfile.TemporaryDirectory(prefix="fresh-oracle-invalid-coordinate-") as tmp:
            root = Path(tmp)
            spec, payload, harness = self.make_case(root)
            spec["function_source_span"]["byte_start"] = -1

            result = self.prove(root, spec, payload, harness)

            self.assertEqual(result["status"], "failed")
            self.assertIn("source_span_invalid", self.kinds(result))

    def test_historical_spec_paths_are_never_read_or_part_of_reuse_identity(self) -> None:
        with tempfile.TemporaryDirectory(prefix="fresh-oracle-history-") as tmp:
            root = Path(tmp)
            spec, payload, harness = self.make_case(root)
            first = self.prove(root, spec, payload, harness)
            changed = copy.deepcopy(spec)
            fixture = changed["fixture_contract"]
            for key in ("c_oracle", "rust_report", "diff", "final_verification"):
                fixture[key] = f"missing/changed-{key}.json"

            second = self.prove(root, changed, payload, harness)

            self.assertEqual(second["status"], "passed")
            self.assertEqual(first["reuse_key_sha256"], second["reuse_key_sha256"])
            self.assertEqual(first["oracle_run_sha256"], second["oracle_run_sha256"])

    def test_payload_with_accepted_oracle_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory(prefix="fresh-oracle-accepted-") as tmp:
            root = Path(tmp)
            spec, payload, harness = self.make_case(root)
            payload["accepted_oracle"] = {"path": "history/oracle.json", "status": "passed"}

            result = self.prove(root, spec, payload, harness)

            self.assertIn("historical_evidence_present", self.kinds(result))

    def test_fresh_harness_source_contract_must_match_spec(self) -> None:
        with tempfile.TemporaryDirectory(prefix="fresh-oracle-source-contract-") as tmp:
            root = Path(tmp)
            spec, payload, harness = self.make_case(root)
            payload["harness_contract"]["source_files"][0]["sha256"] = "0" * 64

            result = self.prove(root, spec, payload, harness)

            self.assertIn("source_contract_mismatch", self.kinds(result))

    def test_harness_fixture_source_and_span_hash_drift_fail_closed(self) -> None:
        mutations = ("harness", "fixture", "source", "span")
        for mutation in mutations:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory(prefix="fresh-oracle-drift-") as tmp:
                root = Path(tmp)
                spec, payload, harness = self.make_case(root)
                if mutation == "harness":
                    harness.write_text("int main(void) { return 7; }\n", encoding="utf-8")
                elif mutation == "fixture":
                    (root / "fixtures/cases.json").write_text("{}", encoding="utf-8")
                elif mutation == "source":
                    (root / "project/src/unit.c").write_text("int changed;\n", encoding="utf-8")
                else:
                    spec["function_source_span"]["sha256"] = "0" * 64

                result = self.prove(root, spec, payload, harness)

                self.assertEqual(result["status"], "failed")
                self.assertTrue(self.kinds(result) & {"harness_hash_mismatch", "fixture_hash_mismatch", "source_hash_mismatch", "source_span_hash_mismatch"})

    def test_path_escape_and_symlink_escape_fail_closed_without_leaking_host_path(self) -> None:
        with tempfile.TemporaryDirectory(prefix="fresh-oracle-escape-") as tmp:
            root = Path(tmp) / "proof"
            root.mkdir()
            outside = Path(tmp) / "outside.c"
            outside.write_text("int secret = 171717;\n", encoding="utf-8")
            spec, payload, harness = self.make_case(root)
            payload["harness_draft_ref"]["path"] = "../outside.c"

            result = self.prove(root, spec, payload, harness)
            encoded = json.dumps(result, sort_keys=True)

            self.assertIn("path_escape", self.kinds(result))
            self.assertNotIn(str(outside), encoded)
            self.assertNotIn("171717", encoded)

    def test_missing_compiler_and_contradictory_execution_states_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="fresh-oracle-tool-") as tmp:
            root = Path(tmp)
            spec, payload, harness = self.make_case(root)
            execution = payload["compile_execution"]
            execution.update({"status": "compiler_not_found", "attempted": False, "returncode": None})
            execution["harness_execution"]["output_gate"]["missing_stdout_fragments"] = ["case"]

            result = self.prove(root, spec, payload, harness)

            self.assertTrue({"compiler_not_found", "compile_execution_invalid", "oracle_output_mismatch"} <= self.kinds(result))

    def test_nested_execution_is_authoritative_and_duplicate_payloads_must_match(self) -> None:
        with tempfile.TemporaryDirectory(prefix="fresh-oracle-duplicates-") as tmp:
            root = Path(tmp)
            spec, payload, harness = self.make_case(root)
            nested_run = payload["compile_execution"]["harness_execution"]
            payload["harness_execution"] = copy.deepcopy(nested_run)
            payload["output_gate"] = copy.deepcopy(nested_run["output_gate"])
            matching = self.prove(root, spec, payload, harness)
            payload["harness_execution"]["returncode"] = 9
            payload["output_gate"]["missing_stdout_fragments"] = ["different"]

            conflicting = self.prove(root, spec, payload, harness)

            self.assertEqual(matching["status"], "passed")
            self.assertTrue({"harness_execution_conflict", "output_gate_conflict"} <= self.kinds(conflicting))

    def test_reuse_key_changes_only_for_source_fixture_flags_or_abi_identity(self) -> None:
        with tempfile.TemporaryDirectory(prefix="fresh-oracle-reuse-") as tmp:
            root = Path(tmp)
            spec, payload, harness = self.make_case(root)
            baseline = self.prove(root, spec, payload, harness)
            renamed = copy.deepcopy(spec)
            renamed["target_id"] = "different-name"
            renamed["slice_id"] = "different-slice"
            same = self.prove(root, renamed, payload, harness)
            changed = copy.deepcopy(spec)
            changed["build_profile"]["defines"] = []
            changed_payload = copy.deepcopy(payload)
            changed_payload["compile_command_draft"]["defines"] = []
            changed_payload["compile_command_draft"]["argv"] = ["cc", "-std=c99", "harness.c", "-o", "harness.exe"]
            changed_payload["compile_execution"]["argv"] = changed_payload["compile_command_draft"]["argv"]

            different = self.prove(root, changed, changed_payload, harness)

            self.assertEqual(baseline["reuse_key_sha256"], same["reuse_key_sha256"])
            self.assertNotEqual(baseline["reuse_key_sha256"], different["reuse_key_sha256"])

    def test_reuse_key_ignores_fresh_harness_and_output_names(self) -> None:
        with tempfile.TemporaryDirectory(prefix="fresh-oracle-harness-name-") as tmp:
            root = Path(tmp)
            spec, payload, harness = self.make_case(root)
            baseline = self.prove(root, spec, payload, harness)
            renamed_harness = harness.with_name("another-harness.c")
            renamed_harness.write_bytes(harness.read_bytes())
            renamed = copy.deepcopy(payload)
            renamed["harness_draft"] = "run/another-harness.c"
            renamed["harness_draft_ref"]["path"] = "run/another-harness.c"
            renamed["compile_command_draft"]["argv"][3] = "another-harness.c"
            renamed["compile_command_draft"]["argv"][5] = "another-harness.exe"
            renamed["compile_execution"]["argv"] = renamed["compile_command_draft"]["argv"]

            second = self.prove(root, spec, renamed, renamed_harness)

            self.assertEqual(second["status"], "passed")
            self.assertEqual(baseline["reuse_key_sha256"], second["reuse_key_sha256"])

    @staticmethod
    def kinds(result: dict[str, object]) -> set[str]:
        return {str(item["kind"]) for item in result["failures"]}


if __name__ == "__main__":
    unittest.main()
