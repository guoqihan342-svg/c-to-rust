from __future__ import annotations

import hashlib
import re
from pathlib import Path

from .build_facts import file_binding, is_linklike, resolve_repository_path


MAX_MAKEFILE_BYTES = 2 * 1024 * 1024
MAX_MANIFESTS = 64
MAX_TOTAL_BYTES = 8 * 1024 * 1024
_MAKEFILE_PRECEDENCE = ("GNUmakefile", "makefile", "Makefile")
_INCLUDE = re.compile(r"^include\s+(.+)$", re.ASCII)
_UNSUPPORTED_DIRECTIVE = re.compile(
    r"^(?:-include|sinclude|ifeq|ifneq|ifdef|ifndef|else|endif|"
    r"define|endef|load)(?:\s|$)",
    re.ASCII,
)
_UNSUPPORTED_SPECIAL = re.compile(
    r"^(?:\.RECIPEPREFIX|\.ONESHELL|\.SECONDEXPANSION|"
    r"\.EXPORT_ALL_VARIABLES|\.NOEXPORT|\.SUFFIXES)\s*(?::|[+:?]?=)",
    re.ASCII,
)
_VARIABLE_DIRECTIVE = re.compile(
    r"(?:^|[\s:])(?:export|unexport|override|private|undefine|vpath)(?:\s|$)",
    re.ASCII,
)
_ASSIGNMENT_OPERATOR = re.compile(
    r"(?:\?=|\+=|!=|:::=|::=|:=|(?<![<>=!])=)", re.ASCII,
)
_DYNAMIC_EXPANSIONS = (
    "$(MAKE)", "${MAKE}", "$(shell", "${shell", "$(file", "${file",
    "$(eval", "${eval", "$(guile", "${guile", "$(info", "${info",
    "$(warning", "${warning", "$(error", "${error",
)


def load_static_make_closure(
    root: Path, build: Path,
) -> tuple[list[dict], dict[str, list[str]]]:
    manifests: list[dict] = []
    sources: dict[str, list[str]] = {}
    active: set[str] = set()
    total_bytes = 0

    def visit(path: Path) -> None:
        nonlocal total_bytes
        resolved = resolve_repository_path(root, path)
        relative = resolved.relative_to(root).as_posix()
        if relative in active:
            raise ValueError("project_test_make_include_cycle")
        if relative in sources:
            raise ValueError("project_test_make_include_duplicate")
        if len(manifests) >= MAX_MANIFESTS or is_linklike(resolved):
            raise ValueError("project_test_make_include_closure_invalid")
        binding = file_binding(root, resolved, max_bytes=MAX_MAKEFILE_BYTES)
        data = resolved.read_bytes()
        if (
            len(data) != binding["size_bytes"]
            or hashlib.sha256(data).hexdigest() != binding["sha256"]
        ):
            raise ValueError("project_test_make_manifest_drifted")
        total_bytes += len(data)
        if total_bytes > MAX_TOTAL_BYTES:
            raise ValueError("project_test_make_include_closure_invalid")
        lines = data.decode("utf-8-sig", errors="strict").splitlines()
        manifests.append(binding)
        sources[relative] = lines
        active.add(relative)
        for include in literal_make_includes(lines):
            visit(resolve_repository_path(root, include, base=build))
        active.remove(relative)

    visit(_select_makefile(build))
    return manifests, sources


def literal_make_includes(lines: list[str]) -> list[str]:
    result: list[str] = []
    for raw in lines:
        line = strip_make_comment(raw).strip()
        if not line or raw.startswith("\t"):
            continue
        reject_dynamic_make_line(raw, line)
        match = _INCLUDE.fullmatch(line)
        if match is None:
            continue
        for value in match.group(1).split():
            if (
                not value or any(character in value for character in "$%*?[]~\\")
                or value.startswith("/") or ".." in Path(value).parts
            ):
                raise ValueError("project_test_make_include_closure_invalid")
            result.append(value)
    return result


def reject_dynamic_make_line(raw: str, line: str) -> None:
    if raw.rstrip().endswith("\\"):
        raise ValueError("project_test_make_continuation_unsupported")
    if (
        _UNSUPPORTED_DIRECTIVE.match(line)
        or _UNSUPPORTED_SPECIAL.match(line)
        or _VARIABLE_DIRECTIVE.search(line)
        or _ASSIGNMENT_OPERATOR.search(line)
        or "&:" in line
        or "$" in line
        or any(token in line for token in _DYNAMIC_EXPANSIONS)
    ):
        raise ValueError("project_test_make_dynamic_semantics_unsupported")


def strip_make_comment(line: str) -> str:
    escaped = False
    for index, character in enumerate(line):
        if character == "#" and not escaped:
            return line[:index]
        escaped = character == "\\" and not escaped
        if character != "\\":
            escaped = False
    return line


def _select_makefile(build: Path) -> Path:
    for name in _MAKEFILE_PRECEDENCE:
        candidate = build / name
        if candidate.exists():
            if is_linklike(candidate) or not candidate.is_file():
                break
            return candidate
    raise ValueError("project_test_make_entry_makefile_invalid")


__all__ = [
    "MAX_MAKEFILE_BYTES", "MAX_MANIFESTS", "MAX_TOTAL_BYTES",
    "load_static_make_closure", "reject_dynamic_make_line",
    "strip_make_comment",
]
