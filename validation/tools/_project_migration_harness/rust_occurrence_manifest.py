from __future__ import annotations

from collections.abc import Mapping
import hashlib
from typing import Any

from .artifacts import content_sha256
from . import _rust_link_product_archive as product_archive


MAGIC = b"C2R_OCCURRENCE_V1\x00"
MAX_OCCURRENCE_COUNT = 1_000_000


def occurrence_manifest_bytes(target: Mapping[str, Any]) -> bytes:
    occurrences = target.get("input_occurrences")
    if not isinstance(occurrences, list) or len(occurrences) > MAX_OCCURRENCE_COUNT:
        raise ValueError("rust_occurrence_manifest_occurrences_invalid")
    for ordinal, occurrence in enumerate(occurrences):
        if not isinstance(occurrence, Mapping) or occurrence.get("ordinal") != ordinal:
            raise ValueError("rust_occurrence_manifest_occurrence_invalid")
    return occurrence_manifest_from_commitment(
        len(occurrences), content_sha256(occurrences),
    )


def occurrence_manifest_from_commitment(
    occurrence_count: int, occurrence_order_sha256: str,
) -> bytes:
    if type(occurrence_count) is not int \
            or not 0 <= occurrence_count <= MAX_OCCURRENCE_COUNT:
        raise ValueError("rust_occurrence_manifest_count_invalid")
    if not isinstance(occurrence_order_sha256, str) \
            or len(occurrence_order_sha256) != 64 \
            or any(character not in "0123456789abcdef"
                   for character in occurrence_order_sha256):
        raise ValueError("rust_occurrence_manifest_digest_invalid")
    return (
        MAGIC + occurrence_count.to_bytes(8, "big")
        + bytes.fromhex(occurrence_order_sha256)
    )


def render_occurrence_manifest_static(target: Mapping[str, Any]) -> list[str]:
    marker = occurrence_manifest_bytes(target)
    identity = content_sha256({
        "target_id": target.get("target_id"),
        "occurrences": target.get("input_occurrences"),
    })[:24]
    if not all(character in "0123456789abcdef" for character in identity):
        raise ValueError("rust_occurrence_manifest_identity_invalid")
    module_name = f"__c2r_occurrence_manifest_{identity}"
    symbol_name = f"__C2R_OCCURRENCE_MANIFEST_{identity.upper()}"
    literal = "".join(f"\\x{byte:02x}" for byte in marker)
    return [
        f"mod {module_name} {{",
        "    #[used]",
        '    #[link_section = ".c2r_occurrence"]',
        "    #[no_mangle]",
        f"    pub static {symbol_name}: [u8; {len(marker)}] = *b\"{literal}\";",
        "}",
        "",
    ]


def inspect_occurrence_manifest(
    data: bytes, target: Mapping[str, Any], *, object_format: str,
) -> dict[str, Any]:
    marker = occurrence_manifest_bytes(target)
    return _inspect_marker(
        data, marker, len(target["input_occurrences"]),
        content_sha256(target["input_occurrences"]), object_format,
    )


def inspect_occurrence_manifest_commitment(
    data: bytes, *, occurrence_count: int, occurrence_order_sha256: str,
    object_format: str,
) -> dict[str, Any]:
    marker = occurrence_manifest_from_commitment(
        occurrence_count, occurrence_order_sha256,
    )
    return _inspect_marker(
        data, marker, occurrence_count, occurrence_order_sha256, object_format,
    )


def _inspect_marker(
    data: bytes, marker: bytes, occurrence_count: int,
    occurrence_order_sha256: str, object_format: str,
) -> dict[str, Any]:
    matches = []
    if object_format == "unix-ar":
        for ordinal, (name, payload) in enumerate(_archive_payloads(data)):
            count = payload.count(marker)
            if count:
                matches.extend((ordinal, name, payload) for _ in range(count))
    elif object_format == "elf":
        matches.extend((None, b"", data) for _ in range(data.count(marker)))
    else:
        raise ValueError("rust_occurrence_manifest_format_unsupported")
    if len(matches) != 1:
        raise ValueError("rust_occurrence_manifest_match_ambiguous")
    ordinal, name, payload = matches[0]
    core = {
        "occurrence_count": occurrence_count,
        "occurrence_order_sha256": occurrence_order_sha256,
        "manifest_sha256": hashlib.sha256(marker).hexdigest(),
        "container_format": object_format,
        "archive_member_ordinal": ordinal,
        "archive_member_name_sha256": (
            hashlib.sha256(name).hexdigest() if ordinal is not None else None
        ),
        "archive_member_payload_sha256": (
            hashlib.sha256(payload).hexdigest() if ordinal is not None else None
        ),
        "semantic_gate": False,
        "translation_coverage_numerator": 0,
    }
    return {**core, "inspection_sha256": content_sha256(core)}


def _archive_payloads(data: bytes) -> list[tuple[bytes, bytes]]:
    candidates = [
        product_archive._normalize_special_fields(data),
        product_archive._normalize_gnu_long_name_padding(data),
        data,
    ]
    failure = None
    for candidate in candidates:
        if candidate is None:
            continue
        try:
            objects = product_archive._archive_objects(candidate)
        except ValueError as error:
            failure = error
            continue
        if objects:
            return [
                (name, payload) for name, payload, _identity in objects
                if name != b"lib.rmeta"
            ]
    raise ValueError("rust_occurrence_manifest_archive_invalid") from failure


__all__ = [
    "MAGIC", "MAX_OCCURRENCE_COUNT", "inspect_occurrence_manifest",
    "inspect_occurrence_manifest_commitment", "occurrence_manifest_bytes",
    "occurrence_manifest_from_commitment", "render_occurrence_manifest_static",
]
