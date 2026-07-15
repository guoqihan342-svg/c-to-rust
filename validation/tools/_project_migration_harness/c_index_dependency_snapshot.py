from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Sequence

from .build_facts import is_linklike


MAX_SNAPSHOT_HEADERS = 8_192
MAX_SNAPSHOT_HEADER_BYTES = 256 * 1024 * 1024


class DependencySnapshot:
    """Content-bound, invocation-local cache for repeated include traversal."""

    def __init__(self, repo_root: Path) -> None:
        self.root = repo_root.resolve(strict=True)
        self._headers: dict[Path, tuple[dict[str, Any], bytes]] = {}
        self._header_facts: dict[str, dict[str, Any]] = {}
        self._repository_paths: dict[Path, str] = {}
        self._resolved_includes: dict[tuple[Any, ...], Path | None] = {}
        self._resolved_paths: dict[tuple[Path, str], Path] = {}
        self._component_identities: dict[Path, tuple[int, int, int]] = {}
        self._header_bytes = 0
        self._counters = {
            "header_hits": 0,
            "header_misses": 0,
            "include_resolution_hits": 0,
            "include_resolution_misses": 0,
            "repository_path_hits": 0,
            "repository_path_misses": 0,
            "path_resolution_hits": 0,
            "path_resolution_misses": 0,
        }
        self._bind_component(self.root)

    def resolve(self, value: str | Path, *, base: Path | None = None) -> Path:
        raw = str(value)
        if _foreign_absolute(raw):
            raise ValueError("foreign_absolute_path")
        anchor = (base or self.root).absolute()
        key = (anchor, raw)
        cached = self._resolved_paths.get(key)
        if cached is not None:
            self._counters["path_resolution_hits"] += 1
            return cached
        self._counters["path_resolution_misses"] += 1
        candidate = Path(value)
        if not candidate.is_absolute():
            candidate = anchor / candidate
        lexical = Path(os.path.abspath(candidate))
        try:
            relative = lexical.relative_to(self.root)
        except ValueError as error:
            raise ValueError("path_outside_repository") from error
        current = self.root
        for part in relative.parts:
            current /= part
            self._bind_component(current)
        self._resolved_paths[key] = lexical
        return lexical

    def repository_path(self, path: Path) -> str:
        key = path.absolute()
        if key in self._repository_paths:
            self._counters["repository_path_hits"] += 1
            return self._repository_paths[key]
        self._counters["repository_path_misses"] += 1
        resolved = self.resolve(path)
        relative = resolved.relative_to(self.root)
        value = "." if not relative.parts else relative.as_posix()
        self._repository_paths[key] = value
        return value

    def read_header(
        self, path: Path, *, max_bytes: int
    ) -> tuple[dict[str, Any], bytes]:
        key = path.absolute()
        cached = self._headers.get(key)
        if cached is not None:
            self._counters["header_hits"] += 1
            return cached
        self._counters["header_misses"] += 1
        resolved = self.resolve(path)
        if not resolved.is_file() or is_linklike(resolved):
            raise ValueError("not_regular_file")
        with resolved.open("rb") as stream:
            raw = stream.read(max_bytes + 1)
        if len(raw) > max_bytes:
            raise ValueError("file_size_limit_exceeded")
        if len(self._headers) >= MAX_SNAPSHOT_HEADERS:
            raise ValueError("dependency_snapshot_header_limit_exceeded")
        if self._header_bytes + len(raw) > MAX_SNAPSHOT_HEADER_BYTES:
            raise ValueError("dependency_snapshot_byte_limit_exceeded")
        binding = {
            "path": self.repository_path(resolved),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "size_bytes": len(raw),
        }
        result = (binding, raw)
        self._headers[key] = result
        self._header_bytes += len(raw)
        return result

    def resolve_include(
        self,
        source: Path,
        target: str,
        quote: bool,
        search_dirs: Sequence[Path],
    ) -> Path | None:
        candidate = PurePosixPath(target)
        roots = ([source.parent] if quote else []) + list(search_dirs)
        key = (
            source.parent.absolute(),
            target,
            quote,
            *(path.absolute() for path in roots),
        )
        if key in self._resolved_includes:
            self._counters["include_resolution_hits"] += 1
            return self._resolved_includes[key]
        self._counters["include_resolution_misses"] += 1
        resolved: Path | None = None
        for base in roots:
            try:
                current = self.resolve(Path(*candidate.parts), base=base)
            except (OSError, ValueError):
                continue
            if current.is_file():
                resolved = current
                break
        self._resolved_includes[key] = resolved
        return resolved

    def record_header_source(self, source: Mapping[str, Any]) -> dict[str, str]:
        fact = {"source": dict(source)}
        encoded = json.dumps(
            fact, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        digest = hashlib.sha256(encoded).hexdigest()
        self._header_facts.setdefault(digest, fact)
        return {
            "header_fact_sha256": digest,
            "path": str(source["path"]),
            "sha256": str(source["sha256"]),
        }

    def header_facts(self) -> dict[str, dict[str, Any]]:
        return {key: self._header_facts[key] for key in sorted(self._header_facts)}

    def header_source(self, digest: str) -> dict[str, Any]:
        fact = self._header_facts.get(digest)
        if fact is None or not isinstance(fact.get("source"), Mapping):
            raise ValueError("dependency snapshot header fact is unavailable")
        return dict(fact["source"])

    def report(self) -> dict[str, Any]:
        self.verify_stability()
        return {
            "scope": "single_index_invocation",
            "unique_header_count": len(self._headers),
            "unique_header_bytes": self._header_bytes,
            "unique_header_fact_count": len(self._header_facts),
            **self._counters,
            "verified_path_component_count": len(self._component_identities),
        }

    def verify_stability(self) -> None:
        for path, expected in self._component_identities.items():
            if _component_identity(path) != expected or is_linklike(path):
                raise ValueError("dependency_snapshot_path_drift")

    def _bind_component(self, path: Path) -> None:
        if path in self._component_identities:
            return
        if path.exists():
            if is_linklike(path):
                raise ValueError("linked_path_component")
            self._component_identities[path] = _component_identity(path)


def _component_identity(path: Path) -> tuple[int, int, int]:
    status = path.stat(follow_symlinks=False)
    return status.st_dev, status.st_ino, status.st_mode


def _foreign_absolute(value: str) -> bool:
    return (
        (PurePosixPath(value).is_absolute() or PureWindowsPath(value).is_absolute())
        and not Path(value).is_absolute()
    )


__all__ = ["DependencySnapshot"]
