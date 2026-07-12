from __future__ import annotations

import re
import shlex
from pathlib import Path
from typing import Any

from .context_security import (
    canonical_json_bytes,
    logical_path,
    redact_text,
    resolve_under,
    sanitize_value,
    sensitive_key,
    sha256_bytes,
)
from .context_response_files import command_parse_failure_report, expand_response_files


def summarize_entry(
    entry: dict[str, Any],
    source_root: Path,
    working_directory: Path,
    entry_file: Path,
    spec: dict[str, Any],
    known_roots: tuple[str, ...],
) -> dict[str, Any]:
    try:
        argv = command_arguments(entry)
    except ValueError:
        command = entry.get("command")
        first_token = command.split(maxsplit=1)[0] if isinstance(command, str) and command.strip() else ""
        argv = [first_token] if first_token else []
        expanded_argv = None
        response_files = command_parse_failure_report(command if isinstance(command, str) else "")
    else:
        expanded_argv = None
        response_files = None
    compiler = compiler_name(argv)
    if response_files is None:
        expanded_argv, response_files = expand_response_files(
            argv,
            source_root=source_root,
            working_directory=working_directory,
            compiler=compiler,
        )
    parsed = (
        parse_arguments(expanded_argv, source_root, working_directory, known_roots)
        if expanded_argv is not None
        else {
            "compiler": compiler,
            "include_paths": [],
            "defines": [],
            "semantic_flags": [],
            "command_target": {},
        }
    )
    if response_files is not None:
        parsed["response_files"] = response_files
    parsed.update(
        {
            "entry_sha256": sha256_bytes(canonical_json_bytes(entry)),
            "source_file": logical_path(source_root, entry_file),
            "working_directory": logical_path(source_root, working_directory),
            "target_abi": target_abi_summary(spec, parsed.pop("command_target", {}), known_roots),
        }
    )
    return parsed


def command_arguments(entry: dict[str, Any]) -> list[str]:
    arguments = entry.get("arguments")
    if "arguments" in entry:
        if isinstance(arguments, list) and arguments and all(isinstance(item, str) for item in arguments):
            return list(arguments)
        raise ValueError("command_argument_parse_invalid")
    command = entry.get("command")
    if not isinstance(command, str) or not command.strip():
        raise ValueError("command_argument_parse_invalid")
    try:
        windows_command = bool(re.search(r"(?:^|\s)[A-Za-z]:\\", command))
        parsed = shlex.split(command, posix=not windows_command)
    except ValueError as error:
        raise ValueError("command_argument_parse_invalid") from error
    normalized = [item.strip('"') for item in parsed]
    if not normalized:
        raise ValueError("command_argument_parse_invalid")
    return normalized


def parse_arguments(
    argv: list[str],
    source_root: Path,
    working_directory: Path,
    known_roots: tuple[str, ...],
) -> dict[str, Any]:
    include_paths: list[dict[str, str]] = []
    defines: list[dict[str, str]] = []
    semantic_flags: set[str] = set()
    command_target: dict[str, Any] = {}
    redacted_defines = 0
    index = 0
    while index < len(argv):
        arg = argv[index]
        following = argv[index + 1] if index + 1 < len(argv) else None
        include_kind, include_value, consumed = include_argument(arg, following)
        if include_kind and include_value is not None:
            include_paths.append(
                {
                    "kind": include_kind,
                    "path": summarize_path(include_value, source_root, working_directory),
                }
            )
            index += consumed
        else:
            define_value, consumed = define_argument(arg, following)
            if define_value is not None:
                name, separator, value = define_value.partition("=")
                if sensitive_key(name):
                    redacted_defines += 1
                elif name:
                    defines.append(
                        {
                            "name": redact_text(name, known_roots),
                            "value": redact_text(value, known_roots) if separator else "1",
                        }
                    )
                index += consumed
            elif arg.startswith("--target="):
                command_target["triple_or_abi"] = redact_text(arg.split("=", 1)[1], known_roots)
            elif arg == "-target" and following:
                command_target["triple_or_abi"] = redact_text(following, known_roots)
                index += 1
            elif arg == "-m32":
                command_target["pointer_width"] = 32
                command_target["long_width"] = 32
                semantic_flags.add(arg)
            elif arg == "-m64":
                command_target["pointer_width"] = 64
                semantic_flags.add(arg)
            elif semantic_flag(arg):
                semantic_flags.add(redact_text(arg, known_roots))
        index += 1

    result: dict[str, Any] = {
        "compiler": compiler_name(argv),
        "include_paths": sorted(include_paths, key=lambda item: (item["kind"], item["path"])),
        "defines": sorted(defines, key=lambda item: (item["name"], item["value"])),
        "semantic_flags": sorted(semantic_flags),
        "command_target": command_target,
    }
    if redacted_defines:
        result["redacted_define_count"] = redacted_defines
    return result


