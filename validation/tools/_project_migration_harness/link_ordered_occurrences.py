from __future__ import annotations

from pathlib import Path
from typing import Any

from .build_facts import json_sha256
from .closure_paths import bind_repository_artifact, path_error_blocker
from .link_external_libraries import external_native_library
from .link_input_paths import bind_positional_link_input
from .link_system_arguments import (
    contains_external_link_option_path, normalize_system_link_argument,
)


_OCCURRENCE_KINDS = {
    "input", "search-root", "system-argument", "external-native-library",
}


def append_ordered_link_occurrence(
    occurrences: list[dict[str, int | str]],
    references: list[Any],
    value: Any,
    *,
    kind: str,
    argument_index: int,
    argument_count: int = 1,
) -> None:
    """Append one category value and its value-free source-order reference."""
    if (
        kind not in _OCCURRENCE_KINDS
        or type(argument_index) is not int
        or argument_index < 0
        or argument_count not in {1, 2}
    ):
        raise ValueError("ordered_link_occurrence_invalid")
    reference_ordinal = len(references)
    references.append(value)
    occurrences.append({
        "ordinal": len(occurrences),
        "argument_index": argument_index,
        "argument_count": argument_count,
        "kind": kind,
        "reference_ordinal": reference_ordinal,
    })


def split_ordered_link_arguments(
    root: Path,
    base: Path,
    fact_path: str,
    arguments: list[str],
    blockers: list[dict[str, Any]],
) -> dict[str, list[Any]]:
    """Classify expanded arguments after link-output arguments are removed."""
    inputs: list[dict[str, Any]] = []
    search_roots: list[dict[str, Any]] = []
    system_args: list[str] = []
    external_libraries: list[dict[str, Any]] = []
    occurrences: list[dict[str, int | str]] = []
    index = 0
    while index < len(arguments):
        argument = arguments[index]
        if argument == "-L" and index + 1 < len(arguments):
            bound = _bind_search_root(
                root, base, arguments[index + 1], blockers,
            )
            if bound is not None:
                append_ordered_link_occurrence(
                    occurrences, search_roots, bound, kind="search-root",
                    argument_index=index, argument_count=2,
                )
            index += 2
            continue
        if argument.startswith("-L") and len(argument) > 2:
            bound = _bind_search_root(root, base, argument[2:], blockers)
            if bound is not None:
                append_ordered_link_occurrence(
                    occurrences, search_roots, bound, kind="search-root",
                    argument_index=index,
                )
            index += 1
            continue
        if argument.startswith("/LIBPATH:"):
            bound = _bind_search_root(root, base, argument[9:], blockers)
            if bound is not None:
                append_ordered_link_occurrence(
                    occurrences, search_roots, bound, kind="search-root",
                    argument_index=index,
                )
            index += 1
            continue
        normalized = normalize_system_link_argument(root, base, argument)
        if normalized is not None:
            append_ordered_link_occurrence(
                occurrences, system_args, normalized, kind="system-argument",
                argument_index=index,
            )
            index += 1
            continue
        external = external_native_library(
            root, base, argument, argument_index=index,
        )
        if external is not None:
            append_ordered_link_occurrence(
                occurrences, external_libraries, external,
                kind="external-native-library", argument_index=index,
            )
            index += 1
            continue
        if argument.startswith("-") or argument.upper().startswith("/DEFAULTLIB:"):
            kind = (
                "external_link_argument"
                if contains_external_link_option_path(argument)
                else "link_argument_unsupported"
            )
            blockers.append({
                "kind": kind,
                "fact": fact_path,
                "argument_sha256": json_sha256(argument),
            })
            index += 1
            continue
        handled, bound = bind_positional_link_input(
            root, base, argument, blockers,
        )
        if handled and bound is not None:
            append_ordered_link_occurrence(
                occurrences, inputs, bound, kind="input",
                argument_index=index,
            )
        elif not handled:
            blockers.append({
                "kind": "link_argument_unsupported",
                "fact": fact_path,
                "argument_sha256": json_sha256(argument),
            })
        index += 1
    return {
        "inputs": inputs,
        "search_roots": search_roots,
        "ordered_system_link_args": system_args,
        "external_native_libraries": external_libraries,
        "ordered_link_occurrences": occurrences,
    }


def _bind_search_root(
    root: Path, base: Path, value: str, blockers: list[dict[str, Any]],
) -> dict[str, Any] | None:
    try:
        return bind_repository_artifact(root, value, base=base, kind="directory")
    except (OSError, ValueError) as error:
        blockers.append(path_error_blocker(
            error, role="link_search_root", path=value,
        ))
        return None


__all__ = [
    "append_ordered_link_occurrence", "split_ordered_link_arguments",
]
