#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from validation.tools._validate_ai_exact_evidence_parts import validate_evidence
from validation.tools._validate_ai_exact_evidence_parts.io import EvidenceError


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate independent AI exact evidence.")
    parser.add_argument("--target-id", required=True)
    parser.add_argument("--slice-id", required=True)
    parser.add_argument("--evidence-root", required=True, type=Path)
    parser.add_argument("--require-semantic-pass", action="store_true")
    args = parser.parse_args()
    try:
        report = validate_evidence(
            target_id=args.target_id,
            slice_id=args.slice_id,
            evidence_root=args.evidence_root,
            require_semantic_pass=args.require_semantic_pass,
        )
    except EvidenceError as error:
        report = {
            "schema_version": 1,
            "status": "failed",
            "target_id": args.target_id,
            "slice_id": args.slice_id,
            "semantic_pass": False,
            "errors": [{"code": error.code, "path": error.path, "message": str(error)}],
        }
        print(json.dumps(report, indent=2, sort_keys=True))
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
