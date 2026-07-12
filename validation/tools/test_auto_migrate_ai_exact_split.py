from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest import mock

from validation.tools import _auto_migrate_ai_exact as exact


class AutoMigrateAiExactSplitTests(unittest.TestCase):
    def test_exact_stage_rejects_stale_manifest_and_context_versions(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ai-exact-contract-") as tmp:
            root = Path(tmp)
            with self.assertRaisesRegex(ValueError, "manifest schema_version 8"):
                exact.validate_ai_exact_stage_contract(
                    {"schema_version": 4},
                    {"schema_version": 7},
                    evidence_dir=root,
                    replay_test_path=root / "replay.rs",
                    canonical_draft_path=root / "candidate.rs",
                )
            with self.assertRaisesRegex(ValueError, "ContextPack schema_version 4"):
                exact.validate_ai_exact_stage_contract(
                    {"schema_version": 3},
                    {"schema_version": 8},
                    evidence_dir=root,
                    replay_test_path=root / "replay.rs",
                    canonical_draft_path=root / "candidate.rs",
                )

    def test_legacy_helpers_remain_importable_from_facade(self) -> None:
        legacy_symbols = (
            "run_ai_exact_stage",
            "_validate_with_new_attempt",
            "next_attempt_dir",
            "_router_candidate",
            "_manifest_candidate_id",
            "_manifest_generator_metadata",
            "_passed_gate_count",
            "_sync_duplicate_audit",
            "_persist_candidate_result",
            "_mark_ai_not_applied",
            "validate_auto_migrate_candidate",
            "persist_exact_validation_summary",
            "router_gate_results",
            "unsafe_policy_from_spec",
            "current_candidate_unsafe_ledger",
            "_artifact_root",
        )
        self.assertEqual([], [name for name in legacy_symbols if not callable(getattr(exact, name, None))])
        manifest = {
            "selected_candidate_id": "candidate-1",
            "candidates": [{"candidate_id": "candidate-1"}],
        }

        self.assertEqual("candidate-1", exact._manifest_candidate_id(manifest))
        self.assertEqual(
            1,
            exact._passed_gate_count(
                {"router_gate_results": {"compile": {"status": "passed"}}}
            ),
        )
        self.assertEqual(
            0,
            exact.unsafe_policy_from_spec(
                {"rust_boundary": {"unsafe_policy": {"max_unsafe_tokens": True}}}
            )["max_unsafe_tokens"],
        )

    def test_attempt_helper_uses_monkeypatched_facade_validation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ai-exact-split-") as tmp:
            root = Path(tmp)
            candidate = root / "candidate.rs"
            candidate.write_text("pub fn migrated() {}\n", encoding="utf-8")
            attempt_dir = root / "attempts" / "01-patched"
            validation = {"status": "passed"}
            with mock.patch.object(
                exact,
                "next_attempt_dir",
                return_value=attempt_dir,
            ), mock.patch.object(
                exact,
                "validate_auto_migrate_candidate",
                return_value=validation,
            ) as validate:
                result = exact._validate_with_new_attempt(
                    {"slice_id": "split-test"},
                    label="patched",
                    candidate_path=candidate,
                    replay_test_path=root / "replay.rs",
                    oracle_payload={},
                    harness_path=root / "harness.c",
                    proof_root=root,
                    attempts_root=root / "attempts",
                    compile_runner=lambda _path: {},
                    replay_runner=lambda _path, _replay: {},
                )

        self.assertEqual(attempt_dir.as_posix(), result["attempt_dir"])
        validate.assert_called_once()

    def test_validation_facade_injects_monkeypatched_dependencies(self) -> None:
        expected = {"status": "passed"}
        with mock.patch.object(
            exact,
            "prove_fresh_oracle",
        ) as prove_oracle, mock.patch.object(
            exact,
            "_validate_auto_migrate_candidate_impl",
            return_value=expected,
        ) as implementation:
            result = exact.validate_auto_migrate_candidate(
                {"slice_id": "split-test"},
                candidate_path=Path("candidate.rs"),
                replay_test_path=Path("replay.rs"),
                oracle_payload={},
                harness_path=Path("harness.c"),
                proof_root=Path("."),
                attempt_dir=Path("attempt"),
                compile_runner=lambda _path: {},
                replay_runner=lambda _path, _replay: {},
            )

        self.assertIs(expected, result)
        self.assertIs(
            prove_oracle,
            implementation.call_args.kwargs["prove_fresh_oracle"],
        )

    def test_persistence_facade_uses_monkeypatched_summary_writer(self) -> None:
        result = {
            "status": "passed",
            "attempt_dir": "attempts/01-ai",
        }
        with mock.patch.object(
            exact,
            "persist_exact_validation_summary",
        ) as persist, mock.patch.object(
            exact,
            "sha256_path",
            return_value="a" * 64,
        ):
            binding = exact._persist_candidate_result(result, Path("summary.json"))

        self.assertEqual(
            {"path": "summary.json", "sha256": "a" * 64, "status": "passed"},
            binding,
        )
        persist.assert_called_once_with(
            {"status": "passed"},
            path=Path("summary.json"),
            attempt_dir=Path("attempts/01-ai"),
        )


if __name__ == "__main__":
    unittest.main()
