from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from validation.tools._auto_migrate_ai_exact_validation import (
    validate_auto_migrate_candidate,
)
from validation.tools import test_replay_call_plan as plan_support
from validation.tools import test_replay_runtime_assertion as replay_support


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


class AutoMigrateAiExactDiagnosticTests(unittest.TestCase):
    def test_real_replay_wrapper_forwards_compile_diagnostics_only(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ai-exact-wrapper-diagnostic-") as tmp:
            root = Path(tmp)
            candidate = root / "candidate.rs"
            replay = root / "replay.rs"
            harness = root / "harness.c"
            attempt = root / "attempt"
            candidate.write_text("pub fn renamed_api() {}\n", encoding="utf-8")
            replay.write_text("#[test] fn replay() {}\n", encoding="utf-8")
            harness.write_text("int main(void) { return 0; }\n", encoding="utf-8")
            captured: dict[str, object] = {}
            diagnostic = json.dumps(
                {
                    "level": "error",
                    "code": {"code": "E0425"},
                    "message": "cannot find function `renamed_api` in this scope",
                }
            )

            def validate_exact(*_args: object, **kwargs: object) -> dict[str, object]:
                replay_runner = kwargs["replay_runner"]
                result = replay_runner(
                    candidate_path=candidate,
                    replay_test_path=replay,
                    work_dir=attempt / "replay",
                    target_contract={"abi": "renamed-target"},
                    shared_fixture_identity={"cases": []},
                    mode="positive",
                )
                captured.update(result)
                attempt.mkdir(parents=True, exist_ok=True)
                (attempt / "gate-index.json").write_text("{}\n", encoding="utf-8")
                return {
                    "generated_replay": {
                        "candidate_sha256": digest(candidate.read_bytes()),
                        "status": "failed",
                    }
                }

            validate_auto_migrate_candidate(
                {},
                candidate_path=candidate,
                replay_test_path=replay,
                oracle_payload={},
                harness_path=harness,
                proof_root=root,
                attempt_dir=attempt,
                compile_runner=lambda _path: {"returncode": 0, "errors": []},
                replay_runner=lambda _candidate, _replay: {
                    "status": "failed",
                    "phase": "compile",
                    "compile_returncode": 1,
                    "compile_stderr": diagnostic,
                    "run_stderr": "oracle and fixture values must not cross",
                },
                canonical_json_bytes=lambda value: json.dumps(
                    value, sort_keys=True, separators=(",", ":")
                ).encode("utf-8"),
                extract_gate_failure_facts=lambda *_args, **_kwargs: {
                    "status": "failed",
                    "failures": [],
                },
                prove_fresh_oracle=lambda *_args, **_kwargs: {
                    "schema_version": 1,
                    "status": "passed",
                    "target_contract": {"abi": "renamed-target"},
                    "target_contract_sha256": "a" * 64,
                    "shared_fixture_identity": {"cases": []},
                    "observable_outputs": {},
                    "oracle_run_sha256": "b" * 64,
                },
                validate_exact_candidate=validate_exact,
                sha256_bytes=digest,
                sha256_path=lambda path: digest(path.read_bytes()),
                artifact_root=lambda *_args: root,
                current_candidate_unsafe_ledger=lambda _sha: {},
                router_gate_results=lambda *_args: {},
                unsafe_policy_from_spec=lambda _spec: {},
            )

            self.assertEqual(captured["phase"], "compile")
            self.assertEqual(captured["compile_stderr"], diagnostic)
            self.assertNotIn("run_stderr", captured)

    def test_real_wrapper_rebuilds_runtime_assertion_inventory(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ai-exact-wrapper-runtime-") as tmp:
            root = Path(tmp)
            spec = plan_support.ReplayCallPlanTests.report_spec()
            spec["fixture_contract"]["path"] = "missing-inline-fixture.json"
            spec["fixture_contract"]["cases"] = [
                {
                    "id": "first-case",
                    "input_ref": "inline",
                    "inputs": {"ip": "127.0.0.1", "port": 80},
                    "expected_outputs": {"code": 0, "family": 2},
                },
                {
                    "id": "second-case",
                    "input_ref": "inline",
                    "inputs": {"ip": "bad", "port": 81},
                    "expected_outputs": {"code": -1, "family": 2},
                },
            ]
            _plan, expected_inventory, replay_source = (
                replay_support.ReplayRuntimeAssertionTests().build_plan(root)
            )
            spec["fixture_contract"]["cases"][0]["id"] = "alpha-case"
            spec["fixture_contract"]["cases"][1]["id"] = "beta-case"
            candidate = root / "candidate.rs"
            replay = root / "replay.rs"
            harness = root / "harness.c"
            attempt = root / "attempt"
            candidate.write_text("pub fn renamed_api() {}\n", encoding="utf-8")
            replay.write_text(replay_source, encoding="utf-8")
            harness.write_text("int main(void) { return 0; }\n", encoding="utf-8")
            assertion_id = expected_inventory["assertions"][0]["assertion_id"]
            captured: dict[str, object] = {}

            def validate_exact(*_args: object, **kwargs: object) -> dict[str, object]:
                captured["inventory"] = kwargs["replay_assertion_inventory"]
                captured["result"] = kwargs["replay_runner"](
                    candidate_path=candidate,
                    replay_test_path=replay,
                    work_dir=attempt / "replay",
                    target_contract={"abi": "renamed-target"},
                    shared_fixture_identity={
                        "cases": [{"id": "alpha-case"}, {"id": "beta-case"}],
                        "behavior_fields": ["code", "family"],
                    },
                    mode="positive",
                )
                attempt.mkdir(parents=True, exist_ok=True)
                (attempt / "gate-index.json").write_text("{}\n", encoding="utf-8")
                return {
                    "generated_replay": {
                        "candidate_sha256": digest(candidate.read_bytes()),
                        "status": "failed",
                    }
                }

            validate_auto_migrate_candidate(
                spec,
                candidate_path=candidate,
                replay_test_path=replay,
                oracle_payload={},
                harness_path=harness,
                proof_root=root,
                attempt_dir=attempt,
                compile_runner=lambda _path: {"returncode": 0, "errors": []},
                replay_runner=lambda _candidate, _replay: {
                    "status": "failed",
                    "phase": "run",
                    "run_returncode": 101,
                    "runtime_assertion_id": assertion_id,
                    "run_stderr": "panic and oracle values must not cross",
                },
                canonical_json_bytes=lambda value: json.dumps(
                    value, sort_keys=True, separators=(",", ":")
                ).encode("utf-8"),
                extract_gate_failure_facts=lambda *_args, **_kwargs: {
                    "status": "failed",
                    "failures": [],
                },
                prove_fresh_oracle=lambda *_args, **_kwargs: {
                    "schema_version": 1,
                    "status": "passed",
                    "target_contract": {"abi": "renamed-target"},
                    "target_contract_sha256": "a" * 64,
                    "shared_fixture_identity": {
                        "cases": [{"id": "alpha-case"}, {"id": "beta-case"}],
                        "behavior_fields": ["code", "family"],
                    },
                    "observable_outputs": {},
                    "oracle_run_sha256": "b" * 64,
                },
                validate_exact_candidate=validate_exact,
                sha256_bytes=digest,
                sha256_path=lambda path: digest(path.read_bytes()),
                artifact_root=lambda *_args: root,
                current_candidate_unsafe_ledger=lambda _sha: {},
                router_gate_results=lambda *_args: {},
                unsafe_policy_from_spec=lambda _spec: {},
            )

            self.assertEqual(captured["inventory"], expected_inventory)
            projected = captured["result"]
            self.assertEqual(
                projected["runtime_assertion_failure"]["assertion_id"], assertion_id
            )
            self.assertNotIn("run_stderr", projected)
            self.assertNotIn("oracle", json.dumps(projected))


if __name__ == "__main__":
    unittest.main()
