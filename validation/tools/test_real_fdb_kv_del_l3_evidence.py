import json
import subprocess
import unittest
from pathlib import Path

from validation.tools import validate_judge_entrypoints as judge_validator


REPO_ROOT = Path(__file__).resolve().parents[2]


class RealFdbKvDelL3EvidenceTests(unittest.TestCase):
    def test_emit_reports_records_real_fdb_kv_del_replay_and_diff_gates(self) -> None:
        result = subprocess.run(
            [
                "cargo",
                "run",
                "--manifest-path",
                "validation/l2_slices/Cargo.toml",
                "--bin",
                "emit_reports",
            ],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
        )
        self.assertEqual(
            result.returncode,
            0,
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

        evidence_dir = REPO_ROOT / "validation" / "evidence" / "flashdb"
        slice_spec = self._load(REPO_ROOT / "validation" / "slice-specs" / "flashdb-real-fdb-kv-del.json")
        prefix = "l3-real-fdb-kv-del"
        c_oracle = self._load(evidence_dir / f"{prefix}-c-oracle.json")
        rust_report = self._load(evidence_dir / f"{prefix}-rust-report.json")
        diff = self._load(evidence_dir / f"{prefix}-diff.json")
        negative_diff = self._load(evidence_dir / f"{prefix}-negative-diff.json")

        self.assertEqual(c_oracle["target_id"], "flashdb")
        self.assertEqual(c_oracle["slice_id"], "real-fdb-kv-del")
        self.assertEqual(c_oracle["status"], "passed")
        self.assertTrue(c_oracle["semantic_pass"])
        self.assertEqual(c_oracle["toolchain_status"], "C_ORACLE_GENERATED")
        self.assertEqual(c_oracle["source_commit"], slice_spec["source_commit"])
        self.assertEqual(rust_report["source_commit"], slice_spec["source_commit"])
        self.assertEqual(diff["source_commit"], slice_spec["source_commit"])
        self.assertEqual(negative_diff["source_commit"], slice_spec["source_commit"])
        self.assertEqual(c_oracle["case_count"], 1)
        self.assertEqual(
            c_oracle["generator"],
            "validation/l2_slices/src/bin/emit_reports.rs::emit_real_fdb_kv_del",
        )
        self.assertEqual(
            c_oracle["command"],
            "cargo run --manifest-path validation/l2_slices/Cargo.toml --bin emit_reports",
        )
        self.assertEqual(
            c_oracle["source_boundary"]["files"],
            ["src/fdb_kvdb.c", "inc/fdb_def.h", "inc/flashdb.h"],
        )
        self.assertEqual(
            rust_report["rust_module_path"],
            "validation/l2_slices/src/fdb_kv_del.rs",
        )
        self.assertEqual(
            [case["return_code"] for case in c_oracle["cases"]],
            [7],
        )
        self.assertEqual(
            [case["return_code"] for case in rust_report["cases"]],
            [7],
        )
        provenance = c_oracle["provenance"]
        self.assertEqual(
            provenance["fixture_sha256"],
            self._sha256(REPO_ROOT / c_oracle["fixture"]),
        )
        self.assertEqual(
            provenance["source_file_hashes"]["src/fdb_kvdb.c"],
            "f917a62faaa28bca738d9cd0b115e791e2d2a333ad0530fca8ba558a3750a030",
        )
        self.assertEqual(
            provenance["source_span_sha256"],
            "7b84bb3061b770b0a75bc8560b4059502f48ce1e87e1fee16f32c698bed09185",
        )
        self.assertEqual(
            provenance["harness_draft_ref"]["path"],
            "validation/evidence/flashdb/auto-translation/real-fdb-kv-del/l3-real-fdb-kv-del-c-oracle-harness-draft.c",
        )
        self.assertEqual(
            provenance["harness_draft_ref"]["sha256"],
            self._sha256(REPO_ROOT / provenance["harness_draft_ref"]["path"]),
        )
        self.assertEqual(
            provenance["evidence_refs"]["c_oracle_status"],
            "validation/evidence/flashdb/auto-translation/real-fdb-kv-del/l3-real-fdb-kv-del-c-oracle-status.json",
        )
        self.assertEqual(diff["status"], "passed")
        self.assertEqual(diff["case_count"], 1)
        self.assertEqual(diff["compared_fields"], ["return_code"])
        self.assertIsNone(diff["first_mismatch"])
        self.assertEqual(negative_diff["status"], "expected_failed")
        self.assertTrue(negative_diff["expected_failure"])
        self.assertTrue(negative_diff["mutation_detected"])
        self.assertEqual(negative_diff["first_mismatch"]["field"], "return_code")

    def test_emit_reports_records_real_fdb_kv_set_replay_and_diff_gates(self) -> None:
        result = subprocess.run(
            [
                "cargo",
                "run",
                "--manifest-path",
                "validation/l2_slices/Cargo.toml",
                "--bin",
                "emit_reports",
            ],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
        )
        self.assertEqual(
            result.returncode,
            0,
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

        evidence_dir = REPO_ROOT / "validation" / "evidence" / "flashdb"
        slice_spec = self._load(REPO_ROOT / "validation" / "slice-specs" / "flashdb-real-fdb-kv-set.json")
        prefix = "l3-real-fdb-kv-set"
        c_oracle = self._load(evidence_dir / f"{prefix}-c-oracle.json")
        rust_report = self._load(evidence_dir / f"{prefix}-rust-report.json")
        diff = self._load(evidence_dir / f"{prefix}-diff.json")
        negative_diff = self._load(evidence_dir / f"{prefix}-negative-diff.json")

        self.assertEqual(c_oracle["target_id"], "flashdb")
        self.assertEqual(c_oracle["slice_id"], "real-fdb-kv-set")
        self.assertEqual(c_oracle["status"], "passed")
        self.assertTrue(c_oracle["semantic_pass"])
        self.assertEqual(c_oracle["toolchain_status"], "C_ORACLE_GENERATED")
        self.assertEqual(c_oracle["source_commit"], slice_spec["source_commit"])
        self.assertEqual(rust_report["source_commit"], slice_spec["source_commit"])
        self.assertEqual(diff["source_commit"], slice_spec["source_commit"])
        self.assertEqual(negative_diff["source_commit"], slice_spec["source_commit"])
        self.assertEqual(c_oracle["case_count"], 2)
        self.assertEqual(
            c_oracle["generator"],
            "validation/l2_slices/src/bin/emit_reports.rs::emit_real_fdb_kv_set",
        )
        self.assertEqual(
            rust_report["rust_module_path"],
            "validation/l2_slices/src/fdb_kv_set.rs",
        )
        self.assertEqual(
            [case["return_code"] for case in c_oracle["cases"]],
            [7, 7],
        )
        self.assertEqual(
            [case["return_code"] for case in rust_report["cases"]],
            [7, 7],
        )
        provenance = c_oracle["provenance"]
        self.assertEqual(
            provenance["fixture_sha256"],
            self._sha256(REPO_ROOT / c_oracle["fixture"]),
        )
        self.assertEqual(
            provenance["source_file_hashes"]["src/fdb_kvdb.c"],
            "f917a62faaa28bca738d9cd0b115e791e2d2a333ad0530fca8ba558a3750a030",
        )
        self.assertEqual(
            provenance["source_span_sha256"],
            "c71859844c82437b87ee6d52739f623d82771252a0eb2b29dc373d6a8ce4dd95",
        )
        self.assertEqual(
            provenance["harness_draft_ref"]["path"],
            "validation/evidence/flashdb/auto-translation/real-fdb-kv-set/l3-real-fdb-kv-set-c-oracle-harness-draft.c",
        )
        self.assertEqual(
            provenance["harness_draft_ref"]["sha256"],
            self._sha256(REPO_ROOT / provenance["harness_draft_ref"]["path"]),
        )
        self.assertEqual(diff["status"], "passed")
        self.assertEqual(diff["case_count"], 2)
        self.assertEqual(diff["compared_fields"], ["return_code"])
        self.assertIsNone(diff["first_mismatch"])
        self.assertEqual(negative_diff["status"], "expected_failed")
        self.assertTrue(negative_diff["expected_failure"])
        self.assertTrue(negative_diff["mutation_detected"])
        self.assertEqual(negative_diff["first_mismatch"]["field"], "return_code")

    @staticmethod
    def _load(path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8-sig"))

    @staticmethod
    def _sha256(path: Path) -> str:
        return judge_validator.sha256_file(path)


if __name__ == "__main__":
    unittest.main()
