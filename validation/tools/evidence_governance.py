#!/usr/bin/env python3
"""Report evidence portability, cost, and retention metadata.

The report is intentionally non-destructive. It inventories evidence artifacts
and flags reproducibility risks, but it does not prune or rewrite historical
evidence.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
import re
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EVIDENCE_ROOT = Path("validation/evidence")
POLICY_TIERS = ("dev", "ci", "release")
PATH_LIKE_KEYS = {
    "path",
    "fixture_path",
    "manifest",
    "source_manifest",
    "evidence_root",
    "slice_spec",
}
CLAIM_ANCHOR_SEGMENTS = {
    "evidence",
    "source_artifacts",
    "artifact_refs",
    "artifact_paths",
    "generated_artifacts",
    "dependent_artifacts",
    "accepted_paths",
    "paths",
    "source_boundary",
}
DIAGNOSTIC_SEGMENTS = {
    "diagnostics",
    "diagnostic",
    "metadata",
    "lowering_report",
    "arguments",
    "command",
    "commands",
    "stdout",
    "stderr",
    "log_excerpt",
    "host",
    "environment",
    "reference_tree",
    "selected_command",
    "worker_result_sources",
}
DIAGNOSTIC_KEYS = {
    "clang_path",
    "source_root",
    "source_file",
    "working_directory",
    "observed_libclang_path",
}
ABSOLUTE_PATH_RE = re.compile(
    r"^([A-Za-z]:[\\/]|/[A-Za-z0-9_.-]|\\\\|/mnt/[A-Za-z]/|/tmp/|/var/tmp/|/private/tmp/)"
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--evidence-root", type=Path, default=DEFAULT_EVIDENCE_ROOT)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--policy-tier",
        choices=POLICY_TIERS,
        default="dev",
        help="Read-only evidence retention policy tier to evaluate: dev, ci, or release.",
    )
    args = parser.parse_args(argv)

    report = build_report(args.repo_root, evidence_root=args.evidence_root, policy_tier=args.policy_tier)
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        output = args.output if args.output.is_absolute() else args.repo_root / args.output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if report["status"] == "passed" else 1


def build_report(
    repo_root: Path,
    *,
    evidence_root: Path = DEFAULT_EVIDENCE_ROOT,
    policy_tier: str = "dev",
) -> dict[str, Any]:
    if policy_tier not in POLICY_TIERS:
        raise ValueError(f"policy_tier must be one of {', '.join(POLICY_TIERS)}")
    repo_root = repo_root.resolve()
    evidence_dir = evidence_root if evidence_root.is_absolute() else repo_root / evidence_root
    inventory = build_inventory(repo_root, evidence_dir)
    portability = build_portability_report(repo_root, evidence_dir)
    failed_gates = []
    if portability["claim_anchor_issue_count"] or portability["profile_hash_issue_count"]:
        failed_gates.append("evidence_portability")
    policy_compliance = build_policy_compliance(policy_tier, portability=portability, inventory=inventory)
    if policy_compliance["status"] != "passed":
        failed_gates.append("evidence_policy_compliance")
    return {
        "schema_version": 1,
        "status": "passed" if not failed_gates else "failed",
        "evidence_root": rel_or_posix(repo_root, evidence_dir),
        "failed_gates": failed_gates,
        "policy_compliance": policy_compliance,
        "portability": portability,
        "inventory": inventory,
    }


def build_policy_compliance(
    policy_tier: str,
    *,
    portability: dict[str, Any],
    inventory: dict[str, Any],
) -> dict[str, Any]:
    gates: list[dict[str, Any]] = []

    def add_gate(name: str, passed: bool, **details: Any) -> None:
        gates.append(
            {
                "name": name,
                "status": "passed" if passed else "failed",
                **details,
            }
        )

    add_gate(
        "portability",
        portability.get("status") == "passed",
        claim_anchor_issue_count=int(portability.get("claim_anchor_issue_count", 0)),
        profile_hash_issue_count=int(portability.get("profile_hash_issue_count", 0)),
    )

    if policy_tier in {"ci", "release"}:
        pipelines = inventory.get("pipelines") if isinstance(inventory.get("pipelines"), list) else []
        retention_policy = inventory.get("retention_policy") if isinstance(inventory.get("retention_policy"), dict) else {}
        missing_metadata = [
            str(pipeline.get("pipeline_id", "<unknown>"))
            for pipeline in pipelines
            if not pipeline.get("retention_class")
            or not pipeline.get("compression_policy")
            or not pipeline.get("prune_policy")
        ]
        add_gate(
            "retention_metadata",
            bool(retention_policy) and not missing_metadata,
            pipeline_count=len(pipelines),
            missing_pipeline_count=len(missing_metadata),
            missing_pipelines=missing_metadata[:10],
        )

    if policy_tier == "release":
        diagnostic_count = int(portability.get("diagnostic_host_metadata_count", 0))
        add_gate(
            "diagnostic_host_metadata",
            diagnostic_count == 0,
            diagnostic_host_metadata_count=diagnostic_count,
        )

    failed_gate_names = [gate["name"] for gate in gates if gate["status"] != "passed"]
    return {
        "policy_tier": policy_tier,
        "status": "passed" if not failed_gate_names else "failed",
        "failed_gates": failed_gate_names,
        "gates": gates,
    }


def build_inventory(repo_root: Path, evidence_dir: Path) -> dict[str, Any]:
    files = sorted(path for path in evidence_dir.rglob("*") if path.is_file()) if evidence_dir.exists() else []
    class_counts: Counter[str] = Counter()
    class_bytes: Counter[str] = Counter()
    largest_files = []
    runtime_ms_observations = []
    total_bytes = 0

    for path in files:
        size = path.stat().st_size
        total_bytes += size
        retention_class = retention_class_for(path.relative_to(evidence_dir), evidence_dir=evidence_dir)
        class_counts[retention_class] += 1
        class_bytes[retention_class] += size
        largest_files.append(
            {
                "path": rel_or_posix(repo_root, path),
                "bytes": size,
                "retention_class": retention_class,
            }
        )
        for _, payload in structured_payloads(path):
            runtime_ms_observations.extend(find_duration_ms(payload))

    largest_files.sort(key=lambda item: item["bytes"], reverse=True)
    return {
        "file_count": len(files),
        "total_bytes": total_bytes,
        "retention_classes": {
            name: {"file_count": class_counts[name], "total_bytes": class_bytes[name]}
            for name in sorted(class_counts)
        },
        "pipelines": build_pipeline_inventory(repo_root, evidence_dir, files),
        "candidate_generation": build_candidate_generation_inventory(files),
        "runtime": {
            "observation_count": len(runtime_ms_observations),
            "total_duration_ms": sum(runtime_ms_observations),
            "max_duration_ms": max(runtime_ms_observations) if runtime_ms_observations else 0,
        },
        "largest_files": largest_files[:10],
        "retention_policy": {
            "compression_policy": "compress large diagnostic_only logs first; keep JSON release evidence text-readable",
            "prune_policy": "diagnostic_only may be pruned after replacement evidence is recorded; committed_release requires milestone review",
            "classes": {
                "committed_release": "release-required evidence kept with artifact hashes",
                "ci_smoke": "short-lived CI evidence that may be regenerated",
                "diagnostic_only": "debug logs and host-local diagnostics; not claim anchors",
                "historical_archive": "older or broad catalogue evidence retained for audit only",
            },
        },
    }


def build_pipeline_inventory(repo_root: Path, evidence_dir: Path, files: list[Path]) -> list[dict[str, Any]]:
    grouped: dict[Path, list[Path]] = {}
    for path in files:
        grouped.setdefault(pipeline_root_for(evidence_dir, path), []).append(path)

    pipelines = []
    for pipeline_root, pipeline_files in sorted(grouped.items()):
        relative_pipeline = pipeline_root.relative_to(evidence_dir)
        total_bytes = sum(path.stat().st_size for path in pipeline_files)
        durations = []
        for path in pipeline_files:
            for _, payload in structured_payloads(path):
                durations.extend(find_duration_ms(payload))
        retention_counts = Counter(
            retention_class_for(path.relative_to(evidence_dir), evidence_dir=evidence_dir)
            for path in pipeline_files
        )
        retention_class = retention_counts.most_common(1)[0][0]
        pipeline = {
            "pipeline_id": rel_or_posix(repo_root, pipeline_root),
            "artifact_count": len(pipeline_files),
            "total_bytes": total_bytes,
            "runtime_ms": max(durations) if durations else None,
            "retention_class": retention_class,
            "compression_policy": compression_policy_for(retention_class),
            "prune_policy": prune_policy_for(retention_class),
            "report_artifacts": report_artifacts_for(repo_root, pipeline_files),
        }
        pipeline.update(pipeline_identity(relative_pipeline))
        pipelines.append(pipeline)
    return pipelines


def report_artifacts_for(repo_root: Path, pipeline_files: list[Path]) -> list[str]:
    report_names = []
    for path in sorted(pipeline_files):
        name = path.name.lower()
        if (
            name in {"summary.json", "events.jsonl"}
            or "report" in name
            or name.endswith("-manifest.json")
        ):
            report_names.append(rel_or_posix(repo_root, path))
    return report_names


def build_candidate_generation_inventory(files: list[Path]) -> dict[str, Any]:
    route_files = [path for path in files if path.name.endswith("-route-decision.json")]
    by_kind: dict[str, Counter[str]] = {}
    by_role: Counter[str] = Counter()
    selected_candidate_count = 0
    candidate_record_count = 0

    for path in route_files:
        payload = load_structured_payload(path)
        if not isinstance(payload, dict):
            continue
        generation = payload.get("candidate_generation")
        if not isinstance(generation, dict):
            continue
        selected_candidate_id = generation.get("selected_candidate_id")
        if selected_candidate_id:
            selected_candidate_count += 1
        candidate_set = generation.get("candidate_set")
        if not isinstance(candidate_set, list):
            continue
        for candidate in candidate_set:
            if not isinstance(candidate, dict):
                continue
            candidate_record_count += 1
            kind = str(candidate.get("kind", "unknown"))
            role = str(candidate.get("role", "unknown"))
            by_role[role] += 1
            counters = by_kind.setdefault(kind, Counter())
            counters["candidate_count"] += 1
            if candidate.get("compatibility_only") is True:
                counters["compatibility_only_count"] += 1
            if candidate.get("candidate_id") == selected_candidate_id:
                counters["selected_count"] += 1
            status = str(candidate.get("status", "unknown"))
            counters[f"status:{status}"] += 1

    return {
        "route_decision_artifact_count": len(route_files),
        "candidate_record_count": candidate_record_count,
        "selected_candidate_count": selected_candidate_count,
        "compatibility_only_candidate_count": sum(
            counters.get("compatibility_only_count", 0) for counters in by_kind.values()
        ),
        "by_kind": {
            kind: {key: counters[key] for key in sorted(counters)}
            for kind, counters in sorted(by_kind.items())
        },
        "by_role": {role: by_role[role] for role in sorted(by_role)},
    }


def pipeline_root_for(evidence_dir: Path, path: Path) -> Path:
    relative = path.relative_to(evidence_dir)
    parts = relative.parts
    if len(parts) >= 3 and parts[1] == "auto-translation":
        return evidence_dir.joinpath(*parts[:3])
    if len(parts) >= 2:
        return evidence_dir / parts[0]
    return evidence_dir


def pipeline_identity(relative_pipeline: Path) -> dict[str, Any]:
    parts = relative_pipeline.parts
    identity: dict[str, Any] = {}
    if len(parts) >= 3 and parts[1] == "auto-translation":
        identity["target_id"] = parts[0]
        identity["slice_id"] = parts[2]
    elif parts:
        identity["target_id"] = parts[0]
        identity["slice_id"] = None
    return identity


def compression_policy_for(retention_class: str) -> str:
    if retention_class == "committed_release":
        return "do_not_compress_claim_anchors"
    if retention_class == "diagnostic_only":
        return "compress_when_large_or_superseded"
    return "text_json_kept_uncompressed_by_default"


def prune_policy_for(retention_class: str) -> str:
    if retention_class == "committed_release":
        return "do_not_prune_without_manifest_update"
    if retention_class == "diagnostic_only":
        return "may_prune_after_replacement_evidence"
    if retention_class == "ci_smoke":
        return "may_prune_after_ci_retention_window"
    return "do_not_prune_without_archive_review"


def build_portability_report(repo_root: Path, evidence_dir: Path) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    profile_hash_issues: list[dict[str, Any]] = []
    diagnostic_host_metadata: list[dict[str, Any]] = []

    for path in sorted(evidence_dir.rglob("*")) if evidence_dir.exists() else []:
        if not path.is_file():
            continue
        payloads = structured_payloads(path)
        for payload_label, payload in payloads:
            scan_payload(
                repo_root=repo_root,
                artifact_path=path,
                payload_label=payload_label,
                node=payload,
                json_path="$",
                segments=[],
                evidence_dir=evidence_dir,
                issues=issues,
                profile_hash_issues=profile_hash_issues,
                diagnostic_host_metadata=diagnostic_host_metadata,
            )

    return {
        "status": "passed" if not issues and not profile_hash_issues else "failed",
        "claim_anchor_issue_count": len(issues),
        "profile_hash_issue_count": len(profile_hash_issues),
        "diagnostic_host_metadata_count": len(diagnostic_host_metadata),
        "issues": issues,
        "profile_hash_issues": profile_hash_issues,
        "diagnostic_host_metadata": diagnostic_host_metadata[:50],
    }


def scan_payload(
    *,
    repo_root: Path,
    artifact_path: Path,
    payload_label: str,
    node: Any,
    json_path: str,
    segments: list[str],
    evidence_dir: Path,
    issues: list[dict[str, Any]],
    profile_hash_issues: list[dict[str, Any]],
    diagnostic_host_metadata: list[dict[str, Any]],
) -> None:
    if isinstance(node, dict):
        if looks_like_competition_profile_ref(segments, node) and not node.get("sha256"):
            profile_hash_issues.append(
                {
                    "code": "missing_profile_hash",
                    "artifact": rel_or_posix(repo_root, artifact_path),
                    "payload": payload_label,
                    "json_path": json_path,
                    "profile_id": node.get("profile_id"),
                    "path": node.get("path"),
                }
            )
        for key, value in node.items():
            scan_payload(
                repo_root=repo_root,
                artifact_path=artifact_path,
                payload_label=payload_label,
                node=value,
                json_path=f"{json_path}.{key}",
                segments=[*segments, str(key)],
                evidence_dir=evidence_dir,
                issues=issues,
                profile_hash_issues=profile_hash_issues,
                diagnostic_host_metadata=diagnostic_host_metadata,
            )
        return
    if isinstance(node, list):
        for index, value in enumerate(node):
            scan_payload(
                repo_root=repo_root,
                artifact_path=artifact_path,
                payload_label=payload_label,
                node=value,
                json_path=f"{json_path}[{index}]",
                segments=[*segments, "[]"],
                evidence_dir=evidence_dir,
                issues=issues,
                profile_hash_issues=profile_hash_issues,
                diagnostic_host_metadata=diagnostic_host_metadata,
            )
        return
    if isinstance(node, str) and is_absolute_or_temp_path(node):
        record = {
            "artifact": rel_or_posix(repo_root, artifact_path),
            "payload": payload_label,
            "json_path": json_path,
            "value": node,
        }
        if is_claim_anchor_path(segments, evidence_dir=evidence_dir):
            issues.append({"code": "absolute_claim_anchor_path", **record})
        else:
            diagnostic_host_metadata.append({"code": "diagnostic_host_metadata_path", **record})


def structured_payloads(path: Path) -> list[tuple[str, Any]]:
    if path.suffix == ".json":
        payload = load_structured_payload(path)
        return [("json", payload)] if payload is not None else []
    if path.suffix == ".jsonl":
        payloads = []
        for line_no, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                payloads.append((f"jsonl:{line_no}", json.loads(line)))
            except json.JSONDecodeError:
                continue
        return payloads
    return []


def load_structured_payload(path: Path) -> Any | None:
    if path.suffix != ".json":
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None


def find_duration_ms(node: Any) -> list[int]:
    values = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "duration_ms" and isinstance(value, int):
                values.append(value)
            else:
                values.extend(find_duration_ms(value))
    elif isinstance(node, list):
        for value in node:
            values.extend(find_duration_ms(value))
    return values


def retention_class_for(relative_path: Path, *, evidence_dir: Path | None = None) -> str:
    parts = set(relative_path.parts)
    name = relative_path.name.lower()
    if is_full_regression_root(evidence_dir):
        return "ci_smoke"
    if name.endswith(".log") or "stdout" in name or "stderr" in name or "diagnostic" in parts:
        return "diagnostic_only"
    if "ci-smoke" in parts or "ci_smoke" in parts:
        return "ci_smoke"
    if "auto-translation" in parts:
        return "committed_release"
    return "historical_archive"


def is_full_regression_root(evidence_dir: Path | None) -> bool:
    if evidence_dir is None:
        return False
    parts = {part.lower() for part in evidence_dir.parts}
    return evidence_dir.name.lower() == "full-regression" or (
        "target" in parts and "full-regression" in parts
    )


def is_claim_anchor_path(segments: list[str], *, evidence_dir: Path | None = None) -> bool:
    leaf = segments[-1] if segments else ""
    if is_full_regression_root(evidence_dir) and leaf in {
        "evidence_root",
        "events",
        "log",
        "working_directory",
    }:
        return False
    if leaf in DIAGNOSTIC_KEYS:
        return False
    if any(segment in DIAGNOSTIC_SEGMENTS for segment in segments):
        return False
    return leaf in PATH_LIKE_KEYS or any(segment in CLAIM_ANCHOR_SEGMENTS for segment in segments)


def looks_like_competition_profile_ref(segments: list[str], node: dict[str, Any]) -> bool:
    if "competition_environment" in segments or "competition_environment_identity" in segments:
        return True
    if node.get("profile_id") == "huawei-competition-ubuntu-24.04":
        return True
    return node.get("path") == "config/competition-env/environment.json"


def is_absolute_or_temp_path(value: str) -> bool:
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", value):
        return False
    return bool(ABSOLUTE_PATH_RE.match(value))


def rel_or_posix(repo_root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root).as_posix()
    except ValueError:
        return path.as_posix()


if __name__ == "__main__":
    sys.exit(main())
