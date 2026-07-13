from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any


AGENT_RELATIVE_PATH = ".opencode/agents/c2rust-candidate.md"
MAX_AGENT_BYTES = 32_768


def verify_project_agent(repo_root: Path) -> dict[str, Any]:
    root = repo_root.resolve(strict=True)
    candidate = root / AGENT_RELATIVE_PATH
    if candidate.is_symlink():
        raise ValueError("project OpenCode agent must be a regular repository file")
    path = candidate.resolve(strict=True)
    try:
        path.relative_to(root)
    except ValueError as error:
        raise ValueError("project OpenCode agent escapes the repository") from error
    if not path.is_file():
        raise ValueError("project OpenCode agent must be a regular repository file")
    data = path.read_bytes()
    if not data or len(data) > MAX_AGENT_BYTES:
        raise ValueError("project OpenCode agent size is invalid")
    try:
        text = data.decode("utf-8")
    except UnicodeError as error:
        raise ValueError("project OpenCode agent must be UTF-8") from error
    normalized = text.replace("\r\n", "\n")
    if not normalized.startswith("---\n") or "\n---\n" not in normalized[4:]:
        raise ValueError("project OpenCode agent front matter is invalid")
    front_matter, body = normalized[4:].split("\n---\n", 1)
    parsed = _strict_front_matter(front_matter)
    checks = (
        parsed.get("mode") == "primary",
        parsed.get("permission") == {"*": "deny"},
        isinstance(parsed.get("description"), str),
        bool(parsed.get("description")),
        "Do not call tools" in body,
        "Return exactly one JSON object" in body,
        "Do not claim compilation" in body,
    )
    if not all(checks):
        raise ValueError("project OpenCode agent is not deny-all and JSON-only")
    return {
        "schema_version": 1,
        "status": "verified",
        "path": AGENT_RELATIVE_PATH,
        "sha256": hashlib.sha256(data).hexdigest(),
        "size_bytes": len(data),
        "agent": "c2rust-candidate",
        "mode": "primary",
        "tool_permission": "deny-all",
        "output_contract": "single-json-object",
    }


def _strict_front_matter(value: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    permission: dict[str, str] | None = None
    for line in value.splitlines():
        if not line or "\t" in line or line.rstrip() != line:
            raise ValueError("project OpenCode agent front matter is not canonical")
        if line.startswith("  "):
            if permission is None or not line.startswith('  "*": '):
                raise ValueError("project OpenCode agent permission map is invalid")
            key, separator, child = line.strip().partition(": ")
            if not separator or key != '"*"' or "*" in permission:
                raise ValueError("project OpenCode agent permission map is invalid")
            permission["*"] = child
            continue
        key, separator, child = line.partition(":")
        if not separator or key not in {"description", "mode", "permission"} or key in result:
            raise ValueError("project OpenCode agent front matter keys are invalid")
        if key == "permission":
            if child:
                raise ValueError("project OpenCode agent permission must be a mapping")
            permission = {}
            result[key] = permission
        else:
            if not child.startswith(" ") or not child[1:]:
                raise ValueError("project OpenCode agent front matter value is invalid")
            result[key] = child[1:]
    if set(result) != {"description", "mode", "permission"}:
        raise ValueError("project OpenCode agent front matter is incomplete")
    return result


__all__ = ["AGENT_RELATIVE_PATH", "verify_project_agent"]
