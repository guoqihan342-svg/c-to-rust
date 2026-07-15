from __future__ import annotations


CARGO_METADATA_ARGS = (
    "metadata",
    "--no-deps",
    "--format-version",
    "1",
)
CARGO_METADATA_COMMAND = ("cargo", *CARGO_METADATA_ARGS)


__all__ = ["CARGO_METADATA_ARGS", "CARGO_METADATA_COMMAND"]
