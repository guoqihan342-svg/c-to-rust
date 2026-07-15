from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from .artifacts import content_sha256


class BaselineArtifactRegistry:
    def __init__(self) -> None:
        self._items: dict[tuple[str, str, int], dict[str, Any]] = {}

    def add(self, role: str, reference: Mapping[str, Any]) -> None:
        identity = (
            str(reference["path"]), str(reference["sha256"]),
            int(reference["size_bytes"]),
        )
        current = {
            "role": role, "visibility": "private-local",
            "ref": dict(reference),
        }
        previous = self._items.get(identity)
        if previous is not None and previous != current:
            raise ValueError("c2rust_artifact_role_conflict")
        self._items[identity] = current

    def add_process(
        self, references: Sequence[Mapping[str, Any]],
    ) -> None:
        if len(references) != 3:
            raise ValueError("c2rust_process_reference_count_invalid")
        for role, reference in zip(
            ("process-stdout", "process-stderr", "process-stdin"),
            references,
        ):
            self.add(role, reference)

    def values(self) -> list[dict[str, Any]]:
        return list(self._items.values())


def portable_tool(value: Mapping[str, Any]) -> dict[str, Any]:
    core = {
        "role": value["role"],
        "basename": Path(str(value["executable_path"])).name,
        "sha256": value["sha256"],
        "size_bytes": value["size_bytes"],
    }
    return {**core, "portable_identity_sha256": content_sha256(core)}


__all__ = ["BaselineArtifactRegistry", "portable_tool"]
