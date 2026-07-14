from __future__ import annotations

from contextlib import ExitStack
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from validation.tools import _auto_migrate_ai_exact as exact


def stage_kwargs(root: Path) -> dict[str, object]:
    return {
        "context_pack": {},
        "ai_manifest": {},
        "evidence_dir": root,
        "canonical_draft_path": root / "candidate.rs",
        "deterministic_candidate_path": None,
        "c2rust_baseline": None,
        "c2rust_baseline_manifest_path": None,
        "replay_test_path": root / "replay.rs",
        "oracle_payload": {},
        "harness_path": root / "harness.c",
        "proof_root": root,
        "compile_runner": lambda _path: {},
        "replay_runner": lambda _path, _replay: {},
        "max_repair_rounds": 0,
        "opencode_command": "unused",
        "resolved_model": "unused",
        "agent": "unused",
        "variant": "unused",
        "timeout_seconds": 1,
    }


class AutoMigrateAiExactSplitTests(unittest.TestCase):
    def test_exact_stage_rejects_stale_manifest_and_context_versions(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ai-exact-contract-") as tmp:
            root = Path(tmp)
            with self.assertRaisesRegex(ValueError, "manifest schema_version 8 or 9"):
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
                    {"schema_version": 9},
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
        missing = [
            name for name in legacy_symbols if not callable(getattr(exact, name, None))
        ]
        self.assertEqual([], missing)
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

    def test_stage_facade_delegates_with_live_monkeypatched_dependencies(self) -> None:
        baseline_resolver = "resolve_current_c2rust_baseline_candidate"
        dependency_names = {
            "validate_ai_exact_stage_contract": "validate_ai_exact_stage_contract",
            baseline_resolver: baseline_resolver,
            "validate_with_new_attempt": "_validate_with_new_attempt",
            "classify_ai_repair_eligibility": "classify_ai_repair_eligibility",
            "passed_gate_count": "_passed_gate_count",
            "repair_c2rust_candidate_after_validation": "repair_c2rust_candidate_after_validation",
            "c2rust_repair_report_binding": "c2rust_repair_report_binding",
            "repair_ai_candidate_after_validation": "repair_ai_candidate_after_validation",
            "manifest_candidate_id": "_manifest_candidate_id",
            "manifest_generator_metadata": "_manifest_generator_metadata",
            "router_candidate": "_router_candidate",
            "route_candidates": "route_candidates",
            "sync_duplicate_audit": "_sync_duplicate_audit",
            "sha256_path": "sha256_path",
            "mark_ai_not_applied": "_mark_ai_not_applied",
            "persist_candidate_result": "_persist_candidate_result",
            "atomic_write_json": "atomic_write_json",
        }
        expected = object()
        with ExitStack() as stack:
            patched = {
                field: stack.enter_context(mock.patch.object(exact, name))
                for field, name in dependency_names.items()
            }
            implementation = stack.enter_context(
                mock.patch.object(
                    exact,
                    "_run_ai_exact_stage_impl",
                    return_value=expected,
                )
            )
            result = exact.run_ai_exact_stage(
                {"slice_id": "split-test"},
                **stage_kwargs(Path("root")),
            )

        self.assertIs(expected, result)
        dependencies = implementation.call_args.kwargs["dependencies"]
        for field, dependency in patched.items():
            self.assertIs(dependency, getattr(dependencies, field), field)
        self.assertEqual(
            Path("root") / "candidate.rs",
            implementation.call_args.kwargs["canonical_draft_path"],
        )

    def test_stage_delegate_honors_monkeypatched_contract(self) -> None:
        with mock.patch.object(
            exact,
            "validate_ai_exact_stage_contract",
            side_effect=ValueError("patched contract"),
        ) as contract:
            with self.assertRaisesRegex(ValueError, "patched contract"):
                exact.run_ai_exact_stage({}, **stage_kwargs(Path("root")))

        contract.assert_called_once()

    def test_attempt_helper_uses_monkeypatched_facade_validation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ai-exact-split-") as tmp:
            root = Path(tmp)
            candidate = root / "candidate.rs"
            candidate.write_text("pub fn migrated() {}\n", encoding="utf-8")
            attempt_dir = root / "attempts" / "01-patched"
            validation = {"status": "passed"}
            candidate_sha = "b" * 64
            compile_runner = lambda _path: {}
            replay_runner = lambda _path, _replay: {}
            with mock.patch.object(
                exact,
                "sha256_path",
                return_value=candidate_sha,
            ), mock.patch.object(
                exact,
                "next_attempt_dir",
                return_value=attempt_dir,
            ) as next_attempt, mock.patch.object(
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
                    compile_runner=compile_runner,
                    replay_runner=replay_runner,
                )

        self.assertEqual(attempt_dir.as_posix(), result["attempt_dir"])
        next_attempt.assert_called_once_with(
            root / "attempts",
            "patched",
            candidate_sha,
        )
        validate.assert_called_once_with(
            {"slice_id": "split-test"},
            candidate_path=candidate,
            replay_test_path=root / "replay.rs",
            oracle_payload={},
            harness_path=root / "harness.c",
            proof_root=root,
            attempt_dir=attempt_dir,
            compile_runner=compile_runner,
            replay_runner=replay_runner,
        )

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

    def test_mark_not_applied_facade_injects_writer_and_updates_manifest(self) -> None:
        manifest = {
            "selected_candidate_id": "candidate-1",
            "candidates": [
                {
                    "candidate_id": "candidate-1",
                    "applied": True,
                    "applied_artifact": {},
                    "rust_draft_sha256": "a" * 64,
                }
            ],
        }
        with mock.patch.object(exact, "atomic_write_json") as writer:
            exact._mark_ai_not_applied(manifest, Path("evidence"), "split-test")

        self.assertNotIn("selected_candidate_id", manifest)
        self.assertEqual(
            {"candidate_id": "candidate-1", "applied": False},
            manifest["candidates"][0],
        )
        writer.assert_called_once_with(
            Path("evidence/l3-split-test-ai-candidate-manifest.json"),
            manifest,
        )


if __name__ == "__main__":
    unittest.main()
