from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from validation.tools import _auto_migrate_ai_exact as exact
from validation.tools import _auto_migrate_c2rust_repair as c2rust_repair
from validation.tools import validate_judge_entrypoints as judge_validator
from validation.tools._ai_candidate_harness_parts import router
from validation.tools._ai_candidate_harness_parts.context import sha256_path


def write_baseline_manifest(evidence_dir: Path, source: str) -> tuple[dict[str, object], Path, Path]:
    baseline_path = evidence_dir / "raw-c2rust-output.rs"
    baseline_path.write_text(source, encoding="utf-8")
    manifest = {
        "schema_version": 1,
        "status": "generated",
        "output": {
            "path": baseline_path.as_posix(),
            "status": "generated",
            "sha256": judge_validator.sha256_file(baseline_path),
        },
    }
    manifest_path = evidence_dir / "current-run-c2rust-baseline-manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return manifest, manifest_path, baseline_path


def exact_result(path: Path, attempt_dir: Path, *, passed_gates: int, passed: bool = False) -> dict[str, object]:
    candidate_sha = sha256_path(path)
    gate_results = {}
    for index, name in enumerate(router.REQUIRED_GATES):
        gate_results[name] = {
            "status": "passed" if index < passed_gates else "failed",
            "candidate_sha256": candidate_sha,
        }
    status = "passed" if passed else "failed"
    return {
        "schema_version": 1,
        "status": status,
        "candidate_sha256": candidate_sha,
        "semantic_pass": passed,
        "oracle_proof": {},
        "gate_index": {"path": "gate-index.json", "sha256": "a" * 64},
        "gates": {},
        "repair_validation_result": {
            "schema_version": 1,
            "status": status,
            "failures": [] if passed else [{"gate": "compile", "kind": "failed", "message": "failed"}],
        },
        "router_gate_results": gate_results,
        "attempt_dir": attempt_dir.as_posix(),
    }


def ai_manifest() -> dict[str, object]:
    return {
        "status": "generated",
        "selected_candidate_id": "opencode-glm51-1",
        "candidates": [{"candidate_id": "opencode-glm51-1", "applied": True}],
    }


def run_stage(
    root: Path,
    *,
    fake_validate: object,
    max_repair_rounds: int = 3,
) -> tuple[dict[str, object], Path, Path, dict[str, object], Path]:
    evidence_dir = root / "evidence"
    evidence_dir.mkdir()
    canonical = evidence_dir / "canonical.rs"
    typed = evidence_dir / "typed.rs"
    canonical.write_text("pub fn migrated(value: i32) -> i32 { value - 1 }\n", encoding="utf-8")
    typed.write_text("pub fn migrated(value: i32) -> i32 { value }\n", encoding="utf-8")
    manifest, manifest_path, baseline = write_baseline_manifest(
        evidence_dir,
        "pub fn migrated(value: i32) -> i32 { value + 1 }\n",
    )
    with mock.patch.object(exact, "_validate_with_new_attempt", side_effect=fake_validate):
        result = exact.run_ai_exact_stage(
            {"slice_id": "generic-slice"},
            context_pack={"target_id": "generic-target", "slice_id": "generic-slice"},
            ai_manifest=ai_manifest(),
            evidence_dir=evidence_dir,
            canonical_draft_path=canonical,
            deterministic_candidate_path=typed,
            c2rust_baseline=manifest,
            c2rust_baseline_manifest_path=manifest_path,
            replay_test_path=evidence_dir / "replay.rs",
            oracle_payload={},
            harness_path=evidence_dir / "oracle.c",
            proof_root=root,
            compile_runner=lambda _path: {},
            replay_runner=lambda _path, _replay: {},
            max_repair_rounds=max_repair_rounds,
            opencode_command="unused",
            resolved_model="unused",
            agent="unused",
            variant="unused",
            timeout_seconds=1,
        )
    return result, canonical, typed, manifest, baseline


