from __future__ import annotations

import re

from validation.tools.replay_assertion_inventory import ASSERTION_MARKER_PREFIX


OPAQUE_GUARD_RE = re.compile(
    r"(?m)^(?P<prefix>[ \t]*if [^\r\n]+) != "
    r"(?P<suffix>[^\r\n]+ \{ panic!\(\""
    + re.escape(ASSERTION_MARKER_PREFIX)
    + r"[0-9a-f]{64}\"\); \})$"
)


def mutate_key_replay_assertion(source: str) -> str | None:
    mutated, count = OPAQUE_GUARD_RE.subn(
        r"\g<prefix> == \g<suffix>", source, count=1
    )
    if count == 1:
        return mutated
    mutated, count = re.subn(r"\bassert_eq\s*!", "assert_ne!", source, count=1)
    return mutated if count == 1 else None


__all__ = ["mutate_key_replay_assertion"]
