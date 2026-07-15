from __future__ import annotations

import hashlib
import os
from pathlib import Path, PureWindowsPath

from .build_facts import is_absolute_any_platform, is_linklike


MAX_BOUND_DIRECTORY_ENTRIES = 16_384
MAX_BOUND_DIRECTORY_BYTES = 256 * 1024 * 1024


def directory_digest(root: Path) -> tuple[str, int, int]:
    root = root.resolve(strict=True)
    records: list[tuple[str, Path]] = []
    node_kinds = {root: "directory"}
    children: dict[Path, list[Path]] = {root: []}
    file_digests: dict[Path, bytes] = {}
    links: dict[Path, tuple[str, Path, str]] = {}
    entries = 0
    total_bytes = 0
    for current_text, directories, files in os.walk(
        root, topdown=True, followlinks=False
    ):
        current = Path(current_text)
        if node_kinds.get(current) != "directory":
            raise ValueError("linked_path_component")
        directory_entries: list[tuple[str, Path]] = []
        file_entries: list[tuple[str, Path]] = []
        traversable_directories: list[str] = []
        for name in sorted(directories):
            child = current / name
            if is_linklike(child):
                target_text, target, target_kind = _relative_internal_symlink(
                    root, child
                )
                links[child] = (target_text, target, target_kind)
                target_entries = (
                    directory_entries if target_kind == "directory" else file_entries
                )
                target_entries.append((f"link-{target_kind}", child))
                continue
            if not child.is_dir():
                raise ValueError("unsupported_directory_entry")
            traversable_directories.append(name)
            node_kinds[child] = "directory"
            children.setdefault(child, [])
            directory_entries.append(("directory", child))
        for name in sorted(files):
            child = current / name
            if is_linklike(child):
                target_text, target, target_kind = _relative_internal_symlink(
                    root, child
                )
                links[child] = (target_text, target, target_kind)
                target_entries = (
                    directory_entries if target_kind == "directory" else file_entries
                )
                target_entries.append((f"link-{target_kind}", child))
                continue
            if not child.is_file():
                raise ValueError("unsupported_directory_entry")
            node_kinds[child] = "file"
            file_entries.append(("file", child))
        directories[:] = sorted(traversable_directories)
        ordered_entries = [
            *sorted(directory_entries, key=lambda item: item[1].name),
            *sorted(file_entries, key=lambda item: item[1].name),
        ]
        for entry_kind, child in ordered_entries:
            entries += 1
            if entries > MAX_BOUND_DIRECTORY_ENTRIES:
                raise ValueError("directory_entry_limit_exceeded")
            records.append((entry_kind, child))
            children[current].append(child)
            if entry_kind in {"directory", "link-directory"}:
                continue
            if entry_kind == "file":
                size = child.stat().st_size
                total_bytes += size
                if total_bytes > MAX_BOUND_DIRECTORY_BYTES:
                    raise ValueError("directory_byte_limit_exceeded")
                file_digests[child] = bytes.fromhex(file_digest(child))

    content_digests = _node_content_digests(
        root,
        node_kinds=node_kinds,
        children=children,
        file_digests=file_digests,
        links=links,
    ) if links else {}

    digest = hashlib.sha256()
    for entry_kind, child in records:
        relative = child.relative_to(root).as_posix().encode("utf-8")
        if entry_kind == "directory":
            digest.update(b"D\0" + relative + b"\0")
            continue
        if entry_kind == "file":
            digest.update(b"F\0" + relative + b"\0")
            digest.update(file_digests[child])
            continue
        target_text, target, target_kind = links[child]
        target_relative = target.relative_to(root).as_posix().encode("utf-8")
        target_marker = b"D" if target_kind == "directory" else b"F"
        digest.update(b"L\0" + relative + b"\0")
        digest.update(target_text.encode("utf-8") + b"\0")
        digest.update(target_marker + b"\0" + target_relative + b"\0")
        digest.update(content_digests[target])
    return digest.hexdigest(), entries, total_bytes


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative_internal_symlink(root: Path, link: Path) -> tuple[str, Path, str]:
    if not link.is_symlink():
        raise ValueError("linked_path_component")
    target_text = os.readlink(link)
    windows_target = PureWindowsPath(target_text)
    if (
        not target_text
        or is_absolute_any_platform(target_text)
        or windows_target.drive
        or windows_target.root
    ):
        raise ValueError("linked_path_component")
    candidate = link.parent / target_text
    lexical_target = Path(os.path.abspath(candidate))
    try:
        lexical_target.relative_to(root)
    except ValueError as error:
        raise ValueError("linked_path_component") from error
    try:
        target = candidate.resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as error:
        raise ValueError("linked_path_component") from error
    try:
        target.relative_to(root)
    except ValueError as error:
        raise ValueError("linked_path_component") from error
    if target.is_dir():
        return target_text, target, "directory"
    if target.is_file():
        return target_text, target, "file"
    raise ValueError("linked_path_component")


def _node_content_digests(
    root: Path,
    *,
    node_kinds: dict[Path, str],
    children: dict[Path, list[Path]],
    file_digests: dict[Path, bytes],
    links: dict[Path, tuple[str, Path, str]],
) -> dict[Path, bytes]:
    nodes = set(node_kinds) | set(links)
    dependencies: dict[Path, set[Path]] = {}
    dependents: dict[Path, set[Path]] = {node: set() for node in nodes}
    for node in nodes:
        link = links.get(node)
        if link is not None:
            _target_text, target, target_kind = link
            if node_kinds.get(target) != target_kind:
                raise ValueError("linked_path_component")
            node_dependencies = {target}
        elif node_kinds.get(node) == "directory":
            node_dependencies = set(children.get(node, ()))
        elif node_kinds.get(node) == "file":
            node_dependencies = set()
        else:
            raise ValueError("linked_path_component")
        if not node_dependencies <= nodes:
            raise ValueError("linked_path_component")
        dependencies[node] = node_dependencies
        for dependency in node_dependencies:
            dependents[dependency].add(node)

    pending = {node: len(values) for node, values in dependencies.items()}
    ready = [node for node, count in pending.items() if count == 0]
    content_digests: dict[Path, bytes] = {}
    while ready:
        path = ready.pop()
        digest = hashlib.sha256()
        link = links.get(path)
        if link is not None:
            target_text, target, target_kind = link
            target_relative = target.relative_to(root).as_posix().encode("utf-8")
            target_marker = b"D" if target_kind == "directory" else b"F"
            digest.update(b"L\0" + target_text.encode("utf-8") + b"\0")
            digest.update(target_marker + b"\0" + target_relative + b"\0")
            digest.update(content_digests[target])
        elif node_kinds[path] == "directory":
            digest.update(b"D\0")
            for child in children.get(path, ()):
                marker = b"L" if child in links else (
                    b"D" if node_kinds.get(child) == "directory" else b"F"
                )
                digest.update(marker + b"\0" + child.name.encode("utf-8") + b"\0")
                digest.update(content_digests[child])
        else:
            digest.update(b"F\0" + file_digests[path])
        content_digests[path] = digest.digest()
        for dependent in dependents[path]:
            pending[dependent] -= 1
            if pending[dependent] == 0:
                ready.append(dependent)
    if len(content_digests) != len(nodes):
        raise ValueError("linked_path_component")
    return content_digests


__all__ = ["directory_digest", "file_digest"]