class C2RustRepairCoordinatorTests(unittest.TestCase):
    def test_reopens_latest_candidate_and_rejects_sha_drift(self) -> None:
        with tempfile.TemporaryDirectory(prefix="c2rust-repair-reopen-") as tmp:
            root = Path(tmp)
            initial = root / "baseline.rs"
            initial_bytes = b"pub fn migrated() {}\r\n"
            initial.write_bytes(initial_bytes)
            report, candidate_path = c2rust_repair.repair_c2rust_candidate_after_validation(
                {"target_id": "generic-target", "slice_id": "generic-slice"},
                out_dir=root / "evidence",
                baseline_candidate_path=initial,
                initial_failure_facts={
                    "schema_version": 1,
                    "status": "failed",
                    "failures": [{"gate": "compile", "kind": "failed", "message": "failed"}],
                },
                validation_runner=lambda _path, _round: {
                    "schema_version": 1,
                    "status": "passed",
                    "failures": [],
                },
                max_rounds=1,
                opencode_command="unused",
                resolved_model="unused",
                agent="unused",
                variant="unused",
                timeout_seconds=1,
                provider_runner=lambda _argv, _timeout: c2rust_repair.ProviderExecution(
                    0,
                    json.dumps(
                        {
                            "type": "message.part.updated",
                            "part": {
                                "type": "text",
                                "text": json.dumps(
                                    {
                                        "schema_version": 1,
                                        "repair": {
                                            "kind": "candidate",
                                            "language": "rust",
                                            "source": "pub fn migrated() { let _value = 1; }\n",
                                        },
                                        "assumptions": [],
                                    }
                                ),
                            },
                        }
                    )
                    + "\n",
                    "",
                ),
            )

            self.assertIsNotNone(report)
            self.assertIsNotNone(candidate_path)
            assert report is not None and candidate_path is not None
            self.assertEqual(report["artifact_label"], "c2rust-repair")
            self.assertEqual(report["input_source"], "c2rust-baseline")
            self.assertEqual(initial.read_bytes(), initial_bytes)
            candidate_path.write_text("drifted\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "sha256 drifted"):
                c2rust_repair.reopen_latest_candidate(report, out_dir=root / "evidence")


class C2RustRepairExactStageTests(unittest.TestCase):
    def test_raw_strictly_better_runs_only_c2rust_repair_and_routes_fresh_candidate(self) -> None:
        with tempfile.TemporaryDirectory(prefix="c2rust-repair-route-") as tmp:
            root = Path(tmp)
            labels: list[str] = []

            def fake_validate(*_args: object, **kwargs: object) -> dict[str, object]:
                label = str(kwargs["label"])
                path = Path(kwargs["candidate_path"])
                labels.append(label)
                scores = {
                    "ai-initial": 1,
                    "typed-ir": 7,
                    "c2rust-baseline": 2,
                    "c2rust-repair-01": 8,
                    "c2rust-repair-final": 8,
                }
                return exact_result(
                    path,
                    Path(kwargs["attempts_root"]) / label,
                    passed_gates=scores[label],
                    passed=label.startswith("c2rust-repair"),
                )

            repair_calls: list[int] = []

            def fake_c2rust_repair(*_args: object, **kwargs: object) -> tuple[dict[str, object], Path]:
                repair_calls.append(int(kwargs["max_rounds"]))
                out_dir = Path(kwargs["out_dir"])
                candidate = out_dir / "l3-generic-slice-c2rust-repair-01-candidate.rs"
                candidate.write_text("pub fn migrated(value: i32) -> i32 { value.wrapping_add(1) }\n", encoding="utf-8")
                kwargs["validation_runner"](candidate, 1)
                report = {
                    "schema_version": 1,
                    "slice_id": "generic-slice",
                    "artifact_label": "c2rust-repair",
                    "input_source": "c2rust-baseline",
                    "status": "candidate_ready_for_common_validation",
                    "rounds": [{"round": 1}],
                    "final_candidate": {"path": candidate.name, "sha256": sha256_path(candidate)},
                }
                (out_dir / "l3-generic-slice-c2rust-repair-report.json").write_text(
                    json.dumps(report),
                    encoding="utf-8",
                )
                return report, candidate

            with mock.patch.object(
                exact,
                "repair_c2rust_candidate_after_validation",
                side_effect=fake_c2rust_repair,
            ), mock.patch.object(exact, "repair_ai_candidate_after_validation") as ai_repair:
                result, canonical, _typed, _manifest, baseline = run_stage(
                    root,
                    fake_validate=fake_validate,
                    max_repair_rounds=3,
                )

            self.assertEqual(repair_calls, [3])
            ai_repair.assert_not_called()
            self.assertEqual(
                labels,
                ["ai-initial", "typed-ir", "c2rust-baseline", "c2rust-repair-01", "c2rust-repair-final"],
            )
            self.assertEqual(result["router"]["selected_candidate_id"], "c2rust-repair:raw-current-run")
            self.assertEqual(
                [item["source"] for item in result["router"]["candidate_set"]],
                ["opencode-ai", "typed-ir", "c2rust-repair", "c2rust-baseline"],
            )
            self.assertIn("c2rust_repair", result["router"]["candidate_evidence"])
            audit = result["router"]["candidate_source_audit"]["c2rust_repair"]
            self.assertEqual(audit["source"], "c2rust-repair")
            self.assertEqual(audit["status"], "exact_gates_completed")
            self.assertEqual(audit["reason"], "fresh_exact_gates_passed")
            self.assertEqual(audit["base_candidate_sha256"], sha256_path(baseline))
            self.assertEqual(audit["repair_rounds"], 1)
            self.assertEqual(audit["final_candidate_sha256"], sha256_path(canonical))
            self.assertFalse(audit["repair_report"]["semantic_pass"])
            report_path = root / "evidence" / audit["repair_report"]["path"]
            self.assertEqual(audit["repair_report"]["sha256"], sha256_path(report_path))
            self.assertEqual(
                baseline.read_text(encoding="utf-8"),
                "pub fn migrated(value: i32) -> i32 { value + 1 }\n",
            )

    def test_gate_count_tie_repairs_ai_and_keeps_source_opencode_ai(self) -> None:
        with tempfile.TemporaryDirectory(prefix="c2rust-repair-tie-") as tmp:
            root = Path(tmp)
            labels: list[str] = []

            def fake_validate(*_args: object, **kwargs: object) -> dict[str, object]:
                label = str(kwargs["label"])
                path = Path(kwargs["candidate_path"])
                labels.append(label)
                passed = label == "ai-repair-final"
                return exact_result(
                    path,
                    Path(kwargs["attempts_root"]) / label,
                    passed_gates=8 if passed else (7 if label == "typed-ir" else 2),
                    passed=passed,
                )

            ai_calls: list[int] = []

            def fake_ai_repair(
                _context: object,
                manifest: dict[str, object],
                **kwargs: object,
            ) -> tuple[dict[str, object], dict[str, object]]:
                ai_calls.append(int(kwargs["max_rounds"]))
                Path(kwargs["canonical_draft_path"]).write_text(
                    "pub fn migrated(value: i32) -> i32 { value.wrapping_add(1) }\n",
                    encoding="utf-8",
                )
                return manifest, {"status": "candidate_ready_for_common_validation"}

            with mock.patch.object(
                exact,
                "repair_ai_candidate_after_validation",
                side_effect=fake_ai_repair,
            ), mock.patch.object(exact, "repair_c2rust_candidate_after_validation") as raw_repair:
                result, _canonical, _typed, _manifest, _baseline = run_stage(
                    root,
                    fake_validate=fake_validate,
                    max_repair_rounds=4,
                )

            self.assertEqual(ai_calls, [4])
            raw_repair.assert_not_called()
            self.assertEqual(labels, ["ai-initial", "typed-ir", "c2rust-baseline", "ai-repair-final"])
            selected = next(
                item
                for item in result["router"]["candidate_set"]
                if item["candidate_id"] == result["router"]["selected_candidate_id"]
            )
            self.assertEqual(selected["source"], "opencode-ai")
            self.assertNotIn("c2rust_repair", result["router"]["candidate_source_audit"])

    def test_zero_token_pass_skips_both_repair_coordinators(self) -> None:
        with tempfile.TemporaryDirectory(prefix="c2rust-repair-skip-") as tmp:
            root = Path(tmp)

            def fake_validate(*_args: object, **kwargs: object) -> dict[str, object]:
                label = str(kwargs["label"])
                path = Path(kwargs["candidate_path"])
                return exact_result(
                    path,
                    Path(kwargs["attempts_root"]) / label,
                    passed_gates=8 if label == "c2rust-baseline" else 1,
                    passed=label == "c2rust-baseline",
                )

            with mock.patch.object(exact, "repair_ai_candidate_after_validation") as ai_repair, mock.patch.object(
                exact,
                "repair_c2rust_candidate_after_validation",
            ) as raw_repair:
                result, _canonical, _typed, _manifest, _baseline = run_stage(
                    root,
                    fake_validate=fake_validate,
                    max_repair_rounds=5,
                )

            ai_repair.assert_not_called()
            raw_repair.assert_not_called()
            self.assertEqual(result["router"]["selected_candidate_id"], "c2rust-baseline:raw-current-run")
            self.assertFalse((root / "evidence" / "l3-generic-slice-ai-repair-report.json").exists())
            self.assertFalse((root / "evidence" / "l3-generic-slice-c2rust-repair-report.json").exists())

    def test_repair_matching_raw_baseline_omits_baseline_evidence_and_syncs_audit(self) -> None:
        with tempfile.TemporaryDirectory(prefix="c2rust-repair-dedup-baseline-") as tmp:
            root = Path(tmp)

            def fake_validate(*_args: object, **kwargs: object) -> dict[str, object]:
                label = str(kwargs["label"])
                path = Path(kwargs["candidate_path"])
                scores = {"ai-initial": 1, "typed-ir": 1, "c2rust-baseline": 2, "c2rust-repair-final": 2}
                return exact_result(
                    path,
                    Path(kwargs["attempts_root"]) / label,
                    passed_gates=scores[label],
                )

            def fake_repair(*_args: object, **kwargs: object) -> tuple[dict[str, object], Path]:
                out_dir = Path(kwargs["out_dir"])
                baseline_path = Path(kwargs["baseline_candidate_path"])
                candidate = out_dir / "l3-generic-slice-c2rust-repair-01-candidate.rs"
                candidate.write_bytes(baseline_path.read_bytes())
                report = self._write_repair_report(out_dir, candidate)
                return report, candidate

            with mock.patch.object(
                exact,
                "repair_c2rust_candidate_after_validation",
                side_effect=fake_repair,
            ), mock.patch.object(exact, "repair_ai_candidate_after_validation") as ai_repair:
                result, _canonical, _typed, _manifest, _baseline = run_stage(
                    root,
                    fake_validate=fake_validate,
                )

            ai_repair.assert_not_called()
            evidence = result["router"]["candidate_evidence"]
            self.assertIn("c2rust_repair", evidence)
            self.assertNotIn("c2rust_baseline", evidence)
            duplicate = next(
                item
                for item in result["router"]["deduplicated_candidates"]
                if item["source"] == "c2rust-baseline"
            )
            audit = result["router"]["candidate_source_audit"]["c2rust_baseline"]
            self.assertEqual(audit["status"], "duplicate")
            self.assertEqual(audit["duplicate_of"], duplicate["duplicate_of"])
            self.assertEqual(audit["duplicate_source"], "c2rust-repair")
            self.assertEqual(audit["duplicate_candidate_sha256"], duplicate["artifact_sha256"])
            self.assertEqual(
                set(evidence),
                {"ai", "typed_ir", "c2rust_repair"},
            )

    def test_repair_matching_ai_or_typed_omits_repair_evidence_and_syncs_audit(self) -> None:
        for duplicate_source in ("ai", "typed"):
            with self.subTest(duplicate_source=duplicate_source), tempfile.TemporaryDirectory(
                prefix=f"c2rust-repair-dedup-{duplicate_source}-"
            ) as tmp:
                root = Path(tmp)
                paths: dict[str, Path] = {}

                def fake_validate(*_args: object, **kwargs: object) -> dict[str, object]:
                    label = str(kwargs["label"])
                    path = Path(kwargs["candidate_path"])
                    paths[label] = path
                    scores = {
                        "ai-initial": 1,
                        "typed-ir": 1,
                        "c2rust-baseline": 2,
                        "c2rust-repair-final": 1,
                    }
                    return exact_result(
                        path,
                        Path(kwargs["attempts_root"]) / label,
                        passed_gates=scores[label],
                    )

                def fake_repair(*_args: object, **kwargs: object) -> tuple[dict[str, object], Path]:
                    out_dir = Path(kwargs["out_dir"])
                    duplicate_path = paths["ai-initial" if duplicate_source == "ai" else "typed-ir"]
                    candidate = out_dir / "l3-generic-slice-c2rust-repair-01-candidate.rs"
                    candidate.write_bytes(duplicate_path.read_bytes())
                    report = self._write_repair_report(out_dir, candidate)
                    return report, candidate

                with mock.patch.object(
                    exact,
                    "repair_c2rust_candidate_after_validation",
                    side_effect=fake_repair,
                ), mock.patch.object(exact, "repair_ai_candidate_after_validation") as ai_repair:
                    result, _canonical, _typed, _manifest, _baseline = run_stage(
                        root,
                        fake_validate=fake_validate,
                    )

                ai_repair.assert_not_called()
                evidence = result["router"]["candidate_evidence"]
                self.assertNotIn("c2rust_repair", evidence)
                self.assertIn("c2rust_baseline", evidence)
                duplicate = next(
                    item
                    for item in result["router"]["deduplicated_candidates"]
                    if item["source"] == "c2rust-repair"
                )
                audit = result["router"]["candidate_source_audit"]["c2rust_repair"]
                expected_source = "opencode-ai" if duplicate_source == "ai" else "typed-ir"
                self.assertEqual(audit["status"], "duplicate")
                self.assertEqual(audit["duplicate_of"], duplicate["duplicate_of"])
                self.assertEqual(audit["duplicate_source"], expected_source)
                self.assertEqual(audit["duplicate_candidate_sha256"], duplicate["artifact_sha256"])
                self.assertEqual(set(evidence), {"ai", "typed_ir", "c2rust_baseline"})

    def _write_repair_report(self, out_dir: Path, candidate: Path) -> dict[str, object]:
        report: dict[str, object] = {
            "schema_version": 1,
            "slice_id": "generic-slice",
            "artifact_label": "c2rust-repair",
            "input_source": "c2rust-baseline",
            "status": "candidate_ready_for_common_validation",
            "rounds": [{"round": 1}],
            "final_candidate": {"path": candidate.name, "sha256": sha256_path(candidate)},
        }
        (out_dir / "l3-generic-slice-c2rust-repair-report.json").write_text(
            json.dumps(report),
            encoding="utf-8",
        )
        return report


if __name__ == "__main__":
    unittest.main()
