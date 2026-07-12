from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

import jsonschema

from validation.tools import ai_candidate_harness
from validation.tools import _auto_migrate_ai_exact as ai_exact
from validation.tools._ai_candidate_harness_parts import provider as candidate_provider
from validation.tools import validate_competition_run_summary as summary_validator
from validation.tools import run_competition as competition_runner
from validation.tools._ai_candidate_harness_parts.model_identity import (
    resolve_model_identity,
)
from validation.tools._ai_candidate_harness_parts.prompt_transport import PROMPT_FILE_MESSAGE
from validation.tools._ai_candidate_harness_parts.provider_response import (
    assistant_text_from_jsonl,
)


DEEPSEEK_MODEL = "opencode/deepseek-v4-flash-free"


def response(source: str) -> str:
    payload = {
        "schema_version": 1,
        "candidate": {"language": "rust", "source": source},
        "assumptions": [],
    }
    return json.dumps(
        {"type": "message.part.updated", "part": {"type": "text", "text": json.dumps(payload)}}
    ) + "\n"


def spec() -> dict[str, object]:
    return {
        "schema_version": 1,
        "target_id": "generic",
        "slice_id": "deepseek-scale",
        "function_name": "scale",
        "c_source": "int scale(int value) { return value * 3; }",
        "c_boundary": {
            "signatures": [{"function": "scale", "return_type": "int"}],
        },
    }


def build_provider_context(spec_path: Path) -> dict[str, object]:
    replay_path = spec_path.with_name("l3-deepseek-scale-rust-replay-test-draft.rs")
    replay_path.write_text(
        "#[test]\nfn replay() { let _ = scale(1); }\n",
        encoding="utf-8",
    )
    return ai_candidate_harness.build_context_pack(
        spec_path,
        replay_test_path=replay_path,
    )


