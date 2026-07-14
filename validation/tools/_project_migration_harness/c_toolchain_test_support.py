from __future__ import annotations

import os
from pathlib import Path
import subprocess
from typing import Any

from .artifacts import content_sha256
from .c_toolchain_probe import (
    MAX_PROBE_STREAM_BYTES, PROBE_TIMEOUT_SECONDS, ProbeExecution,
)


class FakeToolchain:
    def __init__(self, root: Path) -> None:
        suffix = ".exe" if os.name == "nt" else ""
        self.paths = {
            name: self._executable(root / name / f"{name}{suffix}", name.encode())
            for name in ("gcc", "ld", "clang", "distcc", "ar")
        }
        self.calls: list[list[str]] = []
        self.version = "13.3.0"
        self.special: dict[tuple[str, ...], ProbeExecution] = {}

    def resolver(
        self, token: str, *, environment: dict[str, str],
    ) -> str | None:
        self.last_environment = dict(environment)
        candidate = Path(token)
        if candidate.is_absolute() and candidate in self.paths.values():
            return str(candidate)
        return str(self.paths[token]) if token in self.paths else None

    def runner(
        self, argv: list[str], **kwargs: object,
    ) -> subprocess.CompletedProcess[bytes] | ProbeExecution:
        self.calls.append(list(argv))
        assert Path(argv[0]).is_absolute()
        assert kwargs["timeout_seconds"] == PROBE_TIMEOUT_SECONDS
        assert kwargs["max_output_bytes"] == MAX_PROBE_STREAM_BYTES
        arguments = tuple(argv[1:])
        if arguments in self.special:
            return self.special[arguments]
        tool = Path(argv[0]).stem.lower()
        outputs = {
            ("gcc", ("--version",)): f"gcc (Ubuntu) {self.version}\n".encode(),
            ("gcc", ("-dumpmachine",)): b"x86_64-linux-gnu\n",
            ("gcc", ("-print-sysroot",)): b"",
            ("gcc", ("-print-prog-name=ld",)): b"ld\n",
            ("ld", ("--version",)): b"GNU ld 2.42\n",
            ("ar", ("--version",)): b"GNU ar 2.42\n",
            ("clang", ("--no-default-config", "--version")): (
                b"clang version 18.1.3\n"
            ),
            ("clang", ("--no-default-config", "-print-target-triple")): (
                b"x86_64-linux-gnu\n"
            ),
            ("clang", ("--no-default-config", "-print-resource-dir")): (
                b"/opt/llvm/lib/clang/18\n"
            ),
            ("clang", ("--no-default-config", "-print-prog-name=ld")): b"ld\n",
        }
        return subprocess.CompletedProcess(
            argv, 0, outputs.get((tool, arguments), b""), b"",
        )

    @staticmethod
    def _executable(path: Path, content: bytes) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        path.chmod(0o755)
        return path.resolve()


def resign(payload: dict[str, Any]) -> dict[str, Any]:
    core = {
        key: value for key, value in payload.items()
        if key != "evidence_sha256"
    }
    payload["evidence_sha256"] = content_sha256(core)
    return payload


__all__ = ["FakeToolchain", "resign"]
