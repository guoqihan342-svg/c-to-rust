from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from validation.tools import auto_migrate


class ReuseC2RustBaselineTest(unittest.TestCase):
    def test_accepts_generated_hash_valid_baseline_and_rejects_drift(self) -> None:
        target_root = auto_migrate.REPO_ROOT / "target"
        target_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=target_root) as tmp:
            root = Path(tmp)
            slice_spec = root / "slice.json"
            evidence_dir = root / "evidence" / "sample" / "auto-translation" / "slice-a"
            evidence_dir.mkdir(parents=True)
            spec = {
                "target_id": "sample",
                "slice_id": "slice-a",
                "source_commit": "abc123",
            }
            auto_migrate.write_json(slice_spec, spec)
            output_path = evidence_dir / "l3-slice-a-c2rust-baseline-output.rs"
            output_path.write_text("pub fn translated() {}\n", encoding="utf-8", newline="\n")
            baseline_path = evidence_dir / "l3-slice-a-c2rust-baseline-manifest.json"
            manifest = {
                "schema_version": 1,
                **spec,
                "status": "generated",
                "correctness_role": "candidate_context_only",
                "slice_spec": {
                    "path": auto_migrate.rel(slice_spec),
                    "sha256": auto_migrate.sha256(slice_spec),
                },
                "output": {
                    "status": "generated",
                    "path": auto_migrate.rel(output_path),
                    "sha256": auto_migrate.sha256(output_path),
                },
                "compile": {"status": "passed", "semantic_pass": False},
            }
            auto_migrate.write_json(baseline_path, manifest)

            loaded = auto_migrate.load_reusable_c2rust_baseline_manifest(
                spec,
                slice_spec,
                evidence_dir,
            )
            self.assertEqual(loaded, manifest)

            output_path.write_text("pub fn drifted() {}\n", encoding="utf-8", newline="\n")
            with self.assertRaisesRegex(ValueError, "missing or drifted file ref"):
                auto_migrate.load_reusable_c2rust_baseline_manifest(
                    spec,
                    slice_spec,
                    evidence_dir,
                )

            output_path.write_text("pub fn translated() {}\n", encoding="utf-8", newline="\n")
            manifest["slice_spec"]["sha256"] = "0" * 64
            auto_migrate.write_json(baseline_path, manifest)
            with self.assertRaisesRegex(ValueError, "slice_spec drift"):
                auto_migrate.load_reusable_c2rust_baseline_manifest(
                    spec,
                    slice_spec,
                    evidence_dir,
                )


if __name__ == "__main__":
    unittest.main()
