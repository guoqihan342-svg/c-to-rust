#!/usr/bin/env python3
"""Run the judge-facing harness demo and bind its public reports."""

from __future__ import annotations

import argparse
from contextlib import closing
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from validation.tools import opencode_agent_harness as harness
from validation.tools import validate_competition_run_summary

CommandRunner = Callable[..., subprocess.CompletedProcess[str]]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile",
        type=Path,
        default=Path("config/competition-env/planned-batches/flashdb-fdb-utils-before-after.json"),
    )
    parser.add_argument("--run-id", default="competition-flashdb-before-after-exhibit")
    parser.add_argument("--out-root", type=Path, default=Path("target/competition-out-flashdb-before-after-exhibit"))
    parser.add_argument("--milestone-output", type=Path)
    parser.add_argument("--review-checklist", type=Path, action="append", default=[])
    args = parser.parse_args()

    report = run_judge_demo(
        profile_path=args.profile,
        run_id=args.run_id,
        out_root=args.out_root,
        milestone_output=args.milestone_output,
        review_checklist_paths=args.review_checklist,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "passed" else 1


def run_judge_demo(
    *,
    profile_path: Path,
    run_id: str,
    out_root: Path,
    milestone_output: Path | None = None,
    review_checklist_paths: list[Path] | None = None,
    repo_root: Path = REPO_ROOT,
    command_runner: CommandRunner = subprocess.run,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    profile_path = harness.repo_path(profile_path, repo_root=repo_root)
    out_root = harness.repo_path(out_root, repo_root=repo_root)
    summary_dir = out_root / "summary"
    harness_dir = out_root / "harness"
    summary_dir.mkdir(parents=True, exist_ok=True)
    harness_dir.mkdir(parents=True, exist_ok=True)

    summary_path = summary_dir / "competition-run-summary.json"
    batch_profile_report_path = harness_dir / "batch-profile-report.json"
    milestone_output = (
        harness.repo_path(milestone_output, repo_root=repo_root)
        if milestone_output is not None
        else summary_dir / "milestone-release-report.json"
    )
    remove_stale_judge_demo_outputs(
        summary_path=summary_path,
        batch_profile_report_path=batch_profile_report_path,
        milestone_report_path=milestone_output,
        harness_dir=harness_dir,
    )
    review_checklist_paths = [
        harness.repo_path(review_path, repo_root=repo_root)
        for review_path in (review_checklist_paths or [])
    ]
    milestone_review_checklist_paths = copy_review_checklists_for_milestone(
        review_checklist_paths,
        summary_dir=summary_dir,
    )

    commands: list[dict[str, Any]] = []
    commands.append(
        run_stage(
            stage="run_batch_profile",
            argv=[
                sys.executable,
                "-B",
                "-m",
                "validation.tools.opencode_agent_harness",
                "run-batch-profile",
                "--profile",
                harness.repo_relative(profile_path, repo_root=repo_root),
                "--run-id",
                run_id,
                "--out-root",
                harness.repo_relative(out_root, repo_root=repo_root),
            ],
            log_dir=harness_dir,
            repo_root=repo_root,
            command_runner=command_runner,
        )
    )
    if commands[-1]["exit_code"] == 0:
        commands.append(
            run_stage(
                stage="validate_summary",
                argv=[
                    sys.executable,
                    "-B",
                    "validation/tools/validate_competition_run_summary.py",
                    "--summary",
                    harness.repo_relative(summary_path, repo_root=repo_root),
                ],
                log_dir=harness_dir,
                repo_root=repo_root,
                command_runner=command_runner,
            )
        )
    if commands[-1]["exit_code"] == 0:
        refresh_before_after_exhibit_binding(
            profile_path=profile_path,
            summary_path=summary_path,
            batch_profile_report_path=batch_profile_report_path,
            out_root=out_root,
            repo_root=repo_root,
        )
        milestone_argv = [
            sys.executable,
            "-B",
            "validation/tools/milestone_release_report.py",
            "--competition-summary",
            harness.repo_relative(summary_path, repo_root=repo_root),
            "--batch-profile-report",
            harness.repo_relative(batch_profile_report_path, repo_root=repo_root),
        ]
        for review_path in milestone_review_checklist_paths:
            milestone_argv.extend(
                [
                    "--review-checklist",
                    harness.repo_relative(review_path, repo_root=repo_root),
                ]
            )
        milestone_argv.extend(
            [
                "--output",
                harness.repo_relative(milestone_output, repo_root=repo_root),
            ]
        )
        commands.append(
            run_stage(
                stage="milestone_release_report",
                argv=milestone_argv,
                log_dir=harness_dir,
                repo_root=repo_root,
                command_runner=command_runner,
            )
        )

    report = build_report(
        profile_path=profile_path,
        run_id=run_id,
        out_root=out_root,
        summary_path=summary_path,
        batch_profile_report_path=batch_profile_report_path,
        milestone_report_path=milestone_output,
        review_checklist_paths=review_checklist_paths,
        milestone_review_checklist_paths=milestone_review_checklist_paths,
        commands=commands,
        repo_root=repo_root,
    )
    report_path = summary_dir / "judge-demo-report.json"
    judge_index_path = harness_dir / "judge-evidence-index.json"
    report["artifacts"]["judge_demo_report"] = {
        "path": harness.repo_relative(report_path, repo_root=repo_root),
        "status": "present",
    }
    report["sidecar_reports"] = {
        "judge_evidence_index": {
            "path": harness.repo_relative(judge_index_path, repo_root=repo_root),
            "report_kind": "judge-evidence-index",
            "status": str(report["status"]),
        }
    }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_judge_demo_evidence_index(
        report=report,
        report_path=report_path,
        profile_path=profile_path,
        batch_profile_report_path=batch_profile_report_path,
        milestone_report_path=milestone_output,
        review_checklist_paths=review_checklist_paths,
        milestone_review_checklist_paths=milestone_review_checklist_paths,
        run_id=run_id,
        out_root=out_root,
        repo_root=repo_root,
    )
    return report


def remove_stale_judge_demo_outputs(
    *,
    summary_path: Path,
    batch_profile_report_path: Path,
    milestone_report_path: Path,
    harness_dir: Path,
) -> None:
    stale_paths = [
        summary_path,
        summary_path.parent / "workflow-metrics.json",
        summary_path.parent / "before-after-exhibit.json",
        summary_path.parent / "judge-demo-report.json",
        batch_profile_report_path,
        milestone_report_path,
        harness_dir / "judge-evidence-index.json",
    ]
    for path in stale_paths:
        if not path.exists() or not path.is_file():
            continue
        try:
            path.unlink()
        except OSError as exc:
            raise SystemExit(f"failed to remove stale judge-demo artifact {path}: {exc}") from exc


def refresh_before_after_exhibit_binding(
    *,
    profile_path: Path,
    summary_path: Path,
    batch_profile_report_path: Path,
    out_root: Path,
    repo_root: Path,
) -> dict[str, Any] | None:
    batch_report = load_json_if_exists(batch_profile_report_path)
    binding = batch_report.get("before_after_exhibit_report")
    before_after_path = resolve_report_path(
        binding,
        fallback=summary_path.parent / "before-after-exhibit.json",
        repo_root=repo_root,
    )
    if before_after_path is None or not before_after_path.exists():
        return None

    exhibit = load_json_if_exists(before_after_path)
    if not exhibit:
        return None
    summary = load_json_if_exists(summary_path)
    workflow_path = resolve_workflow_metrics_path(summary, summary_path, repo_root=repo_root)

    inputs = exhibit.setdefault("inputs", {})
    if isinstance(inputs, dict):
        inputs["profile"] = artifact_ref(profile_path, repo_root=repo_root)
        inputs["competition_summary"] = artifact_ref(summary_path, repo_root=repo_root)
        inputs["workflow_metrics"] = artifact_ref(workflow_path, repo_root=repo_root)

    stage_contracts = exhibit.get("stage_contracts")
    if isinstance(stage_contracts, dict):
        verifier = stage_contracts.get("verifier")
        if isinstance(verifier, dict):
            verifier["summary"] = artifact_ref(summary_path, repo_root=repo_root)
            verifier["workflow_metrics"] = artifact_ref(workflow_path, repo_root=repo_root)

    before_after_path.write_text(json.dumps(exhibit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    updated_binding = before_after_binding_from_payload(
        exhibit,
        before_after_path=before_after_path,
        repo_root=repo_root,
    )

    for index_path in (out_root / "harness" / "context-pack.json", out_root / "harness" / "agent-index.json"):
        update_before_after_binding_in_index(index_path, updated_binding)

    if batch_report:
        batch_report["before_after_exhibit_report"] = updated_binding
        report_artifacts = batch_report.get("report_artifacts")
        if isinstance(report_artifacts, dict) and "before_after_exhibit_report" in report_artifacts:
            report_artifacts["before_after_exhibit_report"] = updated_binding
        judge_summary = batch_report.get("judge_summary")
        if isinstance(judge_summary, dict):
            core_translation_quality = judge_summary.get("core_translation_quality")
            if isinstance(core_translation_quality, dict) and "before_after_exhibit" in core_translation_quality:
                core_translation_quality["before_after_exhibit"] = updated_binding
            harness_architecture = judge_summary.get("harness_architecture")
            if isinstance(harness_architecture, dict):
                context_ref = artifact_ref(out_root / "harness" / "context-pack.json", repo_root=repo_root)
                agent_ref = artifact_ref(out_root / "harness" / "agent-index.json", repo_root=repo_root)
                if "context_pack" in harness_architecture:
                    harness_architecture["context_pack"] = context_ref
                if "agent_index" in harness_architecture:
                    harness_architecture["agent_index"] = agent_ref
        context_ref = artifact_ref(out_root / "harness" / "context-pack.json", repo_root=repo_root)
        agent_ref = artifact_ref(out_root / "harness" / "agent-index.json", repo_root=repo_root)
        if "context_pack" in batch_report:
            batch_report["context_pack"] = context_ref
        if "agent_index" in batch_report:
            batch_report["agent_index"] = agent_ref
        batch_profile_report_path.write_text(json.dumps(batch_report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        sync_refreshed_indexes_to_ledger(
            batch_report=batch_report,
            context_pack_path=out_root / "harness" / "context-pack.json",
            agent_index_path=out_root / "harness" / "agent-index.json",
            repo_root=repo_root,
        )
    return updated_binding


def sync_refreshed_indexes_to_ledger(
    *,
    batch_report: dict[str, Any],
    context_pack_path: Path,
    agent_index_path: Path,
    repo_root: Path,
) -> None:
    db_path_text = batch_report.get("db_path")
    if not isinstance(db_path_text, str) or not db_path_text:
        return
    db_path = harness.repo_path(Path(db_path_text), repo_root=repo_root)
    if not db_path.exists():
        return
    context_pack = load_json_if_exists(context_pack_path)
    agent_index = load_json_if_exists(agent_index_path)
    if not context_pack or not agent_index:
        return
    context_pack_id = str(context_pack.get("context_pack_id", ""))
    if not context_pack_id:
        return
    run_id = str(context_pack.get("run_id", batch_report.get("run_id", "")))
    budget = context_pack.get("budget") if isinstance(context_pack.get("budget"), dict) else {}
    context_ref = artifact_ref(context_pack_path, repo_root=repo_root)
    agent_ref = artifact_ref(agent_index_path, repo_root=repo_root)
    with closing(harness.connect(db_path)) as connection:
        harness.ensure_schema(connection)
        connection.execute(
            """
            insert into context_packs(
              context_pack_id, run_id, target_id, slice_id, depth, max_tokens,
              artifact_path, artifact_sha256, payload_json
            )
            values (?, ?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(context_pack_id) do update set
              artifact_path=excluded.artifact_path,
              artifact_sha256=excluded.artifact_sha256,
              payload_json=excluded.payload_json
            """,
            (
                context_pack_id,
                run_id,
                context_pack.get("target_id"),
                None,
                nonnegative_int(budget.get("depth")) or 1,
                nonnegative_int(budget.get("max_tokens")) or 20000,
                context_ref["path"],
                context_ref["sha256"],
                json.dumps(context_pack, sort_keys=True),
            ),
        )
        status = str(batch_report.get("status", context_pack.get("status", "unknown")))
        harness.record_artifact(
            connection,
            run_id=run_id,
            worker_id="planner",
            kind="context-pack",
            path=context_pack_path,
            status=status,
            semantic_role="agent-context-pack",
            payload=context_pack,
            repo_root=repo_root,
        )
        harness.record_artifact(
            connection,
            run_id=run_id,
            worker_id="planner",
            kind="agent-index",
            path=agent_index_path,
            status=status,
            semantic_role="agent-index",
            payload=agent_index,
            repo_root=repo_root,
        )
        harness.record_event(
            connection,
            run_id=run_id,
            event_type="judge_demo_refreshed_report_bindings",
            payload={"context_pack": context_ref, "agent_index": agent_ref},
        )
        connection.commit()


def before_after_binding_from_payload(
    payload: dict[str, Any],
    *,
    before_after_path: Path,
    repo_root: Path,
) -> dict[str, Any]:
    translation_before_after = (
        payload.get("translation_before_after")
        if isinstance(payload.get("translation_before_after"), dict)
        else {}
    )
    units = payload.get("units") if isinstance(payload.get("units"), list) else []
    return {
        "path": harness.repo_relative(before_after_path, repo_root=repo_root),
        "sha256": harness.sha256_file(before_after_path),
        "status": str(payload.get("status", "unknown")),
        "report_kind": "before-after-exhibit",
        "unit_count": len(units),
        "measured_unsafe_unit_count": nonnegative_int(translation_before_after.get("measured_unsafe_unit_count")),
        "accepted_patch_unit_count": nonnegative_int(translation_before_after.get("accepted_patch_unit_count")),
    }


def update_before_after_binding_in_index(path: Path, binding: dict[str, Any]) -> None:
    payload = load_json_if_exists(path)
    if not payload:
        return
    changed = False
    for container_name in ("report_artifacts", "reports"):
        container = payload.get(container_name)
        if isinstance(container, dict) and "before_after_exhibit_report" in container:
            container["before_after_exhibit_report"] = binding
            changed = True
    entrypoints = payload.get("entrypoints")
    if isinstance(entrypoints, dict) and "before_after_exhibit_report" in entrypoints:
        entrypoints["before_after_exhibit_report"] = binding["path"]
        changed = True
    if changed:
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_judge_demo_evidence_index(
    *,
    report: dict[str, Any],
    report_path: Path,
    profile_path: Path,
    batch_profile_report_path: Path,
    milestone_report_path: Path,
    review_checklist_paths: list[Path],
    milestone_review_checklist_paths: list[Path],
    run_id: str,
    out_root: Path,
    repo_root: Path,
) -> dict[str, Any]:
    profile = load_json_if_exists(profile_path)
    batch_profile_report = load_json_if_exists(batch_profile_report_path)
    report_architecture = (
        report.get("harness_architecture")
        if isinstance(report.get("harness_architecture"), dict)
        else {}
    )
    delegated_architecture = (
        report_architecture.get("delegated_harness")
        if isinstance(report_architecture.get("delegated_harness"), dict)
        else {}
    )
    architecture = json.loads(json.dumps(delegated_architecture or report_architecture))
    architecture["entrypoint"] = "judge_demo"
    if delegated_architecture.get("entrypoint"):
        architecture["delegated_entrypoint"] = delegated_architecture["entrypoint"]
    for key in ("context_pack", "agent_index"):
        binding = report_architecture.get(key)
        if isinstance(binding, dict):
            architecture[key] = binding

    core_quality = (
        json.loads(json.dumps(report["core_translation_quality"]))
        if isinstance(report.get("core_translation_quality"), dict)
        else {}
    )
    acceptance_boundary = (
        profile.get("acceptance_boundary")
        if isinstance(profile.get("acceptance_boundary"), dict)
        else {}
    )
    if "semantic_claim_source" not in core_quality and isinstance(acceptance_boundary, dict):
        core_quality["semantic_claim_source"] = acceptance_boundary.get("semantic_claim_source", "accepted_evidence_binding")

    artifacts = report.get("artifacts") if isinstance(report.get("artifacts"), dict) else {}
    competition_summary = artifacts.get("competition_summary") if isinstance(artifacts.get("competition_summary"), dict) else {}
    summary_path_text = competition_summary.get("path") if isinstance(competition_summary.get("path"), str) else ""
    profile_rel = harness.repo_relative(profile_path, repo_root=repo_root)
    out_root_rel = harness.repo_relative(out_root, repo_root=repo_root)
    batch_profile_report_rel = harness.repo_relative(batch_profile_report_path, repo_root=repo_root)
    milestone_report_rel = harness.repo_relative(milestone_report_path, repo_root=repo_root)
    review_args = format_review_checklist_command_args(review_checklist_paths, repo_root=repo_root)
    milestone_review_args = format_review_checklist_command_args(
        milestone_review_checklist_paths,
        repo_root=repo_root,
    )
    reproduction_commands = {
        "judge_demo": (
            "python -B -m validation.tools.judge_demo "
            f"--profile {profile_rel} --run-id {run_id} --out-root {out_root_rel}{review_args}"
        ),
        "run_batch_profile": (
            "python -B -m validation.tools.opencode_agent_harness run-batch-profile "
            f"--profile {profile_rel} --run-id {run_id} --out-root {out_root_rel}"
        ),
        "milestone_release_report": (
            "python -B validation/tools/milestone_release_report.py "
            f"--competition-summary {summary_path_text} "
            f"--batch-profile-report {batch_profile_report_rel} "
            f"{milestone_review_args.strip() + ' ' if milestone_review_args else ''}"
            f"--output {milestone_report_rel}"
        ),
    }
    if summary_path_text:
        reproduction_commands["summary_validation"] = (
            "python -B validation/tools/validate_competition_run_summary.py "
            f"--summary {summary_path_text}"
        )

    index_source_report: dict[str, Any] = {
        "status": report.get("status", "unknown"),
        "exit_code": 0 if report.get("status") == "passed" else 1,
        "profile_id": report.get("profile_id"),
        "proof_class": report.get("proof_class"),
        "mode": profile.get("mode", batch_profile_report.get("mode", "deterministic")),
        "batch_profile_report": artifacts.get("batch_profile_report"),
        "context_pack": report_architecture.get("context_pack"),
        "agent_index": report_architecture.get("agent_index"),
        "summary_validation": {"summary": summary_path_text} if summary_path_text else {},
        "judge_summary": {
            "harness_architecture": architecture,
            "core_translation_quality": core_quality,
        },
        "acceptance_boundary": acceptance_boundary,
    }
    if isinstance(batch_profile_report.get("route_governance_metrics_report"), dict):
        index_source_report["route_governance_metrics_report"] = batch_profile_report["route_governance_metrics_report"]
    if isinstance(batch_profile_report.get("context_pack"), dict):
        index_source_report["context_pack"] = batch_profile_report["context_pack"]
    if isinstance(batch_profile_report.get("agent_index"), dict):
        index_source_report["agent_index"] = batch_profile_report["agent_index"]

    extra_artifact_refs = {
        "before_after_exhibit": artifacts.get("before_after_exhibit"),
        "milestone_release_report": artifacts.get("milestone_release_report"),
    }
    if milestone_review_checklist_paths:
        extra_artifact_refs["milestone_review_checklist"] = artifact_ref(
            milestone_review_checklist_paths[0],
            repo_root=repo_root,
        )
    for index, review_path in enumerate(review_checklist_paths):
        name = "internal_review_checklist" if index == 0 else f"internal_review_checklist_{index + 1}"
        extra_artifact_refs[name] = artifact_ref(review_path, repo_root=repo_root)

    return harness.write_judge_evidence_index(
        evaluate_report=index_source_report,
        evaluate_report_path=report_path,
        batch_result=batch_profile_report,
        profile_path=profile_path,
        run_id=run_id,
        out_root=out_root,
        entrypoint_name="judge_demo",
        primary_report_ref_name="judge_demo_report",
        reproduction_commands=reproduction_commands,
        extra_artifact_refs=extra_artifact_refs,
        repo_root=repo_root,
    )


def format_review_checklist_command_args(review_checklist_paths: list[Path], *, repo_root: Path) -> str:
    return "".join(
        f" --review-checklist {harness.repo_relative(review_path, repo_root=repo_root)}"
        for review_path in review_checklist_paths
    )


def copy_review_checklists_for_milestone(review_checklist_paths: list[Path], *, summary_dir: Path) -> list[Path]:
    copied_paths: list[Path] = []
    for index, review_path in enumerate(review_checklist_paths):
        filename = "milestone-review-checklist.json" if len(review_checklist_paths) == 1 else f"milestone-review-checklist-{index + 1}.json"
        copied_path = summary_dir / filename
        copied_path.write_bytes(review_path.read_bytes())
        copied_paths.append(copied_path)
    return copied_paths


def run_stage(
    *,
    stage: str,
    argv: list[str],
    log_dir: Path,
    repo_root: Path,
    command_runner: CommandRunner,
) -> dict[str, Any]:
    completed = command_runner(argv, cwd=repo_root, text=True, capture_output=True)
    stdout_path = log_dir / f"judge-demo-{stage}.stdout.log"
    stderr_path = log_dir / f"judge-demo-{stage}.stderr.log"
    stdout_path.write_text(completed.stdout or "", encoding="utf-8")
    stderr_path.write_text(completed.stderr or "", encoding="utf-8")
    return {
        "stage": stage,
        "argv": portable_argv(argv),
        "exit_code": int(completed.returncode),
        "logs": {
            "stdout": harness.repo_relative(stdout_path, repo_root=repo_root),
            "stderr": harness.repo_relative(stderr_path, repo_root=repo_root),
        },
    }


def portable_argv(argv: list[str]) -> list[str]:
    if not argv:
        return []
    executable = Path(argv[0]).name.lower()
    if executable.startswith("python"):
        return ["python", *argv[1:]]
    return list(argv)


def build_report(
    *,
    profile_path: Path,
    run_id: str,
    out_root: Path,
    summary_path: Path,
    batch_profile_report_path: Path,
    milestone_report_path: Path,
    review_checklist_paths: list[Path],
    milestone_review_checklist_paths: list[Path],
    commands: list[dict[str, Any]],
    repo_root: Path,
) -> dict[str, Any]:
    profile = load_json_if_exists(profile_path)
    summary = load_json_if_exists(summary_path)
    workflow_metrics_path = resolve_workflow_metrics_path(summary, summary_path, repo_root=repo_root)
    workflow_metrics = load_json_if_exists(workflow_metrics_path) if workflow_metrics_path is not None else {}
    batch_profile_report = load_json_if_exists(batch_profile_report_path)
    before_after_path = resolve_report_path(
        batch_profile_report.get("before_after_exhibit_report"),
        fallback=summary_path.parent / "before-after-exhibit.json",
        repo_root=repo_root,
    )
    before_after_exhibit = load_json_if_exists(before_after_path) if before_after_path is not None else {}
    milestone_report = load_json_if_exists(milestone_report_path)
    review_gate = (
        json.loads(json.dumps(milestone_report.get("review_gate")))
        if isinstance(milestone_report.get("review_gate"), dict)
        else {"status": "missing", "review_count": 0}
    )
    final_gate_status = str(summary.get("final_gate", {}).get("status", "missing"))
    semantic_pass_count = summary_semantic_pass_count(summary)
    exhibit_status = str(before_after_exhibit.get("status", "missing"))
    milestone_status = str(milestone_report.get("status", "missing"))
    judge_demo_gate = summarize_judge_demo_gate(
        final_gate_status=final_gate_status,
        workflow_metrics=workflow_metrics,
        before_after_exhibit=before_after_exhibit,
    )
    command_status = summarize_command_status(
        commands,
        judge_demo_gate=judge_demo_gate,
        milestone_status=milestone_status,
    )
    status = (
        "passed"
        if command_status in {"passed", "passed_with_accepted_evidence_gate"}
        and judge_demo_gate["status"] == "passed"
        and review_gate.get("status") == "passed"
        and exhibit_status == "passed"
        and milestone_status in {"internal_preview", "release_candidate", "passed"}
        else "failed"
    )
    repair_summary = build_repair_summary(
        workflow_metrics=workflow_metrics,
        before_after_exhibit=before_after_exhibit,
    )
    batch_judge_summary = (
        batch_profile_report.get("judge_summary")
        if isinstance(batch_profile_report.get("judge_summary"), dict)
        else {}
    )
    batch_harness_architecture = (
        batch_judge_summary.get("harness_architecture")
        if isinstance(batch_judge_summary.get("harness_architecture"), dict)
        else {}
    )
    batch_core_translation_quality = (
        batch_judge_summary.get("core_translation_quality")
        if isinstance(batch_judge_summary.get("core_translation_quality"), dict)
        else {}
    )
    harness_architecture = {
        "entrypoint": "judge_demo",
        "pipeline": ["run-batch-profile", "validate-summary", "milestone-release-report", "judge-demo-report"],
        "command_status": command_status,
        "command_stages": [str(command.get("stage", "unknown")) for command in commands],
        "delegated_harness": batch_harness_architecture,
        "context_pack": batch_profile_report.get("context_pack"),
        "agent_index": batch_profile_report.get("agent_index"),
    }
    core_translation_quality = {
        "final_gate_status": final_gate_status,
        "semantic_pass_count": semantic_pass_count,
        "unsafe_reduction": workflow_metrics.get("unsafe_reduction", {"status": "not_measured"}),
        "translation_before_after": workflow_metrics.get(
            "translation_before_after",
            {"status": "not_provided", "unit_count": 0},
        ),
        "before_after_exhibit": {
            "status": exhibit_status,
            "path": artifact_ref(before_after_path, repo_root=repo_root).get("path"),
        },
        "before_after_units": compact_before_after_units(before_after_exhibit),
        "translation_coverage_numerator": (
            milestone_report.get("metrics", {}).get("translation_coverage_numerator")
            if isinstance(milestone_report.get("metrics"), dict)
            else None
        ),
        "milestone_status": milestone_status,
        "judge_demo_gate": judge_demo_gate,
        "review_gate": review_gate,
        "repair_summary": repair_summary,
        "delegated_core_translation_quality": batch_core_translation_quality,
    }

    return {
        "schema_version": 1,
        "report_kind": "judge-demo-run-report",
        "status": status,
        "run_id": run_id,
        "profile_id": str(profile.get("profile_id", batch_profile_report.get("profile_id", "unknown"))),
        "proof_class": str(summary.get("proof_class", profile.get("proof_class", "unknown"))),
        "out_root": harness.repo_relative(out_root, repo_root=repo_root),
        "commands": commands,
        "artifacts": {
            "profile": artifact_ref(profile_path, repo_root=repo_root),
            "competition_summary": artifact_ref(summary_path, repo_root=repo_root),
            "workflow_metrics": artifact_ref(workflow_metrics_path, repo_root=repo_root),
            "batch_profile_report": artifact_ref(batch_profile_report_path, repo_root=repo_root),
            "before_after_exhibit": artifact_ref(before_after_path, repo_root=repo_root),
            "milestone_release_report": artifact_ref(milestone_report_path, repo_root=repo_root),
            "milestone_review_checklist": artifact_ref(
                milestone_review_checklist_paths[0] if milestone_review_checklist_paths else None,
                repo_root=repo_root,
            ),
            "review_checklists": [
                artifact_ref(review_path, repo_root=repo_root)
                for review_path in review_checklist_paths
            ],
        },
        "harness_architecture": harness_architecture,
        "core_translation_quality": core_translation_quality,
        "metrics": {
            "final_gate": final_gate_status,
            "semantic_pass": semantic_pass_count,
            "units_total": nonnegative_int(workflow_metrics.get("units_total")),
            "units_converged": nonnegative_int(workflow_metrics.get("units_converged")),
            "unsafe_reduction": workflow_metrics.get("unsafe_reduction", {"status": "not_measured"}),
            "translation_before_after": workflow_metrics.get(
                "translation_before_after",
                {"status": "not_provided", "unit_count": 0},
            ),
            "stage_contracts": before_after_exhibit.get("stage_contracts", {}),
            "translation_coverage_numerator": (
                milestone_report.get("metrics", {}).get("translation_coverage_numerator")
                if isinstance(milestone_report.get("metrics"), dict)
                else None
            ),
            "milestone_status": milestone_status,
            "judge_demo_gate": judge_demo_gate,
            "review_gate": review_gate,
        },
        "repair_summary": repair_summary,
        "claim_boundary": {
            "semantic_claim_source": str(judge_demo_gate.get("claim_source", "competition-run-summary.final_gate")),
            "before_after_exhibit_role": (
                "judge-facing artifact binding and unsafe delta; not a translator-generated semantic pass claim"
            ),
            "must_not_claim": [
                "C2Rust-generated baseline when the profile says baseline output is skipped",
                "translator-generated semantic pass from accepted-evidence-authoritative runs",
                "translation coverage numerator increase from before/after exhibits alone",
            ],
        },
    }


def summarize_judge_demo_gate(
    *,
    final_gate_status: str,
    workflow_metrics: dict[str, Any],
    before_after_exhibit: dict[str, Any],
) -> dict[str, Any]:
    translation_before_after = (
        workflow_metrics.get("translation_before_after")
        if isinstance(workflow_metrics.get("translation_before_after"), dict)
        else {}
    )
    if final_gate_status == "passed":
        return {
            "status": "passed",
            "source": "competition_run_summary.final_gate",
            "claim_source": "competition-run-summary.final_gate",
            "translation_before_after_status": str(translation_before_after.get("status", "not_provided")),
        }
    if before_after_exhibit.get("status") == "passed" and translation_before_after.get("status") == "bound":
        return {
            "status": "passed",
            "source": "before_after_exhibit",
            "claim_source": "accepted_evidence_binding",
            "translation_before_after_status": "bound",
            "boundary": (
                "The judge demo may pass as an accepted-evidence before/after exhibit without claiming "
                "translator-generated semantic acceptance."
            ),
        }
    return {
        "status": "failed",
        "source": "missing_gate",
        "claim_source": "competition-run-summary.final_gate",
        "translation_before_after_status": str(translation_before_after.get("status", "not_provided")),
    }


def summarize_command_status(
    commands: list[dict[str, Any]],
    *,
    judge_demo_gate: dict[str, Any],
    milestone_status: str,
) -> str:
    if commands and all(command.get("exit_code") == 0 for command in commands):
        return "passed"
    nonzero_stages = [
        str(command.get("stage", "unknown"))
        for command in commands
        if command.get("exit_code") != 0
    ]
    tolerated = {"run_batch_profile"}
    if milestone_status == "internal_preview":
        tolerated.add("milestone_release_report")
    if set(nonzero_stages) <= tolerated and judge_demo_gate.get("source") == "before_after_exhibit":
        return "passed_with_accepted_evidence_gate"
    return "failed"


def build_repair_summary(*, workflow_metrics: dict[str, Any], before_after_exhibit: dict[str, Any]) -> dict[str, Any]:
    stage_contracts = before_after_exhibit.get("stage_contracts")
    repairer = stage_contracts.get("repairer") if isinstance(stage_contracts, dict) else {}
    if not isinstance(repairer, dict):
        repairer = {}
    histories = repairer.get("histories")
    normalized_histories = (
        [history for history in histories if isinstance(history, dict)]
        if isinstance(histories, list)
        else repair_histories_from_workflow_metrics(workflow_metrics)
    )
    verified = any(history.get("verified") for history in normalized_histories)
    status = str(repairer.get("status") or ("verified" if verified else ("recorded" if normalized_histories else "not_exercised")))
    repair_round_cap = repairer.get("repair_round_cap")
    cap = nonnegative_int(repair_round_cap) if repair_round_cap is not None else int(getattr(harness, "REPAIR_ROUND_CAP", 5))
    root_cause_counts = repairer.get("root_cause_counts")
    if not isinstance(root_cause_counts, dict):
        root_cause_counts = workflow_metrics.get("root_cause_counts") if isinstance(workflow_metrics.get("root_cause_counts"), dict) else {}
    return {
        "status": status,
        "repair_round_cap": cap,
        "observed_repair_unit_count": len(normalized_histories),
        "auto_recovered_unit_count": sum(1 for history in normalized_histories if history.get("auto_recovered")),
        "rollback_evidence_count": sum(repair_history_rollback_count(history) for history in normalized_histories),
        "avg_repair_rounds": float(repairer.get("avg_repair_rounds", workflow_metrics.get("avg_repair_rounds", 0.0)) or 0.0),
        "auto_recovery_rate": float(repairer.get("auto_recovery_rate", workflow_metrics.get("auto_recovery_rate", 0.0)) or 0.0),
        "human_interventions": nonnegative_int(workflow_metrics.get("human_interventions")),
        "root_cause_counts": root_cause_counts,
        "histories": normalized_histories,
        "evidence_boundary": str(
            repairer.get(
                "evidence_boundary",
                "Repair history is shown only when workflow metrics bind measured repair or retry evidence.",
            )
        ),
    }


def repair_histories_from_workflow_metrics(workflow_metrics: dict[str, Any]) -> list[dict[str, Any]]:
    histories = []
    per_unit = workflow_metrics.get("per_unit_statuses")
    if not isinstance(per_unit, list):
        return histories
    for unit in per_unit:
        if not isinstance(unit, dict) or not isinstance(unit.get("repair_history"), dict):
            continue
        history = {
            "unit_id": str(unit.get("unit_id", "unknown")),
            "source": str(unit.get("source", "unknown")),
            "status": str(unit.get("status", "unknown")),
            "repair_rounds": nonnegative_int(unit.get("repair_rounds")),
            "auto_recovered": bool(unit.get("auto_recovered", False)),
            "verified": bool(unit["repair_history"].get("verified", False)),
            "repair_history": unit["repair_history"],
        }
        if isinstance(unit.get("root_cause_key"), str):
            history["root_cause_key"] = unit["root_cause_key"]
        histories.append(history)
    return histories


def compact_before_after_units(exhibit: dict[str, Any]) -> list[dict[str, Any]]:
    units = exhibit.get("units")
    if not isinstance(units, list):
        return []
    compacted = []
    for unit in units:
        if not isinstance(unit, dict):
            continue
        detail = {}
        for key in [
            "unit_id",
            "status",
            "baseline",
            "final",
            "oracle_evidence",
            "accepted_patch",
            "patch_log",
            "unsafe_reduction",
            "repair_history",
        ]:
            if key in unit:
                detail[key] = unit[key]
        compacted.append(detail)
    return compacted


def repair_history_rollback_count(history: dict[str, Any]) -> int:
    repair_history = history.get("repair_history")
    if not isinstance(repair_history, dict):
        return 0
    rollback_ids = repair_history.get("rollback_ids")
    if not isinstance(rollback_ids, list):
        return 0
    return sum(1 for rollback_id in rollback_ids if isinstance(rollback_id, str) and rollback_id)


def resolve_workflow_metrics_path(
    summary: dict[str, Any],
    summary_path: Path,
    *,
    repo_root: Path,
) -> Path | None:
    workflow_ref = summary.get("workflow_metrics")
    if not isinstance(workflow_ref, dict) or not workflow_ref.get("path"):
        return None
    return validate_competition_run_summary.resolve_summary_artifact(
        str(workflow_ref["path"]),
        summary_path=summary_path,
        repo_root=repo_root,
    )


def resolve_report_path(binding: Any, *, fallback: Path, repo_root: Path) -> Path | None:
    if isinstance(binding, dict) and binding.get("path"):
        return harness.repo_path(Path(str(binding["path"])), repo_root=repo_root)
    return fallback if fallback.exists() else None


def artifact_ref(path: Path | None, *, repo_root: Path) -> dict[str, Any]:
    if path is None:
        return {"status": "missing"}
    if not path.exists():
        return {"path": harness.repo_relative(path, repo_root=repo_root), "status": "missing"}
    return {
        "path": harness.repo_relative(path, repo_root=repo_root),
        "sha256": harness.sha256_file(path),
        "status": "present",
    }


def load_json_if_exists(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit(f"expected JSON object: {path}")
    return payload


def nonnegative_int(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, parsed)


def summary_semantic_pass_count(summary: dict[str, Any]) -> int:
    slices = summary.get("slices")
    if isinstance(slices, dict):
        return nonnegative_int(slices.get("semantic_pass"))
    return nonnegative_int(summary.get("semantic_pass"))


if __name__ == "__main__":
    raise SystemExit(main())
