from __future__ import annotations

from collections.abc import Mapping, Sequence
import re
from typing import Any

from .artifacts import content_sha256
from .native_object_validation import validate_native_object_inspection


NATIVE_TARGET_ABI_KIND = "native-target-abi-comparison"
MAX_NATIVE_ABI_INSPECTIONS = 4096
_TOP_KEYS = {
    "schema_version", "artifact_kind", "target_triple", "expected_abi",
    "checks", "inspection_count", "semantic_gate", "abi_gate",
    "report_sha256",
}
_ABI_KEYS = {"architecture", "machine", "class_bits", "endianness"}
_CHECK_KEYS = {"inspection", "mismatches", "abi_match"}
_COMPARE_FIELDS = ("machine", "class_bits", "endianness")
_TARGET = re.compile(
    r"[a-z0-9][a-z0-9_.+]{0,62}"
    r"(?:-[a-z0-9][a-z0-9_.+]{0,62}){2,4}\Z",
    re.ASCII,
)
_I386 = re.compile(r"i[3-6]86\Z", re.ASCII)
_ARM_LE = re.compile(r"arm(?:v[4-8][a-z0-9_]*)?\Z", re.ASCII)
_ARM_BE = re.compile(r"armeb(?:v[4-8][a-z0-9_]*)?\Z", re.ASCII)
_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)


def _profile(
    architecture: str, machine: int, class_bits: int, endianness: str,
) -> dict[str, Any]:
    return {
        "architecture": architecture,
        "machine": machine,
        "class_bits": class_bits,
        "endianness": endianness,
    }


_EXACT_ARCHES = {
    "x86_64": _profile("x86_64", 62, 64, "little"),
    "amd64": _profile("x86_64", 62, 64, "little"),
    "aarch64": _profile("aarch64", 183, 64, "little"),
    "arm64": _profile("aarch64", 183, 64, "little"),
    "aarch64_be": _profile("aarch64", 183, 64, "big"),
    "arm64be": _profile("aarch64", 183, 64, "big"),
    "armel": _profile("arm", 40, 32, "little"),
    "armhf": _profile("arm", 40, 32, "little"),
    "riscv32": _profile("riscv32", 243, 32, "little"),
    "riscv64": _profile("riscv64", 243, 64, "little"),
    "s390x": _profile("s390x", 22, 64, "big"),
    "powerpc": _profile("powerpc", 20, 32, "big"),
    "ppc": _profile("powerpc", 20, 32, "big"),
    "powerpcle": _profile("powerpc", 20, 32, "little"),
    "ppcle": _profile("powerpc", 20, 32, "little"),
    "powerpc64": _profile("powerpc64", 21, 64, "big"),
    "ppc64": _profile("powerpc64", 21, 64, "big"),
    "powerpc64le": _profile("powerpc64", 21, 64, "little"),
    "ppc64le": _profile("powerpc64", 21, 64, "little"),
    "mips": _profile("mips", 8, 32, "big"),
    "mipseb": _profile("mips", 8, 32, "big"),
    "mipsel": _profile("mips", 8, 32, "little"),
    "mips64": _profile("mips64", 8, 64, "big"),
    "mips64eb": _profile("mips64", 8, 64, "big"),
    "mips64el": _profile("mips64", 8, 64, "little"),
    "loongarch64": _profile("loongarch64", 258, 64, "little"),
}


