#!/usr/bin/env python3
"""Extract one deterministic FunctionDecl fixture from clang AST JSON."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any


VOLATILE_AST_FIELDS = {"id", "loc", "range", "typeAliasDeclId"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--clang", default="clang")
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--function", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--include", action="append", default=[], type=Path)
    parser.add_argument("--define", action="append", default=[])
    parser.add_argument("--std", default="c11")
    return parser.parse_args()


def function_definitions(node: Any, function_name: str) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    if isinstance(node, dict):
        children = node.get("inner", [])
        if (
            node.get("kind") == "FunctionDecl"
            and node.get("name") == function_name
            and any(
                isinstance(child, dict) and child.get("kind") == "CompoundStmt"
                for child in children
            )
        ):
            matches.append(node)
        for child in children:
            matches.extend(function_definitions(child, function_name))
    elif isinstance(node, list):
        for child in node:
            matches.extend(function_definitions(child, function_name))
    return matches


def normalized_ast(node: Any) -> Any:
    if isinstance(node, dict):
        return {
            key: normalized_ast(value)
            for key, value in node.items()
            if key not in VOLATILE_AST_FIELDS
        }
    if isinstance(node, list):
        return [normalized_ast(value) for value in node]
    return node


def main() -> int:
    args = parse_args()
    command = [
        args.clang,
        f"-std={args.std}",
        *(f"-I{path}" for path in args.include),
        *(f"-D{define}" for define in args.define),
        "-Xclang",
        "-ast-dump=json",
        "-fsyntax-only",
        str(args.source),
    ]
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    if completed.returncode != 0:
        raise SystemExit(
            "clang AST dump failed\n"
            f"command={json.dumps(command)}\n"
            f"stderr={completed.stderr}"
        )

    ast = json.loads(completed.stdout)
    matches = function_definitions(ast, args.function)
    if len(matches) != 1:
        raise SystemExit(
            f"expected exactly one definition for {args.function}, found {len(matches)}"
        )

    fixture = {
        "kind": "TranslationUnitDecl",
        "inner": [normalized_ast(matches[0])],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(fixture, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "status": "written",
                "function": args.function,
                "output": args.output.as_posix(),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
