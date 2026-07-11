from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
import unittest

import jsonschema

from validation.tools import run_competition as runner
from validation.tools import validate_competition_run_summary as validator


REPO_ROOT = Path(__file__).resolve().parents[2]


def completed(command: list[str], *, returncode: int = 0, stdout: str = "", stderr: str = ""):
    return subprocess.CompletedProcess(command, returncode, stdout, stderr)


class RecordingRunner:
    def __init__(self, *, fail_auto_migrate: bool = False) -> None:
        self.commands: list[list[str]] = []
        self.fail_auto_migrate = fail_auto_migrate

    def __call__(self, command, **_kwargs):
        command = list(command)
        self.commands.append(command)
        if any(item.replace("\\", "/").endswith("unsafe_budget.py") for item in command):
            return completed(
                command,
                stdout=json.dumps(
                    {
                        "status": "passed",
                        "first_party_non_test_unsafe_count": 0,
                        "unsafe_ratio": 0.0,
                    }
                ),
            )
        if any(item.replace("\\", "/").endswith("auto_migrate.py") for item in command):
            return completed(command, returncode=1 if self.fail_auto_migrate else 0)
        return completed(command)


def write_text(path: Path, text: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return runner.sha256(path)


def write_json(path: Path, payload: dict) -> str:
    return write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def nested_ref(path: Path) -> dict:
    return {"path": path.name, "sha256": runner.sha256(path), "status": "present"}


def runtime() -> dict:
    return {
        "opencode_command": "opencode",
        "model": "zai/glm-5.1",
        "agent": "c2rust-migrator",
        "variant": "max",
        "timeout_seconds": 37,
        "resolution": {
            "opencode_command": "cli",
            "model": "cli",
            "agent": "cli",
            "variant": "cli",
            "timeout_seconds": "cli",
        },
        "competition_exact_contract": False,
    }


def write_generated_ai_chain(
    out_root: Path,
    *,
    accepted_binding: bool = False,
    common_acceptance: bool = False,
) -> tuple[dict, dict]:
    target_id = "portable-project"
    slice_id = "sum-values"
    evidence_root = out_root / "evidence"
    base = evidence_root / target_id / "auto-translation" / slice_id
    base.mkdir(parents=True)
    context = base / f"l3-{slice_id}-ai-context-pack.json"
    prompt = base / f"l3-{slice_id}-ai-prompt.txt"
    response = base / f"l3-{slice_id}-ai-response.jsonl"
    candidate_path = base / f"l3-{slice_id}-ai-rust-candidate.rs"
    draft = base / f"l3-{slice_id}-rust-draft.rs"
    write_json(context, {"target_id": target_id, "slice_id": slice_id})
    write_text(prompt, "translate this bounded slice")
    write_text(response, '{"type":"text","text":"candidate"}\n')
    candidate_sha = write_text(candidate_path, "pub fn sum_values(a: i32, b: i32) -> i32 { a + b }\n")
    write_text(draft, candidate_path.read_text(encoding="utf-8"))

    manifest_path = base / f"l3-{slice_id}-ai-candidate-manifest.json"
    candidate_id = "opencode-glm51-1"
    manifest = {
        "schema_version": 2,
        "target_id": target_id,
        "slice_id": slice_id,
        "status": "generated",
        "ai_required_for_default_pipeline": True,
        "generator": {
            "tool": "opencode",
            "provider": "zai",
            "logical_model": "GLM-5.1",
            "resolved_model": "zai/glm-5.1",
            "agent": "c2rust-migrator",
            "variant": "max",
        },
        "bindings": {
            "context_pack": nested_ref(context),
            "prompt": nested_ref(prompt),
            "raw_response": nested_ref(response),
        },
        "selected_candidate_id": candidate_id,
        "candidates": [
            {
                "candidate_id": candidate_id,
                "purpose": "rust_draft",
                "kind": "opencode-ai",
                "artifact": nested_ref(candidate_path),
                "output_hash": candidate_sha,
                "applied": True,
                "applied_artifact": nested_ref(draft),
                "rust_draft_sha256": candidate_sha,
                "semantic_pass": False,
            }
        ],
    }
    write_json(manifest_path, manifest)
    ai_entry = {
        "candidate_id": candidate_id,
        "kind": "opencode-ai",
        "status": "generated",
        "role": "ai_primary_rust_draft",
        "applied": True,
        "rust_draft_sha256": candidate_sha,
        "source_artifact": nested_ref(manifest_path),
    }
    generation = {
        "selected_candidate_id": candidate_id,
        "ai": ai_entry,
        "primary_candidate": {"candidate_id": candidate_id, "selected": "opencode-ai"},
    }
    route_path = base / f"l3-{slice_id}-route-decision.json"
    route = {
        "target_id": target_id,
        "slice_id": slice_id,
        "status": "recorded",
        "candidate_generation": generation,
        "source_artifacts": {"ai_candidate_manifest": nested_ref(manifest_path)},
    }
    write_json(route_path, route)
    semantic = accepted_binding or common_acceptance
    acceptance = {
        "status": "passed" if semantic else "blocked",
        "generated_draft_semantic_pass": semantic,
        "selected_candidate_id": candidate_id,
        "accepted_evidence_binding": {"status": "accepted"} if accepted_binding else None,
        "claim_source": (
            "generated_draft_replay_with_accepted_oracle_binding"
            if accepted_binding
            else "generated_draft_replay_with_common_validation"
            if common_acceptance
            else "blocked_generated_draft_acceptance"
        ),
        "rust_check": {"status": "passed"},
        "rust_draft": {"path": draft.name, "sha256": candidate_sha, "status": "candidate"},
    }
    profile_path = base / f"l3-{slice_id}-validation-profile.json"
    profile = {
        "target_id": target_id,
        "slice_id": slice_id,
        "status": "passed" if semantic else "incomplete",
        "accepted_evidence_authoritative": False,
        "candidate_generation": generation,
        "generated_draft_acceptance": acceptance,
        "generated_draft_semantic_pass": semantic,
    }
    write_json(profile_path, profile)
    final_path = base / f"l3-{slice_id}-final-verification.json"
    final = {
        "target_id": target_id,
        "slice_id": slice_id,
        "status": "passed" if semantic else "incomplete",
        "semantic_pass": semantic,
        "rust_check_status": "passed",
        "validation_profile_status": "passed" if semantic else "incomplete",
        "route_decision": nested_ref(route_path),
        "validation_profile": nested_ref(profile_path),
    }
    write_json(final_path, final)

    log_path = out_root / "logs" / "commands.jsonl"
    command = [
        "python3",
        "validation/tools/auto_migrate.py",
        "--slice-spec",
        "validation/slice-specs/portable.json",
        "--ai-first-candidate",
        "--ai-model",
        "zai/glm-5.1",
        "--ai-agent",
        "c2rust-migrator",
        "--ai-variant",
        "max",
        "--ai-timeout-seconds",
        "37",
        "--ai-opencode-command",
        "opencode",
    ]
    write_text(
        log_path,
        json.dumps({"step": f"auto-migrate-{slice_id}", "command": command, "run_id": "ai-run", "canonical": True}) + "\n",
    )
    summary = {
        "schema_version": 2,
        "run_id": "ai-run",
        "proof_class": "local-simulation",
        "slices": {"attempted": 1},
        "command_log": {
            "path": "logs/commands.jsonl",
            "sha256": runner.sha256(log_path),
        },
    }
    descriptor = runner.ai_metric_descriptor(
        target_id=target_id,
        slice_id=slice_id,
        source="direct",
        execution_mode="fresh_ai_translation",
        evidence_root=evidence_root,
        repo_root=REPO_ROOT,
        out_root=out_root,
    )
    return summary, descriptor


class AiRunMetricsTests(unittest.TestCase):
    def test_fresh_runner_forwards_ai_first_and_all_runtime_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            recording = RecordingRunner(fail_auto_migrate=True)
            result = runner.run_competition(
                slice_specs=[REPO_ROOT / "validation/slice-specs/demo-add-one.json"],
                out_root=Path(tmp),
                proof_class="local-simulation",
                command_runner=recording,
                repo_root=REPO_ROOT,
                run_id="ai-forwarding",
                ai_model="custom/glm-5.1",
                ai_agent="c2rust-migrator",
                ai_variant="max",
                ai_timeout_seconds=41,
                ai_opencode_command="opencode-custom",
            )
            command = next(
                command
                for command in recording.commands
                if any(item.replace("\\", "/").endswith("auto_migrate.py") for item in command)
            )
            self.assertIn("--ai-first-candidate", command)
            self.assertEqual(command[command.index("--ai-model") + 1], "custom/glm-5.1")
            self.assertEqual(command[command.index("--ai-timeout-seconds") + 1], "41")
            self.assertEqual(command[command.index("--ai-opencode-command") + 1], "opencode-custom")
            self.assertEqual(result.summary["schema_version"], 2)
            self.assertEqual(result.summary["ai_translation_metrics"]["abnormal"], 1)

    def test_accepted_evidence_revalidation_skips_auto_migrate_and_ai_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            recording = RecordingRunner()
            result = runner.run_competition(
                slice_specs=[REPO_ROOT / "validation/slice-specs/demo-while-countdown-positive.json"],
                out_root=Path(tmp),
                proof_class="local-simulation",
                command_runner=recording,
                repo_root=REPO_ROOT,
                run_id="accepted-only",
                reuse_accepted_evidence=True,
                accepted_evidence_root=REPO_ROOT / "validation/evidence",
            )
            self.assertFalse(
                any(any(item.replace("\\", "/").endswith("auto_migrate.py") for item in command) for command in recording.commands)
            )
            metrics = result.summary["ai_translation_metrics"]
            self.assertEqual(metrics["historical_evidence"], 1)
            self.assertEqual(
                [metrics[key] for key in ["invocations", "generated", "applied", "selected", "rustc_pass", "semantic_acceptance"]],
                [0, 0, 0, 0, 0, 0],
            )

    def test_generated_ai_funnel_is_recomputed_and_not_semantically_overclaimed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_root = Path(tmp)
            summary, descriptor = write_generated_ai_chain(out_root)
            metrics = runner.build_ai_translation_metrics(
                summary=summary,
                descriptors=[descriptor],
                ai_runtime=runtime(),
                reuse_accepted_evidence=False,
                summary_path=out_root / "summary/competition-run-summary.json",
                repo_root=REPO_ROOT,
                out_root=out_root,
            )
            self.assertEqual(
                [metrics[key] for key in ["invocations", "generated", "applied", "selected", "rustc_pass"]],
                [1, 1, 1, 1, 1],
            )
            self.assertEqual(metrics["semantic_acceptance"], 0)
            self.assertEqual(metrics["blocked"], 1)

    def test_accepted_oracle_binding_cannot_be_counted_as_ai_semantic_acceptance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_root = Path(tmp)
            summary, descriptor = write_generated_ai_chain(out_root, accepted_binding=True)
            metrics = runner.build_ai_translation_metrics(
                summary=summary,
                descriptors=[descriptor],
                ai_runtime=runtime(),
                reuse_accepted_evidence=False,
                summary_path=out_root / "summary/competition-run-summary.json",
                repo_root=REPO_ROOT,
                out_root=out_root,
            )
            self.assertEqual(metrics["semantic_acceptance"], 0)
            self.assertEqual(metrics["blocked"], 1)

    def test_current_common_validation_can_count_exact_ai_candidate_semantics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_root = Path(tmp)
            summary, descriptor = write_generated_ai_chain(out_root, common_acceptance=True)
            metrics = runner.build_ai_translation_metrics(
                summary=summary,
                descriptors=[descriptor],
                ai_runtime=runtime(),
                reuse_accepted_evidence=False,
                summary_path=out_root / "summary/competition-run-summary.json",
                repo_root=REPO_ROOT,
                out_root=out_root,
            )
            self.assertEqual(metrics["semantic_acceptance"], 1)
            self.assertEqual(metrics["terminal_classifications"]["semantic_acceptance"], 1)
            self.assertEqual(metrics["blocked"], 0)

    def test_metric_tampering_and_artifact_drift_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_root = Path(tmp)
            summary, descriptor = write_generated_ai_chain(out_root)
            summary_path = out_root / "summary/competition-run-summary.json"
            metrics = runner.build_ai_translation_metrics(
                summary=summary,
                descriptors=[descriptor],
                ai_runtime=runtime(),
                reuse_accepted_evidence=False,
                summary_path=summary_path,
                repo_root=REPO_ROOT,
                out_root=out_root,
            )
            summary["ai_translation_metrics"] = metrics
            tampered = json.loads(json.dumps(summary))
            tampered["ai_translation_metrics"]["generated"] = 0
            with self.assertRaises(SystemExit):
                validator.validate_ai_translation_metrics(tampered, summary_path=summary_path, repo_root=REPO_ROOT)

            manifest_ref = metrics["units"][0]["artifacts"]["manifest"]["path"]
            manifest_path = out_root / manifest_ref
            manifest_path.write_text(manifest_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            with self.assertRaises(SystemExit):
                validator.validate_ai_translation_metrics(summary, summary_path=summary_path, repo_root=REPO_ROOT)

    def test_command_contract_tampering_invalidates_previously_computed_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_root = Path(tmp)
            summary, descriptor = write_generated_ai_chain(out_root)
            summary_path = out_root / "summary/competition-run-summary.json"
            summary["ai_translation_metrics"] = runner.build_ai_translation_metrics(
                summary=summary,
                descriptors=[descriptor],
                ai_runtime=runtime(),
                reuse_accepted_evidence=False,
                summary_path=summary_path,
                repo_root=REPO_ROOT,
                out_root=out_root,
            )
            log_path = out_root / "logs/commands.jsonl"
            entry = json.loads(log_path.read_text(encoding="utf-8"))
            entry["command"].remove("--ai-first-candidate")
            write_text(log_path, json.dumps(entry) + "\n")
            summary["command_log"]["sha256"] = runner.sha256(log_path)
            with self.assertRaises(SystemExit):
                validator.validate_ai_translation_metrics(summary, summary_path=summary_path, repo_root=REPO_ROOT)

    def test_competition_exact_rejects_runtime_substitution(self) -> None:
        with self.assertRaises(SystemExit):
            runner.resolve_ai_runtime(
                repo_root=REPO_ROOT,
                proof_class="competition-exact",
                model="zai/glm-5.1",
                agent=None,
                variant=None,
                timeout_seconds=None,
                opencode_command=None,
            )

    def test_profile_can_override_every_ai_runtime_setting(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            profile_path = repo_root / "config/competition-env/environment.json"
            write_json(
                profile_path,
                {
                    "opencode_runtime": {
                        "candidate_command": "profile-opencode",
                        "candidate_model": "profile/glm-5.1",
                        "candidate_agent": "profile-agent",
                        "candidate_variant": "profile-variant",
                        "candidate_timeout_seconds": 52,
                    }
                },
            )
            resolved = runner.resolve_ai_runtime(
                repo_root=repo_root,
                proof_class="local-simulation",
                model=None,
                agent=None,
                variant=None,
                timeout_seconds=None,
                opencode_command=None,
            )
            self.assertEqual(
                [resolved[key] for key in ["opencode_command", "model", "agent", "variant", "timeout_seconds"]],
                ["profile-opencode", "profile/glm-5.1", "profile-agent", "profile-variant", 52],
            )
            self.assertTrue(all(source == "profile" for source in resolved["resolution"].values()))

    def test_schema_v2_requires_ai_metrics_while_v1_remains_compatible(self) -> None:
        schema = json.loads((REPO_ROOT / "validation/competition-run-summary.schema.json").read_text(encoding="utf-8"))
        base = {
            "schema_version": 2,
            "run_id": "r",
            "proof_class": "local-simulation",
            "profile_id": "huawei-competition-ubuntu-24.04",
            "profile_sha256": "0" * 64,
            "clang_source": "missing",
            "cargo_mirror_activation": {
                "method": "CARGO_HOME",
                "path": "config/competition-env/cargo",
                "config_file": "config/competition-env/cargo/config.toml",
            },
            "elapsed_seconds": 0,
            "translator_version": "0.1.0",
            "slices": {key: 0 for key in ["attempted", "typed_ir_generated", "compiled", "semantic_pass", "refused", "blocked", "failed"]},
            "unsafe_budget": {"status": "passed", "total_first_party_non_test_unsafe": 0, "ratio": 0.0},
            "workflow_metrics": {"path": "workflow.json", "sha256": "0" * 64},
            "command_log": {"path": "commands.jsonl", "sha256": "0" * 64},
            "artifact_roots": ["target/competition-out/evidence"],
            "final_gate": {"status": "failed", "validator": "validator"},
        }
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(base, schema)
        base["schema_version"] = 1
        jsonschema.validate(base, schema)


if __name__ == "__main__":
    unittest.main()
