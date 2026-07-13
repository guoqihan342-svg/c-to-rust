from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from .artifacts import canonical_json_bytes, checked_relative_path
from .build_facts import is_linklike


MAX_TREE_DIRECTORIES = 100_000
MAX_TREE_FILES = 100_000
MAX_TREE_FILE_BYTES = 128 * 1024 * 1024
MAX_TREE_TOTAL_BYTES = 2 * 1024 * 1024 * 1024
MAX_COMPILE_DATABASE_BYTES = 16 * 1024 * 1024
MAX_COMPILE_ENTRIES = 100_000
MAX_SOURCE_FILE_BYTES = 8 * 1024 * 1024
MAX_SOURCE_TOTAL_BYTES = 32 * 1024 * 1024
MAX_SOURCE_TOKENS = 500_000
MAX_SOURCE_SHINGLES = 250_000


class IntegrityError(ValueError):
    pass


def file_sha256(path: Path, *, max_bytes: int | None = None) -> str:
    candidate = Path(path)
    if _linklike(candidate) or not candidate.is_file():
        raise IntegrityError("bound file is not a regular file")
    before = candidate.stat()
    if max_bytes is not None and before.st_size > max_bytes:
        raise IntegrityError("bound file exceeds its byte limit")
    digest = hashlib.sha256()
    total = 0
    with candidate.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            total += len(chunk)
            if max_bytes is not None and total > max_bytes:
                raise IntegrityError("bound file exceeds its byte limit")
            digest.update(chunk)
    after = candidate.stat()
    if _identity(before) != _identity(after):
        raise IntegrityError("bound file changed while hashing")
    return digest.hexdigest()


def repository_tree_sha256(repo_root: Path) -> str:
    root = Path(repo_root).resolve(strict=True)
    if _linklike(Path(repo_root)) or not root.is_dir():
        raise IntegrityError("repository root must be a regular directory")
    entries: list[dict[str, Any]] = []
    directories_seen = 0
    total_bytes = 0
    for current_text, directories, files in os.walk(
        root, topdown=True, followlinks=False
    ):
        directories_seen += 1
        if directories_seen > MAX_TREE_DIRECTORIES:
            raise IntegrityError("repository directory limit exceeded")
        current = Path(current_text)
        filtered = []
        for name in sorted(directories):
            child = current / name
            if name == ".git":
                continue
            if _linklike(child):
                raise IntegrityError(
                    f"repository contains a linked directory: {child.relative_to(root).as_posix()}"
                )
            filtered.append(name)
        directories[:] = filtered
        for name in sorted(files):
            if name == ".git":
                continue
            path = current / name
            relative = path.relative_to(root).as_posix()
            if _linklike(path) or not path.is_file():
                raise IntegrityError(f"repository contains an unsupported entry: {relative}")
            size = path.stat().st_size
            if size > MAX_TREE_FILE_BYTES:
                raise IntegrityError(f"repository file limit exceeded: {relative}")
            total_bytes += size
            if total_bytes > MAX_TREE_TOTAL_BYTES or len(entries) >= MAX_TREE_FILES:
                raise IntegrityError("repository tree resource limit exceeded")
            entries.append({
                "path": relative,
                "sha256": file_sha256(path, max_bytes=MAX_TREE_FILE_BYTES),
                "size_bytes": size,
            })
    if not entries:
        raise IntegrityError("repository must contain files")
    return hashlib.sha256(canonical_json_bytes(entries)).hexdigest()


def compile_database(
    value: Any, repo: Path,
) -> tuple[Path, str, list[Path]]:
    _require(isinstance(value, Mapping), "compile_database must be an object")
    relative = checked_relative_path(value.get("path"))
    path = confined_path(repo, relative, "compile database", must_exist=True)
    digest = file_sha256(path, max_bytes=MAX_COMPILE_DATABASE_BYTES)
    _match_sha(value.get("sha256"), digest, "compile_database.sha256")
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise IntegrityError("compile database is not valid UTF-8 JSON") from error
    _require(
        isinstance(payload, list) and 0 < len(payload) <= MAX_COMPILE_ENTRIES,
        "compile database entry count is invalid",
    )
    sources: list[Path] = []
    for entry in payload:
        _require(
            isinstance(entry, Mapping) and isinstance(entry.get("file"), str),
            "compile command requires file",
        )
        directory = Path(entry.get("directory", "."))
        directory = directory if directory.is_absolute() else repo / directory
        source = Path(entry["file"])
        source = source if source.is_absolute() else directory / source
        try:
            resolved = source.resolve(strict=True)
            resolved.relative_to(repo.resolve(strict=True))
        except (OSError, ValueError) as error:
            raise IntegrityError("compile source must stay inside repository") from error
        _reject_components(repo, resolved)
        _require(
            resolved.suffix.lower() == ".c" and resolved.is_file(),
            "compile source must be confined C",
        )
        sources.append(resolved)
    return path, digest, sorted(set(sources))


