from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import Any

from .errors import ReporterError
from .source_binding import StaticContext


def run_command(argv: list[str], *, aliases: dict[str, str]) -> dict[str, Any]:
    try:
        completed = subprocess.run(argv, capture_output=True, check=False, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ReporterError(f"negative replay command failed to execute: {exc}") from exc
    return {
        "argv": [stable_text(item, aliases) for item in argv],
        "returncode": completed.returncode,
        "stdout": stable_bytes(completed.stdout, aliases),
        "stderr": stable_bytes(completed.stderr, aliases),
    }


def stable_text(value: str, aliases: dict[str, str]) -> str:
    stable = value
    for source, replacement in sorted(aliases.items(), key=lambda item: len(item[0]), reverse=True):
        variants = {source, source.replace("\\", "/"), source.replace("/", "\\")}
        for variant in variants:
            if variant:
                stable = stable.replace(variant, replacement)
    return stable


def stable_bytes(value: bytes, aliases: dict[str, str]) -> bytes:
    stable = stable_text(value.decode("utf-8", errors="replace"), aliases)
    return (stable.rstrip("\r\n") + ("\n" if stable else "")).encode("utf-8")


def add_command_artifacts(
    artifacts: dict[Path, bytes], artifact_dir: Path, stem: str, result: dict[str, Any]
) -> None:
    artifacts[artifact_dir / f"{stem}.stdout.log"] = result["stdout"]
    artifacts[artifact_dir / f"{stem}.stderr.log"] = result["stderr"]


def command_summary(
    context: StaticContext,
    artifact_dir: Path,
    stem: str,
    compile_result: dict[str, Any],
    run_result: dict[str, Any],
    *,
    expected_run_failure: bool,
) -> dict[str, Any]:
    return {
        "compile": command_result_summary(
            context, artifact_dir, f"{stem}-compile", compile_result
        ),
        "run": command_result_summary(context, artifact_dir, f"{stem}-run", run_result),
        "expected_run_failure": expected_run_failure,
    }


def command_result_summary(
    context: StaticContext, artifact_dir: Path, stem: str, result: dict[str, Any]
) -> dict[str, Any]:
    stdout = result["stdout"]
    stderr = result["stderr"]
    return {
        "argv": result["argv"],
        "returncode": result["returncode"],
        "stdout": content_ref(context.repo_root, artifact_dir / f"{stem}.stdout.log", stdout),
        "stderr": content_ref(context.repo_root, artifact_dir / f"{stem}.stderr.log", stderr),
    }


def path_ref(root: Path, path: Path, sha256: str) -> dict[str, Any]:
    return {"path": path.resolve().relative_to(root).as_posix(), "sha256": sha256}


def content_ref(root: Path, path: Path, content: bytes) -> dict[str, Any]:
    return {
        "path": path.resolve().relative_to(root).as_posix(),
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def ensure_contained(root: Path, path: Path, label: str) -> None:
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ReporterError(f"{label} escapes repo root") from exc