def include_argument(arg: str, following: str | None) -> tuple[str | None, str | None, int]:
    for flag, kind in (("-isystem", "system"), ("-iquote", "quote"), ("-include", "forced")):
        if arg == flag:
            return kind, following, 1 if following is not None else 0
        if arg.startswith(flag) and len(arg) > len(flag):
            return kind, arg[len(flag):], 0
    if arg in {"-I", "/I"}:
        return "include", following, 1 if following is not None else 0
    if arg.startswith(("-I", "/I")) and len(arg) > 2:
        return "include", arg[2:], 0
    return None, None, 0


def define_argument(arg: str, following: str | None) -> tuple[str | None, int]:
    if arg in {"-D", "/D"}:
        return following, 1 if following is not None else 0
    if arg.startswith(("-D", "/D")) and len(arg) > 2:
        return arg[2:], 0
    return None, 0


def summarize_path(value: str, source_root: Path, working_directory: Path) -> str:
    try:
        return logical_path(source_root, resolve_under(source_root, value, base=working_directory))
    except (OSError, ValueError):
        return "<external-path>"


def semantic_flag(arg: str) -> bool:
    return arg.startswith(("-std=", "-O")) or arg in {
        "-ffreestanding",
        "-fno-builtin",
        "-fshort-enums",
        "-fshort-wchar",
        "-fsigned-char",
        "-funsigned-char",
        "-nostdinc",
        "-pthread",
    }


def compiler_name(argv: list[str]) -> str | None:
    for argument in argv:
        if "=" in argument and not argument.startswith(("-", "/")):
            continue
        return argument.replace("\\", "/").rsplit("/", 1)[-1]
    return None


def target_abi_summary(
    spec: dict[str, Any],
    command_target: dict[str, Any],
    known_roots: tuple[str, ...],
) -> dict[str, Any]:
    build_profile = spec.get("build_profile")
    boundary = spec.get("c_boundary")
    target: dict[str, Any] = {}
    if isinstance(build_profile, dict):
        declared_target = build_profile.get("target")
        if isinstance(declared_target, dict):
            target.update(sanitize_value(declared_target, known_roots))
        for key in ("target_triple", "abi"):
            value = build_profile.get(key)
            if isinstance(value, (str, int, bool)):
                target[key] = sanitize_value(value, known_roots)
    if isinstance(boundary, dict) and isinstance(boundary.get("target_abi_contract"), dict):
        target["c_contract"] = sanitize_value(boundary["target_abi_contract"], known_roots)
    target.update(command_target)
    return target


def declared_compile_context(
    spec: dict[str, Any],
    source_root: Path | None,
    known_roots: tuple[str, ...],
) -> dict[str, Any]:
    profile = spec.get("build_profile")
    if not isinstance(profile, dict):
        return {}
    includes = [
        redact_text(item, known_roots) if source_root is None else summarize_path(item, source_root, source_root)
        for item in profile.get("include_paths", [])
        if isinstance(item, str)
    ]
    defines: list[dict[str, str]] = []
    redacted = 0
    for item in profile.get("defines", []):
        if not isinstance(item, str):
            continue
        name, separator, value = item.partition("=")
        if sensitive_key(name):
            redacted += 1
        elif name:
            defines.append({"name": name, "value": redact_text(value, known_roots) if separator else "1"})
    result: dict[str, Any] = {
        "include_paths": sorted(set(includes)),
        "defines": sorted(defines, key=lambda item: (item["name"], item["value"])),
        "target_abi": target_abi_summary(spec, {}, known_roots),
    }
    if redacted:
        result["redacted_define_count"] = redacted
    oracle_build = profile.get("oracle_build")
    if isinstance(oracle_build, dict):
        closure_manifest = oracle_build.get("closure_manifest")
        if isinstance(closure_manifest, dict):
            result["oracle_build"] = {
                "schema_version": oracle_build.get("schema_version"),
                "mode": oracle_build.get("mode"),
                "closure_manifest": {
                    "path": redact_text(str(closure_manifest.get("path", "")), known_roots),
                    "sha256": closure_manifest.get("sha256"),
                },
            }
    return result
