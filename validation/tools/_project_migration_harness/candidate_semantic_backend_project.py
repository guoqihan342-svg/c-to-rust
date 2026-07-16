from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath
from typing import Any

from .artifacts import canonical_json_bytes, content_sha256
from .candidate_semantic_backend_inputs import (
    BackendInputs, ScalarFunction, ScalarType, SemanticBackendError,
)
from .candidate_semantic_stimuli import (
    held_out_scalar_cases, rust_negative_source, stimulus_binding,
)
from .candidate_semantic_scalar_render import (
    c_scalar_literal, rust_scalar_literal, rust_string,
)
from .sandbox_contract import contract_from_payload
from .sandbox_native_linker import resolve_native_linker_toolchain
from .sandbox_native_linker_contract import native_linker_contract


def materialize_behavior_project(
    inputs: BackendInputs, root: Path, verifier_nonce: bytes,
) -> dict[str, Any]:
    native_driver = _native_driver(inputs)
    _materialize_bound_inputs(inputs, root)
    signed_wrapping = "-fwrapv" in inputs.compile_arguments
    cases = held_out_scalar_cases(
        inputs.function, verifier_nonce, inputs.function_source,
        signed_wrapping=signed_wrapping,
    )
    wrapper = _c_behavior_wrapper(inputs.function, inputs.source_path, cases)
    wrapper_path = _write_wrapper(root, inputs.source_path, wrapper)
    _write(root / "Cargo.toml", _cargo_toml(build=True, negative=True))
    _write_linker_config(root, native_driver)
    build = _build_script(wrapper_path, inputs.compile_arguments, native_driver)
    _write(root / "build.rs", build)
    _write(root / "src/c_oracle.rs", _c_oracle_launcher())
    _write(root / "src/rust_replay.rs", _rust_behavior(inputs.function, cases))
    _write(root / "src/rust_negative.rs", rust_negative_source(inputs.function, cases))
    return _manifest(inputs, "behavior", {
        "case_count": len(cases),
        "stimulus": stimulus_binding(
            verifier_nonce, cases, signed_wrapping=signed_wrapping,
        ),
    })


def materialize_abi_project(inputs: BackendInputs, root: Path) -> dict[str, Any]:
    native_driver = _native_driver(inputs)
    _materialize_bound_inputs(inputs, root)
    wrapper = _c_abi_wrapper(inputs.function, inputs.source_path)
    wrapper_path = _write_wrapper(root, inputs.source_path, wrapper)
    _write(root / "Cargo.toml", _cargo_toml(build=True, negative=False))
    _write_linker_config(root, native_driver)
    build = _build_script(wrapper_path, inputs.compile_arguments, native_driver)
    _write(root / "build.rs", build)
    _write(root / "src/c_oracle.rs", _c_oracle_launcher())
    _write(root / "src/rust_replay.rs", _rust_abi(inputs.function))
    return _manifest(
        inputs, "abi-layout",
        {"check_count": 1 + len(inputs.function.parameters)},
    )


def materialize_unsafe_project(inputs: BackendInputs, root: Path) -> dict[str, Any]:
    (root / "src").mkdir(parents=True, exist_ok=True)
    (root / "src/candidate.rs").write_bytes(inputs.candidate_source)
    _write(root / "Cargo.toml", _cargo_toml(build=False, negative=False))
    _write(root / "Cargo.lock", _cargo_lock())
    _write(
        root / "src/lib.rs",
        "#![forbid(unsafe_code)]\n#[path = \"candidate.rs\"]\nmod candidate;\n",
    )
    return _manifest(inputs, "unsafe-alias", {})


