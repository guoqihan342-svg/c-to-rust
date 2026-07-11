from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from validation.tools import _auto_migrate_ai_exact as exact
from validation.tools import validate_judge_entrypoints as judge_validator
from validation.tools._ai_candidate_harness_parts import router
from validation.tools._ai_candidate_harness_parts.context import sha256_path


def write_baseline_manifest(
    evidence_dir: Path,
    source: bytes,
    *,
    status: str = "generated",
    declared_sha256: str | None = None,
    output_path: Path | None = None,
) -> tuple[dict[str, object], Path, Path]:
    evidence_dir.mkdir(parents=True, exist_ok=True)
    artifact = output_path or evidence_dir / "raw-c2rust-output.rs"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_bytes(source)
    manifest = {
        "schema_version": 1,
        "status": status,
        "output": {
            "path": artifact.as_posix(),
            "status": "generated",
            "sha256": declared_sha256 or judge_validator.sha256_file(artifact),
        },
        "compile": {"status": "passed", "semantic_pass": True},
        "correctness_role": "candidate_context_only",
    }
    manifest_path = evidence_dir / "current-run-c2rust-baseline-manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return manifest, manifest_path, artifact


def exact_result(path: Path, attempt_dir: Path, *, passed: bool) -> dict[str, object]:
    candidate_sha = sha256_path(path)
    status = "passed" if passed else "failed"
    gate_status = "passed" if passed else "failed"
    return {
        "schema_version": 1,
        "status": status,
        "candidate_sha256": candidate_sha,
        "semantic_pass": passed,
        "oracle_proof": {},
        "gate_index": {"path": "gate-index.json", "sha256": "a" * 64},
        "gates": {},
        "repair_validation_result": {"status": status, "failures": []},
        "router_gate_results": {
            name: {"status": gate_status, "candidate_sha256": candidate_sha}
            for name in router.REQUIRED_GATES
        },
        "attempt_dir": attempt_dir.as_posix(),
    }


class C2RustBaselineResolutionTests(unittest.TestCase):
    def test_reopens_only_current_run_sha_bound_output(self) -> None:
        with tempfile.TemporaryDirectory(prefix="c2rust-raw-resolve-") as tmp:
            evidence_dir = Path(tmp) / "evidence"
            manifest, manifest_path, artifact = write_baseline_manifest(
                evidence_dir,
                b"pub fn migrated(value: i32) -> i32 { value }\n",
            )

            reopened, audit = exact.resolve_current_c2rust_baseline_candidate(
                manifest,
                manifest_path=manifest_path,
                evidence_dir=evidence_dir,
                repo_root=Path(tmp),
            )

            self.assertEqual(reopened, artifact.resolve())
            self.assertEqual(audit["status"], "eligible_for_exact_gates")
            self.assertEqual(audit["artifact"]["candidate_sha256"], sha256_path(artifact))
            self.assertNotIn("compile", audit)

    def test_skipped_or_sha_drift_is_audited_without_candidate(self) -> None:
        with tempfile.TemporaryDirectory(prefix="c2rust-raw-reject-") as tmp:
            evidence_dir = Path(tmp) / "evidence"
            skipped, skipped_path, _ = write_baseline_manifest(
                evidence_dir,
                b"pub fn skipped() {}\n",
                status="skipped",
            )
            reopened, audit = exact.resolve_current_c2rust_baseline_candidate(
                skipped,
                manifest_path=skipped_path,
                evidence_dir=evidence_dir,
                repo_root=Path(tmp),
            )
            self.assertIsNone(reopened)
            self.assertEqual(audit["reason"], "baseline_manifest_not_generated")

            invalid, invalid_path, _ = write_baseline_manifest(
                evidence_dir,
                b"pub fn drifted() {}\n",
                declared_sha256="0" * 64,
            )
            reopened, audit = exact.resolve_current_c2rust_baseline_candidate(
                invalid,
                manifest_path=invalid_path,
                evidence_dir=evidence_dir,
                repo_root=Path(tmp),
            )
            self.assertIsNone(reopened)
            self.assertEqual(audit["reason"], "baseline_output_sha256_mismatch")

    def test_output_outside_current_run_and_manifest_drift_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory(prefix="c2rust-raw-scope-") as tmp:
            root = Path(tmp)
            evidence_dir = root / "evidence"
            outside = root / "outside.rs"
            manifest, manifest_path, _ = write_baseline_manifest(
                evidence_dir,
                b"pub fn outside() {}\n",
                output_path=outside,
            )
            reopened, audit = exact.resolve_current_c2rust_baseline_candidate(
                manifest,
                manifest_path=manifest_path,
                evidence_dir=evidence_dir,
                repo_root=root,
            )
            self.assertIsNone(reopened)
            self.assertEqual(audit["reason"], "baseline_output_not_reopenable_in_current_run")

            manifest["reason"] = "memory-drift"
            reopened, audit = exact.resolve_current_c2rust_baseline_candidate(
                manifest,
                manifest_path=manifest_path,
                evidence_dir=evidence_dir,
                repo_root=root,
            )
            self.assertIsNone(reopened)
            self.assertEqual(audit["reason"], "baseline_manifest_payload_drift")


