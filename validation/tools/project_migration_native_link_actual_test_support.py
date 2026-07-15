from __future__ import annotations

import os
from pathlib import Path, PurePosixPath
import re
import struct
import subprocess
import tempfile
import unittest
import uuid

from validation.tools._project_migration_harness.artifacts import content_sha256
from validation.tools._project_migration_harness.build_ir import stable_build_id
from validation.tools._project_migration_harness.native_link_model import (
    build_native_link_candidate,
)


TOP_KEYS = {
    "schema_version", "context_sha256", "candidate_sha256",
    "trace_entry_set_sha256", "status", "requirements", "unverified_gates",
    "semantic_gate", "resolution_gate", "artifact_sha256",
}
ITEM_KEYS = {
    "requirement_id", "status", "reason_code", "file_name",
    "trace_ordinals", "trace_entry_set_sha256", "inspection",
}


class NativeLinkActualTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(
            prefix="native-link-actual-resolution-",
        )
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.roots = {
            guest: self.base / name
            for guest, name in (
                ("/usr", "guest-usr"),
                ("/lib", "guest-lib"),
                ("/lib64", "guest-lib64"),
            )
        }
        for root in self.roots.values():
            root.mkdir()
        self.shared_stem = "rnd" + uuid.uuid4().hex[:12]
        self.static_stem = "rnd" + uuid.uuid4().hex[:12]
        self.context = context(
            (f"lib{self.shared_stem}.so.3", "shared-library"),
            (f"lib{self.static_stem}.a", "static-archive"),
        )
        self.candidate = candidate(self.context)

    def _requirement_id(self, portable_name: str) -> str:
        return next(
            item["requirement_id"] for item in self.context["requirements"]
            if item["portable_name"] == portable_name
        )

    def _host_path(self, guest_path: str) -> Path:
        guest_root = next(
            root for root in ("/lib64", "/usr", "/lib")
            if guest_path.startswith(root + "/")
        )
        relative = PurePosixPath(guest_path).relative_to(guest_root)
        return self.roots[guest_root].joinpath(*relative.parts)

    def _write_guest(self, guest_path: str, data: bytes) -> Path:
        return self._write_path(self._host_path(guest_path), data)

    @staticmethod
    def _write_path(path: Path, data: bytes) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def _symlink_directory(self, link: Path, target: Path) -> None:
        try:
            link.symlink_to(target, target_is_directory=True)
        except (NotImplementedError, OSError) as error:
            if os.name != "nt":
                self.skipTest(
                    f"directory symlinks unavailable: {type(error).__name__}",
                )
            completed = subprocess.run(
                ["cmd.exe", "/d", "/c", "mklink", "/J", str(link), str(target)],
                check=False,
                capture_output=True,
                text=True,
            )
            if completed.returncode != 0:
                self.skipTest("directory symlinks and junctions unavailable")
        self.addCleanup(self._remove_directory_link, link)

    @staticmethod
    def _remove_directory_link(link: Path) -> None:
        try:
            if os.name == "nt":
                os.rmdir(link)
            else:
                link.unlink()
        except FileNotFoundError:
            pass


def context(*identities: tuple[str, str]) -> dict:
    requirements = []
    for portable_name, library_format in identities:
        identity = {
            "portable_name": portable_name,
            "library_format": library_format,
        }
        requirements.append({
            "requirement_id": stable_build_id("native-link-requirement", identity),
            **identity,
            "dependency_count": 1,
            "dependency_set_sha256": content_sha256([f"dep:{portable_name}"]),
            "consumer_target_count": 1,
            "consumer_target_set_sha256": content_sha256([
                f"target:{portable_name}",
            ]),
        })
    requirements.sort(key=lambda item: item["requirement_id"])
    result = {
        "schema_version": 1,
        "artifact_kind": "native-link-model-context",
        "status": "planning-required",
        "profile": "competition",
        "build_ir_binding": {
            "artifact": reference("facts/build-ir.json", "build-ir"),
            "semantic_sha256": content_sha256("semantic-build-ir"),
            "toolchain_abi_sha256": content_sha256("toolchain-abi"),
            "toolchain_record_count": 1,
            "abi_fact_count": 1,
        },
        "requirements": requirements,
        "requirement_count": len(requirements),
        "dependency_count": len(requirements),
        "model_policy": {
            "input_scope": "grouped-portable-native-identities",
            "allowed_strategies": ["defer", "ffi-boundary", "rustc-link-lib"],
            "absolute_paths_allowed": False,
            "model_may_claim_resolved": False,
        },
        "claim_boundary": {
            "artifact_role": "native-link-planning-context",
            "native_link_config_resolved": False,
            "cargo_executed": False,
            "semantic_gate": False,
            "translation_coverage_numerator": 0,
        },
    }
    result["context_sha256"] = content_sha256(result)
    return result


