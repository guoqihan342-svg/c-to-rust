from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

from .artifacts import content_sha256
from .build_ir import stable_build_id
from .build_ir_external_dependencies import NATIVE_DEPENDENCY_KIND


def project_native_link_requirements(
    build_irs: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], dict[str, set[str]]] = defaultdict(
        lambda: {"dependencies": set(), "consumers": set()},
    )
    for build_ir in build_irs:
        semantic_sha256 = str(build_ir["semantic_sha256"])
        for dependency in build_ir["external_dependencies"]:
            if dependency.get("kind") != NATIVE_DEPENDENCY_KIND:
                continue
            key = (str(dependency["name"]), str(dependency["format"]))
            grouped[key]["dependencies"].add(stable_build_id(
                "native-link-member", {
                    "build_ir_semantic_sha256": semantic_sha256,
                    "dependency_id": dependency["dependency_id"],
                },
            ))
            grouped[key]["consumers"].update(
                stable_build_id("native-link-consumer", {
                    "build_ir_semantic_sha256": semantic_sha256,
                    "target_id": item,
                })
                for item in dependency["consumer_target_ids"]
            )
    result = []
    for (name, library_format), members in grouped.items():
        dependencies = sorted(members["dependencies"])
        consumers = sorted(members["consumers"])
        identity = {"portable_name": name, "library_format": library_format}
        result.append({
            "requirement_id": stable_build_id("native-link-requirement", identity),
            **identity,
            "dependency_count": len(dependencies),
            "dependency_set_sha256": content_sha256(dependencies),
            "consumer_target_count": len(consumers),
            "consumer_target_set_sha256": content_sha256(consumers),
        })
    return sorted(result, key=lambda item: item["requirement_id"])


__all__ = ["project_native_link_requirements"]
