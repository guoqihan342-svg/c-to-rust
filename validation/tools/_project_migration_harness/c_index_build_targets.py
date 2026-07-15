from __future__ import annotations

from collections.abc import Mapping
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any


_TARGET_FIELDS = {
    "target_id", "name", "kind", "output_paths", "dependency_target_ids",
    "ordered_input_target_ids", "ordered_link_arguments",
}


def normalized_build_target_context(
    value: Any, *, unit_id: str,
) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping) or set(value) != {
        "variant", "object_target", "consumer_targets",
    }:
        raise ValueError("translation unit build_target_context is invalid")
    variant = value.get("variant")
    if not isinstance(variant, Mapping) or set(variant) != {"key", "index", "count"}:
        raise ValueError("translation unit variant context is invalid")
    index = variant.get("index")
    count = variant.get("count")
    if (
        variant.get("key") != unit_id
        or type(index) is not int or type(count) is not int
        or count < 1 or not 0 <= index < count
    ):
        raise ValueError("translation unit variant context is invalid")
    object_target = _target(value.get("object_target"))
    consumers_raw = value.get("consumer_targets")
    if not isinstance(consumers_raw, list):
        raise ValueError("translation unit consumer targets are invalid")
    consumers = [_target(item) for item in consumers_raw]
    consumer_ids = [item["target_id"] for item in consumers]
    if (
        object_target["kind"] != "object"
        or object_target["target_id"] in consumer_ids
        or consumer_ids != sorted(set(consumer_ids))
    ):
        raise ValueError("translation unit consumer targets are invalid")
    reachable = {object_target["target_id"]}
    pending = list(consumers)
    while pending:
        newly_reachable = [
            item for item in pending
            if reachable.intersection(item["dependency_target_ids"])
        ]
        if not newly_reachable:
            break
        reached_ids = {item["target_id"] for item in newly_reachable}
        reachable.update(reached_ids)
        pending = [item for item in pending if item["target_id"] not in reached_ids]
    if pending:
        raise ValueError("translation unit consumer target binding is invalid")
    return {
        "variant": {"key": unit_id, "index": index, "count": count},
        "object_target": object_target,
        "consumer_targets": consumers,
    }


def _target(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _TARGET_FIELDS:
        raise ValueError("translation unit build target is invalid")
    strings = (value.get("target_id"), value.get("name"), value.get("kind"))
    outputs = value.get("output_paths")
    dependencies = value.get("dependency_target_ids")
    ordered_inputs = value.get("ordered_input_target_ids")
    link_arguments = value.get("ordered_link_arguments")
    if (
        not all(isinstance(item, str) and item and "\0" not in item for item in strings)
        or value.get("kind") not in {"object", "archive", "link"}
        or not isinstance(outputs, list) or not outputs
        or any(not _safe_path(item) for item in outputs)
        or len(outputs) != len(set(outputs))
        or not _string_list(dependencies)
        or len(dependencies) != len(set(dependencies))
        or not isinstance(ordered_inputs, list)
        or any(item is not None and not _text(item) for item in ordered_inputs)
        or not _string_list(link_arguments)
        or any(
            item is not None and item not in dependencies
            for item in ordered_inputs
        )
    ):
        raise ValueError("translation unit build target is invalid")
    return {
        "target_id": strings[0], "name": strings[1], "kind": strings[2],
        "output_paths": list(outputs),
        "dependency_target_ids": list(dependencies),
        "ordered_input_target_ids": list(ordered_inputs),
        "ordered_link_arguments": list(link_arguments),
    }


def _safe_path(value: Any) -> bool:
    if not _text(value) or "\\" in value:
        return False
    posix = PurePosixPath(value)
    windows = PureWindowsPath(value)
    return (
        not posix.is_absolute() and not windows.drive and ".." not in posix.parts
        and posix.as_posix() == value
    )


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value) and "\0" not in value


def _string_list(value: Any) -> bool:
    return isinstance(value, list) and all(_text(item) for item in value)


__all__ = ["normalized_build_target_context"]
