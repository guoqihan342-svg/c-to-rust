from __future__ import annotations

from pathlib import Path
import shutil

from .integration_generation import generation_store_root, recover_current_generation


def cleanup_execution_root(root: Path) -> bool:
    try:
        if is_linklike(root):
            return False
        shutil.rmtree(root)
        return not root.exists()
    except OSError:
        return False


def current_managed_source(project: Path) -> Path:
    generation = recover_current_generation(project)
    return generation or project.resolve(strict=True)


def project_target(value: Path) -> Path:
    requested = Path(value).expanduser()
    if requested.name in {"", ".", ".."} or is_linklike(requested):
        raise ValueError("project_root is invalid")
    parent = requested.parent.resolve(strict=True)
    return parent / requested.name


def runtime_root(value: Path, project: Path, source: Path) -> Path:
    requested = Path(value).expanduser()
    if is_linklike(requested):
        raise ValueError("runtime_root must not be a link")
    requested.mkdir(parents=True, exist_ok=True, mode=0o700)
    runtime = requested.resolve(strict=True)
    protected = (project, source, generation_store_root(project))
    if any(_overlaps(runtime, item.resolve()) for item in protected if item.exists()):
        raise ValueError("runtime_root must not overlap managed project state")
    return runtime


def cargo_binary(value: str) -> Path:
    if (
        not isinstance(value, str)
        or value.lower() not in {"cargo", "cargo.exe"}
        or Path(value).name != value
        or any(char in value for char in "\r\n\x00")
    ):
        raise ValueError("cargo_command is invalid")
    resolved = shutil.which(value)
    if not resolved:
        raise ValueError("cargo_command is unavailable")
    path = Path(resolved).resolve(strict=True)
    if (
        path.name.lower() not in {"cargo", "cargo.exe", "rustup", "rustup.exe"}
        or not path.is_file()
    ):
        raise ValueError("cargo_command must resolve to Cargo")
    return path


def is_linklike(path: Path) -> bool:
    is_junction = getattr(path, "is_junction", None)
    return path.is_symlink() or bool(is_junction and is_junction())


def validate_capture_options(
    timeout_seconds: int, *, capture_raw_output: bool,
    capture_native_link_trace: bool, capture_cargo_facts: bool,
    capture_cargo_structure: bool,
) -> None:
    if timeout_seconds < 30 or timeout_seconds > 3_600:
        raise ValueError("timeout_seconds must be between 30 and 3600")
    if capture_native_link_trace and not capture_raw_output:
        raise ValueError("native linker trace requires raw Cargo output capture")
    if capture_cargo_facts and not capture_raw_output:
        raise ValueError("Cargo facts require raw Cargo output capture")
    if capture_cargo_structure and (
        not capture_raw_output or not capture_cargo_facts
    ):
        raise ValueError("Cargo structure requires raw output and Cargo facts")


def _overlaps(left: Path, right: Path) -> bool:
    return left == right or left.is_relative_to(right) or right.is_relative_to(left)


__all__ = [
    "cargo_binary", "cleanup_execution_root", "current_managed_source",
    "is_linklike", "project_target", "runtime_root", "validate_capture_options",
]
