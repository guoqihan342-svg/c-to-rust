from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .artifacts import content_sha256
from .build_ir import is_sha256, normalize_binding


_KEYS = {"ordinal", "binding_sha256"}


def project_link_response_files(raw: Mapping[str, Any]) -> list[dict[str, Any]]:
    values = raw.get("response_files", [])
    if not isinstance(values, list):
        raise ValueError("build_ir_raw_link_response_files_invalid")
    result = []
    for ordinal, value in enumerate(values):
        if not isinstance(value, Mapping):
            raise ValueError("build_ir_raw_link_response_file_invalid")
        materialized = value.get("materialized", True)
        if materialized is not True:
            raise ValueError("build_ir_raw_link_response_file_invalid")
        binding = normalize_binding(value, materialized=True)
        result.append({
            "ordinal": ordinal, "binding_sha256": content_sha256(binding),
        })
    return result


def validate_link_response_files(target: Mapping[str, Any]) -> None:
    values = target.get("link_response_files")
    if not isinstance(values, list):
        raise ValueError("build_ir_link_response_file_authority_invalid")
    for ordinal, value in enumerate(values):
        if (
            not isinstance(value, Mapping) or set(value) != _KEYS
            or value.get("ordinal") != ordinal
            or not is_sha256(value.get("binding_sha256"))
        ):
            raise ValueError("build_ir_link_response_file_authority_invalid")


__all__ = ["project_link_response_files", "validate_link_response_files"]
