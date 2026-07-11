from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from validation.tools._translation_carrier_reporter import emit_reports
from validation.tools._translation_carrier_reporter.contract import ReporterError, parse_contract
from validation.tools._translation_carrier_reporter.source_binding import validate_carrier
from validation.tools.guarded_stats_sequence_reporter_test_support import build_reporter_layout
from validation.tools.guarded_stats_sequence_test_support import REPO_ROOT, build_spec


class TranslationCarrierGuardedStatsSequenceReporterTests(unittest.TestCase):
    def test_reporter_partitions_second_equality_mutation(self) -> None:
        target_root = REPO_ROOT / "target"
        target_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="guarded-stats-reporter-", dir=target_root) as tmp:
            paths = emit_reports(**build_reporter_layout(Path(tmp))["emit_args"])
            reports = {
                name: json.loads(path.read_text(encoding="utf-8"))
                for name, path in paths.items()
            }
            self.assertEqual(reports["diff"]["status"], "passed")
            self.assertFalse(reports["rust_report"]["cases"][1]["accepted"])
            self.assertEqual(reports["rust_report"]["cases"][1]["updated_visits"], 8)
            negative = reports["negative_diff"]
            self.assertEqual(negative["mutation"], "second guard equality == changed to !=")
            self.assertEqual(
                negative["partition_detection"]["observable_mismatch_case_ids"],
                ["both-match", "second-mismatch", "both-match-wrap"],
            )
            self.assertEqual(
                negative["partition_detection"]["mutation_equivalent_case_ids"],
                ["first-mismatch", "both-mismatch"],
            )

    def test_source_binding_rejects_non_short_circuit_and_extra_false_effect(self) -> None:
        spec, _ = build_spec()
        contract = parse_contract(spec)
        carrier = {
            "kind": "exact_source_fragment_wrapper",
            "embedding_mode": "verbatim_once",
            "frontend_contract": "live_clang_slice_source",
            "source_text_normalization": "utf8_universal_newlines",
            "source_file_hash_mode": "raw_bytes",
            "artifact_source_hash_mode": "lf_stable_text",
            "carrier_function": spec["function_name"],
            "carrier_source_sha256": "unused",
            "claim_boundary": {
                "scope": "source_fragment_only",
                "whole_function_semantics_verified": False,
                "external_callee_semantics_verified": False,
                "excluded_semantics": ["surrounding behavior"],
            },
        }
        changed_sources = (
            spec["c_source"].replace(" == CELL_READY && ", " == CELL_READY & "),
            spec["c_source"].replace("    return false;", "    tally->visits += 0;\n    return false;"),
        )
        for changed_source in changed_sources:
            changed = copy.deepcopy(spec)
            changed["c_source"] = changed_source
            carrier["carrier_source_sha256"] = __import__("hashlib").sha256(
                changed_source.encode("utf-8")
            ).hexdigest()
            with self.assertRaisesRegex(ReporterError, "short-circuit &&"):
                validate_carrier(changed, carrier, REPO_ROOT, contract)


if __name__ == "__main__":
    unittest.main()
