import json
import tomllib
import tempfile
import unittest
from pathlib import Path

from validation.tools.validate_flashdb_l3_evidence import validate_flashdb_l3_evidence
from validation.tools.validate_flashdb_version_binding import REPO_ROOT, sha256


class ValidateFlashDbL3EvidenceTests(unittest.TestCase):
    def test_rejects_negative_diff_without_detected_mismatch(self) -> None:
        with tempfile.TemporaryDirectory(prefix="flashdb-l3-test-") as tmp:
            root = Path(tmp)
            self._write_package(root, "l3-demo-slice", negative_mismatch=False)

            with self.assertRaises(SystemExit) as raised:
                validate_flashdb_l3_evidence(root)

            self.assertIn("negative diff", str(raised.exception))
            self.assertIn("demo-slice", str(raised.exception))

    def test_rejects_missing_referenced_evidence_file(self) -> None:
        with tempfile.TemporaryDirectory(prefix="flashdb-l3-test-") as tmp:
            root = Path(tmp)
            self._write_package(root, "l3-demo-slice", omit="unsafe-ledger")

            with self.assertRaises(SystemExit) as raised:
                validate_flashdb_l3_evidence(root)

            self.assertIn("unsafe-ledger", str(raised.exception))
            self.assertIn("demo-slice", str(raised.exception))

    def test_rejects_missing_strict_test_translation_evidence(self) -> None:
        with tempfile.TemporaryDirectory(prefix="flashdb-l3-test-") as tmp:
            root = Path(tmp)
            self._write_package(root, "l3-demo-slice", omit="test-translation")

            with self.assertRaises(SystemExit) as raised:
                validate_flashdb_l3_evidence(root)

            self.assertIn("test-translation", str(raised.exception))
            self.assertIn("demo-slice", str(raised.exception))

    def test_accepts_complete_legacy_summary_package(self) -> None:
        with tempfile.TemporaryDirectory(prefix="flashdb-l3-test-") as tmp:
            root = Path(tmp)
            self._write_package(root, "l3-demo-slice")

            report = validate_flashdb_l3_evidence(root)

            self.assertEqual(report["status"], "passed")
            self.assertEqual(report["slice_count"], 1)
            self.assertEqual(report["slices"][0]["slice_id"], "demo-slice")
            self.assertEqual(report["slices"][0]["negative_diff"], "passed")

    def test_rejects_failed_positive_diff_report(self) -> None:
        with tempfile.TemporaryDirectory(prefix="flashdb-l3-test-") as tmp:
            root = Path(tmp)
            self._write_package(root, "l3-demo-slice", positive_diff_status="failed")

            with self.assertRaises(SystemExit) as raised:
                validate_flashdb_l3_evidence(root)

            self.assertIn("positive diff", str(raised.exception))
            self.assertIn("demo-slice", str(raised.exception))

    def test_rejects_positive_diff_with_first_mismatch(self) -> None:
        with tempfile.TemporaryDirectory(prefix="flashdb-l3-test-") as tmp:
            root = Path(tmp)
            self._write_package(
                root,
                "l3-demo-slice",
                positive_diff_status="passed",
                positive_diff_first_mismatch="steps.demo.value",
            )

            with self.assertRaises(SystemExit) as raised:
                validate_flashdb_l3_evidence(root)

            self.assertIn("positive diff", str(raised.exception))
            self.assertIn("first_mismatch", str(raised.exception))
            self.assertIn("demo-slice", str(raised.exception))

    def test_rejects_failed_final_verification_report(self) -> None:
        with tempfile.TemporaryDirectory(prefix="flashdb-l3-test-") as tmp:
            root = Path(tmp)
            self._write_package(root, "l3-demo-slice", final_verification_status="failed")

            with self.assertRaises(SystemExit) as raised:
                validate_flashdb_l3_evidence(root)

            self.assertIn("final verification", str(raised.exception))
            self.assertIn("demo-slice", str(raised.exception))

    def test_rejects_failed_final_verification_diff_status(self) -> None:
        with tempfile.TemporaryDirectory(prefix="flashdb-l3-test-") as tmp:
            root = Path(tmp)
            self._write_package(root, "l3-demo-slice", final_diff_status="failed")

            with self.assertRaises(SystemExit) as raised:
                validate_flashdb_l3_evidence(root)

            self.assertIn("final verification", str(raised.exception))
            self.assertIn("diff_status", str(raised.exception))
            self.assertIn("demo-slice", str(raised.exception))

    def test_rejects_failed_final_verification_check(self) -> None:
        with tempfile.TemporaryDirectory(prefix="flashdb-l3-test-") as tmp:
            root = Path(tmp)
            self._write_package(
                root,
                "l3-demo-slice",
                final_checks=[{"name": "schema-diff", "status": "failed", "exit_code": 1}],
            )

            with self.assertRaises(SystemExit) as raised:
                validate_flashdb_l3_evidence(root)

            self.assertIn("final verification", str(raised.exception))
            self.assertIn("schema-diff", str(raised.exception))
            self.assertIn("demo-slice", str(raised.exception))

    def test_rejects_summary_declared_evidence_hash_mismatch(self) -> None:
        with tempfile.TemporaryDirectory(prefix="flashdb-l3-test-") as tmp:
            root = Path(tmp)
            self._write_package(root, "l3-demo-slice", summary_hash_mismatch=True)

            with self.assertRaises(SystemExit) as raised:
                validate_flashdb_l3_evidence(root)

            self.assertIn("sha256", str(raised.exception))
            self.assertIn("demo-slice", str(raised.exception))

    def test_rejects_incomplete_passed_summary_even_when_strict_package_exists(self) -> None:
        with tempfile.TemporaryDirectory(prefix="flashdb-l3-test-") as tmp:
            root = Path(tmp)
            self._write_package(root, "l3-demo-slice")
            flashdb = root / "flashdb"
            self._write_json(
                flashdb / "l3-legacy-slice-summary.json",
                {
                    "schema_version": 1,
                    "target_id": "flashdb",
                    "slice_id": "legacy-slice",
                    "status": "passed",
                },
            )

            with self.assertRaises(SystemExit) as raised:
                validate_flashdb_l3_evidence(root)

            self.assertIn("legacy-slice", str(raised.exception))
            self.assertIn("strict", str(raised.exception))

    def test_rejects_invalid_version_manifest_referenced_by_binding(self) -> None:
        with tempfile.TemporaryDirectory(prefix="flashdb-l3-test-") as tmp:
            root = Path(tmp)
            self._write_package(root, "l3-demo-slice", invalid_version_manifest=True)

            with self.assertRaises(SystemExit) as raised:
                validate_flashdb_l3_evidence(root)

            self.assertIn("version manifest", str(raised.exception))

    def test_rejects_declared_evidence_path_with_wrong_directory(self) -> None:
        with tempfile.TemporaryDirectory(prefix="flashdb-l3-test-") as tmp:
            root = Path(tmp)
            prefix = "l3-demo-slice"
            self._write_package(root, prefix)
            summary_path = root / "flashdb" / f"{prefix}-summary.json"
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            summary["c_oracle"]["report"] = f"wrong/evidence/{prefix}-c-oracle.json"
            self._write_json(summary_path, summary)

            with self.assertRaises(SystemExit) as raised:
                validate_flashdb_l3_evidence(root)

            self.assertIn("c-oracle", str(raised.exception))
            self.assertIn("missing", str(raised.exception))

    def _write_package(
        self,
        root: Path,
        prefix: str,
        *,
        negative_mismatch: bool = True,
        omit: str | None = None,
        invalid_version_manifest: bool = False,
        positive_diff_status: str = "passed",
        positive_diff_first_mismatch: str | None = None,
        final_verification_status: str = "passed",
        final_diff_status: str = "passed",
        final_c_oracle_toolchain_status: str = "C_ORACLE_GENERATED",
        final_checks: list[dict] | None = None,
        summary_hash_mismatch: bool = False,
    ) -> None:
        flashdb = root / "flashdb"
        flashdb.mkdir(parents=True)
        slice_id = prefix.removeprefix("l3-")
        self._write_version_manifest(flashdb, invalid=invalid_version_manifest)
        required = [
            "cache-metadata",
            "config-profile",
            "context-pack",
            "slice-contract",
            "pointer-graph",
            "test-translation",
            "c-oracle",
            "rust-report",
            "diff",
            "negative-diff",
            "rust-check",
            "unsafe-scan",
            "unsafe-ledger",
            "performance-smoke",
            "final-verification",
            "version-config-binding",
        ]
        for suffix in required:
            if suffix == omit:
                continue
            payload = {"schema_version": 1, "status": "passed", "slice_id": slice_id}
            if suffix == "negative-diff":
                payload.update(
                    {
                        "status": "expected_failed",
                        "first_mismatch": "steps.demo.value" if negative_mismatch else None,
                    }
                )
            if suffix == "diff":
                payload.update(
                    {
                        "status": positive_diff_status,
                        "first_mismatch": positive_diff_first_mismatch,
                    }
                )
            if suffix == "final-verification":
                payload.update(
                    {
                        "status": final_verification_status,
                        "diff_status": final_diff_status,
                        "c_oracle_toolchain_status": final_c_oracle_toolchain_status,
                        "checks": final_checks
                        if final_checks is not None
                        else [{"name": "unit-test-check", "status": "passed", "exit_code": 0}],
                    }
                )
            if suffix == "unsafe-scan":
                payload.update({"first_party_non_test_unsafe_count": 0, "unsafe_ratio": 0})
            if suffix == "unsafe-ledger":
                payload.update({"first_party_non_test_unsafe_count": 0})
            if suffix == "performance-smoke":
                payload.update({"secondary_only": True})
            if suffix == "pointer-graph":
                payload.update(
                    {
                        "status": "not_applicable",
                        "not_applicable_reason": "unit test pure fixture",
                    }
                )
            if suffix == "test-translation":
                payload.update(
                    {
                        "status": "recorded",
                        "coverage": {"main_paths": ["main"], "error_paths": [], "negative_cases": ["negative"]},
                        "translation_mappings": [
                            {
                                "source": "fixture",
                                "rust_test": "test",
                                "coverage_kind": "main_path",
                                "status": "mapped",
                            },
                            {
                                "source": "negative",
                                "rust_test": "test",
                                "coverage_kind": "negative_case",
                                "status": "mapped",
                            },
                        ],
                    }
                )
            if suffix == "version-config-binding":
                payload.update(
                    {
                        "version_manifest": {
                            "path": "validation/evidence/flashdb/version-governance-manifest.json",
                            "status": "recorded",
                        },
                        "cache_key_inputs": ["command_arguments", "cargo_lock_sha256"],
                    }
                )
            self._write_json(flashdb / f"{prefix}-{suffix}.json", payload)

        summary = {
            "schema_version": 1,
            "level": "L3",
            "target_id": "flashdb",
            "slice_id": slice_id,
            "status": "passed",
            "source_commit": "1234567",
            "fixture": {
                "path": f"flashDB_rust/fixtures/{prefix}.json",
                "sha256": "abc123",
                "operation_count": 1,
            },
            "c_oracle": {
                "status": "passed",
                "marker": "C_ORACLE_GENERATED",
                "report": f"validation/evidence/flashdb/{prefix}-c-oracle.json",
            },
            "diff": {
                "status": "passed",
                "report": f"validation/evidence/flashdb/{prefix}-diff.json",
            },
            "negative_diff": {
                "status": "expected_failed",
                "first_mismatch": "steps.demo.value" if negative_mismatch else None,
                "report": f"validation/evidence/flashdb/{prefix}-negative-diff.json",
            },
            "rust_check": {
                "status": "passed",
                "report": f"validation/evidence/flashdb/{prefix}-rust-check.json",
            },
            "unsafe": {
                "status": "passed",
                "first_party_non_test_unsafe_count": 0,
                "unsafe_ratio": 0,
                "report": f"validation/evidence/flashdb/{prefix}-unsafe-scan.json",
            },
            "performance_smoke": {
                "status": "passed",
                "secondary_only": True,
                "report": f"validation/evidence/flashdb/{prefix}-performance-smoke.json",
            },
        }
        if summary_hash_mismatch:
            summary["evidence"] = {
                "diff": {
                    "path": f"validation/evidence/flashdb/{prefix}-diff.json",
                    "sha256": "not-the-real-hash",
                }
            }
        self._write_json(flashdb / f"{prefix}-summary.json", summary)

    def _write_version_manifest(self, flashdb: Path, *, invalid: bool) -> None:
        if invalid:
            self._write_json(
                flashdb / "version-governance-manifest.json",
                {
                    "command": "version-manifest",
                    "schema_version": 1,
                    "package_name": "flashdb_rust",
                },
            )
            return

        cargo_toml = REPO_ROOT / "flashDB_rust" / "Cargo.toml"
        cargo_lock = REPO_ROOT / "flashDB_rust" / "Cargo.lock"
        cargo = tomllib.loads(cargo_toml.read_text(encoding="utf-8"))
        package = cargo["package"]
        self._write_json(
            flashdb / "version-governance-manifest.json",
            {
                "command": "version-manifest",
                "schema_version": 1,
                "agent_contract_version": "0.1.0",
                "context_schema_version": "0.1.0",
                "patch_plan_schema_version": "0.1.0",
                "fixture_schema_version": 1,
                "evidence_schema_version": 1,
                "package_name": package["name"],
                "package_version": package["version"],
                "cargo_toml_sha256": sha256(cargo_toml),
                "cargo_lock_sha256": sha256(cargo_lock),
                "rustc_version": "rustc test-version",
                "cargo_version": "cargo test-version",
                "openspec_version": "1.4.1",
                "flashdb_source_commit": "1234567",
                "flashdb_feature_matrix": {"FDB_USING_KVDB": True},
                "command_arguments": ["version-manifest"],
                "fixture_sha256": None,
                "ai_metadata": {"used": False, "provider": "not_configured"},
                "cache_key_inputs": [
                    "agent_contract_version",
                    "context_schema_version",
                    "patch_plan_schema_version",
                    "fixture_schema_version",
                    "evidence_schema_version",
                    "package_version",
                    "cargo_toml_sha256",
                    "cargo_lock_sha256",
                    "rustc_version",
                    "cargo_version",
                    "openspec_version",
                    "flashdb_source_commit",
                    "flashdb_feature_matrix",
                    "command_arguments",
                    "fixture_sha256",
                    "ai_metadata",
                ],
            },
        )

    def _write_json(self, path: Path, payload: dict) -> None:
        path.write_text(json.dumps(payload), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
