from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any

from .artifacts import canonical_json_bytes
from .build_facts import is_linklike
from .context_page_proof import _verified_context_page_reference


class PortfolioIntegrityError(ValueError):
    pass


def positive(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise PortfolioIntegrityError(f"{name} must be a positive integer")
    return value


def relative_path(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise PortfolioIntegrityError(f"{name} must be a POSIX repository-relative path")
    path = PurePosixPath(value)
    if (
        not path.parts
        or path.is_absolute()
        or ".." in path.parts
        or path.parts[0].startswith("~")
        or ":" in path.parts[0]
    ):
        raise PortfolioIntegrityError(f"{name} must stay repository-relative")
    if path.as_posix() != value:
        raise PortfolioIntegrityError(f"{name} must be canonical")
    return path.as_posix()


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def groups_by_id(dag: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    groups = dag.get("groups")
    if not isinstance(groups, list):
        raise PortfolioIntegrityError("migration DAG groups must be a list")
    result: dict[str, Mapping[str, Any]] = {}
    for group in groups:
        if not isinstance(group, Mapping) or not isinstance(group.get("group_id"), str) or not group["group_id"]:
            raise PortfolioIntegrityError("every migration group requires a group_id")
        group_id = str(group["group_id"])
        if group_id in result:
            raise PortfolioIntegrityError(f"duplicate migration group: {group_id}")
        result[group_id] = group
    return result


def wave_layout(
    dag: Mapping[str, Any], groups: Mapping[str, Any],
) -> tuple[list[list[str]], dict[str, int]]:
    waves = dag.get("waves")
    if not isinstance(waves, list) or not waves:
        raise PortfolioIntegrityError("migration DAG waves must be a non-empty list")
    layout: list[list[str]] = []
    membership: dict[str, int] = {}
    for index, wave in enumerate(waves):
        if isinstance(wave, Mapping):
            declared = wave.get("wave_index", index)
            if isinstance(declared, bool) or not isinstance(declared, int) or declared != index:
                raise PortfolioIntegrityError(f"wave {index} has a non-canonical wave_index")
            raw_ids = wave.get("group_ids", wave.get("groups"))
        else:
            raw_ids = wave
        if not isinstance(raw_ids, list):
            raise PortfolioIntegrityError(f"wave {index} must contain a group_ids list")
        ids: list[str] = []
        for value in raw_ids:
            group_id = value.get("group_id") if isinstance(value, Mapping) else value
            if not isinstance(group_id, str) or group_id not in groups:
                raise PortfolioIntegrityError(f"wave {index} references an unknown group")
            if group_id in membership:
                raise PortfolioIntegrityError(f"group appears in multiple waves: {group_id}")
            membership[group_id] = index
            ids.append(group_id)
        layout.append(ids)
    missing = sorted(set(groups) - set(membership))
    if missing:
        raise PortfolioIntegrityError(f"migration DAG waves omit groups: {','.join(missing)}")
    return layout, membership


def dependencies_by_group(
    groups: Mapping[str, Mapping[str, Any]], membership: Mapping[str, int],
) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for group_id, group in groups.items():
        raw = group.get("dependencies", group.get("depends_on", []))
        if not isinstance(raw, list) or not all(isinstance(item, str) and item for item in raw):
            raise PortfolioIntegrityError(f"group {group_id} dependencies must be a string list")
        if len(raw) != len(set(raw)):
            raise PortfolioIntegrityError(f"group {group_id} dependencies must be unique")
        unknown = sorted(set(raw) - set(groups))
        if unknown:
            raise PortfolioIntegrityError(
                f"group {group_id} references unknown dependencies: {','.join(unknown)}"
            )
        result[group_id] = list(raw)
    return result


def bind_context(
    context: Mapping[str, Any], *,
    page_payloads: Mapping[str, Any] | None,
    page_root: str | Path | None,
    max_page_bytes: int,
    verified_group_proof: Any | None = None,
) -> dict[str, Any]:
    if verified_group_proof is not None and (page_payloads is not None or page_root is not None):
        raise PortfolioIntegrityError(
            "verified context group cannot be combined with payloads or page_root"
        )
    path = relative_path(context.get("path"), "context_pack.path")
    pages = context.get("pages", [])
    page_count = context.get("page_count", len(pages) if isinstance(pages, list) else None)
    if (
        not isinstance(pages, list)
        or isinstance(page_count, bool)
        or not isinstance(page_count, int)
        or page_count < 0
        or page_count != len(pages)
    ):
        raise PortfolioIntegrityError("context_pack page_count/pages binding is invalid")
    normalized_pages: list[dict[str, Any]] = []
    seen: set[str] = set()
    for page in pages:
        if not isinstance(page, Mapping):
            raise PortfolioIntegrityError("context_pack pages must be objects")
        page_path = relative_path(page.get("path"), "context_pack.pages.path")
        if page_path in seen:
            raise PortfolioIntegrityError(f"duplicate context page path: {page_path}")
        seen.add(page_path)
        if verified_group_proof is None:
            encoded = _page_bytes(
                page_path, page_payloads, page_root, max_page_bytes=max_page_bytes
            )
            digest, size = hashlib.sha256(encoded).hexdigest(), len(encoded)
        else:
            try:
                reference = _verified_context_page_reference(
                    verified_group_proof, str(page.get("page_id", "")), page_path,
                    max_page_bytes=max_page_bytes,
                )
            except (TypeError, ValueError) as error:
                raise PortfolioIntegrityError(str(error)) from error
            digest, size = reference["sha256"], reference["size_bytes"]
        _match(page.get("sha256"), digest, f"context page {page_path} sha256")
        _match_count(page, ("byte_count", "bytes", "size_bytes"), size, page_path)
        _match_count(page, ("token_count", "tokens", "estimated_tokens"), size, page_path)
        page_payload = {
            key: value
            for key, value in page.items()
            if key not in {
                "path", "sha256", "byte_count", "bytes", "size_bytes",
                "token_count", "tokens", "estimated_tokens", "token_estimator",
                "payload", "content",
            }
        }
        normalized_pages.append({
            **page_payload,
            "path": page_path,
            "sha256": digest,
            "byte_count": size,
            "token_count": size,
            "token_estimator": "utf8_bytes_upper_bound",
        })
    if normalized_pages:
        byte_count = sum(item["byte_count"] for item in normalized_pages)
        token_count = sum(item["token_count"] for item in normalized_pages)
        _match_count(context, ("byte_count", "bytes"), byte_count, path)
        _match_count(context, ("token_count", "tokens"), token_count, path)
    else:
        byte_count = _non_negative_count(context, ("byte_count", "bytes"), "context_pack byte count")
        token_count = _non_negative_count(context, ("token_count", "tokens"), "context_pack token count")
    payload = {
        **{
            key: value
            for key, value in context.items()
            if key not in {
                "path", "sha256", "byte_count", "bytes", "token_count", "tokens",
                "token_estimator", "page_count", "pages",
            }
        },
        "path": path,
        "byte_count": byte_count,
        "token_count": token_count,
        "token_estimator": "utf8_bytes_upper_bound",
        "page_count": page_count,
        "pages": normalized_pages,
    }
    return {**payload, "sha256": canonical_sha256(payload)}


def canonical_group(
    group: Mapping[str, Any], dependencies: Sequence[str], context: Mapping[str, Any] | None,
) -> tuple[dict[str, Any], str]:
    payload = {key: value for key, value in group.items() if key != "content_sha256"}
    payload.pop("depends_on", None)
    payload["dependencies"] = list(dependencies)
    if "context_pack" in payload or context is not None:
        payload["context_pack"] = dict(context) if context is not None else None
    return payload, canonical_sha256(payload)


def canonical_dag(dag: Mapping[str, Any], groups: Sequence[Mapping[str, Any]]) -> str:
    payload = {key: value for key, value in dag.items() if key != "dag_sha256"}
    payload["groups"] = [dict(group) for group in groups]
    return canonical_sha256(payload)


def _page_bytes(
    path: str, payloads: Mapping[str, Any] | None, root: str | Path | None,
    *, max_page_bytes: int,
) -> bytes:
    if payloads is not None and path in payloads:
        value = payloads[path]
        if isinstance(value, bytes):
            encoded = value
        elif isinstance(value, bytearray):
            encoded = bytes(value)
        elif isinstance(value, str):
            encoded = value.encode("utf-8")
        elif isinstance(value, (Mapping, list, tuple)):
            encoded = canonical_json_bytes(value)
        else:
            raise PortfolioIntegrityError(f"context page payload has unsupported type: {path}")
        if len(encoded) > max_page_bytes:
            raise PortfolioIntegrityError(f"context page exceeds byte budget: {path}")
        return encoded
    if root is None:
        raise PortfolioIntegrityError(f"context page payload is unavailable: {path}")
    requested_root = Path(root)
    if is_linklike(requested_root):
        raise PortfolioIntegrityError("context page_root must not be a link or junction")
    base = requested_root.resolve()
    target = (base / Path(*PurePosixPath(path).parts)).resolve()
    try:
        target.relative_to(base)
    except ValueError as error:
        raise PortfolioIntegrityError(f"context page escapes page_root: {path}") from error
    current = base
    for part in PurePosixPath(path).parts:
        current /= part
        if current.exists() and is_linklike(current):
            raise PortfolioIntegrityError(f"context page path contains a link: {path}")
    try:
        if target.stat().st_size > max_page_bytes:
            raise PortfolioIntegrityError(f"context page exceeds byte budget: {path}")
        with target.open("rb") as stream:
            encoded = stream.read(max_page_bytes + 1)
        if len(encoded) > max_page_bytes:
            raise PortfolioIntegrityError(f"context page exceeds byte budget: {path}")
        return encoded
    except PortfolioIntegrityError:
        raise
    except OSError as error:
        raise PortfolioIntegrityError(f"context page cannot be read: {path}") from error


def _match(actual: Any, expected: str, label: str) -> None:
    if actual is not None and actual != expected:
        raise PortfolioIntegrityError(f"{label} does not match the verified payload")


def _match_count(value: Mapping[str, Any], keys: Sequence[str], expected: int, label: str) -> None:
    for key in keys:
        if key not in value:
            continue
        actual = value[key]
        if isinstance(actual, bool) or not isinstance(actual, int) or actual < 0:
            raise PortfolioIntegrityError(f"{label} {key} must be a non-negative integer")
        if actual != expected:
            raise PortfolioIntegrityError(f"{label} {key} does not match the verified payload")


def _non_negative_count(value: Mapping[str, Any], keys: Sequence[str], label: str) -> int:
    for key in keys:
        if key in value:
            result = value[key]
            if isinstance(result, bool) or not isinstance(result, int) or result < 0:
                break
            return result
    raise PortfolioIntegrityError(f"{label} must be a non-negative integer")


__all__ = [
    "PortfolioIntegrityError", "bind_context", "canonical_dag", "canonical_group",
    "canonical_sha256", "dependencies_by_group", "groups_by_id", "positive",
    "relative_path", "wave_layout",
]