class AiModelIdentityTests(unittest.TestCase):
    def test_default_candidate_agent_is_tool_free_and_unknown_agent_fails_before_launch(self) -> None:
        self.assertEqual("c2rust-candidate", candidate_provider.DEFAULT_AGENT)
        calls = 0
        with tempfile.TemporaryDirectory(prefix="missing-ai-agent-") as tmp:
            root = Path(tmp)
            spec_path = root / "slice.json"
            spec_path.write_text(json.dumps(spec()), encoding="utf-8")
            context = build_provider_context(spec_path)

            def runner(_argv: list[str], _timeout: int) -> ai_candidate_harness.ProviderExecution:
                nonlocal calls
                calls += 1
                return ai_candidate_harness.ProviderExecution(0, response("pub fn scale() {}"), "")

            with self.assertRaisesRegex(ValueError, "repository-local agent definition"):
                ai_candidate_harness.generate_candidate(
                    context,
                    out_dir=root / "out",
                    agent="missing-candidate-agent",
                    runner=runner,
                )
        self.assertEqual(0, calls)

    def test_competition_worker_and_candidate_agents_are_separate(self) -> None:
        self.assertEqual("c2rust-migrator", competition_runner.COMPETITION_OPENCODE_AGENT)
        self.assertEqual(
            "c2rust-candidate",
            competition_runner.COMPETITION_OPENCODE_CANDIDATE_AGENT,
        )
        runtime = competition_runner.resolve_ai_runtime(
            repo_root=Path(__file__).resolve().parents[2],
            proof_class="competition-exact",
            model=None,
            agent=None,
            variant=None,
            timeout_seconds=None,
            opencode_command=None,
        )
        self.assertEqual("c2rust-candidate", runtime["agent"])
        self.assertEqual("zai/glm-5.1", runtime["model"])
        for probe in (
            competition_runner.opencode_models_stdout_lists_required_model,
            summary_validator.opencode_models_stdout_lists_required_model,
        ):
            self.assertTrue(probe("GLM-5.1\n"))
            self.assertTrue(probe("zai/glm-5.1\n"))
            self.assertFalse(probe("zai/glm-5.10\n"))
            self.assertFalse(probe("not-zai/glm-5.1\n"))

    def test_exact_router_candidate_id_must_bind_the_only_manifest_candidate(self) -> None:
        manifest = {
            "selected_candidate_id": "opencode-deepseek-v4-flash-1",
            "candidates": [{"candidate_id": "opencode-deepseek-v4-flash-1"}],
        }
        self.assertEqual(
            "opencode-deepseek-v4-flash-1",
            ai_exact._manifest_candidate_id(manifest),
        )
        manifest["selected_candidate_id"] = "opencode-glm51-1"
        with self.assertRaisesRegex(ValueError, "must bind its only candidate"):
            ai_exact._manifest_candidate_id(manifest)

    def test_identity_is_derived_from_resolved_model(self) -> None:
        competition = resolve_model_identity("zai/glm-5.1")
        auxiliary = resolve_model_identity(DEEPSEEK_MODEL)

        self.assertEqual(("zai", "GLM-5.1", True), (
            competition.provider_label,
            competition.logical_model,
            competition.competition_eligible,
        ))
        self.assertEqual(
            ("opencode", "DeepSeek-V4-Flash", False, "auxiliary-local-validation"),
            (
                auxiliary.provider_label,
                auxiliary.logical_model,
                auxiliary.competition_eligible,
                auxiliary.evaluation_scope,
            ),
        )
        self.assertEqual("opencode-deepseek-v4-flash-1", auxiliary.candidate_id)
        with self.assertRaises(ValueError):
            resolve_model_identity("deepseek-v4-flash-free")

    def test_deepseek_candidate_is_honestly_labeled_and_not_competition_eligible(self) -> None:
        with tempfile.TemporaryDirectory(prefix="deepseek-ai-candidate-") as tmp:
            root = Path(tmp)
            spec_path = root / "slice.json"
            spec_path.write_text(json.dumps(spec()), encoding="utf-8")
            context = build_provider_context(spec_path)
            out_dir = root / "out"
            manifest = ai_candidate_harness.generate_candidate(
                context,
                out_dir=out_dir,
                resolved_model=DEEPSEEK_MODEL,
                runner=lambda _argv, _timeout: ai_candidate_harness.ProviderExecution(
                    0,
                    response("pub fn scale(value: i32) -> i32 { value.wrapping_mul(3) }\n"),
                    "",
                ),
            )

            generator = manifest["generator"]
            candidate = manifest["candidates"][0]
            self.assertEqual(8, manifest["schema_version"])
            self.assertEqual("opencode", generator["provider"])
            self.assertEqual("DeepSeek-V4-Flash", generator["logical_model"])
            self.assertFalse(generator["competition_eligible"])
            self.assertEqual("auxiliary-local-validation", generator["evaluation_scope"])
            self.assertEqual("opencode", candidate["provider_label"])
            self.assertEqual("DeepSeek-V4-Flash", candidate["model_label"])
            self.assertEqual("opencode-deepseek-v4-flash-1", candidate["candidate_id"])
            self.assertFalse(candidate["competition_eligible"])

            schema_path = (
                Path(__file__).resolve().parents[1]
                / "auto-translation-template"
                / "ai-candidate-manifest.schema.json"
            )
            jsonschema.Draft7Validator(
                json.loads(schema_path.read_text(encoding="utf-8"))
            ).validate(manifest)
            validation = summary_validator.validate_fresh_ai_manifest(
                manifest,
                manifest_path=out_dir / "l3-deepseek-scale-ai-candidate-manifest.json",
                policy={
                    "model": DEEPSEEK_MODEL,
                    "agent": "c2rust-candidate",
                    "variant": "max",
                },
                summary_path=root / "competition-run-summary.json",
                repo_root=root,
            )
            self.assertIn("ai_candidate_not_competition_eligible", validation["reasons"])

            forged = json.loads(json.dumps(manifest))
            forged["generator"].update(
                {
                    "provider": "zai",
                    "logical_model": "GLM-5.1",
                    "competition_eligible": True,
                    "evaluation_scope": "competition-primary",
                }
            )
            forged["candidates"][0].update(
                {
                    "competition_eligible": True,
                    "evaluation_scope": "competition-primary",
                }
            )
            rejected = summary_validator.validate_fresh_ai_manifest(
                forged,
                manifest_path=out_dir / "l3-deepseek-scale-ai-candidate-manifest.json",
                policy={
                    "model": DEEPSEEK_MODEL,
                    "agent": "c2rust-candidate",
                    "variant": "max",
                },
                summary_path=root / "competition-run-summary.json",
                repo_root=root,
            )
            self.assertIn(
                "ai_manifest_generator_does_not_match_execution_policy",
                rejected["reasons"],
            )
            self.assertIn("ai_candidate_model_identity_mismatch", rejected["reasons"])

            fully_forged = json.loads(json.dumps(manifest))
            fully_forged["generator"].update(
                {
                    "provider": "zai",
                    "logical_model": "GLM-5.1",
                    "resolved_model": "zai/glm-5.1",
                    "competition_eligible": True,
                    "evaluation_scope": "competition-primary",
                }
            )
            fully_forged["candidates"][0].update(
                {
                    "candidate_id": "opencode-glm51-1",
                    "provider_label": "zai",
                    "model_label": "GLM-5.1",
                    "resolved_model": "zai/glm-5.1",
                    "competition_eligible": True,
                    "evaluation_scope": "competition-primary",
                }
            )
            receipt_rejected = summary_validator.validate_fresh_ai_manifest(
                fully_forged,
                manifest_path=out_dir / "l3-deepseek-scale-ai-candidate-manifest.json",
                policy={
                    "model": "zai/glm-5.1",
                    "agent": "c2rust-candidate",
                    "variant": "max",
                },
                summary_path=root / "competition-run-summary.json",
                repo_root=root,
            )
            self.assertIn(
                "ai_invocation_receipt_identity_mismatch",
                receipt_rejected["reasons"],
            )

            (root / "competition-run-summary.json").write_text(
                json.dumps({"proof_class": "competition-exact"}),
                encoding="utf-8",
            )
            unattested = summary_validator.validate_fresh_ai_manifest(
                manifest,
                manifest_path=out_dir / "l3-deepseek-scale-ai-candidate-manifest.json",
                policy={
                    "model": DEEPSEEK_MODEL,
                    "agent": "c2rust-candidate",
                    "variant": "max",
                },
                summary_path=root / "competition-run-summary.json",
                repo_root=root,
            )
            self.assertIn(
                "ai_invocation_receipt_not_provider_attested",
                unattested["reasons"],
            )

            forged_receipt = {
                "session_id": "ses_deepseek_actual",
                "provider_id": "zai",
                "model_id": "glm-5.1",
                "agent": "c2rust-candidate",
                "variant": "max",
                "opencode_version": "1.17.18",
            }
            actual_export = {
                "info": {
                    "id": "ses_deepseek_actual",
                    "agent": "c2rust-candidate",
                    "version": "1.17.18",
                    "model": {
                        "providerID": "opencode",
                        "id": "deepseek-v4-flash-free",
                        "variant": "max",
                    },
                }
            }
            completed = subprocess.CompletedProcess(
                ["opencode", "export"],
                0,
                stdout=json.dumps(actual_export),
                stderr="",
            )
            with mock.patch.object(
                summary_validator.subprocess,
                "run",
                return_value=completed,
            ):
                self.assertFalse(
                    summary_validator.validate_live_opencode_session_identity(
                        forged_receipt,
                        opencode_command="opencode",
                        expected_export_sha256=candidate_provider.sha256_bytes(
                            completed.stdout.encode("utf-8")
                        ),
                        prompt_path=out_dir / manifest["bindings"]["prompt"]["path"],
                        response_text=response("pub fn scale(value: i32) -> i32 { value * 3 }"),
                    )
                )

            receipt_ref = manifest["bindings"]["invocation_receipt"]
            receipt_path = out_dir / receipt_ref["path"]
            sensitive_receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            sensitive_receipt["api_key"] = "must-not-be-accepted"
            sensitive_receipt["messages"] = [{"content": "full session"}]
            receipt_path.write_text(json.dumps(sensitive_receipt), encoding="utf-8")
            sensitive_manifest = json.loads(json.dumps(manifest))
            sensitive_manifest["bindings"]["invocation_receipt"]["sha256"] = (
                candidate_provider.sha256_path(receipt_path)
            )
            sensitive_rejected = summary_validator.validate_fresh_ai_manifest(
                sensitive_manifest,
                manifest_path=out_dir / "l3-deepseek-scale-ai-candidate-manifest.json",
                policy={
                    "model": DEEPSEEK_MODEL,
                    "agent": "c2rust-candidate",
                    "variant": "max",
                },
                summary_path=root / "competition-run-summary.json",
                repo_root=root,
            )
            self.assertIn(
                "ai_invocation_receipt_schema_invalid",
                sensitive_rejected["reasons"],
            )

    def test_live_session_identity_binds_prompt_and_response(self) -> None:
        with tempfile.TemporaryDirectory(prefix="live-ai-session-") as tmp:
            root = Path(tmp)
            prompt_path = root / "prompt.txt"
            prompt_path.write_text("bounded prompt", encoding="utf-8")
            raw_response = response(
                "pub fn scale(value: i32) -> i32 { value.wrapping_mul(3) }"
            )
            assistant_text = assistant_text_from_jsonl(raw_response)
            session_id = "ses_bound_glm"
            export_payload = {
                "info": {
                    "id": session_id,
                    "agent": "c2rust-candidate",
                    "version": "1.17.18",
                    "model": {"providerID": "zai", "id": "glm-5.1", "variant": "max"},
                },
                "messages": [
                    {
                        "info": {"role": "user"},
                        "parts": [
                            {"type": "text", "text": PROMPT_FILE_MESSAGE},
                            {"type": "text", "text": "1: bounded prompt"},
                            {"type": "file", "url": prompt_path.resolve().as_uri()},
                        ],
                    },
                    {
                        "info": {"role": "assistant"},
                        "parts": [{"type": "text", "text": assistant_text}],
                    },
                ],
            }
            export_stdout = json.dumps(export_payload)
            completed = subprocess.CompletedProcess(
                ["opencode", "export", session_id],
                0,
                stdout=export_stdout,
                stderr="",
            )
            receipt = {
                "session_id": session_id,
                "provider_id": "zai",
                "model_id": "glm-5.1",
                "agent": "c2rust-candidate",
                "variant": "max",
                "opencode_version": "1.17.18",
            }
            kwargs = {
                "opencode_command": "opencode",
                "expected_export_sha256": candidate_provider.sha256_bytes(
                    export_stdout.encode("utf-8")
                ),
                "prompt_path": prompt_path,
                "response_text": raw_response,
            }
            with mock.patch.object(summary_validator.subprocess, "run", return_value=completed):
                self.assertTrue(
                    summary_validator.validate_live_opencode_session_identity(
                        receipt,
                        **kwargs,
                    )
                )
                self.assertFalse(
                    summary_validator.validate_live_opencode_session_identity(
                        receipt,
                        **{**kwargs, "response_text": response("pub fn scale() {}")},
                    )
                )

    def test_deepseek_style_fenced_json_and_structured_assumptions_are_bounded(self) -> None:
        assistant_payload = {
            "schema_version": 1,
            "candidate": {
                "language": "rust",
                "source": "pub fn scale(value: i32) -> i32 { value.wrapping_mul(3) }",
            },
            "assumptions": [
                {"kind": "integer_width", "description": "C int maps to i32"},
                {"description": "Caller preserves the declared input domain"},
            ],
        }
        stdout = json.dumps(
            {
                "type": "message.part.updated",
                "part": {
                    "type": "text",
                    "text": f"```json\n{json.dumps(assistant_payload)}\n```",
                },
            }
        )

        parsed = ai_candidate_harness.parse_candidate_response(stdout)

        self.assertEqual(
            [
                "integer_width: C int maps to i32",
                "Caller preserves the declared input domain",
            ],
            parsed["assumptions"],
        )
        mixed = json.dumps(
            {
                "type": "message.part.updated",
                "part": {
                    "type": "text",
                    "text": f"prose before\n```json\n{json.dumps(assistant_payload)}\n```",
                },
            }
        )
        mixed_parsed = ai_candidate_harness.parse_candidate_response(mixed)
        self.assertEqual(assistant_payload["candidate"], mixed_parsed["candidate"])
        self.assertEqual(parsed["assumptions"], mixed_parsed["assumptions"])
        multiple = json.dumps(
            {
                "type": "message.part.updated",
                "part": {
                    "type": "text",
                    "text": f"```json\n{{}}\n```\n```json\n{json.dumps(assistant_payload)}\n```",
                },
            }
        )
        with self.assertRaises(ValueError):
            ai_candidate_harness.parse_candidate_response(multiple)

    def test_candidate_response_rejects_tool_events(self) -> None:
        stdout = response("pub fn scale(value: i32) -> i32 { value * 3 }")
        tool_event = json.dumps(
            {"type": "tool_use", "part": {"type": "tool", "tool": "read"}}
        )

        with self.assertRaisesRegex(ValueError, "forbidden tool"):
            ai_candidate_harness.parse_candidate_response(tool_event + "\n" + stdout)
        nested_tool_event = json.dumps(
            {
                "type": "message.part.updated",
                "properties": {"part": {"type": "tool", "tool": "read"}},
            }
        )
        with self.assertRaisesRegex(ValueError, "forbidden tool"):
            ai_candidate_harness.parse_candidate_response(nested_tool_event + "\n" + stdout)
        nested_tool_name_only = json.dumps(
            {
                "type": "message.part.updated",
                "properties": {"part": {"tool": "read", "state": {"status": "completed"}}},
            }
        )
        with self.assertRaisesRegex(ValueError, "forbidden tool"):
            ai_candidate_harness.parse_candidate_response(nested_tool_name_only + "\n" + stdout)

    def test_router_rejects_opencode_candidate_without_model_identity(self) -> None:
        candidate_sha = "a" * 64
        gates = {
            gate: {"status": "passed", "candidate_sha256": candidate_sha}
            for gate in ai_candidate_harness.REQUIRED_GATES
        }
        result = ai_candidate_harness.route_candidates(
            [
                {
                    "candidate_id": "opencode-deepseek-v4-flash-1",
                    "source": "opencode-ai",
                    "artifact_sha256": candidate_sha,
                    "gate_results": gates,
                }
            ],
            provider_invocations=1,
        )

        self.assertIsNone(result["selected_candidate_id"])
        self.assertEqual(
            "model_identity",
            result["candidate_set"][0]["rejection_facts"][0]["gate"],
        )


if __name__ == "__main__":
    unittest.main()