def candidate(value: dict, overrides: dict[str, dict] | None = None) -> dict:
    changes = {} if overrides is None else overrides
    proposals = []
    for requirement in value["requirements"]:
        portable_name = requirement["portable_name"]
        library_format = requirement["library_format"]
        proposal = {
            "requirement_id": requirement["requirement_id"],
            "strategy": "rustc-link-lib",
            "rustc_link_name": test_stem(portable_name),
            "rustc_link_kind": (
                "dylib" if library_format == "shared-library" else "static"
            ),
        }
        proposal.update(changes.get(requirement["requirement_id"], {}))
        proposals.append(proposal)
    return build_native_link_candidate(value, {
        "schema_version": 1,
        "artifact_kind": "native-link-model-response",
        "context_sha256": value["context_sha256"],
        "proposals": proposals,
    })


def test_stem(portable_name: str) -> str:
    matched = re.fullmatch(
        r"lib(?P<stem>[A-Za-z0-9][A-Za-z0-9_+.-]*)"
        r"(?:\.so(?:\.[0-9]+)*|\.a)",
        portable_name,
    )
    return matched.group("stem") if matched is not None else portable_name


def trace(*values: str | tuple[str, str]) -> dict:
    entries = []
    for ordinal, value in enumerate(values):
        base = {
            "ordinal": ordinal,
            "diagnostic_ordinal": 0,
            "link_ordinal": ordinal,
        }
        if isinstance(value, tuple):
            path, member = value
            entries.append({
                **base, "path": path, "archive_member": member,
            })
        else:
            entries.append({**base, "path": value})
    return {
        "schema_version": 2,
        "diagnostic_count": 1,
        "entries": entries,
        "entry_set_sha256": content_sha256(entries),
        "source_sha256": content_sha256(["test-trace-source", entries]),
        "semantic_gate": False,
    }


def reference(path: str, content: str) -> dict:
    return {
        "path": path,
        "sha256": content_sha256(content),
        "size_bytes": len(content),
    }


def elf(
    *, object_type: int, machine: int, class_bits: int = 64,
    suffix: bytes = b"",
) -> bytes:
    class_code = 1 if class_bits == 32 else 2
    ident = b"\x7fELF" + bytes((class_code, 1, 1, 0, 0)) + b"\x00" * 7
    if class_bits == 32:
        header = struct.pack(
            "<HHIIIIIHHHHHH",
            object_type, machine, 1, 0, 0, 0, 0, 52, 32, 0, 40, 0, 0,
        )
    else:
        header = struct.pack(
            "<HHIQQQIHHHHHH",
            object_type, machine, 1, 0, 0, 0, 0, 64, 56, 0, 64, 0, 0,
        )
    return ident + header + suffix


def ar_member(token: str, payload: bytes) -> bytes:
    encoded = token.encode("ascii")
    fields = (
        encoded.ljust(16, b" "), b"0".ljust(12, b" "),
        b"0".ljust(6, b" "), b"0".ljust(6, b" "),
        b"100644".ljust(8, b" "),
        str(len(payload)).encode("ascii").ljust(10, b" "), b"`\n",
    )
    return b"".join(fields) + payload + (b"\n" if len(payload) % 2 else b"")


def archive(*members: bytes) -> bytes:
    return b"!<arch>\n" + b"".join(members)


def strings(value: object):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from strings(item)
