import json
import hashlib
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
AUTO_MIGRATE = REPO_ROOT / "validation" / "tools" / "auto_migrate.py"
VALIDATOR = REPO_ROOT / "validation" / "tools" / "validate_auto_translation_evidence.py"


class ValidateAutoTranslationEvidenceTests(unittest.TestCase):
    def test_rejects_missing_route_profile_reference_in_final_verification(self) -> None:
        spec_path = REPO_ROOT / "validation" / "slice-specs" / "zlib-adler32-step.json"
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            tmp_path = Path(tmp)
            out_root = tmp_path / "evidence"

            subprocess.run(
                [
                    "python",
                    str(AUTO_MIGRATE),
                    "--slice-spec",
                    str(spec_path),
                    "--out-root",
                    str(out_root),
                    "--skip-c-oracle",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=True,
            )

            evidence_dir = out_root / "zlib-ng" / "auto-translation" / "adler32-step"
            final_path = evidence_dir / "l3-adler32-step-final-verification.json"
            final = json.loads(final_path.read_text(encoding="utf-8"))
            final.pop("validation_profile", None)
            final_path.write_text(json.dumps(final), encoding="utf-8")

            result = subprocess.run(
                [
                    "python",
                    str(VALIDATOR),
                    "--target-id",
                    "zlib-ng",
                    "--slice-id",
                    "adler32-step",
                    "--slice-spec",
                    str(spec_path),
                    "--evidence-root",
                    str(out_root),
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("final_verification.validation_profile", result.stderr + result.stdout)

    def test_rejects_missing_c2rust_baseline_reference_in_l3_manifest(self) -> None:
        spec_path = REPO_ROOT / "validation" / "slice-specs" / "zlib-adler32-step.json"
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            tmp_path = Path(tmp)
            out_root = tmp_path / "evidence"

            subprocess.run(
                [
                    "python",
                    str(AUTO_MIGRATE),
                    "--slice-spec",
                    str(spec_path),
                    "--out-root",
                    str(out_root),
                    "--skip-c-oracle",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=True,
            )

            evidence_dir = out_root / "zlib-ng" / "auto-translation" / "adler32-step"
            manifest_path = evidence_dir / "l3-adler32-step-evidence-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["evidence"].pop("c2rust_baseline", None)
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            result = subprocess.run(
                [
                    "python",
                    str(VALIDATOR),
                    "--target-id",
                    "zlib-ng",
                    "--slice-id",
                    "adler32-step",
                    "--slice-spec",
                    str(spec_path),
                    "--evidence-root",
                    str(out_root),
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("c2rust_baseline", result.stderr + result.stdout)

    def test_rejects_route_decision_ref_sha_drift(self) -> None:
        spec_path = REPO_ROOT / "validation" / "slice-specs" / "zlib-adler32-step.json"
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            tmp_path = Path(tmp)
            out_root = tmp_path / "evidence"

            subprocess.run(
                [
                    "python",
                    str(AUTO_MIGRATE),
                    "--slice-spec",
                    str(spec_path),
                    "--out-root",
                    str(out_root),
                    "--skip-c-oracle",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=True,
            )

            evidence_dir = out_root / "zlib-ng" / "auto-translation" / "adler32-step"
            manifest_path = evidence_dir / "l3-adler32-step-evidence-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["evidence"]["route_decision"]["sha256"] = "wrong-sha"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            result = subprocess.run(
                [
                    "python",
                    str(VALIDATOR),
                    "--target-id",
                    "zlib-ng",
                    "--slice-id",
                    "adler32-step",
                    "--slice-spec",
                    str(spec_path),
                    "--evidence-root",
                    str(out_root),
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("sha256", result.stderr + result.stdout)

    def test_rejects_cache_missing_route_baseline_profile_identities(self) -> None:
        spec_path = REPO_ROOT / "validation" / "slice-specs" / "zlib-adler32-step.json"
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            tmp_path = Path(tmp)
            out_root = tmp_path / "evidence"

            subprocess.run(
                [
                    "python",
                    str(AUTO_MIGRATE),
                    "--slice-spec",
                    str(spec_path),
                    "--out-root",
                    str(out_root),
                    "--skip-c-oracle",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=True,
            )

            evidence_dir = out_root / "zlib-ng" / "auto-translation" / "adler32-step"
            cache_path = evidence_dir / "l3-adler32-step-auto-cache-metadata.json"
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
            cache.pop("route_decision_identity", None)
            cache_path.write_text(json.dumps(cache), encoding="utf-8")

            result = subprocess.run(
                [
                    "python",
                    str(VALIDATOR),
                    "--target-id",
                    "zlib-ng",
                    "--slice-id",
                    "adler32-step",
                    "--slice-spec",
                    str(spec_path),
                    "--evidence-root",
                    str(out_root),
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("route_decision_identity", result.stderr + result.stdout)

    def test_rejects_generated_c2rust_baseline_without_output(self) -> None:
        spec_path = REPO_ROOT / "validation" / "slice-specs" / "zlib-adler32-step.json"
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            tmp_path = Path(tmp)
            out_root = tmp_path / "evidence"

            subprocess.run(
                [
                    "python",
                    str(AUTO_MIGRATE),
                    "--slice-spec",
                    str(spec_path),
                    "--out-root",
                    str(out_root),
                    "--skip-c-oracle",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=True,
            )

            evidence_dir = out_root / "zlib-ng" / "auto-translation" / "adler32-step"
            baseline_path = evidence_dir / "l3-adler32-step-c2rust-baseline-manifest.json"
            baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
            baseline["status"] = "generated"
            baseline["reason"] = "test-forged-generated-status"
            baseline["selected_command"] = {
                "name": "c2rust",
                "path": "fake-c2rust",
                "available": True,
                "version_status": "OK",
                "version": "fake",
            }
            baseline["output"] = None
            baseline_path.write_text(json.dumps(baseline), encoding="utf-8")

            result = subprocess.run(
                [
                    "python",
                    str(VALIDATOR),
                    "--target-id",
                    "zlib-ng",
                    "--slice-id",
                    "adler32-step",
                    "--slice-spec",
                    str(spec_path),
                    "--evidence-root",
                    str(out_root),
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("object", result.stderr + result.stdout)

    def test_rejects_semantic_pass_missing_external_callee_context_binding(self) -> None:
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            tmp_path = Path(tmp)
            out_root = tmp_path / "evidence"
            source_dir = REPO_ROOT / "validation" / "evidence" / "demo" / "auto-translation" / "call-expression"
            evidence_dir = out_root / "demo" / "auto-translation" / "call-expression"
            shutil.copytree(source_dir, evidence_dir)
            self._backfill_route_baseline_profile_evidence(evidence_dir, "demo", "call-expression")

            spec = json.loads((REPO_ROOT / "validation" / "slice-specs" / "demo-call-expression.json").read_text())
            spec["c_boundary"]["signatures"].append(
                {
                    "id": "sig-helper-add-one",
                    "role": "external_direct_callee",
                    "function": "helper_add_one",
                    "return_type": "int",
                    "parameters": [{"name": "value", "c_type": "int"}],
                    "source_ref": "unit/helper.c#helper_add_one",
                    "signature_sha256": "helper-signature-sha",
                    "definition_status": "real_source_bound",
                    "c_source": "int helper_add_one(int value) { return value + 1; }",
                }
            )
            spec["c_boundary"]["external_direct_callees"] = [
                {
                    "name": "helper_add_one",
                    "signature_ref": "sig-helper-add-one",
                    "source_files": [{"path": "unit/helper.c", "sha256": "helper-sha"}],
                    "definition_status": "real_source_bound",
                    "stub_boundary": "compile_only",
                }
            ]
            spec_path = tmp_path / "demo-call-expression-external-callee.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")

            result = subprocess.run(
                [
                    "python",
                    str(VALIDATOR),
                    "--target-id",
                    "demo",
                    "--slice-id",
                    "call-expression",
                    "--slice-spec",
                    str(spec_path),
                    "--evidence-root",
                    str(out_root),
                    "--require-semantic-pass",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("external callee", result.stderr + result.stdout)

    def test_rejects_read_write_pointer_graph_missing_alias_gate_fields(self) -> None:
        spec_path = REPO_ROOT / "validation" / "slice-specs" / "demo-copy-i32-ptr-arith.json"
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            tmp_path = Path(tmp)
            out_root = tmp_path / "evidence"

            subprocess.run(
                [
                    "python",
                    str(AUTO_MIGRATE),
                    "--slice-spec",
                    str(spec_path),
                    "--out-root",
                    str(out_root),
                    "--skip-c-oracle",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=True,
            )

            pointer_graph_path = (
                out_root
                / "demo"
                / "auto-translation"
                / "copy-i32-ptr-arith"
                / "l3-copy-i32-ptr-arith-pointer-graph.json"
            )
            pointer_graph = json.loads(pointer_graph_path.read_text(encoding="utf-8"))
            for key in ["alias_sets", "alias_risks", "alias_contract", "safe_boundary_preconditions"]:
                pointer_graph.pop(key, None)
            pointer_graph_path.write_text(json.dumps(pointer_graph), encoding="utf-8")

            result = subprocess.run(
                [
                    "python",
                    str(VALIDATOR),
                    "--target-id",
                    "demo",
                    "--slice-id",
                    "copy-i32-ptr-arith",
                    "--slice-spec",
                    str(spec_path),
                    "--evidence-root",
                    str(out_root),
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("alias gate", result.stderr + result.stdout)

    def _backfill_route_baseline_profile_evidence(self, evidence_dir: Path, target_id: str, slice_id: str) -> None:
        prefix = f"l3-{slice_id}"
        manifest_path = evidence_dir / f"{prefix}-evidence-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        source_commit = manifest.get("source_commit", "UNKNOWN0")
        baseline_path = evidence_dir / f"{prefix}-c2rust-baseline-manifest.json"
        route_path = evidence_dir / f"{prefix}-route-decision.json"
        profile_path = evidence_dir / f"{prefix}-validation-profile.json"

        baseline = {
            "schema_version": 1,
            "target_id": target_id,
            "slice_id": slice_id,
            "status": "skipped",
            "reason": "unit_test_backfill_for_legacy_fixture",
            "correctness_role": "candidate_context_only",
            "fallback_oracle": "original_c_oracle_required",
            "validation_impact": "legacy fixture backfill only; accepted gates remain authoritative",
            "source_commit": source_commit,
            "slice_spec": {"path": f"validation/slice-specs/demo-{slice_id}.json", "sha256": "legacy-fixture"},
            "build_profile_hash": "legacy-fixture",
            "commands": [],
            "selected_command": None,
            "reference_tree": {"path": "F:/agent/c2rust-master", "status": "missing", "cargo_toml": ""},
            "output": None,
            "diagnostics": ["legacy fixture backfill"],
        }
        self._write_json(baseline_path, baseline)

        route = {
            "schema_version": 1,
            "target_id": target_id,
            "slice_id": slice_id,
            "status": "recorded",
            "level": "L0",
            "translator": {"kind": "tier1", "candidate_generation_allowed": True},
            "rationale": [{"feature": "legacy_fixture_backfill", "weight": "low"}],
            "verification_profile": "L0-dev",
            "source_artifacts": {
                "type_map": self._ref(evidence_dir / f"{prefix}-type-map.json", "recorded"),
                "cfg": self._ref(evidence_dir / f"{prefix}-cfg.json", "recorded"),
                "pointer_graph": self._ref(evidence_dir / f"{prefix}-pointer-graph.json", "not_applicable"),
                "translation_plan": self._ref(evidence_dir / f"{prefix}-auto-translation-plan.json", "draft_generated"),
                "c2rust_baseline": self._ref(baseline_path, "skipped"),
            },
            "policy": {
                "goal": "dev",
                "fixed_loop_count_required": False,
                "repair_budget_source": "run_policy",
            },
            "misroute": None,
        }
        self._write_json(route_path, route)

        profile = {
            "schema_version": 1,
            "target_id": target_id,
            "slice_id": slice_id,
            "status": "passed",
            "profile": "L0-dev",
            "route_level": "L0",
            "goal": "dev",
            "required_gates": ["compile", "c_oracle_diff"],
            "optional_gates": ["negative_diff", "evidence_cleanliness", "fuzz_property", "miri", "kani"],
            "skipped_gates": [],
            "required_gate_status": {"compile": "passed", "c_oracle_diff": "C_ORACLE_GENERATED"},
            "loop_policy": {"source": "run_policy", "fixed_project_loop_count_required": False, "stress_loops": None},
            "tool_boundaries": {
                "c_ub": ["clang_diagnostics", "sanitizer_oracle", "unsupported_evidence"],
                "rust_ub": ["miri", "unsafe_ledger", "rust_verification_tools"],
            },
        }
        self._write_json(profile_path, profile)

        route_ref = self._ref(route_path, "recorded")
        route_ref["level"] = "L0"
        profile_ref = self._ref(profile_path, "passed")
        profile_ref["profile"] = "L0-dev"
        baseline_ref = self._ref(baseline_path, "skipped")

        final_path = evidence_dir / f"{prefix}-final-verification.json"
        final = json.loads(final_path.read_text(encoding="utf-8"))
        final["c2rust_baseline"] = baseline_ref
        final["route_decision"] = route_ref
        final["validation_profile"] = profile_ref
        final["skipped_gates"] = []
        final["validation_profile_status"] = "passed"
        self._write_json(final_path, final)

        cache_path = evidence_dir / f"{prefix}-auto-cache-metadata.json"
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
        cache["c2rust_baseline_identity"] = {"status": "skipped", "sha256": self._sha256_json(baseline)}
        cache["route_decision_identity"] = {"status": "recorded", "sha256": self._sha256_json(route)}
        cache["validation_profile_identity"] = {"status": "passed", "sha256": self._sha256_json(profile)}
        fields = cache.setdefault("cache_input_fields", [])
        for key in ["c2rust_baseline_identity", "route_decision_identity", "validation_profile_identity"]:
            if key not in fields:
                fields.append(key)
        cache["dependent_artifacts"] = {
            "c2rust_baseline": baseline_ref,
            "route_decision": route_ref,
            "validation_profile": profile_ref,
        }
        self._write_json(cache_path, cache)

        auto_manifest_path = evidence_dir / f"{prefix}-auto-translation-manifest.json"
        if auto_manifest_path.exists():
            auto_manifest = json.loads(auto_manifest_path.read_text(encoding="utf-8"))
            auto_manifest["c2rust_baseline"] = baseline_ref
            auto_manifest["route_decision"] = route_ref
            auto_manifest["validation_profile"] = profile_ref
            self._write_json(auto_manifest_path, auto_manifest)

        manifest["evidence"]["c2rust_baseline"] = baseline_ref
        manifest["evidence"]["route_decision"] = route_ref
        manifest["evidence"]["validation_profile"] = profile_ref
        manifest["evidence"]["final_verification"] = self._ref(final_path, final.get("status", "passed"))
        manifest["evidence"]["cache_metadata"] = self._ref(cache_path, "recorded")
        self._write_json(manifest_path, manifest)

    def _ref(self, path: Path, status: str) -> dict:
        return {"path": path.as_posix(), "status": status, "sha256": self._sha256(path)}

    def _write_json(self, path: Path, payload: dict) -> None:
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def _sha256(self, path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _sha256_json(self, payload: dict) -> str:
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()

    def test_rejects_missing_alias_gate_in_manifest_and_final_verification(self) -> None:
        spec_path = REPO_ROOT / "validation" / "slice-specs" / "demo-copy-i32-ptr-arith.json"
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            tmp_path = Path(tmp)
            out_root = tmp_path / "evidence"

            subprocess.run(
                [
                    "python",
                    str(AUTO_MIGRATE),
                    "--slice-spec",
                    str(spec_path),
                    "--out-root",
                    str(out_root),
                    "--skip-c-oracle",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=True,
            )

            evidence_dir = out_root / "demo" / "auto-translation" / "copy-i32-ptr-arith"
            for file_name in [
                "l3-copy-i32-ptr-arith-evidence-manifest.json",
                "l3-copy-i32-ptr-arith-final-verification.json",
            ]:
                path = evidence_dir / file_name
                payload = json.loads(path.read_text(encoding="utf-8"))
                payload.get("claim_boundary", {}).pop("alias_gate", None)
                payload.pop("alias_gate", None)
                path.write_text(json.dumps(payload), encoding="utf-8")

            result = subprocess.run(
                [
                    "python",
                    str(VALIDATOR),
                    "--target-id",
                    "demo",
                    "--slice-id",
                    "copy-i32-ptr-arith",
                    "--slice-spec",
                    str(spec_path),
                    "--evidence-root",
                    str(out_root),
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("alias gate", result.stderr + result.stdout)

    def test_rejects_empty_alias_risk_and_noalias_precondition_for_unknown_alias(self) -> None:
        spec_path = REPO_ROOT / "validation" / "slice-specs" / "demo-copy-i32-ptr-arith.json"
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            tmp_path = Path(tmp)
            out_root = tmp_path / "evidence"

            subprocess.run(
                [
                    "python",
                    str(AUTO_MIGRATE),
                    "--slice-spec",
                    str(spec_path),
                    "--out-root",
                    str(out_root),
                    "--skip-c-oracle",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=True,
            )

            pointer_graph_path = (
                out_root
                / "demo"
                / "auto-translation"
                / "copy-i32-ptr-arith"
                / "l3-copy-i32-ptr-arith-pointer-graph.json"
            )
            pointer_graph = json.loads(pointer_graph_path.read_text(encoding="utf-8"))
            pointer_graph["alias_risks"] = []
            pointer_graph["safe_boundary_preconditions"] = []
            pointer_graph_path.write_text(json.dumps(pointer_graph), encoding="utf-8")

            result = subprocess.run(
                [
                    "python",
                    str(VALIDATOR),
                    "--target-id",
                    "demo",
                    "--slice-id",
                    "copy-i32-ptr-arith",
                    "--slice-spec",
                    str(spec_path),
                    "--evidence-root",
                    str(out_root),
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("alias gate", result.stderr + result.stdout)


if __name__ == "__main__":
    unittest.main()
