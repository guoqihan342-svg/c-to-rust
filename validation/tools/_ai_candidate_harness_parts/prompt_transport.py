from __future__ import annotations

import hashlib
from pathlib import Path


PROMPT_TRANSPORT_KIND = "opencode-file-attachment-v1"
PROMPT_FILE_MESSAGE = (
    "Use the attached prompt file as the complete task input and return only the required JSON object."
)
PROMPT_FILE_OPTION = "--file"
PROMPT_FILE_OPTION_STYLE = "equals"


def prompt_file_arguments(prompt_path: Path) -> list[str]:
    return [f"{PROMPT_FILE_OPTION}={prompt_path}", PROMPT_FILE_MESSAGE]


def prompt_transport_contract() -> dict[str, object]:
    return {
        "kind": PROMPT_TRANSPORT_KIND,
        "file_option": PROMPT_FILE_OPTION,
        "file_option_style": PROMPT_FILE_OPTION_STYLE,
        "message_sha256": hashlib.sha256(PROMPT_FILE_MESSAGE.encode("utf-8")).hexdigest(),
        "inline_prompt_in_argv": False,
    }
__all__ = [
    "PROMPT_FILE_MESSAGE",
    "PROMPT_TRANSPORT_KIND",
    "prompt_file_arguments",
    "prompt_transport_contract",
]
