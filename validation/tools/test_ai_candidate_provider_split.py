from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from validation.tools import ai_candidate_harness
from validation.tools._ai_candidate_harness_parts import provider
from validation.tools._ai_candidate_harness_parts import provider_command
from validation.tools._ai_candidate_harness_parts import provider_generation
from validation.tools._ai_candidate_harness_parts import provider_manifest
from validation.tools._ai_candidate_harness_parts import provider_runtime


EXPECTED_PUBLIC_NAMES = {
    "Any",
    "COMPETITION_LOGICAL_MODEL",
    "Callable",
    "DEFAULT_AGENT",
    "DEFAULT_RESOLVED_MODEL",
    "DEFAULT_VARIANT",
    "LOGICAL_MODEL",
    "MAX_ASSUMPTIONS",
    "MAX_ASSUMPTION_BYTES",
    "MAX_CANDIDATE_BYTES",
    "MAX_PROVIDER_STDERR_BYTES",
    "MAX_PROVIDER_STDOUT_BYTES",
    "OPENCODE_LOG_PATH_ENV",
    "PROVIDER_AUTH_SENTINEL",
    "PROVIDER_BALANCE_SENTINEL",
    "PROVIDER_INVOCATION_SENTINEL",
    "Path",
    "ProviderExecution",
    "Runner",
    "agent_definition_sha256",
    "append_provider_log_diagnostic",
    "appended_provider_log_diagnostic",
    "apply_generated_candidate",
    "assistant_text_from_jsonl",
    "atomic_write_bytes",
    "atomic_write_json",
    "cache_key_payload",
    "cache_key_sha256",
    "candidate_generation_lock",
    "candidate_record",
    "canonical_json_bytes",
    "classify_provider_failure",
    "decode_timeout_output",
    "evaluate_provider_readiness",
    "generate_candidate",
    "load_candidate_cache",
    "manifest_base",
    "materialize_replay_api_contract",
    "opencode_log_candidates",
    "os",
    "parse_candidate_response",
    "prompt_file_arguments",
    "prompt_scope_for_context",
    "prompt_transport_contract",
    "provider_command_prefix",
    "render_prompt",
    "resolve_model_identity",
    "run_with_empty_completion_retry",
    "sha256_bytes",
    "sha256_path",
    "shlex",
    "snapshot_opencode_log",
    "store_candidate_cache",
    "strip_matching_quotes",
    "subprocess",
    "subprocess_runner",
    "text_fragments",
}


def candidate_response(source: str) -> str:
    payload = {
        "schema_version": 1,
        "candidate": {"language": "rust", "source": source},
        "assumptions": [],
    }
    event = {"type": "message.part.updated", "part": {"type": "text", "text": json.dumps(payload)}}
    return json.dumps(event) + "\n"


class AiCandidateProviderSplitTests(unittest.TestCase):
    def test_facade_preserves_legacy_public_import_surface(self) -> None:
        self.assertNotIn("__all__", vars(provider))
        expected_names = set(EXPECTED_PUBLIC_NAMES)
        if "annotations" in vars(provider):
            expected_names.add("annotations")
        self.assertEqual(
            expected_names,
            {name for name in vars(provider) if not name.startswith("_")},
        )
        self.assertIs(provider.generate_candidate, provider_generation.generate_candidate)
        self.assertIs(
            provider.provider_command_prefix,
            provider_command.provider_command_prefix,
        )
        self.assertIs(provider.strip_matching_quotes, provider_command.strip_matching_quotes)
        self.assertIs(
            provider.apply_generated_candidate,
            provider_manifest.apply_generated_candidate,
        )
        self.assertIs(provider.candidate_record, provider_manifest.candidate_record)
        self.assertIs(provider.manifest_base, provider_manifest.manifest_base)

    def test_facade_subprocess_patch_point_remains_live(self) -> None:
        completed = subprocess.CompletedProcess(
            args=["opencode"],
            returncode=7,
            stdout="captured stdout",
            stderr="captured stderr",
        )
        self.assertIs(provider.subprocess, provider_runtime.subprocess)
        self.assertIs(provider.subprocess_runner, provider_runtime.subprocess_runner)

        with mock.patch.object(provider.subprocess, "run", return_value=completed) as runner:
            execution = provider.subprocess_runner(["opencode"], 30)

        self.assertEqual(7, execution.returncode)
        self.assertEqual("captured stdout", execution.stdout)
        self.assertEqual("captured stderr", execution.stderr)
        runner.assert_called_once()

    def test_facade_generation_preserves_cache_miss_then_hit(self) -> None:
        with tempfile.TemporaryDirectory(prefix="provider-split-cache-") as tmp:
            root = Path(tmp)
            spec_path = root / "slice.json"
            replay_path = root / "l3-provider-split-rust-replay-test-draft.rs"
            spec = {
                "schema_version": 1,
                "target_id": "generic-target",
                "slice_id": "provider-split",
                "function_name": "scale_value",
                "c_source": "int scale_value(int value) { return value * 3; }",
                "source_file": "src/math.c",
                "source_commit": "abc123",
                "source_file_hashes": {"src/math.c": "a" * 64},
                "function_source_span": {"file": "src/math.c", "sha256": "b" * 64},
                "build_profile": {"include_paths": [str(root / "include")]},
                "c_boundary": {
                    "signatures": [{"function": "scale_value", "return_type": "int"}]
                },
                "rust_boundary": {"public_api": [{"name": "scale_value"}]},
            }
            spec_path.write_text(json.dumps(spec), encoding="utf-8")
            replay_path.write_text(
                "#[test]\nfn replay() { let _ = scale_value(1); }\n",
                encoding="utf-8",
            )
            context = ai_candidate_harness.build_context_pack(
                spec_path,
                replay_test_path=replay_path,
            )
            calls = 0

            def runner(_argv: list[str], _timeout: int) -> provider.ProviderExecution:
                nonlocal calls
                calls += 1
                return provider.ProviderExecution(
                    0,
                    candidate_response("pub fn scale_value(value: i32) -> i32 { value * 3 }\n"),
                    "",
                )

            first = provider.generate_candidate(
                context,
                out_dir=root / "first",
                cache_root=root / "cache",
                runner=runner,
            )
            second = provider.generate_candidate(
                context,
                out_dir=root / "second",
                cache_root=root / "cache",
                runner=lambda _argv, _timeout: self.fail("cache hit invoked provider"),
            )

        self.assertEqual(1, calls)
        self.assertEqual((1, "miss", True), (
            first["provider_invocations"],
            first["cache"]["status"],
            first["cache"]["stored"],
        ))
        self.assertEqual((0, "hit"), (
            second["provider_invocations"],
            second["cache"]["status"],
        ))

    def test_provider_modules_stay_bounded_and_use_regular_imports(self) -> None:
        parts = Path(provider.__file__).resolve().parent
        provider_paths = list(parts.glob("provider*.py"))
        paths = [*provider_paths, Path(__file__).resolve()]
        offenders = {}
        for path in sorted(set(paths)):
            source = path.read_text(encoding="utf-8")
            line_count = len(source.splitlines())
            if line_count > 300:
                offenders[path.name] = line_count

        for path in provider_paths:
            source = path.read_text(encoding="utf-8")
            self.assertNotIn("exec(", source, path.name)
            self.assertNotIn(".pyfrag", source, path.name)

        self.assertEqual({}, offenders)


if __name__ == "__main__":
    unittest.main()
