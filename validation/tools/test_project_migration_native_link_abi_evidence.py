from __future__ import annotations

import copy
import unittest

from validation.tools._project_migration_harness.artifacts import content_sha256
from validation.tools._project_migration_harness.native_link_abi_evidence import (
    build_native_link_abi_evidence,
    validate_native_link_abi_evidence,
)
from validation.tools._project_migration_harness.native_link_actual_resolution import (
    resolve_traced_native_artifacts,
)
from validation.tools.project_migration_native_link_actual_test_support import (
    NativeLinkActualTestCase,
    archive,
    ar_member,
    elf,
    trace,
)


class NativeLinkAbiEvidenceTests(NativeLinkActualTestCase):
    def setUp(self) -> None:
        super().setUp()
        values = []
        for requirement in self.context["requirements"]:
            if requirement["library_format"] == "shared-library":
                guest = f"/usr/lib/{requirement['portable_name']}.1"
                self._write_guest(guest, elf(object_type=3, machine=62))
                values.append(guest)
            else:
                guest = f"/lib64/{requirement['portable_name']}"
                self._write_guest(
                    guest,
                    archive(ar_member("object.o/", elf(
                        object_type=1, machine=62,
                    ))),
                )
                values.append((guest, "object.o"))
        self.link_trace = trace(*values)
        self.actual = resolve_traced_native_artifacts(
            self.link_trace, self.context, self.candidate,
            guest_roots=self.roots,
        )
        self.contract = _contract("x86_64-unknown-linux-gnu")

    def test_matching_trusted_target_passes_and_revalidates(self) -> None:
        result = build_native_link_abi_evidence(
            self.contract, self.link_trace, self.context,
            self.candidate, self.actual,
        )
        self.assertEqual("passed", result["status"])
        self.assertTrue(result["abi_gate"])
        self.assertFalse(result["semantic_gate"])
        self.assertEqual(
            result,
            validate_native_link_abi_evidence(
                result, self.contract, self.link_trace, self.context,
                self.candidate, self.actual,
            ),
        )

    def test_mismatched_target_and_tampering_block(self) -> None:
        mismatch = build_native_link_abi_evidence(
            _contract("aarch64-unknown-linux-gnu"),
            self.link_trace, self.context, self.candidate, self.actual,
        )
        self.assertEqual("blocked", mismatch["status"])
        self.assertFalse(mismatch["abi_gate"])

        valid = build_native_link_abi_evidence(
            self.contract, self.link_trace, self.context,
            self.candidate, self.actual,
        )
        tampered = copy.deepcopy(valid)
        tampered["abi_gate"] = False
        with self.assertRaisesRegex(ValueError, "evidence_invalid"):
            validate_native_link_abi_evidence(
                tampered, self.contract, self.link_trace, self.context,
                self.candidate, self.actual,
            )


def _contract(target: str) -> dict:
    binding = {
        "driver": {
            "basename": "cc", "family": "gnu-compiler", "sha256": "1" * 64,
        },
        "linker": {
            "basename": "ld", "family": "linker", "sha256": "2" * 64,
        },
        "target_triple": target,
    }
    return {"schema_version": 1, **binding, "binding_sha256": content_sha256(binding)}


if __name__ == "__main__":
    unittest.main()
