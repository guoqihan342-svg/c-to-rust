from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any, Mapping

from .c2rust_project_baseline_cargo_manifest import (
    discover_manifests, library_call_path, update_manifest,
)
from .c2rust_project_baseline_exports import privatize_duplicate_exports
from .c2rust_project_baseline_repair import (
    MainSignature, add_deref_nullptr_allow, rename_single_public_main,
    repair_module_static_parameter_collisions,
)
from .c2rust_project_baseline_variadics import modernize_c2rust_variadics

MAX_RUST_SOURCE_BYTES = 32 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class CargoPreparation:
    manifests: tuple[Path, ...]
    wrappers: tuple[dict[str, Any], ...]
    repairs: tuple[dict[str, Any], ...]


def prepare_generated_cargo(
    generated_root: Path,
    source_working_directories: Mapping[str, str],
) -> CargoPreparation:
    root = Path(generated_root).resolve(strict=True)
    working_directories = _validated_working_directories(
        source_working_directories,
    )
    manifests = discover_manifests(root)
    manifest_roots = {manifest.parent: manifest for manifest in manifests}
    wrappers: list[dict[str, Any]] = []
    repairs: list[dict[str, Any]] = []
    sources = _rust_sources(root)
    for source in sources:
        package_root = _nearest_package(source, manifest_roots)
        raw = source.read_bytes()
        if len(raw) > MAX_RUST_SOURCE_BYTES:
            raise ValueError("c2rust_generated_rust_source_too_large")
        try:
            text = raw.decode("utf-8")
        except UnicodeError as error:
            raise ValueError("c2rust_generated_rust_source_not_utf8") from error
        variadic_repair = modernize_c2rust_variadics(text)
        static_repair = repair_module_static_parameter_collisions(
            variadic_repair.source,
        )
        rewritten = add_deref_nullptr_allow(static_repair.source)
        relative = source.relative_to(root).as_posix()
        digest = hashlib.sha256(relative.encode("utf-8")).hexdigest()[:16]
        replacement = f"c2rust_project_main_{digest}"
        main = rename_single_public_main(rewritten, replacement)
        signature: MainSignature | None = None
        if main is not None:
            rewritten, signature = main
        if rewritten != text:
            source.write_text(rewritten, encoding="utf-8", newline="\n")
        repair_entry: dict[str, Any] = {
            "source_path": relative,
            "deref_nullptr_allow": True,
            "renamed_statics": list(static_repair.renamed_statics),
            "rewritten_static_reference_count": (
                static_repair.rewritten_reference_count
            ),
            "va_list_type_rewrite_count": (
                variadic_repair.va_list_type_rewrite_count
            ),
            "va_list_adapter_rewrite_count": (
                variadic_repair.va_list_adapter_rewrite_count
            ),
            "public_main": signature is not None,
        }
        if signature is not None:
            try:
                source_working_directory = working_directories[relative]
            except KeyError as error:
                raise ValueError(
                    "c2rust_source_working_directory_missing"
                ) from error
            wrapper = _write_wrapper(
                root, package_root, source, signature, digest,
                source_working_directory,
            )
            wrappers.append(wrapper)
            repair_entry["renamed_main"] = signature.symbol
        repairs.append(repair_entry)
    export_repair = privatize_duplicate_exports({
        source.relative_to(root).as_posix(): source.read_text(encoding="utf-8")
        for source in sources
    })
    for relative, rewritten in export_repair.sources.items():
        source = root.joinpath(*Path(relative).parts)
        if source.read_text(encoding="utf-8") != rewritten:
            source.write_text(rewritten, encoding="utf-8", newline="\n")
    for repair in repairs:
        repair["privatized_duplicate_exports"] = list(
            export_repair.privatized.get(repair["source_path"], ())
        )
    if not wrappers:
        raise ValueError("c2rust_no_public_main")
    by_manifest: dict[Path, list[dict[str, Any]]] = {
        manifest: [] for manifest in manifests
    }
    for wrapper in wrappers:
        manifest = root.joinpath(*Path(wrapper["manifest_path"]).parts)
        by_manifest[manifest].append(wrapper)
    for manifest, selected in by_manifest.items():
        if selected:
            update_manifest(root, manifest, selected)
    return CargoPreparation(
        manifests, tuple(sorted(wrappers, key=lambda item: item["name"])),
        tuple(repairs),
    )


