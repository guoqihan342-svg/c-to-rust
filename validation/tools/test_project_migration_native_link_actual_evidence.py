from __future__ import annotations

import copy
import unittest

from validation.tools._project_migration_harness.ledger_security import LedgerError
from validation.tools._project_migration_harness.native_link_actual_evidence import (
    persist_native_link_actual_evidence,
    reopen_native_link_actual_evidence,
)
from validation.tools.project_migration_native_link_actual_test_support import (
    NativeLinkActualTestCase,
    candidate,
    context,
    elf,
    trace,
)


class NativeLinkActualEvidenceTests(NativeLinkActualTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.link_context = context(
            (f"lib{self.shared_stem}.so", "shared-library"),
        )
        self.link_candidate = candidate(self.link_context)
        self.guest = f"/usr/lib/lib{self.shared_stem}.so.2"
        self.host = self._write_guest(
            self.guest, elf(object_type=3, machine=62, suffix=b"initial"),
        )
        self.link_trace = trace(self.guest)
        self.out_root = self.base / "run"
        self.ledger = self.out_root / "state" / "project.sqlite3"
        self.ledger.parent.mkdir(parents=True)
        self.binding = persist_native_link_actual_evidence(
            self.link_trace,
            self.link_context,
            self.link_candidate,
            out_root=self.out_root,
            guest_roots=self.roots,
        )

    def reopen(self, binding: dict | None = None) -> dict:
        return reopen_native_link_actual_evidence(
            self.ledger,
            self.binding if binding is None else binding,
            self.link_trace,
            self.link_context,
            self.link_candidate,
            guest_roots=self.roots,
        )

    def test_persists_and_recomputes_actual_artifact(self) -> None:
        result = self.reopen()
        self.assertEqual("observed", result["status"])
        self.assertEqual("passed", result["requirements"][0]["status"])
        self.assertFalse(result["semantic_gate"])
        self.assertFalse(result["resolution_gate"])

    def test_changed_native_object_fails_recompute(self) -> None:
        self.host.write_bytes(
            elf(object_type=3, machine=62, suffix=b"replacement"),
        )
        with self.assertRaisesRegex(LedgerError, "recompute drifted"):
            self.reopen()

    def test_context_candidate_trace_and_binding_tamper_fail_closed(self) -> None:
        fields = (
            "context_sha256", "candidate_sha256", "trace_entry_set_sha256",
        )
        for field in fields:
            tampered = copy.deepcopy(self.binding)
            tampered[field] = "0" * 64
            with self.subTest(field=field), self.assertRaisesRegex(
                ValueError, "summary_invalid",
            ):
                self.reopen(tampered)

        tampered = copy.deepcopy(self.binding)
        tampered["artifact"]["sha256"] = "0" * 64
        with self.assertRaises((LedgerError, ValueError)):
            self.reopen(tampered)

        tampered = copy.deepcopy(self.binding)
        tampered["status"] = "blocked"
        with self.assertRaisesRegex(LedgerError, "binding drifted"):
            self.reopen(tampered)


if __name__ == "__main__":
    unittest.main()
