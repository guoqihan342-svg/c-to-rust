from __future__ import annotations

import argparse
import json
from pathlib import Path

from .context import build_context_pack
from .provider import DEFAULT_AGENT, DEFAULT_RESOLVED_MODEL, DEFAULT_VARIANT, generate_candidate


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a hash-bound OpenCode Rust candidate")
    parser.add_argument("--slice-spec", required=True, type=Path)
    parser.add_argument("--deterministic-evidence-dir", type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--opencode-command", default="opencode")
    parser.add_argument("--model", default=DEFAULT_RESOLVED_MODEL)
    parser.add_argument("--agent", default=DEFAULT_AGENT)
    parser.add_argument("--variant", default=DEFAULT_VARIANT)
    parser.add_argument("--timeout-seconds", type=int, default=180)
    args = parser.parse_args()
    if args.timeout_seconds < 1 or args.timeout_seconds > 600:
        parser.error("--timeout-seconds must be between 1 and 600")

    context = build_context_pack(
        args.slice_spec,
        deterministic_evidence_dir=args.deterministic_evidence_dir,
    )
    manifest = generate_candidate(
        context,
        out_dir=args.out_dir,
        opencode_command=args.opencode_command,
        resolved_model=args.model,
        agent=args.agent,
        variant=args.variant,
        timeout_seconds=args.timeout_seconds,
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0 if manifest["status"] == "generated" else 2
