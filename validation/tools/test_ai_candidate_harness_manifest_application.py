from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from validation.tools import ai_candidate_harness
from validation.tools import auto_migrate
from validation.tools import validate_auto_translation_evidence as evidence_validator
from validation.tools.ai_candidate_harness_test_support import (
    build_provider_context,
    jsonl_response,
    minimal_spec,
)


class AiCandidateHarnessManifestApplicationTests(unittest.TestCase):
    def test_apply_candidate_rejects_sha_drift(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ai-candidate-drift-") as tmp:
            root = Path(tmp)
            spec_path = root / "slice.json"
            spec_path.write_text(json.dumps(minimal_spec(str(root))), encoding="utf-8")
            context = build_provider_context(spec_path)
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
            context = build_provider_context(spec_path)
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
            context = build_provider_context(spec_path)
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
