from __future__ import annotations

import re
from typing import Any


SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def response_file_contract_status(context_pack: dict[str, Any]) -> str:
    compile_context = context_pack.get("compile_context")
    selected = compile_context.get("selected_entry") if isinstance(compile_context, dict) else None
    response_files = selected.get("response_files") if isinstance(selected, dict) else None
    if response_files is None:
        return "not_present"
    if not isinstance(response_files, dict):
        return "invalid"
    if response_files.get("status") == "blocked":
        return "blocked"
    files = response_files.get("files")
    bindings = context_pack.get("bindings")
    inputs = bindings.get("inputs") if isinstance(bindings, dict) else None
    if response_files.get("status") != "expanded" or not isinstance(files, list) or not isinstance(inputs, list):
        return "invalid"
    limits = response_files.get("limits")
    if limits != {
        "max_depth": 4,
        "max_files": 16,
        "max_file_bytes": 65_536,
        "max_total_bytes": 262_144,
        "max_arguments": 4_096,
    }:
        return "invalid"
    if (
        response_files.get("contract_version") != 1
        or response_files.get("dialect") != "gnu-v1"
        or response_files.get("unique_file_count") != len(files)
        or not isinstance(response_files.get("expansion_count"), int)
        or response_files["expansion_count"] < len(files)
        or response_files["expansion_count"] > 16
        or not isinstance(response_files.get("expanded_argument_count"), int)
        or response_files["expanded_argument_count"] > 4_096
        or not _is_sha256(response_files.get("original_argv_sha256"))
        or not _is_sha256(response_files.get("expanded_argv_sha256"))
    ):
        return "invalid"
    paths: set[str] = set()
    for item in files:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("path"), str)
            or not item["path"].startswith("<source-root>/")
            or item["path"] in paths
            or not _is_sha256(item.get("sha256"))
            or not isinstance(item.get("size_bytes"), int)
            or not 0 <= item["size_bytes"] <= 65_536
            or not isinstance(item.get("depth"), int)
            or not 1 <= item["depth"] <= 4
        ):
            return "invalid"
        paths.add(item["path"])
    expected = sorted(files, key=lambda item: str(item.get("path")) if isinstance(item, dict) else "")
    actual = sorted(
        (
            {key: value for key, value in item.items() if key != "kind"}
            for item in inputs
            if isinstance(item, dict) and item.get("kind") == "compile_response_file"
        ),
        key=lambda item: str(item.get("path")),
    )
    return "expanded" if expected == actual else "invalid"


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and SHA256_RE.fullmatch(value) is not None


__all__ = ["response_file_contract_status"]
