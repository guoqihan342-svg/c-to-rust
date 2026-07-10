from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from validation.tools._translation_carrier_reporter import emit_reports
from validation.tools._translation_carrier_reporter.contract import ReporterError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Emit accepted reports for a declared exact-fragment translation carrier."
    )
    parser.add_argument("--slice-spec", type=Path, required=True)
    parser.add_argument("--auto-evidence-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    try:
        paths = emit_reports(
            slice_spec=args.slice_spec,
            auto_evidence_dir=args.auto_evidence_dir,
            output_dir=args.output_dir,
            repo_root=args.repo_root,
        )
    except (ReporterError, OSError, ValueError) as exc:
        print(f"translation-carrier-reporter: {exc}", file=sys.stderr)
        return 2
    for name, path in paths.items():
        print(f"{name}={path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
