#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from validation.tools._project_migration_harness.held_out_acceptance import (
    HeldOutContractError,
    run_acceptance_suite,
    validate_manifest,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run a finite, hash-bound held-out project acceptance contract."
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--mode", choices=("offline-contract", "real-projects"), required=True)
    parser.add_argument("--out-root", default="target/project-migration-held-out")
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    try:
        manifest_path = args.manifest.resolve(strict=True)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        if not isinstance(manifest, dict):
            raise HeldOutContractError("manifest must be a JSON object")
        if args.validate_only:
            validated = validate_manifest(
                manifest, manifest_dir=manifest_path.parent,
                harness_root=REPO_ROOT, mode=args.mode,
            )
            result = {
                "schema_version": 1, "status": "contract_validated",
                "suite_id": validated["suite_id"], "mode": args.mode,
                "project_count": validated["project_count"],
                "construct_family_count": len(validated["construct_families"]),
                "held_out_project_count": validated["held_out_project_count"],
                "claim_boundary": {"semantic_gate": False, "translation_coverage_numerator": 0},
            }
        else:
            result = run_acceptance_suite(
                manifest, manifest_dir=manifest_path.parent, harness_root=REPO_ROOT,
                mode=args.mode, out_root=args.out_root,
            )
    except (HeldOutContractError, OSError, ValueError, json.JSONDecodeError) as error:
        result = {"schema_version": 1, "status": "rejected", "error": str(error)}
    text = json.dumps(result, indent=2, sort_keys=True)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if result["status"] in {"contract_validated", "contract_passed", "acceptance_passed"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
