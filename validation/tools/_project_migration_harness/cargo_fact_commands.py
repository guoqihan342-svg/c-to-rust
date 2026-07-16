from __future__ import annotations


CARGO_METADATA_ARGS = (
    "metadata",
    "--no-deps",
    "--format-version",
    "1",
    "--locked",
    "--offline",
)
CARGO_METADATA_COMMAND = ("cargo", *CARGO_METADATA_ARGS)
CARGO_BUILD_ARGS = (
    "build", "--workspace", "--all-targets", "--all-features",
    "--offline", "--locked", "--message-format=json", "--jobs", "1",
)
CARGO_BUILD_COMMAND = ("cargo", *CARGO_BUILD_ARGS)


__all__ = [
    "CARGO_BUILD_ARGS", "CARGO_BUILD_COMMAND",
    "CARGO_METADATA_ARGS", "CARGO_METADATA_COMMAND",
]
