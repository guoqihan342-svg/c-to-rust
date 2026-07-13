from __future__ import annotations

import os
import re
import shutil
import stat
from pathlib import Path
from typing import Mapping

from . import cargo_project
from . import integration
from . import integration_generation as generations
from . import integration_validation as validation


_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def trusted_candidate_root(value: Path) -> Path:
    path = Path(value).expanduser()
    if _path_linklike(path):
        _fail("candidate_root_untrusted", "filesystem")
    try:
        root = path.resolve(strict=True)
    except OSError:
        _fail("candidate_root_invalid", "filesystem")
    if not root.is_dir():
        _fail("candidate_root_invalid", "filesystem")
    return root


def detached_root(value: Path, candidates: Path) -> Path:
    requested = Path(value).expanduser()
    if requested.name in {"", ".", ".."}:
        _fail("quarantine_root_invalid", "filesystem")
    if _path_linklike(requested.parent):
        _fail("quarantine_root_untrusted", "filesystem")
    try:
        parent = requested.parent.resolve(strict=True)
    except OSError:
        _fail("quarantine_root_invalid", "filesystem")
    target = parent / requested.name
    if present(target):
        if _linklike(target) or not target.is_dir():
            _fail("quarantine_root_untrusted", "filesystem")
        target = target.resolve(strict=True)
    if (
        target == candidates
        or target.is_relative_to(candidates)
        or candidates.is_relative_to(target)
    ):
        _fail("quarantine_root_overlaps_candidates", "filesystem")
    return target


def ensure_store(root: Path) -> Path:
    if present(root):
        if _linklike(root) or not root.is_dir():
            _fail("quarantine_root_untrusted", "filesystem")
        if any(item.name != "generations" for item in root.iterdir()):
            _fail("quarantine_root_not_dedicated", "filesystem")
    else:
        root.mkdir(mode=0o700)
        generations._fsync_directory(root.parent)
    store = root / "generations"
    if present(store):
        if _linklike(store) or not store.is_dir():
            _fail("quarantine_store_untrusted", "filesystem")
    else:
        store.mkdir(mode=0o700)
        generations._fsync_directory(root)
    return store


def write_stage(stage: Path, files: Mapping[str, bytes]) -> None:
    integration._write_stage(stage, files)
    directories = {stage}
    for relative in files:
        path = stage.joinpath(*validation.generated_path(relative).parts)
        directories.update(
            parent for parent in path.parents
            if parent == stage or stage in parent.parents
        )
    for directory in sorted(
        directories, key=lambda item: len(item.parts), reverse=True,
    ):
        generations._fsync_directory(directory)


def publish(
    stage: Path, store: Path, state: str, files: Mapping[str, bytes],
) -> Path:
    generation = store / state
    if present(generation):
        verify_generation(generation, files, "quarantine_generation_collision")
        remove_tree(stage)
        return generation
    generations._make_read_only(stage)
    try:
        os.replace(stage, generation)
    except OSError:
        if not present(generation):
            raise
        verify_generation(generation, files, "quarantine_generation_collision")
        remove_tree(stage)
        return generation
    generations._fsync_directory(store)
    verify_generation(generation, files, "quarantine_publish_invalid")
    return generation


def verify_generation(root: Path, files: Mapping[str, bytes], code: str) -> str:
    try:
        _assert_no_links(root, code)
        state, managed = validation.existing_state(root)
        expected = validation.digest(files[cargo_project.LAST_GOOD_MANIFEST])
        if not managed or state != expected or _SHA256.fullmatch(state) is None:
            raise ValueError
        for relative, data in files.items():
            path = root.joinpath(*validation.generated_path(relative).parts)
            if validation.read_bounded(path, len(data)) != data:
                raise ValueError
        return state
    except (OSError, ValueError, cargo_project.ProjectInputError):
        _fail(code, "generation_publish")


def present(path: Path) -> bool:
    return path.exists() or path.is_symlink()


def remove_tree(root: Path) -> None:
    if not present(root):
        return
    for directory, directories, filenames in os.walk(root, followlinks=False):
        base = Path(directory)
        base.chmod(0o700)
        for name in directories:
            (base / name).chmod(0o700)
        for name in filenames:
            (base / name).chmod(0o600)
    shutil.rmtree(root, ignore_errors=True)


def _assert_no_links(root: Path, code: str) -> None:
    if _linklike(root) or not root.is_dir():
        _fail(code, "generation_publish")
    for directory, directories, filenames in os.walk(root, followlinks=False):
        base = Path(directory)
        if any(_linklike(base / name) for name in directories + filenames):
            _fail(code, "generation_publish")


def _path_linklike(path: Path) -> bool:
    absolute = Path(os.path.abspath(path))
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        if present(current) and _linklike(current):
            return True
    return False


def _linklike(path: Path) -> bool:
    junction = getattr(path, "is_junction", None)
    if path.is_symlink() or bool(junction and junction()):
        return True
    try:
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
    except OSError:
        return False
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def _fail(code: str, stage: str) -> None:
    raise cargo_project.ProjectInputError(code, stage)
