from __future__ import annotations

import copy
import unittest

from validation.tools._project_migration_harness.artifacts import content_sha256
from validation.tools._project_migration_harness.native_link_actual_resolution import (
    resolve_traced_native_artifacts,
)
from validation.tools._project_migration_harness.native_link_order import (
    build_native_link_order_evidence,
    validate_native_link_order_evidence,
)
from validation.tools.project_migration_native_link_actual_test_support import (
    NativeLinkActualTestCase,
    archive,
    ar_member,
    elf,
    trace,
)


class NativeLinkOrderTests(NativeLinkActualTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.paths = {}
        for requirement in self.context["requirements"]:
            name = requirement["portable_name"]
            if requirement["library_format"] == "shared-library":
                guest = f"/usr/lib/{name}.4"
                self._write_guest(guest, elf(object_type=3, machine=62))
                value: str | tuple[str, str] = guest
            else:
                guest = f"/lib64/{name}"
                self._write_guest(
                    guest,
                    archive(ar_member("object.o/", elf(
                        object_type=1, machine=62,
                    ))),
                )
                value = (guest, "object.o")
            self.paths[requirement["requirement_id"]] = value
        self.order = [item["requirement_id"] for item in self.candidate["proposals"]]

    def evidence(self, link_trace: dict) -> dict:
        actual = resolve_traced_native_artifacts(
            link_trace, self.context, self.candidate, guest_roots=self.roots,
        )
        return build_native_link_order_evidence(
            link_trace, self.context, self.candidate, actual,
        )

    def test_one_linker_invocation_in_candidate_order_passes(self) -> None:
        link_trace = trace(*(self.paths[item] for item in self.order))
        actual = resolve_traced_native_artifacts(
            link_trace, self.context, self.candidate, guest_roots=self.roots,
        )
        result = build_native_link_order_evidence(
            link_trace, self.context, self.candidate, actual,
        )
        self.assertEqual("passed", result["status"])
        self.assertTrue(result["order_gate"])
        self.assertEqual([0], result["witness_diagnostic_ordinals"])
        self.assertEqual(
            result,
            validate_native_link_order_evidence(
                result, link_trace, self.context, self.candidate, actual,
            ),
        )

    def test_reverse_order_and_split_linker_invocations_block(self) -> None:
        reversed_trace = trace(*(self.paths[item] for item in reversed(self.order)))
        self.assertFalse(self.evidence(reversed_trace)["order_gate"])

        split = trace(*(self.paths[item] for item in self.order))
        for diagnostic, entry in enumerate(split["entries"]):
            entry["diagnostic_ordinal"] = diagnostic
            entry["link_ordinal"] = 0
        split["diagnostic_count"] = len(split["entries"])
        split["entry_set_sha256"] = content_sha256(split["entries"])
        result = self.evidence(split)
        self.assertEqual("blocked", result["status"])
        self.assertEqual([], result["witness_diagnostic_ordinals"])

    def test_duplicate_occurrences_preserve_a_valid_order_witness(self) -> None:
        first, second = self.order
        link_trace = trace(
            self.paths[first], self.paths[second], self.paths[first],
        )
        result = self.evidence(link_trace)
        self.assertTrue(result["order_gate"])
        self.assertEqual([[0, 2], [1]], result["diagnostics"][0][
            "requirement_link_ordinals"
        ])

    def test_report_and_bound_inputs_cannot_be_rewritten(self) -> None:
        link_trace = trace(*(self.paths[item] for item in self.order))
        actual = resolve_traced_native_artifacts(
            link_trace, self.context, self.candidate, guest_roots=self.roots,
        )
        result = build_native_link_order_evidence(
            link_trace, self.context, self.candidate, actual,
        )
        for field in ("candidate_order", "diagnostics", "report_sha256"):
            tampered = copy.deepcopy(result)
            if field == "candidate_order":
                tampered[field].reverse()
            elif field == "diagnostics":
                tampered[field][0]["order_match"] = False
            else:
                tampered[field] = "0" * 64
            with self.subTest(field=field), self.assertRaisesRegex(
                ValueError, "evidence_invalid",
            ):
                validate_native_link_order_evidence(
                    tampered, link_trace, self.context, self.candidate, actual,
                )


if __name__ == "__main__":
    unittest.main()
