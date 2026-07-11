from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from validation.tools._translation_carrier_reporter.call_continue_contract import (
    parse_contract,
)
from validation.tools._translation_carrier_reporter.call_continue_negative_execution import (
    run_call_continue_negative_execution,
)
from validation.tools.call_continue_test_support import (
    REPO_ROOT,
    renamed_zero_start_rust_draft,
    renamed_zero_start_spec,
    zero_start_replay_source,
)


class CallContinueSchemaV2NegativeTest(unittest.TestCase):
    def test_sentinel_mutation_excludes_zero_start_partitions(self) -> None:
        spec, cases = renamed_zero_start_spec()
        contract = parse_contract(spec)
        context = SimpleNamespace(
            repo_root=REPO_ROOT,
            spec={"slice_id": "renamed-zero-start", "function_name": "advance_window"},
            contract=contract,
            cases=cases,
        )
        (REPO_ROOT / "target").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="call-continue-v2-", dir=REPO_ROOT / "target"
        ) as tmp:
            root = Path(tmp)
            draft = root / "draft.rs"
            replay = root / "replay.rs"
            draft.write_text(
                renamed_zero_start_rust_draft(), encoding="utf-8", newline="\n"
            )
            replay.write_text(
                zero_start_replay_source(cases), encoding="utf-8", newline="\n"
            )
            result = run_call_continue_negative_execution(
                context, draft, replay, root / "out"
            )

        scenarios = {item["scenario_id"]: item for item in result["scenarios"]}
        comparison = scenarios["comparison-equality-flip"]["partition_replay"]
        self.assertEqual(
            comparison["detected_case_ids"],
            ["hit-wrap", "miss-zero-return", "miss-ordinary"],
        )
        self.assertEqual(
            comparison["passed_case_ids"], ["zero-start-wrap", "zero-start-plain"]
        )
        continuation = scenarios["continue-noop"]["partition_replay"]
        self.assertEqual(continuation["detected_case_ids"], ["hit-wrap"])


if __name__ == "__main__":
    unittest.main()
