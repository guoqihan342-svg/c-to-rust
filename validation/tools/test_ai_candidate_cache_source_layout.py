from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path
import unittest


MAX_MODULE_LINES = 300
EXPECTED_CACHE_TESTS = {
    "test_cache_round_trip_is_reparsed_and_first_writer_wins",
    "test_concurrent_publish_keeps_one_complete_entry",
    "test_invalid_response_is_never_stored",
    "test_key_fields_and_artifact_drift_fail_closed",
    "test_prompt_and_parse_contract_versions_change_the_key",
    "test_provider_failure_does_not_create_entry",
    "test_provider_miss_then_hit_uses_zero_new_calls_and_drift_reinvokes",
    "test_same_key_provider_generation_is_single_flight",
    "test_windows_generation_lock_retries_resource_deadlock",
}


class AiCandidateCacheSourceLayoutTests(unittest.TestCase):
    def slice_paths(self) -> list[Path]:
        tools = Path(__file__).resolve().parent
        return sorted(
            {
                *tools.glob("test_ai_candidate_cache*.py"),
                tools / "ai_candidate_cache_test_support.py",
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

    def test_original_cache_methods_are_defined_once(self) -> None:
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

        self.assertEqual(EXPECTED_CACHE_TESTS, set(counts))
        self.assertEqual([], sorted(name for name, count in counts.items() if count != 1))
        self.assertEqual(len(EXPECTED_CACHE_TESTS), sum(counts.values()))


if __name__ == "__main__":
    unittest.main()
