from __future__ import annotations

import copy
import unittest

from validation.tools._project_migration_harness.artifacts import content_sha256
from validation.tools._project_migration_harness.native_link_actual_resolution import (
    resolve_traced_native_artifacts,
)
from validation.tools._project_migration_harness.native_link_actual_validation import (
    validate_native_link_actual_resolution,
)
from validation.tools.project_migration_native_link_actual_test_support import (
    NativeLinkActualTestCase,
    archive,
    ar_member,
    elf,
    trace,
)


class NativeLinkActualValidationTests(NativeLinkActualTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.shared_guest = f"/usr/lib/lib{self.shared_stem}.so.3.2"
        self.static_guest = f"/lib64/lib{self.static_stem}.a"
        self._write_guest(
            self.shared_guest, elf(object_type=3, machine=62),
        )
        self._write_guest(
            self.static_guest,
            archive(ar_member("object.o/", elf(object_type=1, machine=62))),
        )
        self.link_trace = trace(
            self.shared_guest, (self.static_guest, "object.o"),
        )
        self.result = resolve_traced_native_artifacts(
            self.link_trace,
            self.context,
            self.candidate,
            guest_roots=self.roots,
        )

    def validate(self, value: dict) -> dict:
        return validate_native_link_actual_resolution(
            value, self.link_trace, self.context, self.candidate,
        )

    def test_reopens_complete_observation_and_blocked_result(self) -> None:
        self.assertEqual(self.result, self.validate(self.result))
        missing_trace = trace("/usr/lib/libunrelated.so")
        blocked = resolve_traced_native_artifacts(
            missing_trace, self.context, self.candidate,
            guest_roots=self.roots,
        )
        self.assertEqual("blocked", blocked["status"])
        self.assertEqual(
            blocked,
            validate_native_link_actual_resolution(
                blocked, missing_trace, self.context, self.candidate,
            ),
        )

    def test_top_level_input_bindings_and_hash_are_enforced(self) -> None:
        for key in (
            "context_sha256", "candidate_sha256", "trace_entry_set_sha256",
        ):
            tampered = copy.deepcopy(self.result)
            tampered[key] = content_sha256(["tampered", key])
            self._rehash(tampered)
            with self.subTest(key=key), self.assertRaisesRegex(
                ValueError, "summary_invalid",
            ):
                self.validate(tampered)

        tampered = copy.deepcopy(self.result)
        tampered["artifact_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "sha256_drift"):
            self.validate(tampered)

    def test_requirement_coverage_order_and_trace_binding_are_enforced(self) -> None:
        mutations = []
        missing = copy.deepcopy(self.result)
        missing["requirements"].pop()
        mutations.append(("coverage", missing))
        reversed_items = copy.deepcopy(self.result)
        reversed_items["requirements"].reverse()
        mutations.append(("order", reversed_items))
        item_trace = copy.deepcopy(self.result)
        item_trace["requirements"][0]["trace_entry_set_sha256"] = "0" * 64
        mutations.append(("trace", item_trace))
        for name, tampered in mutations:
            self._rehash(tampered)
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.validate(tampered)

    def test_item_state_file_ordinals_and_inspection_are_enforced(self) -> None:
        cases = []
        bad_status = copy.deepcopy(self.result)
        bad_status["requirements"][0]["status"] = "blocked"
        cases.append(("status", bad_status))
        bad_reason = copy.deepcopy(self.result)
        bad_reason["requirements"][0]["reason_code"] = "native_link_unknown"
        cases.append(("reason", bad_reason))
        bad_file = copy.deepcopy(self.result)
        bad_file["requirements"][0]["file_name"] = "../escape.so"
        cases.append(("file", bad_file))
        bad_ordinals = copy.deepcopy(self.result)
        bad_ordinals["requirements"][0]["trace_ordinals"] = [99]
        cases.append(("ordinal", bad_ordinals))
        bad_inspection = copy.deepcopy(self.result)
        bad_inspection["requirements"][0]["inspection"]["machine"] = 0
        cases.append(("inspection", bad_inspection))
        for name, tampered in cases:
            self._rehash(tampered)
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.validate(tampered)

    @staticmethod
    def _rehash(value: dict) -> None:
        projection = {
            key: item for key, item in value.items()
            if key != "artifact_sha256"
        }
        value["artifact_sha256"] = content_sha256(projection)


if __name__ == "__main__":
    unittest.main()