def _materialize_bound_inputs(inputs: BackendInputs, root: Path) -> None:
    source = _target(root / "csrc", inputs.source_path)
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(inputs.source_bytes)
    for path, data in inputs.headers:
        target = _target(root / "csrc", path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    (root / "src").mkdir(parents=True, exist_ok=True)
    (root / "src/candidate.rs").write_bytes(inputs.candidate_source)
    _write(root / "Cargo.lock", _cargo_lock())


def _write_wrapper(root: Path, source_path: str, content: str) -> str:
    source = PurePosixPath(source_path)
    if any(char in source.name for char in '"\r\n'):
        raise SemanticBackendError("semantic_c_source_name_unsupported")
    wrapper = source.parent / "candidate_semantic_oracle.c"
    _write(_target(root / "csrc", wrapper.as_posix()), content)
    return f"/workspace/csrc/{wrapper.as_posix()}"


def _c_behavior_wrapper(
    function: ScalarFunction, source_path: str,
    cases: tuple[tuple[int, ...], ...],
) -> str:
    source_name = PurePosixPath(source_path).name
    lines = [f'#include "{source_name}"', "#include <stdio.h>", "int main(void) {"]
    for index, values in enumerate(cases):
        arguments = ", ".join(
            f"({kind.c_name}){c_scalar_literal(kind, value)}"
            for kind, value in zip(function.parameters, values, strict=True)
        )
        expression = f"{function.symbol}({arguments})"
        if function.result.signed:
            lines.append(
                f'    if (printf("{index}:%lld\\n", (long long)({expression})) < 0) return 74;'
            )
        else:
            lines.append(
                f'    if (printf("{index}:%llu\\n", (unsigned long long)({expression})) < 0) return 74;'
            )
    lines.extend(("    return 0;", "}", ""))
    return "\n".join(lines)


def _rust_behavior(
    function: ScalarFunction, cases: tuple[tuple[int, ...], ...],
) -> str:
    lines = ["#[path = \"candidate.rs\"]", "mod candidate;", "fn main() {"]
    for index, values in enumerate(cases):
        arguments = ", ".join(
            rust_scalar_literal(kind, value)
            for kind, value in zip(function.parameters, values, strict=True)
        )
        cast = "i128" if function.result.signed else "u128"
        lines.append(
            f'    println!("{index}:{{}}", candidate::{function.symbol}({arguments}) as {cast});'
        )
    lines.extend(("}", ""))
    return "\n".join(lines)


def _c_abi_wrapper(function: ScalarFunction, source_path: str) -> str:
    source_name = PurePosixPath(source_path).name
    values = [("result", function.result), *(
        (f"parameter-{index}", value)
        for index, value in enumerate(function.parameters)
    )]
    lines = [f'#include "{source_name}"', "#include <stdio.h>", "int main(void) {"]
    for label, kind in values:
        lines.append(
            f'    printf("{label}:%zu:%zu\\n", sizeof({kind.c_name}), _Alignof({kind.c_name}));'
        )
    lines.extend(("    return 0;", "}", ""))
    return "\n".join(lines)


def _rust_abi(function: ScalarFunction) -> str:
    parameters = ", ".join(item.rust_name for item in function.parameters)
    values = [("result", function.result), *(
        (f"parameter-{index}", value)
        for index, value in enumerate(function.parameters)
    )]
    lines = [
        "#[path = \"candidate.rs\"]", "mod candidate;", "fn main() {",
        f"    let _: fn({parameters}) -> {function.result.rust_name} = candidate::{function.symbol};",
    ]
    for label, kind in values:
        lines.append(
            f'    println!("{label}:{{}}:{{}}", std::mem::size_of::<{kind.rust_name}>(), '
            f'std::mem::align_of::<{kind.rust_name}>());'
        )
    lines.extend(("}", ""))
    return "\n".join(lines)


def _build_script(
    wrapper_path: str, arguments: tuple[str, ...], native_driver: str,
) -> str:
    standard = () if any(value.startswith("-std=") for value in arguments) else ("-std=c11",)
    values = [*standard, wrapper_path, "-o"]
    encoded_args = ", ".join(rust_string(value) for value in arguments)
    argument_line = (
        f"    for argument in [{encoded_args}] {{ command.arg(argument); }}"
        if arguments else ""
    )
    fixed_args = ", ".join(rust_string(value) for value in values)
    return "\n".join(item for item in (
        "use std::{env, path::PathBuf, process::Command};",
        "fn main() {",
        "    let output = PathBuf::from(env::var_os(\"OUT_DIR\").unwrap()).join(\"c-oracle\");",
        f"    let mut command = Command::new({rust_string(native_driver)});",
        argument_line,
        f"    command.args([{fixed_args}]).arg(&output);",
        "    let status = command.status().expect(\"C oracle compiler unavailable\");",
        "    assert!(status.success(), \"C oracle compilation failed\");",
        "    println!(\"cargo:rustc-env=C_ORACLE_BIN={}\", output.display());",
        "}", "",
    ) if item)


def _write_linker_config(root: Path, native_driver: str) -> None:
    content = "[target.'cfg(target_os = \"linux\")']\n"
    _write(root / ".cargo/config.toml", content + f"linker = {rust_string(native_driver)}\n")


def _native_driver(inputs: BackendInputs) -> str:
    try:
        expected = contract_from_payload(inputs.sandbox_contract)
        binding = resolve_native_linker_toolchain()
    except (OSError, ValueError) as error:
        raise SemanticBackendError("semantic_native_linker_unavailable") from error
    if (
        expected.native_linker is None
        or native_linker_contract(binding) != expected.native_linker
        or binding.resolved_driver_path.name != inputs.compiler_basename
        or binding.driver_sha256 != inputs.compiler_binary_sha256
        or binding.resolved_driver_path.stat().st_size
        != inputs.compiler_binary_size_bytes
    ):
        raise SemanticBackendError("semantic_original_compiler_drifted")
    return binding.resolved_driver_path.as_posix()


def _c_oracle_launcher() -> str:
    return "\n".join((
        "use std::process::{Command, exit};",
        "fn main() {",
        "    let status = Command::new(env!(\"C_ORACLE_BIN\")).status().unwrap();",
        "    exit(status.code().unwrap_or(125));",
        "}", "",
    ))


def _cargo_toml(*, build: bool, negative: bool) -> str:
    build_line = 'build = "build.rs"\n' if build else ""
    bins = "" if not build else "\n".join((
        "[[bin]]", 'name = "c-oracle"', 'path = "src/c_oracle.rs"', "",
        "[[bin]]", 'name = "rust-replay"', 'path = "src/rust_replay.rs"', "",
        *(('[[bin]]', 'name = "rust-negative"',
           'path = "src/rust_negative.rs"', "") if negative else ()),
    ))
    library = "\n[lib]\npath = \"src/lib.rs\"\n" if not build else ""
    return (
        "[package]\nname = \"candidate-semantic-adapter\"\nversion = \"0.0.0\"\n"
        f"edition = \"2021\"\n{build_line}\n{bins}{library}"
    )


def _cargo_lock() -> str:
    return "\n".join((
        "# This file is automatically @generated by Cargo.",
        "# It is not intended for manual editing.",
        "version = 3", "", "[[package]]",
        'name = "candidate-semantic-adapter"', 'version = "0.0.0"', "",
    ))


def _manifest(
    inputs: BackendInputs, purpose: str, extra: dict[str, Any],
) -> dict[str, Any]:
    value = {
        "schema_version": 1, "purpose": purpose,
        "input_sha256": inputs.input_sha256,
        "candidate_sha256": hashlib.sha256(inputs.candidate_source).hexdigest(),
        "c_source_sha256": hashlib.sha256(inputs.source_bytes).hexdigest(),
        "function": {
            "symbol_sha256": hashlib.sha256(inputs.function.symbol.encode()).hexdigest(),
            "result": inputs.function.result.rust_name,
            "parameters": [item.rust_name for item in inputs.function.parameters],
        },
        "compile_arguments_sha256": content_sha256(list(inputs.compile_arguments)),
        **extra,
    }
    value["manifest_sha256"] = content_sha256(value)
    return value


def write_manifest(root: Path, value: dict[str, Any]) -> str:
    data = canonical_json_bytes(value)
    (root / "semantic-manifest.json").write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def _target(root: Path, relative: str) -> Path:
    value = PurePosixPath(relative)
    if value.is_absolute() or ".." in value.parts or "\\" in relative:
        raise SemanticBackendError("semantic_materialization_path_invalid")
    return root.joinpath(*value.parts)


def _write(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8", newline="\n")


__all__ = [
    "materialize_abi_project", "materialize_behavior_project",
    "materialize_unsafe_project", "write_manifest",
]
