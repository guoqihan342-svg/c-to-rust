from __future__ import annotations

from pathlib import Path
from typing import Any

from . import project_cli_runtime
from .artifacts import write_json_artifact
from .project_test_target_proposal import build_project_test_target_proposal


def run_prepare_make_test_target_proposal(
    args: Any, *, harness_root: Path,
) -> dict[str, Any]:
    payload = build_project_test_target_proposal(
        target=args.target, provider=args.provider, model=args.model,
        prompt_sha256=args.prompt_sha256,
        response_sha256=args.response_sha256,
    )
    out_rel = project_cli_runtime.target_relative(
        args.out_root, "proposal-out-root", repo_root=harness_root,
    )
    output = project_cli_runtime.target_path(
        args.out_root, "proposal-out-root", repo_root=harness_root,
    )
    reference = write_json_artifact(
        output, "project-test-target-proposal.json", payload,
    )
    proposal_path = f"{out_rel}/{reference['path']}"
    return {
        "schema_version": 1, "status": "materialized",
        "artifact_kind": "project-test-target-proposal-materialization",
        "proposal": {**reference, "path": proposal_path},
        "migrate_arguments": [
            "--project-test-target-proposal", proposal_path,
            "--project-test-target-proposal-sha256", reference["sha256"],
            "--project-test-target-proposal-size-bytes",
            str(reference["size_bytes"]),
        ],
        "semantic_gate": False,
    }


__all__ = ["run_prepare_make_test_target_proposal"]
