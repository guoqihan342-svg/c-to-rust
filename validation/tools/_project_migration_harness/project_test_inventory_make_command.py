from __future__ import annotations

import shlex


MAX_PROCESS_ARGUMENTS = 128


def parse_direct_make_test_command(line: str) -> tuple[list[str], str | None]:
    redirections = _validate_shell_boundary(line)
    try:
        argv = shlex.split(line, posix=True)
    except ValueError as error:
        raise ValueError("project_test_make_command_invalid") from error
    if (
        not argv or not argv[0] or len(argv) > MAX_PROCESS_ARGUMENTS + 3
        or any(len(item.encode("utf-8")) > 4096 for item in argv)
    ):
        raise ValueError("project_test_make_command_invalid")
    if redirections == 0:
        if len(argv) > MAX_PROCESS_ARGUMENTS + 1:
            raise ValueError("project_test_make_command_invalid")
        return argv, None
    if (
        redirections != 1 or len(argv) < 3 or argv[-2] != "<"
        or any("<" in item for item in argv[:-2])
    ):
        raise ValueError("project_test_make_stdin_redirection_invalid")
    command, stdin_path = argv[:-2], argv[-1]
    if (
        not command or not stdin_path
        or len(command) > MAX_PROCESS_ARGUMENTS + 1
    ):
        raise ValueError("project_test_make_stdin_redirection_invalid")
    return command, stdin_path


def _validate_shell_boundary(line: str) -> int:
    quote: str | None = None
    redirections = 0
    for index, character in enumerate(line):
        if quote == "'":
            quote = None if character == "'" else quote
        elif quote == '"':
            if character == '"':
                quote = None
            elif character in "$`\\":
                raise ValueError("project_test_make_shell_control_rejected")
        elif character in "'\"":
            quote = character
        elif character == "<":
            before = line[index - 1] if index else " "
            after = line[index + 1] if index + 1 < len(line) else " "
            if not before.isspace() or not after.isspace():
                raise ValueError("project_test_make_stdin_redirection_invalid")
            redirections += 1
        elif character in ";|&>()`$\\*?[]{}~":
            raise ValueError("project_test_make_shell_control_rejected")
        elif character == "#" and (index == 0 or line[index - 1].isspace()):
            raise ValueError("project_test_make_shell_control_rejected")
    if quote is not None or "\x00" in line:
        raise ValueError("project_test_make_command_invalid")
    return redirections


__all__ = ["parse_direct_make_test_command"]