def source_shape(sources: list[Path]) -> tuple[set[str], str]:
    keywords = {
        "if", "else", "for", "while", "do", "switch", "case", "return",
        "struct", "union", "enum", "typedef", "const", "static", "extern",
        "sizeof", "void", "char", "short", "int", "long", "float", "double",
        "signed", "unsigned", "break", "continue", "goto",
    }
    token_pattern = re.compile(
        r'"(?:\\.|[^"\\])*"|\b\d+(?:\.\d+)?\b|[A-Za-z_]\w*|'
        r'==|!=|<=|>=|->|&&|\|\||\S'
    )
    digest = hashlib.sha256()
    shingles: set[str] = set()
    total_bytes = 0
    total_tokens = 0
    for path in sources:
        size = path.stat().st_size
        total_bytes += size
        if size > MAX_SOURCE_FILE_BYTES or total_bytes > MAX_SOURCE_TOTAL_BYTES:
            raise IntegrityError("held-out source input exceeds its byte limit")
        try:
            text = path.read_text(encoding="utf-8", errors="strict")
        except (OSError, UnicodeError) as error:
            raise IntegrityError("held-out source is not readable UTF-8") from error
        text = re.sub(r"/\*.*?\*/|//[^\n]*", " ", text, flags=re.S)
        normalized = []
        for token in token_pattern.findall(text):
            current = token if token in keywords or not re.match(r"[A-Za-z_]", token) else "ID"
            current = "STR" if current.startswith('"') else (
                "NUM" if current[:1].isdigit() else current
            )
            normalized.append(current)
            digest.update(current.encode("utf-8") + b"\0")
        total_tokens += len(normalized)
        if total_tokens > MAX_SOURCE_TOKENS:
            raise IntegrityError("held-out source token limit exceeded")
        for index in range(max(1, len(normalized) - 4)):
            shingles.add(" ".join(normalized[index:index + 5]))
            if len(shingles) > MAX_SOURCE_SHINGLES:
                raise IntegrityError("held-out source shape limit exceeded")
    return shingles, digest.hexdigest()


def bound_file(value: Any, root: Path, label: str) -> Path:
    _require(isinstance(value, Mapping), f"{label} must be a path/sha256 object")
    relative = checked_relative_path(value.get("path"))
    path = confined_path(root, relative, label, must_exist=True)
    _match_sha(value.get("sha256"), file_sha256(path), f"{label}.sha256")
    return path


def confined_path(
    root: Path, relative: str, label: str, *, must_exist: bool,
) -> Path:
    base = root.resolve(strict=True)
    candidate = base.joinpath(*PurePosixPath(relative).parts)
    _reject_components(base, candidate)
    try:
        resolved = candidate.resolve(strict=must_exist)
        resolved.relative_to(base)
    except (OSError, ValueError) as error:
        raise IntegrityError(f"{label} must stay inside its root") from error
    return resolved


def _reject_components(root: Path, candidate: Path) -> None:
    base = root.resolve(strict=True)
    try:
        relative = candidate.absolute().relative_to(base)
    except ValueError as error:
        raise IntegrityError("path escapes its trusted root") from error
    current = base
    for part in relative.parts:
        current /= part
        if current.exists() and _linklike(current):
            raise IntegrityError("path contains a linked or reparse component")


def _linklike(path: Path) -> bool:
    try:
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
    except OSError:
        attributes = 0
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return is_linklike(path) or bool(attributes & reparse)


def _identity(value: os.stat_result) -> tuple[int, int, int, int]:
    return value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns


def _match_sha(actual: Any, expected: str, label: str) -> None:
    _require(
        isinstance(actual, str) and re.fullmatch(r"[0-9a-f]{64}", actual) is not None,
        f"{label} must be sha256",
    )
    _require(actual == expected, f"{label} mismatch")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise IntegrityError(message)


__all__ = [
    "IntegrityError", "bound_file", "compile_database", "confined_path",
    "file_sha256", "repository_tree_sha256", "source_shape",
]