class C2RustBaselineExactRouteTests(unittest.TestCase):
    def run_stage(self, root: Path, *, duplicate_typed: bool = False) -> tuple[dict[str, object], list[str]]:
        evidence_dir = root / "evidence"
        evidence_dir.mkdir()
        canonical = evidence_dir / "canonical.rs"
        typed = evidence_dir / "typed.rs"
        canonical.write_text("pub fn migrated(value: i32) -> i32 { value - 1 }\n", encoding="utf-8")
        typed.write_text("pub fn migrated(value: i32) -> i32 { value }\n", encoding="utf-8")
        baseline_source = typed.read_bytes() if duplicate_typed else b"pub fn migrated(value: i32) -> i32 { value + 1 }\n"
        manifest, manifest_path, baseline = write_baseline_manifest(evidence_dir, baseline_source)
        calls: list[str] = []

        def fake_validate(*args: object, **kwargs: object) -> dict[str, object]:
            path = Path(kwargs["candidate_path"])
            calls.append(path.name)
            passed = path.resolve() == baseline.resolve() and not duplicate_typed
            return exact_result(path, Path(kwargs["attempts_root"]) / path.stem, passed=passed)

        ai_manifest: dict[str, object] = {
            "status": "generated",
            "selected_candidate_id": "opencode-glm51-1",
            "candidates": [{"candidate_id": "opencode-glm51-1", "applied": True}],
        }
        with mock.patch.object(exact, "_validate_with_new_attempt", side_effect=fake_validate):
            result = exact.run_ai_exact_stage(
                {"slice_id": "generic-slice"},
                context_pack={},
                ai_manifest=ai_manifest,
                evidence_dir=evidence_dir,
                canonical_draft_path=canonical,
                deterministic_candidate_path=typed,
                c2rust_baseline=manifest,
                c2rust_baseline_manifest_path=manifest_path,
                replay_test_path=evidence_dir / "replay.rs",
                oracle_payload={},
                harness_path=evidence_dir / "oracle.c",
                proof_root=root,
                compile_runner=lambda path: {},
                replay_runner=lambda path, replay: {},
                max_repair_rounds=0,
                opencode_command="unused",
                resolved_model="unused",
                agent="unused",
                variant="unused",
                timeout_seconds=1,
            )
        return result, calls

    def test_raw_baseline_runs_common_exact_gates_and_can_be_selected(self) -> None:
        with tempfile.TemporaryDirectory(prefix="c2rust-raw-route-") as tmp:
            root = Path(tmp)
            result, calls = self.run_stage(root)

            self.assertEqual(calls, ["canonical.rs", "typed.rs", "raw-c2rust-output.rs"])
            self.assertEqual(result["router"]["selected_candidate_id"], "c2rust-baseline:raw-current-run")
            self.assertEqual(
                [item["source"] for item in result["router"]["candidate_set"]],
                ["opencode-ai", "typed-ir", "c2rust-baseline"],
            )
            self.assertEqual(result["router"]["provider_invocations"], 1)
            self.assertEqual(
                result["router"]["candidate_source_audit"]["c2rust_baseline"]["reason"],
                "fresh_exact_gates_passed",
            )
            self.assertEqual(
                (root / "evidence" / "canonical.rs").read_bytes(),
                (root / "evidence" / "raw-c2rust-output.rs").read_bytes(),
            )
            self.assertFalse(result["ai_manifest"]["candidates"][0]["applied"])

    def test_duplicate_baseline_is_audited_without_an_extra_gate_run(self) -> None:
        with tempfile.TemporaryDirectory(prefix="c2rust-raw-duplicate-") as tmp:
            result, calls = self.run_stage(Path(tmp), duplicate_typed=True)

            self.assertEqual(calls, ["canonical.rs", "typed.rs"])
            self.assertEqual(result["router"]["selected_candidate_id"], None)
            self.assertEqual(len(result["router"]["deduplicated_candidates"]), 1)
            self.assertEqual(
                result["router"]["candidate_source_audit"]["c2rust_baseline"]["reason"],
                "duplicate_exact_artifact_sha256",
            )
            self.assertNotIn("c2rust_baseline", result["router"]["candidate_evidence"])


if __name__ == "__main__":
    unittest.main()