def _rust_sources(root: Path) -> tuple[Path, ...]:
    result = []
    for path in root.rglob("*.rs"):
        relative = path.relative_to(root)
        if "target" in relative.parts:
            continue
        if path.is_symlink() or not path.is_file():
            raise ValueError("c2rust_generated_rust_source_invalid")
        result.append(path.resolve(strict=True))
    if not result:
        raise ValueError("c2rust_generated_rust_source_missing")
    return tuple(sorted(result, key=lambda item: item.as_posix()))


def _nearest_package(source: Path, roots: dict[Path, Path]) -> Path:
    matches = [root for root in roots if source.is_relative_to(root)]
    if not matches:
        raise ValueError("c2rust_generated_source_without_manifest")
    return max(matches, key=lambda item: len(item.parts))


def _write_wrapper(
    generated_root: Path, package_root: Path, translated: Path,
    signature: MainSignature, digest: str,
    source_working_directory: str,
) -> dict[str, Any]:
    name = f"c2rust-baseline-{digest}"
    wrapper = package_root / "c2rust-baseline-bins" / f"{name}.rs"
    wrapper.parent.mkdir(parents=True, exist_ok=True)
    call_path = library_call_path(package_root, translated, signature.symbol)
    invocation = _main_invocation(call_path, signature)
    text = "\n".join((
        "#![allow(deref_nullptr)]",
        "fn main() {",
        *[f"    {line}" for line in invocation],
        "}",
        "",
    ))
    wrapper.write_text(text, encoding="utf-8", newline="\n")
    return {
        "name": name,
        "manifest_path": (package_root / "Cargo.toml").relative_to(
            generated_root
        ).as_posix(),
        "wrapper_path": wrapper.relative_to(generated_root).as_posix(),
        "translated_module_path": translated.relative_to(generated_root).as_posix(),
        "source_working_directory": source_working_directory,
        "renamed_main_symbol": signature.symbol,
        "library_call_path": call_path,
        "parameter_count": signature.parameter_count,
        "returns_value": signature.returns_value,
    }


def _validated_working_directories(
    value: Mapping[str, str],
) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise ValueError("c2rust_source_working_directories_invalid")
    result: dict[str, str] = {}
    for source, working_directory in value.items():
        if not _is_relative_posix_path(source, allow_dot=False):
            raise ValueError("c2rust_translated_source_path_invalid")
        if not _is_relative_posix_path(working_directory, allow_dot=True):
            raise ValueError("c2rust_source_working_directory_invalid")
        result[source] = working_directory
    return result


def _is_relative_posix_path(value: object, *, allow_dot: bool) -> bool:
    if not isinstance(value, str) or not value or "\\" in value:
        return False
    path = PurePosixPath(value)
    return (
        not path.is_absolute()
        and ".." not in path.parts
        and path.as_posix() == value
        and (allow_dot or value != ".")
    )


def _main_invocation(call_path: str, signature: MainSignature) -> tuple[str, ...]:
    if signature.parameter_count == 0:
        arguments: list[str] = []
        setup: list[str] = []
    elif signature.parameter_count in {2, 3}:
        setup = [
            "let c_args: Vec<std::ffi::CString> = std::env::args_os()",
            "    .map(|value| std::ffi::CString::new(value.to_string_lossy().as_bytes()).unwrap())",
            "    .collect();",
            "let mut argv: Vec<*mut std::os::raw::c_char> = c_args.iter()",
            "    .map(|value| value.as_ptr() as *mut std::os::raw::c_char)",
            "    .collect();",
            "argv.push(std::ptr::null_mut());",
        ]
        arguments = ["(argv.len() - 1) as _", "argv.as_mut_ptr() as _"]
        if signature.parameter_count == 3:
            arguments.append("std::ptr::null_mut()")
    elif signature.parameter_count <= 8:
        setup = []
        arguments = [
            "unsafe { std::mem::zeroed() }"
            for _ in range(signature.parameter_count)
        ]
    else:
        raise ValueError("c2rust_public_main_signature_unsupported")
    call = f"unsafe {{ {call_path}({', '.join(arguments)}) }}"
    if signature.returns_value:
        return tuple([*setup, f"let code = {call};", "std::process::exit(code as i32);"])
    return tuple([*setup, f"{call};"])


__all__ = ["CargoPreparation", "prepare_generated_cargo"]
