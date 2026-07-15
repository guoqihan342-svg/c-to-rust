from __future__ import annotations

import json
import os
from pathlib import Path
import re
import tomllib
from typing import Any, Mapping


MAX_MANIFEST_BYTES = 4 * 1024 * 1024
_HEADER = re.compile(r"^\s*(\[\[?[^\]]+\]\]?)\s*(?:#.*)?$")


def discover_manifests(root: Path) -> tuple[Path, ...]:
    values = []
    for path in root.rglob("Cargo.toml"):
        if path.is_symlink() or "target" in path.relative_to(root).parts:
            continue
        if not path.is_file() or path.stat().st_size > MAX_MANIFEST_BYTES:
            raise ValueError("c2rust_generated_cargo_manifest_invalid")
        parse_manifest(path)
        values.append(path.resolve(strict=True))
    if not values:
        raise ValueError("c2rust_generated_cargo_manifest_missing")
    return tuple(sorted(values, key=lambda item: item.as_posix()))


def update_manifest(
    generated_root: Path, manifest: Path,
    wrappers: list[dict[str, Any]],
) -> None:
    text = manifest.read_text(encoding="utf-8")
    parsed = parse_manifest(manifest)
    package = parsed.get("package")
    if not isinstance(package, dict) or not isinstance(package.get("name"), str):
        raise ValueError("c2rust_generated_cargo_package_invalid")
    text = _disable_auto_bins(text)
    text = _drop_bin_tables(text)
    additions = []
    for wrapper in sorted(wrappers, key=lambda item: item["name"]):
        path = _relative_path(
            manifest.parent,
            generated_root.joinpath(*Path(wrapper["wrapper_path"]).parts),
        )
        additions.extend((
            "[[bin]]", f"name = {json.dumps(wrapper['name'])}",
            f"path = {json.dumps(path)}", "",
        ))
    manifest.write_text(
        text.rstrip() + "\n\n" + "\n".join(additions),
        encoding="utf-8", newline="\n",
    )
    parse_manifest(manifest)


def library_call_path(
    package_root: Path, translated: Path, symbol: str,
) -> str:
    manifest = parse_manifest(package_root / "Cargo.toml")
    package = manifest.get("package")
    library = manifest.get("lib", {})
    if not isinstance(package, dict) or not isinstance(library, dict):
        raise ValueError("c2rust_generated_library_target_missing")
    package_name = package.get("name")
    crate_name = library.get("name", package_name)
    lib_path = library.get("path", "src/lib.rs")
    if not isinstance(crate_name, str) or not isinstance(lib_path, str):
        raise ValueError("c2rust_generated_library_target_invalid")
    crate_name = crate_name.replace("-", "_")
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", crate_name):
        raise ValueError("c2rust_generated_library_name_invalid")
    crate_root = (package_root / lib_path).resolve(strict=True)
    if not crate_root.is_file() or not translated.is_relative_to(crate_root.parent):
        raise ValueError("c2rust_generated_module_outside_library")
    relative = translated.relative_to(crate_root.parent)
    if relative == Path(crate_root.name):
        modules: list[str] = []
    else:
        modules = list(relative.with_suffix("").parts)
        if modules and modules[-1] == "mod":
            modules.pop()
    if any(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", part) is None for part in modules):
        raise ValueError("c2rust_generated_module_path_invalid")
    return "::".join((crate_name, *modules, symbol))


def parse_manifest(path: Path) -> dict[str, Any]:
    try:
        value = tomllib.loads(path.read_text(encoding="utf-8"))
    except (UnicodeError, tomllib.TOMLDecodeError) as error:
        raise ValueError("c2rust_generated_cargo_manifest_invalid") from error
    if not isinstance(value, dict):
        raise ValueError("c2rust_generated_cargo_manifest_invalid")
    return value


def _disable_auto_bins(text: str) -> str:
    lines = text.splitlines()
    package_index = next(
        (index for index, line in enumerate(lines) if line.strip() == "[package]"),
        None,
    )
    if package_index is None:
        raise ValueError("c2rust_generated_cargo_package_missing")
    end = next(
        (index for index in range(package_index + 1, len(lines))
         if _HEADER.match(lines[index])), len(lines),
    )
    for index in range(package_index + 1, end):
        if re.match(r"^\s*autobins\s*=", lines[index]):
            lines[index] = "autobins = false"
            return "\n".join(lines) + "\n"
    lines.insert(package_index + 1, "autobins = false")
    return "\n".join(lines) + "\n"


def _drop_bin_tables(text: str) -> str:
    lines = text.splitlines(keepends=True)
    starts = [
        index for index, line in enumerate(lines) if line.strip() == "[[bin]]"
    ]
    remove: set[int] = set()
    for start in starts:
        end = next(
            (index for index in range(start + 1, len(lines))
             if _HEADER.match(lines[index].rstrip("\r\n"))), len(lines),
        )
        chunk = "".join(lines[start:end])
        try:
            tables = tomllib.loads(chunk).get("bin")
        except tomllib.TOMLDecodeError as error:
            raise ValueError("c2rust_generated_bin_table_invalid") from error
        if not isinstance(tables, list) or len(tables) != 1:
            raise ValueError("c2rust_generated_bin_table_invalid")
        remove.update(range(start, end))
    return "".join(line for index, line in enumerate(lines) if index not in remove)


def _relative_path(base: Path, target: Path) -> str:
    return Path(os.path.relpath(target, base)).as_posix()


__all__ = [
    "discover_manifests", "library_call_path", "parse_manifest",
    "update_manifest",
]
