from __future__ import annotations

import json
from pathlib import Path

from validation.tools._project_migration_harness.artifacts import (
    write_json_artifact,
)
from validation.tools._project_migration_harness.build_ir_projection import (
    project_build_ir,
)
from validation.tools._project_migration_harness.discovery import discover_project
from validation.tools._project_migration_harness.generated_closure import (
    verify_generated_build_closure,
)


def materialize_native_build_ir(
    base: Path, name: str, external_arguments: str,
) -> tuple[Path, Path, dict, dict]:
    root = base / name
    root.mkdir()
    source = _write(root, "src/unit.c", "int unit(void) { return 1; }\n")
    _write(root, "build/unit.o", b"object")
    _write(root, "build/program", b"program")
    _write(
        root,
        "build/CMakeFiles/sample.dir/link.txt",
        f"clang unit.o {external_arguments} -o program\n",
    )
    database = _write(
        root,
        "build/compile_commands.json",
        json.dumps([{
            "directory": str(root / "build"),
            "file": str(source),
            "arguments": ["clang", "-c", str(source), "-o", "unit.o"],
            "output": "unit.o",
        }]),
    )
    discovery = discover_project(root, compile_database=database)
    closure = discovery["generated_build_closure"]
    verification = verify_generated_build_closure(root, closure)
    output = base / f"{name}-out"
    output.mkdir()
    refs = [
        {"role": role, **write_json_artifact(output, relative, payload)}
        for role, relative, payload in (
            ("discovery", "plan/discovery.json", discovery),
            ("generated-build-closure", "plan/closure.json", closure),
            (
                "generated-build-closure-verification",
                "plan/verification.json",
                verification,
            ),
        )
    ]
    build_ir = project_build_ir(discovery, closure, verification, refs)
    reference = write_json_artifact(base, f"facts/{name}.json", build_ir)
    return root, database, build_ir, reference


def _write(root: Path, relative: str, value: str | bytes) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value if isinstance(value, bytes) else value.encode("utf-8"))
    return path


__all__ = ["materialize_native_build_ir"]
