from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from validation.tools._translation_carrier_reporter import emit_reports
from validation.tools._translation_carrier_reporter.contract import ReporterError
from validation.tools.sequence_replay_test_support import sha256_file, write_json
from validation.tools.test_translation_carrier_sequence_reporter import (
    REPO_ROOT,
    build_reporter_layout,
)


class TranslationCarrierRuntimeBindingTests(unittest.TestCase):
    def test_mutable_refs_are_field_bound_and_immutable_leaves_are_hash_bound(self) -> None:
        target_root = REPO_ROOT / "target"
        target_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="runtime-binding-", dir=target_root) as tmp:
            layout = build_reporter_layout(Path(tmp))
            add_candidate_rust_report(layout)
            reports = emit_reports(**layout["emit_args"])
            c_oracle = json.loads(reports["c_oracle"].read_text(encoding="utf-8"))
            refs = c_oracle["provenance"]["evidence_refs"]

            mutable = {
                "translation_plan",
                "clang_lowering_report",
                "c_oracle_status",
                "rust_check",
                "generated_replay_evidence",
                "candidate_rust_report",
                "test_translation",
            }
            for name in mutable:
                with self.subTest(mutable_ref=name):
                    self.assertEqual(refs[name]["binding_mode"], "field_bound")
                    self.assertNotIn("sha256", refs[name])
                    self.assertIn("Accepted-evidence promotion", refs[name]["cycle_boundary"])

            immutable = {
                "translator_input",
                "c_oracle_harness",
                "generated_rust_draft",
                "generated_replay_test",
                "generated_replay_stdout",
                "generated_replay_stderr",
            }
            for name in immutable:
                with self.subTest(immutable_ref=name):
                    path = REPO_ROOT / refs[name]["path"]
                    self.assertEqual(refs[name]["sha256"], sha256_file(path))
                    self.assertNotIn("cycle_boundary", refs[name])

    def test_immutable_replay_test_drift_fails_closed(self) -> None:
        target_root = REPO_ROOT / "target"
        target_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="runtime-binding-", dir=target_root) as tmp:
            layout = build_reporter_layout(Path(tmp))
            auto_dir = Path(layout["emit_args"]["auto_evidence_dir"])
            replay_test = auto_dir / "l3-advance-window-tail-rust-replay-test-draft.rs"
            replay_test.write_text(
                replay_test.read_text(encoding="utf-8") + "\n// immutable leaf drift\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ReporterError, "generated replay test sha256 drifted"):
                emit_reports(**layout["emit_args"])


def add_candidate_rust_report(layout: dict[str, object]) -> None:
    auto_dir = Path(layout["emit_args"]["auto_evidence_dir"])
    spec_path = Path(layout["emit_args"]["slice_spec"])
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    replay = json.loads(
        (auto_dir / "l3-advance-window-tail-test-translation-generated.json").read_text(
            encoding="utf-8"
        )
    )
    draft_path = auto_dir / "l3-advance-window-tail-rust-draft.rs"
    write_json(
        auto_dir / "l3-advance-window-tail-rust-report.json",
        {
            "schema_version": 1,
            "target_id": spec["target_id"],
            "slice_id": spec["slice_id"],
            "source_commit": spec["source_commit"],
            "status": "passed",
            "generated_draft_replay_pass": True,
            "generated_draft_semantic_pass": False,
            "generated_draft": {
                "path": draft_path.relative_to(REPO_ROOT).as_posix(),
                "sha256": sha256_file(draft_path),
            },
            "replay": replay,
        },
    )


if __name__ == "__main__":
    unittest.main()
