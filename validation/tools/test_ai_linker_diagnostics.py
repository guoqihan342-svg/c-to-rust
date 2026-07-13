from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from validation.tools import ai_candidate_harness
from validation.tools._ai_candidate_harness_parts.compiler_diagnostics import (
    normalize_compiler_diagnostics,
)
from validation.tools.test_ai_compiler_diagnostics import (
    ReplayCompileFailureRunner,
)
from validation.tools.test_ai_exact_validation import (
    REPLAY,
    TARGET,
    canonical_digest,
    digest,
    oracle,
    unsafe_ledger,
    unsafe_policy,
)


class LinkerReplayCompileFailureRunner(ReplayCompileFailureRunner):
    def replay(self, **kwargs: object) -> dict[str, object]:
        result = super().replay(**kwargs)
        result["compile_stderr"] = json.dumps(
            {
                "level": "error",
                "code": None,
                "message": "linking with `cc` failed: exit status: 1",
                "children": [
                    {
                        "level": "note",
                        "message": (
                            "rust-lld: error: undefined symbol: renamed_external\n"
                            ">>> referenced by /private/generated_replay.rs"
                        ),
                    }
                ],
            }
        )
        return result


class ReplayBindingMismatchRunner(ReplayCompileFailureRunner):
    def __init__(self, field: str) -> None:
        super().__init__()
        self.field = field

    def replay(self, **kwargs: object) -> dict[str, object]:
        result = super().replay(**kwargs)
        result[self.field] = "f" * 64
        return result


def repair_facts(root: Path, runner: ReplayCompileFailureRunner) -> dict[str, object]:
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
        compile_runner=runner.compile,
        replay_runner=runner.replay,
    )
    return ai_candidate_harness.extract_gate_failure_facts(
        gates, selected_candidate_sha256=candidate_sha
    )


class AiLinkerDiagnosticsTests(unittest.TestCase):
    def test_linker_symbol_reaches_repair_without_linker_metadata(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ai-exact-linker-feedback-") as tmp:
            facts = repair_facts(Path(tmp), LinkerReplayCompileFailureRunner())
            replay_fact = next(
                item for item in facts["failures"] if item["gate"] == "generated_replay"
            )

            self.assertEqual(
                replay_fact["details"]["compiler_diagnostics"],
                [{
                    "code": "linker_undefined_symbol",
                    "message": "undefined external symbol `renamed_external`",
                }],
            )
            self.assertNotIn("private", json.dumps(replay_fact))

    def test_replay_diagnostics_require_all_exact_bindings(self) -> None:
        for field in (
            "candidate_sha256",
            "replay_test_sha256",
            "shared_fixture_identity_sha256",
            "target_contract_sha256",
        ):
            with self.subTest(field=field), tempfile.TemporaryDirectory(
                prefix="ai-exact-replay-binding-drift-"
            ) as tmp:
                facts = repair_facts(Path(tmp), ReplayBindingMismatchRunner(field))
                replay_fact = next(
                    item for item in facts["failures"]
                    if item["gate"] == "generated_replay"
                )
                self.assertNotIn("compiler_diagnostics", json.dumps(replay_fact))
                self.assertNotIn("E0425", json.dumps(replay_fact))

    def test_linker_child_exposes_only_identifier_shaped_undefined_symbol(self) -> None:
        diagnostics = normalize_compiler_diagnostics(
            {
                "compile_stderr": json.dumps(
                    {
                        "level": "error",
                        "code": None,
                        "message": "linking with `cc` failed: exit status: 1",
                        "children": [
                            {
                                "level": "note",
                                "message": (
                                    "rust-lld: error: undefined symbol: renamed_external\n"
                                    ">>> referenced by C:/private/oracle.rs\n"
                                    "secret=must_not_cross"
                                ),
                            },
                            {
                                "level": "note",
                                "message": "rust-lld: error: undefined symbol: bad/symbol",
                            },
                        ],
                        "rendered": "C:/private/rendered source",
                    }
                )
            }
        )

        self.assertEqual(
            diagnostics,
            [{
                "code": "linker_undefined_symbol",
                "message": "undefined external symbol `renamed_external`",
            }],
        )
        serialized = json.dumps(diagnostics)
        self.assertNotIn("private", serialized)
        self.assertNotIn("secret", serialized)

    def test_linker_symbol_text_without_exact_parent_contract_is_not_classified(self) -> None:
        diagnostics = normalize_compiler_diagnostics(
            {
                "compile_stderr": json.dumps(
                    {
                        "level": "error",
                        "code": None,
                        "message": "candidate supplied diagnostic text",
                        "children": [
                            {
                                "level": "note",
                                "message": "rust-lld: error: undefined symbol: spoofed_name",
                            }
                        ],
                    }
                )
            }
        )

        self.assertEqual(
            diagnostics,
            [{"code": "compile_error", "message": "candidate supplied diagnostic text"}],
        )


if __name__ == "__main__":
    unittest.main()
