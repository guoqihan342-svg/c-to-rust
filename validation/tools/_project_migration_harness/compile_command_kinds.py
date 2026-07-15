from __future__ import annotations

from collections.abc import Sequence


_CLANG_FRONTEND_MODES = {"-cc1", "-cc1as"}


def is_clang_frontend_job(argv: Sequence[str]) -> bool:
    if len(argv) < 2 or argv[1] not in _CLANG_FRONTEND_MODES:
        return False
    executable = argv[0].replace("\\", "/").rsplit("/", 1)[-1].lower()
    if executable.endswith(".exe"):
        executable = executable[:-4]
    return (
        executable in {"clang", "clang++", "clang-cl"}
        or executable.startswith("clang-")
    )


__all__ = ["is_clang_frontend_job"]
