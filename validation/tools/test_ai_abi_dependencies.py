from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from validation.tools import ai_candidate_harness
from validation.tools._ai_candidate_harness_parts.abi_dependencies import (
    classify_abi_dependencies,
)
from validation.tools._ai_candidate_harness_parts.exact_validation_contracts import (
    abi_gate,
    mask_noncode,
)
from validation.tools import test_ai_compiler_diagnostics as compiler_support
from validation.tools import test_ai_exact_validation as exact_support


CANDIDATE_SHA = "c" * 64
TARGET_SHA = exact_support.target_sha()


def bound_gate(*, status: str = "passed", candidate_sha: str = CANDIDATE_SHA) -> dict:
    return {
        "candidate_sha256": candidate_sha,
        "status": status,
        "target_contract_sha256": TARGET_SHA,
    }


def classify(source: str) -> dict:
    return classify_abi_dependencies(mask_noncode(source))


class AiAbiDependencyTests(unittest.TestCase):
    def test_renamed_safe_candidate_is_independent_of_failed_replay(self) -> None:
        source = "pub fn renamed_total(left: i32, right: i32) -> i32 { left + right }\n"
        result = abi_gate(
            CANDIDATE_SHA,
            mask_noncode(source),
            bound_gate(),
            bound_gate(status="failed"),
            bound_gate(),
            TARGET_SHA,
            None,
        )

        self.assertEqual(result["status"], "passed")
        self.assertFalse(result["required"])
        self.assertEqual(result["proof_class"], "not_required")
        self.assertEqual(result["dependency_kinds"], [])

    def test_comments_strings_and_identifiers_cannot_spoof_dependencies(self) -> None:
        source = (
            '// #[repr(C)] extern "C" { fn hidden(); } usize size_of::<u64>()\n'
            'const NOTE: &str = "*const i32 target_pointer_width transmute";\n'
            "pub fn external_value(usize_counted_name: i32) -> i32 { usize_counted_name }\n"
        )
        self.assertEqual(classify(source)["dependencies"], [])

    def test_target_dependencies_require_matching_execution_bindings(self) -> None:
        source = "pub fn item_count(values: &[i32]) -> usize { values.len() }\n"
        passed = abi_gate(
            CANDIDATE_SHA,
            mask_noncode(source),
            bound_gate(),
            bound_gate(),
            bound_gate(),
            TARGET_SHA,
            None,
        )
        self.assertEqual(passed["status"], "passed")
        self.assertTrue(passed["required"])
        self.assertEqual(passed["proof_class"], "target_execution_bindings")
        self.assertIn("target_width_integer", passed["dependency_kinds"])

        for label, gates in {
            "replay-failed": (bound_gate(), bound_gate(status="failed"), bound_gate()),
            "candidate-drift": (
                bound_gate(candidate_sha="d" * 64),
                bound_gate(),
                bound_gate(),
            ),
            "target-drift": (
                bound_gate(),
                {**bound_gate(), "target_contract_sha256": "d" * 64},
                bound_gate(),
            ),
        }.items():
            with self.subTest(label=label):
                failed = abi_gate(
                    CANDIDATE_SHA,
                    mask_noncode(source),
                    *gates,
                    TARGET_SHA,
                    None,
                )
                self.assertEqual(
                    failed["failures"][0]["kind"],
                    "abi_target_execution_unproven",
                )

    def test_layout_and_ffi_dependencies_never_pass_without_specific_proof(self) -> None:
        sources = {
            "repr_c": "#[repr(C)] struct Pair { left: i32, right: i32 }\n",
            "repr_layout_modifier": "#[repr(transparent)] struct Code(i32);\n",
            "raw_pointer": "pub fn read(value: *const i32) -> i32 { 0 }\n",
            "extern_abi": 'extern "C" { fn foreign_call(value: i32) -> i32; }\n',
            "linkage_attribute": "#[no_mangle] pub fn exported() {}\n",
            "layout_intrinsic": "const N: usize = core::mem::size_of::<i32>();\n",
            "transmute": "fn cast(v: u32) -> i32 { unsafe { core::mem::transmute(v) } }\n",
            "union_layout": "union Number { signed: i32, bits: u32 }\n",
            "assembly": "fn fence() { unsafe { core::arch::asm!(\"\") } }\n",
        }
        for expected_kind, source in sources.items():
            with self.subTest(expected_kind=expected_kind):
                result = abi_gate(
                    CANDIDATE_SHA,
                    mask_noncode(source),
                    bound_gate(),
                    bound_gate(),
                    bound_gate(),
                    TARGET_SHA,
                    None,
                )
                self.assertEqual(
                    result["failures"][0]["kind"], "abi_layout_proof_missing"
                )
                self.assertIn(expected_kind, result["layout_dependency_kinds"])

    def test_exact_validation_does_not_copy_replay_failure_into_safe_abi_gate(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ai-abi-safe-exact-") as tmp:
            root = Path(tmp)
            candidate = root / "candidate.rs"
            replay = root / "replay.rs"
            candidate.write_text(
                "pub fn add_one(value: i32) -> i32 { value + 1 }\n",
                encoding="utf-8",
            )
            replay.write_text(exact_support.REPLAY, encoding="utf-8")
            candidate_sha = exact_support.digest(candidate.read_bytes())
            runner = compiler_support.ReplayCompileFailureRunner()
            gates = ai_candidate_harness.validate_exact_candidate(
                candidate,
                candidate_sha256=candidate_sha,
                generated_replay_test=replay,
                fresh_oracle_proof=exact_support.oracle(),
                unsafe_policy=exact_support.unsafe_policy(),
                unsafe_ledger=exact_support.unsafe_ledger(candidate_sha),
                target_contract=exact_support.TARGET,
                attempt_dir=root / "attempt",
                compile_runner=runner.compile,
                replay_runner=runner.replay,
            )

        self.assertEqual(gates["generated_replay"]["status"], "failed")
        self.assertEqual(gates["abi_contract"]["status"], "passed")
        self.assertFalse(gates["abi_contract"]["required"])
        self.assertFalse(gates["final_verification"]["semantic_pass"])

    def test_layout_dependency_kind_reaches_repair_without_source_text(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ai-abi-layout-feedback-") as tmp:
            root = Path(tmp)
            candidate = root / "candidate.rs"
            replay = root / "replay.rs"
            candidate.write_text(
                "#[repr(C)] struct RenamedPair { left: i32, right: i32 }\n"
                "pub fn add_one(value: i32) -> i32 { value + 1 }\n",
                encoding="utf-8",
            )
            replay.write_text(exact_support.REPLAY, encoding="utf-8")
            candidate_sha = exact_support.digest(candidate.read_bytes())
            runner = exact_support.RunnerPair()
            gates = ai_candidate_harness.validate_exact_candidate(
                candidate,
                candidate_sha256=candidate_sha,
                generated_replay_test=replay,
                fresh_oracle_proof=exact_support.oracle(),
                unsafe_policy=exact_support.unsafe_policy(),
                unsafe_ledger=exact_support.unsafe_ledger(candidate_sha),
                target_contract=exact_support.TARGET,
                attempt_dir=root / "attempt",
                compile_runner=runner.compile,
                replay_runner=runner.replay,
            )
            facts = ai_candidate_harness.extract_gate_failure_facts(
                gates, selected_candidate_sha256=candidate_sha
            )

        abi = next(item for item in facts["failures"] if item["gate"] == "abi_contract")
        self.assertEqual(abi["kind"], "abi_layout_proof_missing")
        self.assertEqual(abi["details"], {"dependency_kinds": ["repr_c"]})
        self.assertNotIn("RenamedPair", str(abi))


if __name__ == "__main__":
    unittest.main()
