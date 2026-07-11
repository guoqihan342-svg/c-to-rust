from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

import jsonschema

from validation.tools import ai_candidate_harness


def minimal_spec(source_root: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "target_id": "generic-target",
        "slice_id": "generic-scale",
        "function_name": "scale_value",
        "c_source": "int scale_value(int value) { return value * 3; }",
        "source_root": source_root,
        "source_file": "src/math.c",
        "source_commit": "abc123",
        "source_file_hashes": {"src/math.c": "a" * 64},
        "function_source_span": {"file": "src/math.c", "sha256": "b" * 64},
        "build_profile": {
            "include_paths": [f"{source_root}/include"],
            "defines": ["FEATURE=1"],
            "api_key": "must-not-leak",
        },
        "c_boundary": {"signatures": [{"function": "scale_value", "return_type": "int"}]},
        "rust_boundary": {"public_api": [{"name": "scale_value"}]},
    }


def jsonl_response(source: str) -> str:
    payload = json.dumps(
        {
            "schema_version": 1,
            "candidate": {"language": "rust", "source": source},
            "assumptions": [],
        }
    )
    return json.dumps({"type": "message.part.updated", "part": {"type": "text", "text": payload}}) + "\n"


class AiCandidateHarnessTests(unittest.TestCase):
    def assert_manifest_schema(self, manifest: dict[str, object]) -> None:
        schema_path = (
            Path(__file__).resolve().parents[1]
            / "auto-translation-template"
            / "ai-candidate-manifest.schema.json"
        )
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        jsonschema.Draft7Validator(schema).validate(manifest)

    def test_context_pack_redacts_source_root_and_sensitive_fields(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ai-context-") as tmp:
            root = Path(tmp)
            source_root = "/mnt/c/external/project"
            spec_path = root / "slice.json"
            spec_path.write_text(json.dumps(minimal_spec(source_root)), encoding="utf-8")

            context = ai_candidate_harness.build_context_pack(spec_path)

            encoded = json.dumps(context)
            self.assertNotIn(source_root, encoded)
            self.assertNotIn("must-not-leak", encoded)
            self.assertIn("<source-root>", encoded)
            self.assertFalse(context["claim_boundary"]["semantic_gate"])

    def test_generate_candidate_writes_hash_bound_nonsemantic_manifest(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ai-candidate-") as tmp:
            root = Path(tmp)
            spec_path = root / "slice.json"
            spec_path.write_text(json.dumps(minimal_spec(str(root))), encoding="utf-8")
            context = ai_candidate_harness.build_context_pack(spec_path)
            observed_argv: list[str] = []

            def runner(argv: list[str], timeout: int) -> ai_candidate_harness.ProviderExecution:
                observed_argv.extend(argv)
                self.assertEqual(timeout, 30)
                return ai_candidate_harness.ProviderExecution(
                    0,
                    jsonl_response("pub fn scale_value(value: i32) -> i32 { value.wrapping_mul(3) }\n"),
                    "",
                )

            out_dir = root / "out"
            manifest = ai_candidate_harness.generate_candidate(
                context,
                out_dir=out_dir,
                timeout_seconds=30,
                runner=runner,
            )

            self.assertEqual(manifest["status"], "generated")
            self.assertTrue(manifest["ai_required_for_default_pipeline"])
            self.assertFalse(manifest["claim_boundary"]["semantic_gate"])
            self.assertFalse(manifest["candidates"][0]["semantic_pass"])
            self.assert_manifest_schema(manifest)
            self.assertIn("--model", observed_argv)
            self.assertIn("zai/glm-5.1", observed_argv)
            candidate = out_dir / manifest["candidates"][0]["artifact"]["path"]
            self.assertTrue(candidate.is_file())
            self.assertIn("wrapping_mul", candidate.read_text(encoding="utf-8"))

    def test_invalid_ai_response_is_blocked_without_candidate(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ai-invalid-") as tmp:
            root = Path(tmp)
            spec_path = root / "slice.json"
            spec_path.write_text(json.dumps(minimal_spec(str(root))), encoding="utf-8")
            context = ai_candidate_harness.build_context_pack(spec_path)

            manifest = ai_candidate_harness.generate_candidate(
                context,
                out_dir=root / "out",
                runner=lambda _argv, _timeout: ai_candidate_harness.ProviderExecution(
                    0,
                    json.dumps({"type": "text", "text": "```rust\nfn bad() {}\n```"}) + "\n",
                    "",
                ),
            )

            self.assertEqual(manifest["status"], "blocked")
            self.assertEqual(manifest["failure"]["kind"], "invalid_ai_response")
            self.assertEqual(manifest["candidates"], [])
            self.assert_manifest_schema(manifest)
            self.assertFalse(any((root / "out").glob("*-ai-rust-candidate.rs")))

    def test_provider_balance_failure_is_structured_and_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ai-balance-") as tmp:
            root = Path(tmp)
            spec_path = root / "slice.json"
            spec_path.write_text(json.dumps(minimal_spec(str(root))), encoding="utf-8")
            context = ai_candidate_harness.build_context_pack(spec_path)

            manifest = ai_candidate_harness.generate_candidate(
                context,
                out_dir=root / "out",
                runner=lambda _argv, _timeout: ai_candidate_harness.ProviderExecution(
                    1,
                    "",
                    "Insufficient balance or no resource package. Please recharge.",
                ),
            )

            self.assertEqual(manifest["status"], "blocked")
            self.assertEqual(manifest["failure"]["kind"], "provider_insufficient_balance")
            self.assertEqual(manifest["candidates"], [])
            self.assert_manifest_schema(manifest)

    def test_timeout_is_not_retried_inside_candidate_generator(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ai-timeout-") as tmp:
            root = Path(tmp)
            spec_path = root / "slice.json"
            spec_path.write_text(json.dumps(minimal_spec(str(root))), encoding="utf-8")
            context = ai_candidate_harness.build_context_pack(spec_path)
            calls = 0

            def runner(_argv: list[str], _timeout: int) -> ai_candidate_harness.ProviderExecution:
                nonlocal calls
                calls += 1
                return ai_candidate_harness.ProviderExecution(124, "", "", timed_out=True)

            manifest = ai_candidate_harness.generate_candidate(context, out_dir=root / "out", runner=runner)

            self.assertEqual(calls, 1)
            self.assertEqual(manifest["failure"]["kind"], "provider_timeout")


if __name__ == "__main__":
    unittest.main()
