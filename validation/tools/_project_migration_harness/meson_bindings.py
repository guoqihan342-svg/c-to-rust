from __future__ import annotations

from pathlib import Path
from typing import Any

from .meson_paths import (
    MAX_REFERENCED_BYTES, MAX_REFERENCED_FILE_BYTES, MesonPathError,
    configured_file, confined_path, declared_file, hash_binding,
    repository_lexical_path,
)


class MesonBindingCollector:
    def __init__(self, root: Path) -> None:
        self.root = root
        self._cache: dict[str, dict[str, Any]] = {}
        self._total_bytes = 0

    def materialized(self, value: str) -> dict[str, Any]:
        return self._bind(configured_file(self.root, value))

    def declared(
        self, value: str, declaration_kind: str, producer: dict[str, Any] | None,
    ) -> dict[str, Any]:
        path, materialized = declared_file(self.root, value)
        if producer is None:
            if not materialized:
                raise MesonPathError("meson_generated_source_producer_missing")
            producer = {"kind": "meson_configuration"}
        result = {
            "path": repository_lexical_path(self.root, path),
            "declaration_kind": declaration_kind,
            "producer": producer,
            "materialized": materialized,
        }
        if materialized:
            binding = self._bind(path)
            result["sha256"] = binding["sha256"]
            result["size_bytes"] = binding["size_bytes"]
        return result

    def artifacts(self) -> list[dict[str, Any]]:
        return [self._cache[path] for path in sorted(self._cache)]

    def _bind(self, path: Path) -> dict[str, Any]:
        relative = repository_lexical_path(self.root, path)
        if relative in self._cache:
            return self._cache[relative]
        binding = hash_binding(self.root, path, MAX_REFERENCED_FILE_BYTES)
        self._total_bytes += binding["size_bytes"]
        if self._total_bytes > MAX_REFERENCED_BYTES:
            raise MesonPathError("meson_referenced_byte_limit_exceeded")
        self._cache[relative] = binding
        return binding


def bind_targets(
    root: Path, specs: list[dict[str, Any]], collector: MesonBindingCollector,
) -> list[dict[str, Any]]:
    producers = _target_producers(root, specs)
    targets: list[dict[str, Any]] = []
    for spec in specs:
        current = {
            key: value for key, value in spec.items() if key not in {
                "defined_in_path", "extra_file_paths", "output_paths", "source_groups",
            }
        }
        current["defined_in"] = collector.materialized(spec["defined_in_path"])
        current["outputs"] = [
            collector.declared(
                path, "target_output", _target_producer(spec["id"], spec["type"])
            )
            for path in spec["output_paths"]
        ]
        current["extra_files"] = [
            collector.materialized(path) for path in spec["extra_file_paths"]
        ]
        current["source_groups"] = [
            _bind_source_group(root, spec["id"], group, producers, collector)
            for group in spec["source_groups"]
        ]
        targets.append(current)
    return targets


def bind_buildsystem_files(
    paths: list[str], collector: MesonBindingCollector,
) -> list[dict[str, Any]]:
    return [collector.materialized(path) for path in paths]


def validate_dependency_target_ids(
    dependencies: list[dict[str, Any]], targets: list[dict[str, Any]],
) -> None:
    target_ids = {target["id"] for target in targets}
    for dependency in dependencies:
        if any(
            item not in target_ids for item in dependency["target_dependency_ids"]
        ):
            raise MesonPathError("meson_dependency_target_id_unknown")


def _target_producers(
    root: Path, specs: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for spec in specs:
        producer = _target_producer(spec["id"], spec["type"])
        for value in spec["output_paths"]:
            path = confined_path(root, value)
            relative = repository_lexical_path(root, path)
            if relative in result:
                raise MesonPathError("meson_output_producer_ambiguous")
            result[relative] = producer
    return result


def _target_producer(identifier: str, target_type: str) -> dict[str, Any]:
    return {
        "kind": "meson_target",
        "target_id": identifier,
        "target_type": target_type,
    }


def _bind_source_group(
    root: Path,
    consumer_id: str,
    group: dict[str, Any],
    producers: dict[str, dict[str, Any]],
    collector: MesonBindingCollector,
) -> dict[str, Any]:
    current = {
        key: value for key, value in group.items() if key not in {
            "source_paths", "generated_source_paths",
        }
    }
    current["sources"] = [
        collector.materialized(path) for path in group.get("source_paths", [])
    ]
    generated = []
    for value in group.get("generated_source_paths", []):
        path = confined_path(root, value)
        relative = repository_lexical_path(root, path)
        binding = collector.declared(
            value, "generated_output", producers.get(relative)
        )
        binding["consumer_target_id"] = consumer_id
        generated.append(binding)
    current["generated_sources"] = generated
    return current


__all__ = [
    "MesonBindingCollector", "bind_buildsystem_files", "bind_targets",
    "validate_dependency_target_ids",
]
