from __future__ import annotations

import copy
from pathlib import Path
import tempfile
import unittest

from validation.tools._ai_candidate_harness_parts.context_replay import (
    build_replay_api_contract,
    count_rust_function_calls,
    materialize_replay_api_contract,
    validate_replay_api_contract_binding,
)


class AiReplayContractTests(unittest.TestCase):
    def test_call_counter_ignores_noncode_occurrences(self) -> None:
        source = """
// translate(fake)
/* translate(fake) */
const TEXT: &str = "translate(fake)";
const RAW: &str = r#"translate(fake)"#;
fn run<'static>(value: &'static [u8]) { let _ = translate(value, value.len()); }
"""
        self.assertEqual(1, count_rust_function_calls(source, "translate"))
        self.assertEqual(
            0,
            count_rust_function_calls(
                "fn translate(value: &[u8]) -> bool { !value.is_empty() }\n"
                "fn replay(value: &[u8]) { let _ = translate(value); }\n",
                "translate",
            ),
        )
        self.assertEqual(
            0,
            count_rust_function_calls(
                "fn replay() { module::translate(); object.translate(); }\n",
                "translate",
            ),
        )

    def test_bound_contract_materializes_and_detects_drift(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ai-replay-contract-") as tmp:
            root = Path(tmp)
            replay = root / "l3-generic-rust-replay-test-draft.rs"
            replay.write_text(
                "fn replay(value: &[u8]) { let _ = translate(value, value.len()); }\n",
                encoding="utf-8",
            )
            contract = build_replay_api_contract(
                replay,
                function_name="translate",
                trusted_root=root,
                expected_filename=replay.name,
            )
            self.assertEqual("bound", contract["status"])
            self.assertEqual(1, contract["call_count"])

            out = root / "out"
            out.mkdir()
            context = {
                "schema_version": 4,
                "slice_id": "generic",
                "function_name": "translate",
                "replay_api_contract": contract,
            }
            materialize_replay_api_contract(context, out)
            context_path = out / "context.json"
            context_path.write_text("{}", encoding="utf-8")
            self.assertEqual("bound", validate_replay_api_contract_binding(context, context_path))

            wrong_function = copy.deepcopy(context)
            wrong_function["function_name"] = "unrelated"
            self.assertEqual(
                "binding_mismatch",
                validate_replay_api_contract_binding(wrong_function, context_path),
            )

            (out / replay.name).write_text("fn replay() {}\n", encoding="utf-8")
            self.assertEqual(
                "binding_mismatch",
                validate_replay_api_contract_binding(context, context_path),
            )

    def test_missing_sensitive_bom_and_call_missing_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ai-replay-blocked-") as tmp:
            root = Path(tmp)
            self.assertEqual(
                "missing",
                build_replay_api_contract(
                    None,
                    function_name="translate",
                    trusted_root=root,
                    expected_filename="replay.rs",
                )["status"],
            )

            replay = root / "replay.rs"
            replay.write_text('const KEY: &str = "api_key=secret";\ntranslate();\n', encoding="utf-8")
            self.assertEqual(
                "blocked_replay_source_sensitive",
                build_replay_api_contract(
                    replay,
                    function_name="translate",
                    trusted_root=root,
                    expected_filename=replay.name,
                )["status"],
            )

            replay.write_bytes(b"\xef\xbb\xbffn replay() { translate(); }\n")
            self.assertEqual(
                "blocked_replay_source_unreadable",
                build_replay_api_contract(
                    replay,
                    function_name="translate",
                    trusted_root=root,
                    expected_filename=replay.name,
                )["status"],
            )

            replay.write_text("fn replay() {}\n", encoding="utf-8")
            self.assertEqual(
                "blocked_replay_call_missing",
                build_replay_api_contract(
                    replay,
                    function_name="translate",
                    trusted_root=root,
                    expected_filename=replay.name,
                )["status"],
            )

    def test_materialization_rejects_internal_hash_drift(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ai-replay-hash-") as tmp:
            root = Path(tmp)
            replay = root / "l3-generic-rust-replay-test-draft.rs"
            replay.write_text("fn replay() { translate(); }\n", encoding="utf-8")
            contract = build_replay_api_contract(
                replay,
                function_name="translate",
                trusted_root=root,
                expected_filename=replay.name,
            )
            drifted = copy.deepcopy(contract)
            drifted["source"]["sha256"] = "0" * 64
            with self.assertRaisesRegex(ValueError, "binding drifted"):
                materialize_replay_api_contract(
                    {"schema_version": 4, "replay_api_contract": drifted},
                    root / "out",
                )

    def test_untrusted_root_and_expected_name_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ai-replay-path-") as tmp:
            root = Path(tmp)
            trusted = root / "trusted"
            external = root / "external"
            trusted.mkdir()
            external.mkdir()
            replay = external / "l3-generic-rust-replay-test-draft.rs"
            replay.write_text("fn replay() { translate(); }\n", encoding="utf-8")

            outside = build_replay_api_contract(
                replay,
                function_name="translate",
                trusted_root=trusted,
                expected_filename=replay.name,
            )
            wrong_name = build_replay_api_contract(
                replay,
                function_name="translate",
                trusted_root=external,
                expected_filename="l3-other-rust-replay-test-draft.rs",
            )

            self.assertEqual("blocked_replay_source_path", outside["status"])
            self.assertEqual("blocked_replay_source_path", wrong_name["status"])


if __name__ == "__main__":
    unittest.main()