def compare_native_target_abi(
    target_triple: str,
    inspections: Mapping[str, Any] | Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Compare validated, path-free ELF identities with a trusted cc target."""
    expected = _target_abi(target_triple)
    normalized = _normalize_inspections(inspections)
    checks = sorted(
        (_check(inspection, expected) for inspection in normalized),
        key=lambda item: item["inspection"]["inspection_sha256"],
    )
    identities = [item["inspection"]["inspection_sha256"] for item in checks]
    if len(identities) != len(set(identities)):
        raise ValueError("native_target_abi_duplicate_inspection")
    core = {
        "schema_version": 1,
        "artifact_kind": NATIVE_TARGET_ABI_KIND,
        "target_triple": target_triple,
        "expected_abi": expected,
        "checks": checks,
        "inspection_count": len(checks),
        "semantic_gate": False,
        "abi_gate": all(item["abi_match"] for item in checks),
    }
    return validate_native_target_abi({
        **core, "report_sha256": content_sha256(core),
    })


def validate_native_target_abi(value: Any) -> dict[str, Any]:
    """Strictly recompute target identity, object checks, gates, and hash."""
    if not isinstance(value, Mapping) or set(value) != _TOP_KEYS:
        raise ValueError("native_target_abi_schema_invalid")
    target_triple = value.get("target_triple")
    expected = _target_abi(target_triple)
    raw_expected = value.get("expected_abi")
    if (
        not isinstance(raw_expected, Mapping)
        or set(raw_expected) != _ABI_KEYS
        or dict(raw_expected) != expected
    ):
        raise ValueError("native_target_abi_expected_identity_invalid")
    raw_checks = value.get("checks")
    if (
        not isinstance(raw_checks, list)
        or not 0 < len(raw_checks) <= MAX_NATIVE_ABI_INSPECTIONS
    ):
        raise ValueError("native_target_abi_checks_invalid")
    checks = [_validate_check(item, expected) for item in raw_checks]
    identities = [item["inspection"]["inspection_sha256"] for item in checks]
    if identities != sorted(identities) or len(identities) != len(set(identities)):
        raise ValueError("native_target_abi_checks_noncanonical")
    abi_gate = all(item["abi_match"] for item in checks)
    if (
        value.get("schema_version") != 1
        or value.get("artifact_kind") != NATIVE_TARGET_ABI_KIND
        or type(value.get("inspection_count")) is not int
        or value.get("inspection_count") != len(checks)
        or value.get("semantic_gate") is not False
        or value.get("abi_gate") is not abi_gate
    ):
        raise ValueError("native_target_abi_summary_invalid")
    core = {
        "schema_version": 1,
        "artifact_kind": NATIVE_TARGET_ABI_KIND,
        "target_triple": target_triple,
        "expected_abi": expected,
        "checks": checks,
        "inspection_count": len(checks),
        "semantic_gate": False,
        "abi_gate": abi_gate,
    }
    claimed = value.get("report_sha256")
    if (
        type(claimed) is not str
        or _SHA256.fullmatch(claimed) is None
        or claimed != content_sha256(core)
    ):
        raise ValueError("native_target_abi_report_sha256_drift")
    return {**core, "report_sha256": claimed}


def _normalize_inspections(
    value: Mapping[str, Any] | Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    if isinstance(value, Mapping):
        raw = [value]
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        raw = list(value)
    else:
        raise ValueError("native_target_abi_inspections_invalid")
    if not 0 < len(raw) <= MAX_NATIVE_ABI_INSPECTIONS:
        raise ValueError("native_target_abi_inspections_invalid")
    return [validate_native_object_inspection(item) for item in raw]


def _check(
    inspection: dict[str, Any], expected: Mapping[str, Any],
) -> dict[str, Any]:
    mismatches = [
        field for field in _COMPARE_FIELDS
        if inspection[field] != expected[field]
    ]
    return {
        "inspection": inspection,
        "mismatches": mismatches,
        "abi_match": not mismatches,
    }


def _validate_check(
    value: Any, expected: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _CHECK_KEYS:
        raise ValueError("native_target_abi_check_schema_invalid")
    inspection = validate_native_object_inspection(value.get("inspection"))
    result = _check(inspection, expected)
    if (
        value.get("mismatches") != result["mismatches"]
        or value.get("abi_match") is not result["abi_match"]
    ):
        raise ValueError("native_target_abi_check_invalid")
    return result


def _target_abi(value: Any) -> dict[str, Any]:
    if (
        type(value) is not str
        or len(value) > 255
        or _TARGET.fullmatch(value) is None
    ):
        raise ValueError("native_target_abi_target_triple_invalid")
    parts = value.split("-")
    if parts[1:].count("linux") != 1:
        raise ValueError("native_target_abi_linux_target_required")
    expected = _arch_profile(parts[0])
    later_profiles = [_arch_profile(item) for item in parts[1:]]
    if expected is None:
        reason = "ambiguous" if any(later_profiles) else "unsupported"
        raise ValueError(f"native_target_abi_target_triple_{reason}")
    if any(later_profiles):
        raise ValueError("native_target_abi_target_triple_ambiguous")
    modifiers = parts[1:]
    if any(
        marker in item
        for item in modifiers
        for marker in ("x32", "ilp32", "n32")
    ):
        raise ValueError("native_target_abi_target_triple_ambiguous")
    if expected["class_bits"] == 64 and any("abi32" in item for item in modifiers):
        raise ValueError("native_target_abi_target_triple_ambiguous")
    if expected["class_bits"] == 32 and any("abi64" in item for item in modifiers):
        raise ValueError("native_target_abi_target_triple_ambiguous")
    return expected


def _arch_profile(value: str) -> dict[str, Any] | None:
    exact = _EXACT_ARCHES.get(value)
    if exact is not None:
        return dict(exact)
    if _I386.fullmatch(value):
        return _profile("i386", 3, 32, "little")
    if _ARM_LE.fullmatch(value):
        return _profile("arm", 40, 32, "little")
    if _ARM_BE.fullmatch(value):
        return _profile("arm", 40, 32, "big")
    return None


build_native_target_abi_report = compare_native_target_abi
validate_native_target_abi_report = validate_native_target_abi


__all__ = [
    "MAX_NATIVE_ABI_INSPECTIONS", "NATIVE_TARGET_ABI_KIND",
    "build_native_target_abi_report", "compare_native_target_abi",
    "validate_native_target_abi", "validate_native_target_abi_report",
]
