from __future__ import annotations

import os
from pathlib import Path
import shlex


def provider_command_prefix(command: str) -> list[str]:
    if not isinstance(command, str) or not command.strip():
        raise ValueError("OpenCode command must be non-empty")
    direct = Path(command)
    if direct.is_file():
        return [command]
    tokens = shlex.split(command, posix=os.name != "nt")
    normalized = [strip_matching_quotes(token) for token in tokens]
    if not normalized or any(not token for token in normalized):
        raise ValueError("OpenCode command could not be parsed")
    return normalized


def strip_matching_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


__all__ = ["provider_command_prefix", "strip_matching_quotes"]
