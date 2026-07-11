from __future__ import annotations

import re


LOGICAL_CANDIDATE_PATH = "candidate.rs"
MAX_PATCH_BYTES = 128_000
HUNK_HEADER = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(?: .*)?$")


def apply_candidate_patch(source: str, patch: str) -> str:
    if len(patch.encode("utf-8")) > MAX_PATCH_BYTES:
        raise ValueError(f"repair patch exceeds {MAX_PATCH_BYTES} bytes")
    lines = patch.splitlines()
    if len(lines) < 3:
        raise ValueError("repair patch is incomplete")
    if lines[0] != f"--- a/{LOGICAL_CANDIDATE_PATH}" or lines[1] != f"+++ b/{LOGICAL_CANDIDATE_PATH}":
        raise ValueError("repair patch may target only candidate.rs")
    if any(line.startswith(("diff --git ", "rename from ", "rename to ", "Binary files ")) for line in lines):
        raise ValueError("repair patch cannot add, rename, or target other files")
    if any(line.startswith(("--- ", "+++ ")) for line in lines[2:]):
        raise ValueError("repair patch must contain exactly one file")

    original = source.splitlines()
    output: list[str] = []
    cursor = 0
    index = 2
    saw_hunk = False
    while index < len(lines):
        match = HUNK_HEADER.match(lines[index])
        if match is None:
            raise ValueError("repair patch requires valid unified-diff hunks")
        saw_hunk = True
        old_start = int(match.group(1))
        old_count = int(match.group(2) or "1")
        new_start = int(match.group(3))
        new_count = int(match.group(4) or "1")
        old_index = 0 if old_start == 0 else old_start - 1
        new_index = 0 if new_start == 0 else new_start - 1
        if old_index < cursor or old_index > len(original):
            raise ValueError("repair patch hunk range is outside candidate.rs")
        output.extend(original[cursor:old_index])
        if len(output) != new_index:
            raise ValueError("repair patch new hunk range is inconsistent")
        cursor = old_index
        index += 1
        consumed = 0
        produced = 0
        while index < len(lines) and not lines[index].startswith("@@ "):
            line = lines[index]
            if line.startswith("\\"):
                raise ValueError("repair patch no-newline markers are unsupported")
            if not line or line[0] not in {" ", "+", "-"}:
                raise ValueError("repair patch contains an invalid hunk line")
            marker, content = line[0], line[1:]
            if marker in {" ", "-"}:
                if cursor >= len(original) or original[cursor] != content:
                    raise ValueError("repair patch context does not match candidate.rs")
                cursor += 1
                consumed += 1
            if marker in {" ", "+"}:
                output.append(content)
                produced += 1
            index += 1
        if consumed != old_count or produced != new_count:
            raise ValueError("repair patch hunk counts do not match its content")
    if not saw_hunk:
        raise ValueError("repair patch requires at least one hunk")
    output.extend(original[cursor:])
    repaired = "\n".join(output)
    if source.endswith("\n"):
        repaired += "\n"
    if not repaired.strip():
        raise ValueError("repair patch produced an empty candidate")
    return repaired
