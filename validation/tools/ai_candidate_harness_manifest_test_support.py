from __future__ import annotations

import json
from pathlib import Path

import jsonschema

from validation.tools import ai_candidate_harness
from validation.tools import validate_competition_run_summary as summary_validator
from validation.tools._ai_candidate_harness_parts import prompt_transport
from validation.tools._ai_candidate_harness_parts import provider


def assert_generated_manifest_contract(
    self: object,
    manifest: dict[str, object],
    observed_argv: list[str],
    out_dir: Path,
    root: Path,
) -> None:
    self.assertEqual(manifest["status"], "generated")
    self.assertTrue(manifest["ai_required_for_default_pipeline"])
    self.assertEqual(1, manifest["provider_invocations"])
    self.assertEqual("ready", manifest["provider_preflight"]["status"])
    self.assertFalse(manifest["claim_boundary"]["semantic_gate"])
    self.assertFalse(manifest["candidates"][0]["semantic_pass"])
    self.assert_manifest_schema(manifest)
    extended_scope = json.loads(json.dumps(manifest))
    extended_scope["candidates"][0]["prompt_scope"].append(
        "external_callee_source_blocks"
    )
    extended_scope["candidates"][0]["prompt_scope"].append("typed_ir_excerpt")
    self.assert_manifest_schema(extended_scope)
    missing_receipt = json.loads(json.dumps(manifest))
    missing_receipt["bindings"].pop("invocation_receipt")
    schema_path = (
        Path(__file__).resolve().parents[1]
        / "auto-translation-template"
        / "ai-candidate-manifest.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    with self.assertRaises(jsonschema.ValidationError):
        jsonschema.Draft7Validator(schema).validate(missing_receipt)
    missing_receipt_validation = summary_validator.validate_fresh_ai_manifest(
        missing_receipt,
        manifest_path=out_dir / "l3-generic-scale-ai-candidate-manifest.json",
        policy={
            "model": "zai/glm-5.1",
            "agent": "c2rust-candidate",
            "variant": "max",
        },
        summary_path=root / "competition-run-summary.json",
        repo_root=root,
    )
    self.assertIn(
        "ai_invocation_receipt_binding_invalid",
        missing_receipt_validation["reasons"],
    )
    self.assertIn("--model", observed_argv)
    self.assertIn("zai/glm-5.1", observed_argv)
    self.assertEqual(9, manifest["schema_version"])
    receipt_ref = manifest["bindings"]["invocation_receipt"]
    receipt_path = out_dir / receipt_ref["path"]
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt_schema_path = (
        Path(__file__).resolve().parents[1]
        / "auto-translation-template"
        / "ai-invocation-receipt.schema.json"
    )
    receipt_schema = json.loads(receipt_schema_path.read_text(encoding="utf-8"))
    jsonschema.Draft7Validator(receipt_schema).validate(receipt)
    sensitive_receipt = json.loads(json.dumps(receipt))
    sensitive_receipt["api_key"] = "must-not-be-accepted"
    sensitive_receipt["messages"] = [{"content": "full session"}]
    with self.assertRaises(jsonschema.ValidationError):
        jsonschema.Draft7Validator(receipt_schema).validate(sensitive_receipt)
    self.assertEqual("runner-contract", receipt["source"])
    self.assertEqual("zai", receipt["provider_id"])
    self.assertEqual("glm-5.1", receipt["model_id"])
    self.assertEqual("c2rust-candidate", receipt["agent"])
    self.assertEqual(
        prompt_transport.prompt_transport_contract(),
        receipt["prompt_transport"],
    )
    self.assertTrue(manifest["generator"]["competition_eligible"])
    self.assertEqual("competition-primary", manifest["generator"]["evaluation_scope"])
    self.assertEqual(
        ["slice_spec", "source_spans", "generated_replay_api_contract"],
        manifest["candidates"][0]["prompt_scope"],
    )
    self.assertEqual(
        prompt_transport.prompt_transport_contract(),
        manifest["generator"]["prompt_transport"],
    )
    file_args = [arg for arg in observed_argv if arg.startswith("--file=")]
    self.assertEqual(1, len(file_args))
    attached_prompt = Path(file_args[0].split("=", 1)[1])
    self.assertEqual(out_dir / "l3-generic-scale-ai-prompt.txt", attached_prompt)
    self.assertEqual(prompt_transport.PROMPT_FILE_MESSAGE, observed_argv[-2])
    self.assertEqual(file_args[0], observed_argv[-1])
    self.assertNotIn("Task mode: generate-candidate", observed_argv)
    self.assertLess(sum(len(arg.encode("utf-8")) for arg in observed_argv), 2_048)
    self.assertGreater(attached_prompt.stat().st_size, 16_000)
    self.assertTrue(
        attached_prompt.read_text(encoding="utf-8").startswith(
            "Task mode: generate-candidate"
        )
    )
    candidate = out_dir / manifest["candidates"][0]["artifact"]["path"]
    self.assertTrue(candidate.is_file())
    self.assertIn("wrapping_mul", candidate.read_text(encoding="utf-8"))

    tampered = json.loads(json.dumps(manifest))
    tampered["status"] = "blocked"
    tampered["candidates"] = []
    tampered["provider_invocations"] = 0
    tampered["provider_preflight"] = {
        "status": "blocked",
        "source_span_status": "source_binding_incomplete",
    }
    tampered["failure"] = {
        "kind": "context_not_provider_ready",
        "message": "tampered",
    }
    tampered_validation = summary_validator.validate_fresh_ai_manifest(
        tampered,
        manifest_path=out_dir / "l3-generic-scale-ai-candidate-manifest.json",
        policy={
            "model": "zai/glm-5.1",
            "agent": "c2rust-candidate",
            "variant": "max",
        },
        summary_path=root / "competition-run-summary.json",
        repo_root=root,
    )
    self.assertIn(
        "ai_manifest_provider_preflight_context_mismatch",
        tampered_validation["reasons"],
    )
    self.assertIn(
        "ai_manifest_provider_invocations_context_mismatch",
        tampered_validation["reasons"],
    )

    scope_drift = json.loads(json.dumps(manifest))
    scope_drift["candidates"][0]["prompt_scope"].append("cfg_excerpt")
    scope_validation = summary_validator.validate_fresh_ai_manifest(
        scope_drift,
        manifest_path=out_dir / "l3-generic-scale-ai-candidate-manifest.json",
        policy={
            "model": "zai/glm-5.1",
            "agent": "c2rust-candidate",
            "variant": "max",
        },
        summary_path=root / "competition-run-summary.json",
        repo_root=root,
    )
    self.assertIn(
        "ai_manifest_prompt_scope_context_mismatch",
        scope_validation["reasons"],
    )

    legacy_scope_drift = json.loads(json.dumps(scope_drift))
    legacy_scope_drift["schema_version"] = 4
    legacy_scope_validation = summary_validator.validate_fresh_ai_manifest(
        legacy_scope_drift,
        manifest_path=out_dir / "l3-generic-scale-ai-candidate-manifest.json",
        policy={
            "model": "zai/glm-5.1",
            "agent": "c2rust-candidate",
            "variant": "max",
        },
        summary_path=root / "competition-run-summary.json",
        repo_root=root,
    )
    self.assertIn(
        "ai_manifest_schema_version_stale_for_fresh_run",
        legacy_scope_validation["reasons"],
    )

    context_path = out_dir / "l3-generic-scale-ai-context-pack.json"
    original_context_bytes = context_path.read_bytes()
    prompt_context_drift = json.loads(json.dumps(manifest))
    drifted_context = json.loads(original_context_bytes.decode("utf-8"))
    drifted_context["deterministic_artifacts"] = {
        "unit-cfg.json": {
            "status": "loaded",
            "context_excerpt": {"blocks": [{"id": "entry"}]},
            "failure_summary": [],
        }
    }
    provider.atomic_write_json(context_path, drifted_context)
    drifted_context_sha = provider.sha256_path(context_path)
    prompt_context_drift["bindings"]["context_pack"]["sha256"] = drifted_context_sha
    prompt_context_drift["candidates"][0]["input_artifact_hashes"][
        "context_pack"
    ] = drifted_context_sha
    prompt_context_drift["candidates"][0]["prompt_scope"] = [
        "slice_spec",
        "source_spans",
        "cfg_excerpt",
    ]
    prompt_context_validation = summary_validator.validate_fresh_ai_manifest(
        prompt_context_drift,
        manifest_path=out_dir / "l3-generic-scale-ai-candidate-manifest.json",
        policy={
            "model": "zai/glm-5.1",
            "agent": "c2rust-candidate",
            "variant": "max",
        },
        summary_path=root / "competition-run-summary.json",
        repo_root=root,
    )
    self.assertIn(
        "ai_manifest_prompt_context_mismatch",
        prompt_context_validation["reasons"],
    )
    provider.atomic_write_bytes(context_path, original_context_bytes)

    replay_path = out_dir / "l3-generic-scale-rust-replay-test-draft.rs"
    original_replay_bytes = replay_path.read_bytes()
    provider.atomic_write_bytes(replay_path, b"fn replay() {}\n")
    replay_drift_validation = summary_validator.validate_fresh_ai_manifest(
        manifest,
        manifest_path=out_dir / "l3-generic-scale-ai-candidate-manifest.json",
        policy={
            "model": "zai/glm-5.1",
            "agent": "c2rust-candidate",
            "variant": "max",
        },
        summary_path=root / "competition-run-summary.json",
        repo_root=root,
    )
    self.assertIn(
        "ai_context_replay_api_contract_binding_invalid",
        replay_drift_validation["reasons"],
    )
    provider.atomic_write_bytes(replay_path, original_replay_bytes)

    transport_drift = json.loads(json.dumps(manifest))
    transport_drift["generator"]["prompt_transport"]["message_sha256"] = "0" * 64
    transport_validation = summary_validator.validate_fresh_ai_manifest(
        transport_drift,
        manifest_path=out_dir / "l3-generic-scale-ai-candidate-manifest.json",
        policy={
            "model": "zai/glm-5.1",
            "agent": "c2rust-candidate",
            "variant": "max",
        },
        summary_path=root / "competition-run-summary.json",
        repo_root=root,
    )
    self.assertIn(
        "ai_manifest_generator_does_not_match_execution_policy",
        transport_validation["reasons"],
    )

    missing_accounting = json.loads(json.dumps(manifest))
    missing_accounting.pop("provider_invocations")
    missing_accounting.pop("provider_preflight")
    with self.assertRaises(jsonschema.ValidationError):
        self.assert_manifest_schema(missing_accounting)
    missing_validation = summary_validator.validate_fresh_ai_manifest(
        missing_accounting,
        manifest_path=out_dir / "l3-generic-scale-ai-candidate-manifest.json",
        policy={
            "model": "zai/glm-5.1",
            "agent": "c2rust-candidate",
            "variant": "max",
        },
        summary_path=root / "competition-run-summary.json",
        repo_root=root,
    )
    self.assertIn(
        "ai_manifest_provider_accounting_missing",
        missing_validation["reasons"],
    )

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
