from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from validation.tools import ai_candidate_harness
from validation.tools.test_ai_exact_validation import (
    REPLAY,
    TARGET,
    RunnerPair,
    canonical_digest,
    digest,
    oracle,
    unsafe_ledger,
    unsafe_policy,
)


class CompileFailureRunner(RunnerPair):
    def compile(self, **kwargs: object) -> dict[str, object]:
        self.compile_calls += 1
        return {
            "status": "failed",
            "returncode": 1,
            "candidate_sha256": digest(Path(kwargs["candidate_path"]).read_bytes()),
            "target_contract_sha256": canonical_digest(kwargs["target_contract"]),
            "errors": [
                {
                    "level": "error",
                    "code": {"code": "E0308"},
                    "message": "mismatched candidate API types",
                    "rendered": "oracle-bearing rendered source must not cross the boundary",
                }
            ],
        }


class ReplayCompileFailureRunner(RunnerPair):
    def replay(self, **kwargs: object) -> dict[str, object]:
        test_path = Path(kwargs["replay_test_path"])
        diagnostics = [
            {
                "level": "error",
                "code": {"code": "E0425"},
                "message": "cannot find type `RequiredReport` in this scope",
                "rendered": "fixture and oracle values must remain withheld",
            },
            {
                "level": "error",
                "code": {"code": "E0061"},
                "message": "this function takes 3 arguments but 2 arguments were supplied",
            },
        ]
        return {
            "status": "failed",
            "phase": "compile",
            "returncode": 1,
            "candidate_sha256": digest(Path(kwargs["candidate_path"]).read_bytes()),
            "replay_test_sha256": digest(test_path.read_bytes()),
            "shared_fixture_identity_sha256": canonical_digest(
                kwargs["shared_fixture_identity"]
            ),
            "target_contract_sha256": canonical_digest(kwargs["target_contract"]),
            "compile_stderr": "\n".join(json.dumps(item) for item in diagnostics),
            "oracle_values": {"return": 2},
        }


class BindingMismatchCompileFailureRunner(CompileFailureRunner):
    def compile(self, **kwargs: object) -> dict[str, object]:
        result = super().compile(**kwargs)
        result["candidate_sha256"] = "f" * 64
        return result


class AiCompilerDiagnosticsTests(unittest.TestCase):
    def run_validation(
        self, root: Path, runners: RunnerPair
    ) -> tuple[dict[str, dict[str, object]], str]:
        candidate = root / "input.rs"
        replay = root / "replay.rs"
        candidate.write_text(
            "pub fn add_one(value: i32) -> i32 { value + 1 }\n",
            encoding="utf-8",
        )
        replay.write_text(REPLAY, encoding="utf-8")
        candidate_sha = digest(candidate.read_bytes())
        gates = ai_candidate_harness.validate_exact_candidate(
            candidate,
            candidate_sha256=candidate_sha,
            generated_replay_test=replay,
            fresh_oracle_proof=oracle(),
            unsafe_policy=unsafe_policy(),
            unsafe_ledger=unsafe_ledger(candidate_sha),
            target_contract=TARGET,
            attempt_dir=root / "attempt",
            compile_runner=runners.compile,
            replay_runner=runners.replay,
        )
        return gates, candidate_sha

    def repair_facts(self, root: Path, runners: RunnerPair) -> dict[str, object]:
        gates, candidate_sha = self.run_validation(root, runners)
        return ai_candidate_harness.extract_gate_failure_facts(
            gates, selected_candidate_sha256=candidate_sha
        )

    def test_compile_diagnostics_reach_repair_facts_without_rendered_source(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ai-exact-compile-feedback-") as tmp:
            facts = self.repair_facts(Path(tmp), CompileFailureRunner())
            rustc_fact = next(item for item in facts["failures"] if item["gate"] == "rustc")
            self.assertEqual(
                rustc_fact["details"]["compiler_diagnostics"],
                [{"code": "E0308", "message": "mismatched candidate API types"}],
            )
            self.assertNotIn("rendered", json.dumps(rustc_fact))

    def test_replay_compile_diagnostics_reach_repair_without_oracle_values(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ai-exact-replay-feedback-") as tmp:
            facts = self.repair_facts(Path(tmp), ReplayCompileFailureRunner())
            replay_fact = next(
                item for item in facts["failures"] if item["gate"] == "generated_replay"
            )
            self.assertEqual(
                replay_fact["details"]["compiler_diagnostics"],
                [
                    {
                        "code": "E0425",
                        "message": "cannot find type `RequiredReport` in this scope",
                    },
                    {
                        "code": "E0061",
                        "message": "this function takes 3 arguments but 2 arguments were supplied",
                    },
                ],
            )
            serialized = json.dumps(replay_fact)
            self.assertNotIn("oracle_values", serialized)
            self.assertNotIn("rendered", serialized)

    def test_runner_diagnostics_are_discarded_when_candidate_binding_drifts(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ai-exact-diagnostic-binding-") as tmp:
            facts = self.repair_facts(Path(tmp), BindingMismatchCompileFailureRunner())
            rustc_fact = next(item for item in facts["failures"] if item["gate"] == "rustc")
            self.assertEqual(rustc_fact["kind"], "candidate_sha256_mismatch")
            self.assertNotIn("compiler_diagnostics", json.dumps(rustc_fact))
            self.assertNotIn("E0308", json.dumps(rustc_fact))

if __name__ == "__main__":
    unittest.main()
