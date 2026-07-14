from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path
import unittest


MAX_MODULE_LINES = 300
EXPECTED_HARNESS_TESTS = {
    "test_applied_ai_candidate_becomes_agent_route_primary_without_semantic_claim",
    "test_apply_candidate_rejects_canonical_path_escape",
    "test_apply_candidate_rejects_sha_drift",
    "test_context_pack_redacts_source_root_and_sensitive_fields",
    "test_empty_completion_fingerprint_requires_terminal_zero_token_finish",
    "test_empty_completion_retries_once_with_same_prompt_and_binds_both_attempts",
    "test_empty_completion_second_empty_or_invalid_remains_blocked",
    "test_generate_candidate_writes_hash_bound_nonsemantic_manifest",
    "test_invalid_ai_response_is_blocked_without_candidate",
    "test_missing_replay_contract_blocks_before_provider_invocation",
    "test_only_exact_empty_completion_fingerprint_retries",
    "test_oversized_provider_output_is_blocked_and_capture_is_bounded",
    "test_provider_balance_failure_is_structured_and_fail_closed",
    "test_rejected_declared_source_root_cannot_fall_back_to_inline_ready",
    "test_response_with_extra_fields_is_blocked",
    "test_source_context_failure_blocks_without_provider_invocation",
    "test_subprocess_runner_does_not_apply_log_diagnostic_after_success",
    "test_subprocess_runner_exports_minimal_session_identity_receipt",
    "test_subprocess_runner_reads_only_sanitized_appended_provider_diagnostic",
    "test_subprocess_runner_reads_provider_diagnostic_from_new_log",
    "test_subprocess_runner_recovers_provider_diagnostic_after_nonzero_exit",
    "test_subprocess_runner_sanitizes_provider_launch_failure",
    "test_timeout_is_not_retried_inside_candidate_generator",
    "test_timeout_with_provider_balance_diagnostic_uses_actionable_classification",
    "test_validator_rejects_applied_ai_candidate_draft_drift",
}


class AiCandidateHarnessSourceLayoutTests(unittest.TestCase):
    def slice_paths(self) -> list[Path]:
        tools = Path(__file__).resolve().parent
        return sorted(
            {
                *tools.glob("test_ai_candidate_harness*.py"),
                *tools.glob("ai_candidate_harness*_test_support.py"),
            }
        )

    def test_split_modules_stay_bounded_and_use_static_python(self) -> None:
        offenders = {}
        dynamic_calls = {}
        for path in self.slice_paths():
            source = path.read_text(encoding="utf-8")
            line_count = len(source.splitlines())
            if line_count > MAX_MODULE_LINES:
                offenders[path.name] = line_count
            tree = ast.parse(source, filename=str(path))
            calls = sorted(
                {
                    node.func.id
                    for node in ast.walk(tree)
                    if isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id in {"exec", "eval", "__import__"}
                }
            )
            if calls:
                dynamic_calls[path.name] = calls

        self.assertEqual({}, offenders)
        self.assertEqual({}, dynamic_calls)

    def test_original_harness_methods_are_defined_once(self) -> None:
        counts: Counter[str] = Counter()
        for path in self.slice_paths():
            if path == Path(__file__).resolve() or not path.name.startswith("test_"):
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            counts.update(
                node.name
                for node in ast.walk(tree)
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name.startswith("test_")
            )

        self.assertEqual(EXPECTED_HARNESS_TESTS, set(counts))
        self.assertEqual([], sorted(name for name, count in counts.items() if count != 1))
        self.assertEqual(len(EXPECTED_HARNESS_TESTS), sum(counts.values()))


if __name__ == "__main__":
    unittest.main()
