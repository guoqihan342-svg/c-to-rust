from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
from typing import Callable

from .sandbox_contract import canonical_sha256


MAX_TOOL_BYTES = 512 * 1024 * 1024
MAX_RUSTUP_OUTPUT_BYTES = 16 * 1024
MAX_TOOLCHAIN_ENTRIES = 200_000
MAX_TOOLCHAIN_BYTES = 8 * 1024 * 1024 * 1024
RUST_TOOLS = ("cargo", "rustc", "rustdoc")
Runner = Callable[..., subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class ResolvedToolchain:
    cargo: Path
    rustc: Path
    rustdoc: Path
    root: Path | None
    sha256: str

    def paths(self) -> dict[str, Path]:
        return {"cargo": self.cargo, "rustc": self.rustc, "rustdoc": self.rustdoc}


def resolve_toolchain(
    cargo_binary: Path, project_root: Path | None = None, *, runner: Runner | None = None,
) -> ResolvedToolchain:
    cwd = Path(project_root or Path.cwd()).resolve(strict=True)
    if not cwd.is_dir():
        raise ValueError("toolchain project root is invalid")
    candidates = {"cargo": _resolved_file(cargo_binary)}
    for name in ("rustc", "rustdoc"):
        value = shutil.which(name)
        if not value:
            raise ValueError(f"{name} is unavailable")
        candidates[name] = _resolved_file(Path(value))
    rustup = _rustup_binary(candidates)
    if rustup is not None:
        proxy_flags = [_same_executable(path, rustup) for path in candidates.values()]
        if any(proxy_flags):
            if not all(proxy_flags):
                raise ValueError("mixed rustup and direct toolchain is untrusted")
            tools = _resolve_rustup_tools(rustup, cwd, runner or subprocess.run)
            root = _toolchain_root(tools, cwd)
            return _binding(tools, root)
    tools = {
        name: _named_tool(path, name) for name, path in candidates.items()
    }
    return _binding(tools, None)


def toolchain_sha256(
    tools: dict[str, Path], root: Path | None = None,
) -> str:
    if set(tools) != set(RUST_TOOLS):
        raise ValueError("sandbox toolchain is incomplete")
    hashes = {
        name: file_sha256(_named_tool(path, name))
        for name, path in sorted(tools.items())
    }
    if len(set(hashes.values())) != len(RUST_TOOLS):
        raise ValueError("sandbox toolchain executables are aliases")
    payload: dict[str, object] = {"tools": hashes}
    if root is not None:
        payload["root_tree_sha256"] = toolchain_tree_sha256(root)
    return canonical_sha256(payload)


def toolchain_tree_sha256(root: Path) -> str:
    resolved = root.resolve(strict=True)
    if not resolved.is_dir() or resolved == resolved.parent:
        raise ValueError("sandbox toolchain root is invalid")
    before = _tree_inventory(resolved)
    entries = []
    for item in before:
        relative, kind, _, _, _, _ = item
        path = resolved.joinpath(*Path(relative).parts)
        if kind == "directory":
            entries.append({"kind": kind, "path": relative})
        else:
            entries.append({
                "kind": kind,
                "path": relative,
                "sha256": _regular_file_sha256(path, executable=False),
            })
    if before != _tree_inventory(resolved):
        raise ValueError("sandbox toolchain changed while hashing")
    return canonical_sha256(entries)


def file_sha256(path: Path) -> str:
    return _regular_file_sha256(path, executable=True)


def _regular_file_sha256(path: Path, *, executable: bool) -> str:
    resolved = path.resolve(strict=True)
    before = resolved.stat()
    if (
        not resolved.is_file()
        or before.st_size > MAX_TOOL_BYTES
        or (executable and not os.access(resolved, os.X_OK))
    ):
        raise ValueError("sandbox tool is invalid")
    digest = hashlib.sha256()
    with resolved.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    after = resolved.stat()
    before_identity = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    after_identity = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    if before_identity != after_identity:
        raise ValueError("sandbox tool changed while hashing")
    return digest.hexdigest()


def _binding(tools: dict[str, Path], root: Path | None) -> ResolvedToolchain:
    return ResolvedToolchain(
        cargo=tools["cargo"],
        rustc=tools["rustc"],
        rustdoc=tools["rustdoc"],
        root=root,
        sha256=toolchain_sha256(tools, root),
    )


def _rustup_binary(candidates: dict[str, Path]) -> Path | None:
    embedded = {path for path in candidates.values() if path.name.lower() in {"rustup", "rustup.exe"}}
    if len(embedded) > 1:
        raise ValueError("multiple rustup proxies are untrusted")
    if embedded:
        return next(iter(embedded))
    value = shutil.which("rustup")
    sibling_names = ("rustup.exe",) if os.name == "nt" else ("rustup",)
    sibling_values = [
        candidate.parent / name
        for candidate in candidates.values()
        for name in sibling_names
        if (candidate.parent / name).is_file()
    ]
    possible = [Path(value)] if value else sibling_values
    resolved = {_resolved_file(path) for path in possible}
    if not resolved:
        return None
    if len(resolved) != 1:
        raise ValueError("multiple rustup commands are untrusted")
    rustup = next(iter(resolved))
    if rustup.name.lower() not in {"rustup", "rustup.exe"}:
        raise ValueError("rustup command is untrusted")
    return rustup


def _same_executable(left: Path, right: Path) -> bool:
    try:
        if left.samefile(right):
            return True
    except OSError:
        return False
    return file_sha256(left) == file_sha256(right)


def _resolve_rustup_tools(rustup: Path, cwd: Path, runner: Runner) -> dict[str, Path]:
    tools = {}
    environment = _rustup_environment()
    for name in RUST_TOOLS:
        try:
            completed = runner(
                [str(rustup), "which", name], cwd=cwd, env=environment,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                encoding="utf-8", errors="strict", timeout=10, check=False,
            )
        except (OSError, subprocess.SubprocessError, UnicodeError) as error:
            raise ValueError("rustup toolchain resolution failed") from error
        stdout = completed.stdout
        stderr = completed.stderr
        if (
            completed.returncode != 0
            or not isinstance(stdout, str)
            or not isinstance(stderr, str)
            or len(stdout.encode("utf-8")) > MAX_RUSTUP_OUTPUT_BYTES
            or len(stderr.encode("utf-8")) > MAX_RUSTUP_OUTPUT_BYTES
        ):
            raise ValueError("rustup toolchain resolution failed")
        value = stdout.rstrip("\r\n")
        if not value or value != value.strip() or "\n" in value or "\r" in value or "\x00" in value:
            raise ValueError("rustup tool path is untrusted")
        path = Path(value)
        if not path.is_absolute():
            raise ValueError("rustup tool path must be absolute")
        tools[name] = _named_tool(_resolved_file(path), name)
    if len(set(tools.values())) != len(RUST_TOOLS):
        raise ValueError("rustup resolved duplicate tools")
    return tools


def _toolchain_root(tools: dict[str, Path], project_root: Path) -> Path:
    parents = {path.parent for path in tools.values()}
    if len(parents) != 1:
        raise ValueError("rustup tools do not share one toolchain")
    bin_root = next(iter(parents))
    root = bin_root.parent.resolve(strict=True)
    if bin_root.name != "bin" or not root.is_dir() or root == root.parent:
        raise ValueError("rustup toolchain root is untrusted")
    if root == project_root or root.is_relative_to(project_root) or project_root.is_relative_to(root):
        raise ValueError("rustup toolchain overlaps project input")
    return root


def _rustup_environment() -> dict[str, str]:
    home = Path.home().resolve(strict=True)
    environment = {
        "HOME": str(home),
        "PATH": "",
        "RUSTUP_AUTO_INSTALL": "0",
        "RUSTUP_NO_UPDATE_CHECK": "1",
    }
    rustup_home = os.environ.get("RUSTUP_HOME")
    if rustup_home:
        requested = Path(rustup_home).expanduser()
        if not requested.is_absolute():
            raise ValueError("RUSTUP_HOME is untrusted")
        candidate = requested.resolve(strict=True)
        if not candidate.is_dir():
            raise ValueError("RUSTUP_HOME is untrusted")
        environment["RUSTUP_HOME"] = str(candidate)
    override = os.environ.get("RUSTUP_TOOLCHAIN")
    if override:
        if len(override) > 256 or any(char in override for char in "\r\n\x00"):
            raise ValueError("RUSTUP_TOOLCHAIN is untrusted")
        environment["RUSTUP_TOOLCHAIN"] = override
    return environment


def _resolved_file(path: Path) -> Path:
    resolved = path.resolve(strict=True)
    if not resolved.is_file():
        raise ValueError("sandbox tool is not a file")
    return resolved


def _named_tool(path: Path, name: str) -> Path:
    resolved = _resolved_file(path)
    if resolved.name.lower() not in {name, f"{name}.exe"}:
        raise ValueError(f"resolved {name} tool has an unexpected name")
    return resolved


def _tree_inventory(root: Path) -> list[tuple[str, str, int, int, int, int]]:
    result: list[tuple[str, str, int, int, int, int]] = []
    total_bytes = 0
    for current_text, directories, files in os.walk(
        root, topdown=True, followlinks=False
    ):
        current = Path(current_text)
        directories[:] = sorted(directories)
        for name, kind in [
            *((name, "directory") for name in directories),
            *((name, "file") for name in sorted(files)),
        ]:
            path = current / name
            if path.is_symlink() or not (
                path.is_dir() if kind == "directory" else path.is_file()
            ):
                raise ValueError("sandbox toolchain contains an unsupported entry")
            metadata = path.stat()
            size = metadata.st_size if kind == "file" else 0
            total_bytes += size
            if len(result) >= MAX_TOOLCHAIN_ENTRIES or total_bytes > MAX_TOOLCHAIN_BYTES:
                raise ValueError("sandbox toolchain exceeds the hashing bound")
            result.append((
                path.relative_to(root).as_posix(), kind, size,
                metadata.st_mtime_ns, metadata.st_dev, metadata.st_ino,
            ))
    return result


__all__ = [
    "ResolvedToolchain",
    "file_sha256",
    "resolve_toolchain",
    "toolchain_sha256",
    "toolchain_tree_sha256",
]
