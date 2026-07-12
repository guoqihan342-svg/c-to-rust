from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from validation.tools import ai_candidate_harness


TARGET = {
    "schema_version": 1,
    "target_triple": "x86_64-unknown-linux-gnu",
    "pointer_width": 64,
    "endianness": "little",
    "calling_convention": "C",
}
SHARED_FIXTURE = {"case_set": "add-one-v1", "input_schema": ["i32"]}
REPLAY = "#[test]\nfn exact_replay() { assert_eq!(add_one(1), 2); }\n"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_digest(value: object) -> str:
    encoded = (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()
    return digest(encoded)


def target_sha() -> str:
    return canonical_digest(TARGET)


def oracle(outputs: object | None = None) -> dict[str, object]:
    values = {"return": 2} if outputs is None else outputs
    return {
        "schema_version": 1,
        "status": "passed",
        "shared_fixture_identity": SHARED_FIXTURE,
        "oracle_run_sha256": "e" * 64,
        "target_contract_sha256": target_sha(),
        "observable_outputs": values,
        "observable_outputs_sha256": canonical_digest(values),
    }


def unsafe_policy(maximum: int = 0) -> dict[str, object]:
    return {"schema_version": 1, "max_unsafe_tokens": maximum, "require_ledger": True}


def unsafe_ledger(candidate_sha: str, entries: list[dict[str, object]] | None = None) -> dict[str, object]:
    return {
        "schema_version": 1,
        "status": "passed",
        "provenance": "current_candidate",
        "candidate_sha256": candidate_sha,
        "entries": [] if entries is None else entries,
    }


class RunnerPair:
    def __init__(self, *, outputs: object | None = None, mutation_survives: bool = False) -> None:
        self.outputs = {"return": 2} if outputs is None else outputs
        self.mutation_survives = mutation_survives
        self.compile_calls = 0

    def compile(self, **kwargs: object) -> dict[str, object]:
        self.compile_calls += 1
        return {
            "status": "passed",
            "returncode": 0,
            "candidate_sha256": digest(Path(kwargs["candidate_path"]).read_bytes()),
            "target_contract_sha256": canonical_digest(kwargs["target_contract"]),
        }

    def replay(self, **kwargs: object) -> dict[str, object]:
        test_path = Path(kwargs["replay_test_path"])
        mode = kwargs["mode"]
        passed = mode == "positive" or self.mutation_survives
        return {
            "status": "passed" if passed else "failed",
            "phase": "run",
            "returncode": 0 if passed else 101,
            "candidate_sha256": digest(Path(kwargs["candidate_path"]).read_bytes()),
            "replay_test_sha256": digest(test_path.read_bytes()),
            "shared_fixture_identity_sha256": canonical_digest(
                kwargs["shared_fixture_identity"]
            ),
            "target_contract_sha256": canonical_digest(kwargs["target_contract"]),
            "observable_outputs": self.outputs,
            "observable_outputs_sha256": canonical_digest(self.outputs),
        }


class AiExactValidationTests(unittest.TestCase):
    def run_validation(
        self,
        root: Path,
        source: str,
        *,
        runners: RunnerPair | None = None,
        expected_sha: str | None = None,
        policy: dict[str, object] | None = None,
        ledger: dict[str, object] | None = None,
        alias_proof: dict[str, object] | None = None,
        oracle_proof: dict[str, object] | None = None,
    ) -> tuple[dict[str, dict[str, object]], RunnerPair, str]:
        candidate = root / "input.rs"
        replay = root / "replay.rs"
        candidate.write_text(source, encoding="utf-8")
        replay.write_text(REPLAY, encoding="utf-8")
        candidate_sha = digest(candidate.read_bytes())
        pair = runners or RunnerPair()
        gates = ai_candidate_harness.validate_exact_candidate(
            candidate,
            candidate_sha256=expected_sha or candidate_sha,
            generated_replay_test=replay,
            fresh_oracle_proof=oracle_proof or oracle(),
            unsafe_policy=policy or unsafe_policy(),
            unsafe_ledger=ledger or unsafe_ledger(candidate_sha),
            target_contract=TARGET,
            attempt_dir=root / "attempt",
            compile_runner=pair.compile,
            replay_runner=pair.replay,
            alias_proof=alias_proof,
        )
        return gates, pair, candidate_sha

    def test_correct_candidate_produces_exact_hash_bound_semantic_evidence(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ai-exact-pass-") as tmp:
            root = Path(tmp)
            gates, _, candidate_sha = self.run_validation(
                root, "pub fn add_one(value: i32) -> i32 { value + 1 }\n"
            )

            facts = ai_candidate_harness.extract_gate_failure_facts(
                gates, selected_candidate_sha256=candidate_sha
            )
            self.assertEqual(facts, {"schema_version": 1, "status": "passed", "failures": []})
            self.assertTrue(gates["final_verification"]["semantic_pass"])
            self.assertTrue(all(item["candidate_sha256"] == candidate_sha for item in gates.values()))
            self.assertEqual(len(list((root / "attempt").glob("[0-9][0-9]-*.json"))), 10)
            self.assertTrue((root / "attempt" / "gate-index.json").is_file())

    def test_semantic_mismatch_fails_schema_diff_and_final(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ai-exact-diff-") as tmp:
            root = Path(tmp)
            source = "pub fn add_one(value: i32) -> i32 { value + 2 }\n"
            pair = RunnerPair(outputs={"return": 3})

            gates, _, candidate_sha = self.run_validation(root, source, runners=pair)

            self.assertEqual(gates["schema_diff"]["status"], "failed")
            self.assertEqual(gates["schema_diff"]["failures"][0]["kind"], "value_mismatch")
            self.assertFalse(gates["final_verification"]["semantic_pass"])
            facts = ai_candidate_harness.extract_gate_failure_facts(
                gates, selected_candidate_sha256=candidate_sha
            )
            self.assertIn("schema_diff", {fact["gate"] for fact in facts["failures"]})

    def test_surviving_negative_mutation_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ai-exact-negative-") as tmp:
            root = Path(tmp)
            source = "pub fn add_one(value: i32) -> i32 { value + 1 }\n"
            pair = RunnerPair(mutation_survives=True)

            gates, _, _ = self.run_validation(root, source, runners=pair)

            self.assertEqual(gates["negative_mutation"]["status"], "failed")
            self.assertEqual(gates["negative_mutation"]["failures"][0]["kind"], "mutation_survived")
            self.assertFalse(gates["final_verification"]["semantic_pass"])

    def test_unregistered_unsafe_is_rejected_even_with_available_budget(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ai-exact-unsafe-") as tmp:
            root = Path(tmp)
            source = "pub fn add_one(value: i32) -> i32 { unsafe { value + 1 } }\n"
            seed = root / "seed.rs"
            seed.write_text(source, encoding="utf-8")
            candidate_sha = digest(seed.read_bytes())
            seed.unlink()

            gates, _, _ = self.run_validation(
                root,
                source,
                policy=unsafe_policy(1),
                ledger=unsafe_ledger(candidate_sha),
            )

            self.assertEqual(gates["unsafe_scan"]["status"], "passed")
            self.assertEqual(gates["unsafe_ledger"]["failures"][0]["kind"], "unregistered_unsafe")
            self.assertFalse(gates["final_verification"]["semantic_pass"])

    def test_candidate_sha_drift_fails_before_any_runner_executes(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ai-exact-sha-") as tmp:
            root = Path(tmp)
            source = "pub fn add_one(value: i32) -> i32 { value + 1 }\n"
            pair = RunnerPair()

            gates, pair, _ = self.run_validation(
                root, source, runners=pair, expected_sha="b" * 64
            )

            self.assertEqual(pair.compile_calls, 0)
            self.assertTrue(
                all(item["failures"][0]["kind"] == "candidate_sha256_mismatch" for item in gates.values())
            )
            self.assertFalse(gates["final_verification"]["semantic_pass"])

    def test_raw_pointer_requires_current_candidate_alias_proof(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ai-exact-alias-") as tmp:
            root = Path(tmp)
            source = "pub unsafe fn read(value: *const i32) -> i32 { *value }\n"
            seed = root / "seed.rs"
            seed.write_text(source, encoding="utf-8")
            candidate_sha = digest(seed.read_bytes())
            seed.unlink()
            entries = [{"ordinal": 1, "line": 1, "justification": "FFI boundary"}]

            gates, _, _ = self.run_validation(
                root,
                source,
                policy=unsafe_policy(1),
                ledger=unsafe_ledger(candidate_sha, entries),
            )

            self.assertEqual(gates["alias_contract"]["failures"][0]["kind"], "alias_proof_missing")
            self.assertFalse(gates["final_verification"]["semantic_pass"])

    def test_non_null_type_does_not_require_raw_pointer_alias_proof(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ai-exact-non-null-") as tmp:
            root = Path(tmp)
            source = (
                "pub struct Proxy { "
                "pub opaque: Option<core::ptr::NonNull<core::ffi::c_void>> "
                "}\n"
                "pub fn add_one(value: i32) -> i32 { value + 1 }\n"
            )

            gates, _, _ = self.run_validation(root, source)

            self.assertEqual(gates["alias_contract"]["status"], "passed")
            self.assertFalse(gates["alias_contract"]["required"])
            self.assertEqual(gates["alias_contract"]["raw_pointer_token_count"], 0)
            self.assertTrue(gates["final_verification"]["semantic_pass"])

    def test_non_null_raw_pointer_operations_still_require_alias_proof(self) -> None:
        sources = {
            "as-ptr": (
                "pub fn add_one(value: i32) -> i32 { "
                "let pointer = core::ptr::NonNull::<i32>::dangling(); "
                "let _raw = pointer.as_ptr(); value + 1 }\n"
            ),
            "constructor": (
                "pub fn add_one(value: i32) -> i32 { "
                "let _pointer = core::ptr::NonNull::<i32>::dangling(); value + 1 }\n"
            ),
            "ptr-api": (
                "pub fn add_one(value: i32) -> i32 { "
                "let _raw = core::ptr::null::<i32>(); value + 1 }\n"
            ),
            "spaced-ptr-api": (
                "pub fn add_one(value: i32) -> i32 { "
                "let _raw = core :: ptr :: null::<i32>(); value + 1 }\n"
            ),
            "commented-constructor-path": (
                "pub fn add_one(value: i32) -> i32 { "
                "let _pointer = core/*path*/::ptr::NonNull::<i32>::dangling(); "
                "value + 1 }\n"
            ),
            "module-import": (
                "use core::ptr;\n"
                "pub fn add_one(value: i32) -> i32 { let _ = ptr::null::<i32>(); value + 1 }\n"
            ),
            "unsafe-non-null-use": (
                "pub struct Proxy { "
                "pub opaque: Option<core::ptr::NonNull<core::ffi::c_void>> "
                "}\n"
                "pub fn add_one(value: i32) -> i32 { unsafe { value + 1 } }\n"
            ),
        }
        for label, source in sources.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory(
                prefix=f"ai-exact-non-null-{label}-"
            ) as tmp:
                gates, _, _ = self.run_validation(Path(tmp), source)

                self.assertEqual(
                    gates["alias_contract"]["failures"][0]["kind"],
                    "alias_proof_missing",
                )
                self.assertFalse(gates["final_verification"]["semantic_pass"])

    def test_historical_oracle_report_path_is_never_accepted(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ai-exact-history-") as tmp:
            root = Path(tmp)
            proof = oracle()
            proof["source"] = "validation/evidence/accepted/oracle.json"

            gates, _, _ = self.run_validation(
                root,
                "pub fn add_one(value: i32) -> i32 { value + 1 }\n",
                oracle_proof=proof,
            )

            self.assertEqual(gates["oracle_contract"]["status"], "failed")
            self.assertEqual(
                gates["oracle_contract"]["failures"][0]["kind"],
                "fresh_oracle_required",
            )
            self.assertFalse(gates["final_verification"]["semantic_pass"])


if __name__ == "__main__":
    unittest.main()
