from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from .make_dry_run_collect import collect_make_facts


def add_collect_make_parser(commands: Any) -> None:
    collect = commands.add_parser("collect-make-facts")
    collect.add_argument("--repo-root", type=Path, required=True)
    collect.add_argument("--working-directory", default=".")
    collect.add_argument("--makefile", required=True)
    collect.add_argument(
        "--target", dest="targets", action="append", required=True,
    )
    collect.add_argument(
        "--out-root", default="target/project-migration-make-facts",
    )
    collect.add_argument("--timeout-seconds", type=int, default=300)


def run_collect_make_command(args: argparse.Namespace) -> dict[str, Any]:
    return collect_make_facts(
        args.repo_root,
        working_directory=args.working_directory,
        makefile=args.makefile,
        targets=args.targets,
        out_root=args.out_root,
        timeout_seconds=args.timeout_seconds,
    )


__all__ = ["add_collect_make_parser", "run_collect_make_command"]
