from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import tempfile

from . import cargo_project
from . import integration_validation as validation


CURRENT = "CURRENT"
RECOVERY = "RECOVERY"
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
MAX_POINTER_BYTES = 1_024


class GenerationCommitError(Exception):
    def __init__(self, code: str, preserved: bool):
        super().__init__(code)
        self.code = code
        self.preserved = preserved


def generation_store_root(project_root: Path) -> Path:
    target = Path(project_root)
    return target.parent / f".{target.name}.a19-generations"


def create_generation_stage(project_root: Path) -> Path:
    store = _ensure_store(project_root)
    generations = store / "generations"
    return Path(tempfile.mkdtemp(prefix=".staging.", dir=generations))


def recover_current_generation(project_root: Path) -> Path | None:
    target = Path(project_root)
    store = generation_store_root(target)
    if not store.exists():
        return None
    _trusted_directory(store, "generation_store_untrusted")
    pointer = store / CURRENT
    if not pointer.exists():
        (store / RECOVERY).unlink(missing_ok=True)
        return None
    generation, state = _read_pointer(store)
    generation_state, managed = validation.existing_state(generation)
    if not managed or generation_state != state:
        raise GenerationCommitError("generation_state_mismatch", False)
    try:
        target_state, target_managed = validation.existing_state(target)
    except cargo_project.ProjectInputError:
        target_state, target_managed = "invalid", False
    if not target_managed or target_state != state or (store / RECOVERY).exists():
        try:
            _synchronize_projection(generation, target, store, state)
        except (OSError, cargo_project.ProjectInputError):
            raise GenerationCommitError("generation_recovery_failed", True) from None
    return generation


def publish_generation(stage: Path, project_root: Path, expected_state: str) -> Path:
    target = Path(project_root)
    _assert_current_state(target, expected_state)
    stage_state, managed = validation.existing_state(stage)
    if not managed or SHA256.fullmatch(stage_state) is None:
        raise GenerationCommitError("staged_generation_invalid", True)
    store = _ensure_store(target)
    generations = store / "generations"
    if stage.parent.resolve(strict=True) != generations.resolve(strict=True):
        raise GenerationCommitError("generation_stage_untrusted", True)
    generation = generations / stage_state
    if generation.exists():
        current_state, current_managed = validation.existing_state(generation)
        if not current_managed or current_state != stage_state:
            raise GenerationCommitError("generation_collision", True)
        shutil.rmtree(stage)
    else:
        os.replace(stage, generation)
        _make_read_only(generation)
        _fsync_directory(generations)
    _write_pointer(store, CURRENT, stage_state)
    try:
        _synchronize_projection(generation, target, store, stage_state)
    except (OSError, cargo_project.ProjectInputError):
        raise GenerationCommitError("generation_projection_pending", True) from None
    return generation


def _assert_current_state(target: Path, expected_state: str) -> None:
    store = generation_store_root(target)
    if store.exists():
        _trusted_directory(store, "generation_store_untrusted")
    if (store / CURRENT).exists():
        generation, state = _read_pointer(store)
        actual, managed = validation.existing_state(generation)
        if not managed or actual != state:
            raise GenerationCommitError("generation_state_mismatch", False)
    else:
        actual, _managed = validation.existing_state(target)
    if actual != expected_state:
        raise GenerationCommitError("project_changed_during_integration", True)


def _ensure_store(project_root: Path) -> Path:
    store = generation_store_root(project_root)
    if store.exists():
        _trusted_directory(store, "generation_store_untrusted")
    else:
        store.mkdir(mode=0o700)
    generations = store / "generations"
    if generations.exists():
        _trusted_directory(generations, "generation_store_untrusted")
    else:
        generations.mkdir(mode=0o700)
    return store


def _trusted_directory(path: Path, code: str) -> None:
    if _is_linklike(path) or not path.is_dir():
        raise GenerationCommitError(code, False)


def _read_pointer(store: Path) -> tuple[Path, str]:
    pointer = store / CURRENT
    if _is_linklike(pointer):
        raise GenerationCommitError("generation_pointer_untrusted", False)
    try:
        raw = validation.read_bounded(pointer, MAX_POINTER_BYTES)
        payload = json.loads(raw.decode("ascii"))
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
        raise GenerationCommitError("generation_pointer_invalid", False) from None
    if (
        raw != cargo_project.canonical_json_bytes(payload)
        or set(payload) != {"generation", "schema_version"}
        or payload.get("schema_version") != 1
        or not isinstance(payload.get("generation"), str)
        or SHA256.fullmatch(payload["generation"]) is None
    ):
        raise GenerationCommitError("generation_pointer_invalid", False)
    generation = store / "generations" / payload["generation"]
    if _is_linklike(generation):
        raise GenerationCommitError("generation_untrusted", False)
    try:
        resolved = generation.resolve(strict=True)
        resolved.relative_to((store / "generations").resolve(strict=True))
    except (OSError, ValueError):
        raise GenerationCommitError("generation_missing", False) from None
    if not resolved.is_dir():
        raise GenerationCommitError("generation_untrusted", False)
    return resolved, payload["generation"]


def _write_pointer(store: Path, name: str, generation: str) -> None:
    data = cargo_project.canonical_json_bytes({
        "generation": generation,
        "schema_version": 1,
    })
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{name}.", dir=store)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, store / name)
        _fsync_directory(store)
    finally:
        temporary.unlink(missing_ok=True)


def _synchronize_projection(
    generation: Path, target: Path, store: Path, state: str,
) -> None:
    projection = Path(tempfile.mkdtemp(prefix=f".{target.name}.projection.", dir=target.parent))
    try:
        _copy_tree(generation, projection)
        projected_state, managed = validation.existing_state(projection)
        if not managed or projected_state != state:
            raise OSError("projection validation failed")
        _write_pointer(store, RECOVERY, state)
        if target.exists():
            if _is_linklike(target) or not target.is_dir():
                raise OSError("project target is untrusted")
            shutil.rmtree(target)
        os.replace(projection, target)
        _fsync_directory(target.parent)
        (store / RECOVERY).unlink(missing_ok=True)
        _fsync_directory(store)
    finally:
        if projection.exists():
            shutil.rmtree(projection, ignore_errors=True)


def _copy_tree(source: Path, target: Path) -> None:
    for directory, directories, filenames in os.walk(source, followlinks=False):
        base = Path(directory)
        if any(_is_linklike(base / name) for name in directories + filenames):
            raise OSError("generation links are forbidden")
        relative = base.relative_to(source)
        destination = target / relative
        destination.mkdir(parents=True, exist_ok=True)
        for filename in filenames:
            output = destination / filename
            shutil.copyfile(base / filename, output)
            output.chmod(0o600)


def _make_read_only(root: Path) -> None:
    directories = []
    for directory, _names, filenames in os.walk(root, followlinks=False):
        base = Path(directory)
        directories.append(base)
        for filename in filenames:
            (base / filename).chmod(0o400)
    for directory in reversed(directories):
        directory.chmod(0o500)


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _is_linklike(path: Path) -> bool:
    is_junction = getattr(path, "is_junction", None)
    return path.is_symlink() or bool(is_junction and is_junction())


__all__ = [
    "GenerationCommitError",
    "create_generation_stage",
    "generation_store_root",
    "publish_generation",
    "recover_current_generation",
]
