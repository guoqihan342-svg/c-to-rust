from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

import jsonschema

from validation.tools import ai_candidate_harness
from validation.tools import auto_migrate
from validation.tools import validate_auto_translation_evidence as evidence_validator


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

            canonical = out_dir / "l3-generic-scale-rust-draft.rs"
            applied = ai_candidate_harness.apply_generated_candidate(
                manifest,
                out_dir=out_dir,
                canonical_draft_path=canonical,
            )
            self.assertTrue(applied["candidates"][0]["applied"])
            self.assertEqual(applied["selected_candidate_id"], "opencode-glm51-1")
            self.assertEqual(
                applied["candidates"][0]["applied_artifact"]["sha256"],
                applied["candidates"][0]["rust_draft_sha256"],
            )

    def test_apply_candidate_rejects_sha_drift(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ai-candidate-drift-") as tmp:
            root = Path(tmp)
            spec_path = root / "slice.json"
            spec_path.write_text(json.dumps(minimal_spec(str(root))), encoding="utf-8")
            context = ai_candidate_harness.build_context_pack(spec_path)
            out_dir = root / "out"
            manifest = ai_candidate_harness.generate_candidate(
                context,
                out_dir=out_dir,
                runner=lambda _argv, _timeout: ai_candidate_harness.ProviderExecution(
                    0,
                    jsonl_response("pub fn scale_value(value: i32) -> i32 { value * 3 }\n"),
                    "",
                ),
            )
            candidate_path = out_dir / manifest["candidates"][0]["artifact"]["path"]
            candidate_path.write_text("pub fn drifted() {}\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "sha256 drifted"):
                ai_candidate_harness.apply_generated_candidate(
                    manifest,
                    out_dir=out_dir,
                    canonical_draft_path=out_dir / "canonical.rs",
                )

    def test_apply_candidate_rejects_canonical_path_escape(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ai-candidate-path-") as tmp:
            root = Path(tmp)
            spec_path = root / "slice.json"
            spec_path.write_text(json.dumps(minimal_spec(str(root))), encoding="utf-8")
            context = ai_candidate_harness.build_context_pack(spec_path)
            out_dir = root / "out"
            manifest = ai_candidate_harness.generate_candidate(
                context,
                out_dir=out_dir,
                runner=lambda _argv, _timeout: ai_candidate_harness.ProviderExecution(
                    0,
                    jsonl_response("pub fn scale_value(value: i32) -> i32 { value * 3 }\n"),
                    "",
                ),
            )

            with self.assertRaisesRegex(ValueError, "canonical Rust draft escapes"):
                ai_candidate_harness.apply_generated_candidate(
                    manifest,
                    out_dir=out_dir,
                    canonical_draft_path=root / "escaped.rs",
                )

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

    def test_applied_ai_candidate_becomes_agent_route_primary_without_semantic_claim(self) -> None:
        ai_candidate = {
            "candidate_id": "opencode-glm51-1",
            "kind": "opencode-ai",
            "status": "generated",
            "role": "ai_primary_rust_draft",
            "applied": True,
            "rust_draft_sha256": "c" * 64,
            "semantic_pass": False,
        }
        primary = auto_migrate.primary_candidate_binding({}, ai_candidate)
        candidates = auto_migrate.candidate_set_binding(
            primary,
            [],
            {"status": "not_available", "rust_draft_generated": False},
            {
                "candidate_id": "c2rust-baseline",
                "kind": "c2rust-baseline",
                "status": "skipped",
                "role": "baseline_or_repair_candidate_context",
                "semantic_pass": False,
            },
            ai_candidate,
        )
        candidate_generation = {
            "selected_candidate_id": primary["candidate_id"],
            "candidate_set": candidates,
            "ai": ai_candidate,
        }

        level, rationale = auto_migrate.route_level(
            {},
            {"status": "blocked"},
            {"status": "recorded"},
            {"status": "recorded"},
            {"pointer_nodes": []},
            {"status": "blocked"},
            candidate_generation,
        )
        route = {
            "candidate_generation": candidate_generation,
            "level": level,
            "translator": auto_migrate.route_translator(level),
        }

        self.assertEqual(primary["selected"], "opencode-ai")
        self.assertEqual(level, "L3")
        self.assertEqual(rationale[0]["feature"], "opencode_ai_candidate_applied")
        self.assertTrue(auto_migrate.route_has_generated_rust_draft(route))
        self.assertFalse(candidates[0]["semantic_pass"])

    def test_validator_rejects_applied_ai_candidate_draft_drift(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ai-validator-drift-") as tmp:
            root = Path(tmp)
            spec_path = root / "slice.json"
            spec_path.write_text(json.dumps(minimal_spec(str(root))), encoding="utf-8")
            context = ai_candidate_harness.build_context_pack(spec_path)
            manifest = ai_candidate_harness.generate_candidate(
                context,
                out_dir=root,
                runner=lambda _argv, _timeout: ai_candidate_harness.ProviderExecution(
                    0,
                    jsonl_response("pub fn scale_value(value: i32) -> i32 { value * 3 }\n"),
                    "",
                ),
            )
            canonical = root / "l3-generic-scale-rust-draft.rs"
            ai_candidate_harness.apply_generated_candidate(
                manifest,
                out_dir=root,
                canonical_draft_path=canonical,
            )
            binding = auto_migrate.ai_candidate_binding(root, "l3-generic-scale")
            candidates = {binding["candidate_id"]: dict(binding)}

            evidence_validator.validate_ai_candidate_binding(
                {"ai": binding},
                candidates,
                binding["candidate_id"],
                evidence_dir=root,
                prefix="l3-generic-scale",
                route_level="L3",
            )
            canonical.write_text("pub fn drifted() {}\n", encoding="utf-8")

            with self.assertRaisesRegex(SystemExit, "rust_draft_sha256 drifted"):
                evidence_validator.validate_ai_candidate_binding(
                    {"ai": binding},
                    candidates,
                    binding["candidate_id"],
                    evidence_dir=root,
                    prefix="l3-generic-scale",
                    route_level="L3",
                )


if __name__ == "__main__":
    unittest.main()
