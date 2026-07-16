from __future__ import annotations

from .sandbox_environment import canonical_environment_items, cargo_guest_environment


_PROJECT_TOOL_ENVIRONMENT = (
    ("HOME", "/home/sandbox"),
    ("LANG", "C.UTF-8"),
    ("LC_ALL", "C.UTF-8"),
    ("PATH", "/toolchain/bin:/usr/bin:/bin"),
    ("TMPDIR", "/tmp"),
)


def canonical_project_tool_environment() -> tuple[tuple[str, str], ...]:
    """Return the canonical superset required by the shared bwrap builder."""
    return canonical_environment_items(cargo_guest_environment())


def restrict_project_tool_environment(argv: list[str]) -> list[str]:
    """Reduce the canonical Cargo environment to the fixed project-tool subset."""
    boundary = argv.index("--")
    expected = dict(_PROJECT_TOOL_ENVIRONMENT)
    result: list[str] = []
    observed: dict[str, str] = {}
    index = 0
    while index < boundary:
        if argv[index] != "--setenv":
            result.append(argv[index])
            index += 1
            continue
        if index + 2 >= boundary:
            raise ValueError("project test sandbox environment is invalid")
        key, value = argv[index + 1:index + 3]
        if key in expected:
            if key in observed or value != expected[key]:
                raise ValueError("project test sandbox environment is invalid")
            observed[key] = value
            result.extend(("--setenv", key, value))
        index += 3
    if observed != expected:
        raise ValueError("project test sandbox environment is invalid")
    return [*result, *argv[boundary:]]


__all__ = [
    "canonical_project_tool_environment", "restrict_project_tool_environment",
]
