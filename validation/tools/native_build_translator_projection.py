"""Project verified native-build metadata into translator input fields."""

from __future__ import annotations

from typing import Any


def native_translator_build_profile(
    build_profile: dict[str, Any],
    target: dict[str, Any],
    context: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    profile = dict(build_profile)
    projected_target = dict(target)
    closure_target = context["target_abi"]
    overlap = {
        "triple_or_abi": closure_target["triple"],
        "endianness": closure_target["endianness"],
        "pointer_width": closure_target["pointer_width"],
    }
    for field, value in overlap.items():
        declared = projected_target.get(field)
        if declared not in (None, "", 0) and declared != value:
            raise SystemExit(f"native build closure target ABI conflicts at {field}")
        projected_target[field] = value
    profile["include_paths"] = list(context["include_paths"])
    profile["defines"] = list(context["defines"])
    profile["target"] = projected_target
    profile["target_triple"] = closure_target["triple"]
    profile["abi"] = closure_target["triple"]
    profile["compiler_command_source"] = context["compile_database"]["path"]
    return profile, projected_target


def rebase_native_source_files(
    source_files: list[dict[str, Any]],
    source_root: str,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    projected: list[dict[str, Any]] = []
    projection: dict[str, str] = {}
    for item in source_files:
        original = normalized_metadata_path(item.get("path"))
        path = (
            original
            if item.get("role") == "fixture"
            else rebase_native_source_path(original, source_root)
        )
        projection[original] = path
        projected.append({**item, "path": path})
    return projected, projection


def rebase_native_source_path(path: str, source_root: str) -> str:
    path = normalized_metadata_path(path)
    root = normalized_metadata_path(source_root).rstrip("/")
    if not path or path.startswith("/") or ".." in path.split("/"):
        raise SystemExit("native build source paths must be canonical repo-relative paths")
    if path == root or path.startswith(f"{root}/"):
        return path
    return f"{root}/{path}"


def rebase_native_source_span(
    source_span: dict[str, Any] | None,
    projection: dict[str, str],
    source_root: str,
) -> dict[str, Any] | None:
    if source_span is None:
        return None
    result = dict(source_span)
    original = normalized_metadata_path(result.get("file"))
    result["file"] = projection.get(original) or rebase_native_source_path(
        original,
        source_root,
    )
    return result


def rebase_native_signature(
    signature: dict[str, Any],
    projection: dict[str, str],
    source_root: str,
) -> dict[str, Any]:
    result = dict(signature)
    result["source_span"] = rebase_native_source_span(
        signature.get("source_span"),
        projection,
        source_root,
    )
    return result


def normalized_metadata_path(value: Any) -> str:
    return str(value or "").strip().replace("\\", "/")


__all__ = [
    "native_translator_build_profile",
    "rebase_native_signature",
    "rebase_native_source_files",
    "rebase_native_source_path",
    "rebase_native_source_span",
]
