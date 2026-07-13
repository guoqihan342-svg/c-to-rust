from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest

from validation.tools import ai_candidate_harness
from validation.tools._ai_candidate_harness_parts.repair_contract import (
    normalize_validation_result,
)
from validation.tools.replay_runtime_assertion import (
    runtime_assertion_failure_envelope,
)
from validation.tools.test_ai_exact_validation import (
    TARGET,
    RunnerPair,
    canonical_digest,
    digest,
    unsafe_ledger,
    unsafe_policy,
)
from validation.tools import test_replay_runtime_assertion as replay_support


def oracle(identity: dict[str, object]) -> dict[str, object]:
    outputs = {"result": {"code": 0, "family": 2}}
    return {
        "schema_version": 1,
        "status": "passed",
        "shared_fixture_identity": identity,
        "oracle_run_sha256": "e" * 64,
        "target_contract_sha256": canonical_digest(TARGET),
        "observable_outputs": outputs,
        "observable_outputs_sha256": canonical_digest(outputs),
    }


class RuntimeFailureRunner(RunnerPair):
    def __init__(
        self,
        envelope: dict[str, str],
        *,
        binding_drift: str | None = None,
    ) -> None:
        super().__init__()
        self.envelope = envelope
        self.binding_drift = binding_drift

    def replay(self, **kwargs: object) -> dict[str, object]:
        if kwargs["mode"] != "positive":
            raise AssertionError("negative replay must not run after positive failure")
        test_path = Path(kwargs["replay_test_path"])
        result: dict[str, object] = {
            "status": "failed",
            "phase": "run",
            "returncode": 101,
            "candidate_sha256": digest(Path(kwargs["candidate_path"]).read_bytes()),
            "replay_test_sha256": digest(test_path.read_bytes()),
            "shared_fixture_identity_sha256": canonical_digest(
                kwargs["shared_fixture_identity"]
            ),
            "target_contract_sha256": canonical_digest(kwargs["target_contract"]),
            "runtime_assertion_failure": self.envelope,
        }
        if self.binding_drift is not None:
            result[self.binding_drift] = "f" * 64
        return result


def runtime_facts(
    root: Path,
    *,
    envelope_drift: str | None = None,
    binding_drift: str | None = None,
) -> dict[str, object]:
    _plan, inventory, replay_source = replay_support.ReplayRuntimeAssertionTests().build_plan(
        root
    )
    assertion = next(
        item
        for item in inventory["assertions"]
        if item["case_id"] == "beta-case" and item["observable_field"] == "family"
    )
    envelope = runtime_assertion_failure_envelope(assertion["assertion_id"], inventory)
    assert envelope is not None
    if envelope_drift == "assertion_id":
        envelope["assertion_id"] = "f" * 64
    elif envelope_drift == "plan_sha256":
        envelope["replay_call_plan_sha256"] = "f" * 64
    elif envelope_drift == "inventory_sha256":
        envelope["assertion_inventory_sha256"] = "f" * 64

    candidate = root / "candidate.rs"
    replay = root / "replay.rs"
    candidate.write_text("pub fn neutral_candidate() {}\n", encoding="utf-8")
    replay.write_text(replay_source, encoding="utf-8")
    candidate_sha = digest(candidate.read_bytes())
    identity = {
        "cases": [{"id": "alpha-case"}, {"id": "beta-case"}],
        "behavior_fields": ["code", "family"],
    }
    runner = RuntimeFailureRunner(envelope, binding_drift=binding_drift)
    gates = ai_candidate_harness.validate_exact_candidate(
        candidate,
        candidate_sha256=candidate_sha,
        generated_replay_test=replay,
        fresh_oracle_proof=oracle(identity),
        unsafe_policy=unsafe_policy(),
        unsafe_ledger=unsafe_ledger(candidate_sha),
        target_contract=TARGET,
        attempt_dir=root / "attempt",
        compile_runner=runner.compile,
        replay_runner=runner.replay,
        replay_assertion_inventory=copy.deepcopy(inventory),
    )
    return ai_candidate_harness.extract_gate_failure_facts(
        gates, selected_candidate_sha256=candidate_sha
    )


def replay_fact(facts: dict[str, object]) -> dict[str, object]:
    return next(
        item
        for item in facts["failures"]
        if item["gate"] == "generated_replay"
    )


class AiRuntimeAssertionFeedbackTests(unittest.TestCase):
    def test_exact_gate_exposes_only_renamed_case_and_field(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ai-runtime-feedback-") as tmp:
            fact = replay_fact(runtime_facts(Path(tmp)))

        self.assertEqual(fact["kind"], "runtime_assertion_failed")
        self.assertEqual(
            fact["details"],
            {"case_id": "beta-case", "observable_field": "family"},
        )
        serialized = json.dumps(fact)
        for forbidden in (
            "expected",
            "actual",
            "127.0.0.1",
            "generated_replay.rs",
            "panic",
            "line",
            "private",
            "secret",
        ):
            self.assertNotIn(forbidden, serialized)

    def test_envelope_and_execution_binding_drift_remove_localization(self) -> None:
        for field in ("assertion_id", "plan_sha256", "inventory_sha256"):
            with self.subTest(envelope=field), tempfile.TemporaryDirectory(
                prefix="ai-runtime-envelope-drift-"
            ) as tmp:
                fact = replay_fact(runtime_facts(Path(tmp), envelope_drift=field))
                self.assertEqual(fact["kind"], "replay_failed")
                self.assertNotIn("details", fact)
        for field in (
            "candidate_sha256",
            "replay_test_sha256",
            "shared_fixture_identity_sha256",
            "target_contract_sha256",
        ):
            with self.subTest(binding=field), tempfile.TemporaryDirectory(
                prefix="ai-runtime-binding-drift-"
            ) as tmp:
                fact = replay_fact(runtime_facts(Path(tmp), binding_drift=field))
                self.assertNotEqual(fact["kind"], "runtime_assertion_failed")
                self.assertNotIn("case_id", json.dumps(fact))

    def test_repair_contract_rejects_extra_oracle_value(self) -> None:
        payload = {
            "schema_version": 1,
            "status": "failed",
            "failures": [
                {
                    "gate": "generated_replay",
                    "kind": "runtime_assertion_failed",
                    "message": "opaque assertion failed",
                    "details": {
                        "case_id": "renamed-case",
                        "observable_field": "renamed-field",
                        "expected": "must-not-cross",
                    },
                }
            ],
        }
        with self.assertRaisesRegex(ValueError, "exact case/field"):
            normalize_validation_result(payload, require_failed=True)


if __name__ == "__main__":
    unittest.main()
