from __future__ import annotations

from .project_test_target_proposal import valid_make_target


def literal_make_rule(line: str) -> tuple[list[str], list[str]] | None:
    if ";" in line or "::" in line or "&:" in line:
        return None
    left, separator, right = line.partition(":")
    if (
        not separator or ":" in right or "=" in left
        or "$" in left or "$" in right or "|" in right
    ):
        return None
    targets = left.split()
    prerequisites = right.split()
    if (
        not targets or not all(valid_make_target(item) for item in targets)
        or not all(valid_make_target(item) for item in prerequisites)
    ):
        return None
    return targets, prerequisites


def rule_mentions_target(line: str, target: str) -> bool:
    left, separator, _ = line.partition(":")
    return bool(separator and target in left.split())


__all__ = ["literal_make_rule", "rule_mentions_target"]
