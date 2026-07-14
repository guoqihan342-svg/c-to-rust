from __future__ import annotations

import base64
import binascii
import hashlib
from collections.abc import Mapping
from typing import Any

from .c_toolchain_runner import MAX_PROBE_STREAM_BYTES


EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()


def encoded_probe_streams(stdout: bytes, stderr: bytes) -> dict[str, Any]:
    return {
        **_encoded_stream("stdout", stdout),
        **_encoded_stream("stderr", stderr),
    }


def decode_probe_streams(value: Mapping[str, Any]) -> tuple[bytes, bytes]:
    return _decode_stream(value, "stdout"), _decode_stream(value, "stderr")


def reported_value(
    kind: str, stdout: bytes, stderr: bytes, family: str,
) -> str | None:
    out = stdout.decode("utf-8").strip()
    err = stderr.decode("utf-8").strip()
    if kind == "version":
        for line in (out + "\n" + err).splitlines():
            candidate = line.strip()
            if candidate:
                return _bounded_line(candidate)
        return None
    if kind == "target" and family == "msvc-compiler":
        for line in (out + "\n" + err).splitlines():
            marker = line.lower().rfind(" for ")
            if marker >= 0:
                return _bounded_line(line[marker + 5:].strip())
        return None
    if not out:
        return None
    lines = out.splitlines()
    return _bounded_line(lines[0]) if len(lines) == 1 else None


def _encoded_stream(prefix: str, value: bytes) -> dict[str, Any]:
    return {
        f"{prefix}_b64": base64.b64encode(value).decode("ascii"),
        f"{prefix}_sha256": hashlib.sha256(value).hexdigest(),
        f"{prefix}_size_bytes": len(value),
    }


def _decode_stream(value: Mapping[str, Any], prefix: str) -> bytes:
    encoded = value.get(f"{prefix}_b64")
    if type(encoded) is not str:
        raise ValueError("c_toolchain_probe_output_base64_invalid")
    try:
        raw = base64.b64decode(encoded.encode("ascii"), validate=True)
    except (UnicodeEncodeError, binascii.Error, ValueError) as error:
        raise ValueError("c_toolchain_probe_output_base64_invalid") from error
    if base64.b64encode(raw).decode("ascii") != encoded:
        raise ValueError("c_toolchain_probe_output_base64_invalid")
    size = value.get(f"{prefix}_size_bytes")
    if (
        type(size) is not int
        or not 0 <= size <= MAX_PROBE_STREAM_BYTES + 1
        or size != len(raw)
    ):
        raise ValueError("c_toolchain_probe_output_size_invalid")
    digest = value.get(f"{prefix}_sha256")
    if type(digest) is not str or digest != hashlib.sha256(raw).hexdigest():
        raise ValueError("c_toolchain_probe_output_sha256_invalid")
    return raw


def _bounded_line(value: str) -> str | None:
    if not value or "\x00" in value or len(value.encode("utf-8")) > 4096:
        return None
    return value


__all__ = [
    "EMPTY_SHA256", "decode_probe_streams", "encoded_probe_streams",
    "reported_value",
]
