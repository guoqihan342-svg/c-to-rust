from __future__ import annotations

import json
import re
import unittest

from validation.tools._project_migration_harness.artifacts import content_sha256
from validation.tools._project_migration_harness.native_link_actual_resolution import (
    resolve_traced_native_artifacts,
)
from validation.tools.project_migration_native_link_actual_test_support import (
    ITEM_KEYS,
    TOP_KEYS,
    NativeLinkActualTestCase,
    archive,
    ar_member,
    candidate,
    context,
    elf,
    strings,
    trace,
)


class NativeLinkActualObservationTests(NativeLinkActualTestCase):
    def test_observes_random_shared_version_and_static_archive(self) -> None:
        shared_guest = f"/usr/lib/lib{self.shared_stem}.so.3.1"
        static_guest = f"/lib64/lib{self.static_stem}.a"
        self._write_guest(
            shared_guest, elf(object_type=3, machine=62, suffix=b"shared"),
        )
        self._write_guest(
            static_guest,
            archive(
                ar_member(
                    "first.o/", elf(object_type=1, machine=62, suffix=b"one"),
                ),
                ar_member(
                    "second.o/", elf(object_type=1, machine=62, suffix=b"two"),
                ),
            ),
        )
        link_trace = trace(
            shared_guest,
            shared_guest,
            (static_guest, "first.o"),
            (static_guest, "second.o"),
        )

        first = resolve_traced_native_artifacts(
            link_trace, self.context, self.candidate, guest_roots=self.roots,
        )
        second = resolve_traced_native_artifacts(
            link_trace, self.context, self.candidate, guest_roots=self.roots,
        )

        self.assertEqual(first, second)
        self.assertEqual(TOP_KEYS, set(first))
        self.assertEqual(self.context["context_sha256"], first["context_sha256"])
        self.assertEqual(
            self.candidate["candidate_sha256"], first["candidate_sha256"],
        )
        self.assertEqual(
            link_trace["entry_set_sha256"], first["trace_entry_set_sha256"],
        )
        self.assertEqual("observed", first["status"])
        self.assertEqual(["symbols", "target-triple"], first["unverified_gates"])
        self.assertFalse(first["semantic_gate"])
        self.assertFalse(first["resolution_gate"])
        self.assertEqual(
            content_sha256({
                key: value for key, value in first.items()
                if key != "artifact_sha256"
            }),
            first["artifact_sha256"],
        )
        by_id = {item["requirement_id"]: item for item in first["requirements"]}
        shared = by_id[self._requirement_id(f"lib{self.shared_stem}.so.3")]
        static = by_id[self._requirement_id(f"lib{self.static_stem}.a")]
        self.assertEqual([0, 1], shared["trace_ordinals"])
        self.assertEqual([2, 3], static["trace_ordinals"])
        self.assertEqual("elf", shared["inspection"]["object_format"])
        self.assertEqual("shared-object", shared["inspection"]["object_kind"])
        self.assertEqual("unix-ar", static["inspection"]["object_format"])
        self.assertEqual("static-archive", static["inspection"]["object_kind"])
        self.assertTrue(all(
            item["status"] == "passed" for item in by_id.values()
        ))
        self.assertTrue(all(set(item) == ITEM_KEYS for item in by_id.values()))
        self.assertTrue(all(
            item["trace_entry_set_sha256"] == link_trace["entry_set_sha256"]
            for item in by_id.values()
        ))
        for value in strings(first):
            self.assertFalse(value.startswith(("/", "\\")))
            self.assertIsNone(re.match(r"[A-Za-z]:[\\/]", value))
        serialized = json.dumps(first, sort_keys=True)
        self.assertNotIn(shared_guest, serialized)
        self.assertNotIn(static_guest, serialized)
        self.assertNotEqual("resolved", first["status"])

    def test_missing_ambiguous_and_nonexact_static_trace_matches_block(self) -> None:
        shared_context = context(
            (f"lib{self.shared_stem}.so", "shared-library"),
        )
        shared_candidate = candidate(shared_context)
        file_name = f"lib{self.shared_stem}.so.8"
        ambiguous = trace(
            f"/usr/lib/{file_name}",
            f"/usr/lib/{file_name}",
            f"/lib/{file_name}",
        )
        result = resolve_traced_native_artifacts(
            ambiguous, shared_context, shared_candidate,
            guest_roots=self.roots,
        )
        item = result["requirements"][0]
        self.assertEqual("blocked", result["status"])
        self.assertEqual("native_link_trace_match_ambiguous", item["reason_code"])
        self.assertEqual([0, 1, 2], item["trace_ordinals"])
        self.assertIsNone(item["file_name"])
        self.assertIsNone(item["inspection"])

        missing = trace("/usr/lib/libunrelated-random-name.so")
        item = resolve_traced_native_artifacts(
            missing, shared_context, shared_candidate,
            guest_roots=self.roots,
        )["requirements"][0]
        self.assertEqual("native_link_trace_match_missing", item["reason_code"])
        self.assertEqual([], item["trace_ordinals"])

        static_context = context(
            (f"lib{self.static_stem}.a", "static-archive"),
        )
        item = resolve_traced_native_artifacts(
            trace(f"/usr/lib/lib{self.static_stem}.a.1"),
            static_context,
            candidate(static_context),
            guest_roots=self.roots,
        )["requirements"][0]
        self.assertEqual("native_link_trace_match_missing", item["reason_code"])

    def test_shared_trace_stays_in_original_portable_version_family(self) -> None:
        shared_context = context(
            (f"lib{self.shared_stem}.so.3", "shared-library"),
        )
        shared_candidate = candidate(shared_context)
        for suffix in (".so", ".so.3", ".so.3.7"):
            with self.subTest(suffix=suffix):
                guest = f"/usr/lib/lib{self.shared_stem}{suffix}"
                self._write_guest(guest, elf(object_type=3, machine=62))
                item = resolve_traced_native_artifacts(
                    trace(guest), shared_context, shared_candidate,
                    guest_roots=self.roots,
                )["requirements"][0]
                self.assertEqual("passed", item["status"])
        item = resolve_traced_native_artifacts(
            trace(f"/usr/lib/lib{self.shared_stem}.so.4"),
            shared_context,
            shared_candidate,
            guest_roots=self.roots,
        )["requirements"][0]
        self.assertEqual("native_link_trace_match_missing", item["reason_code"])
        self.assertEqual([], item["trace_ordinals"])

    def test_strategy_proposal_and_linux_format_boundaries_block(self) -> None:
        shared_context = context(
            (f"lib{self.shared_stem}.so", "shared-library"),
        )
        requirement_id = shared_context["requirements"][0]["requirement_id"]
        link_trace = trace(f"/usr/lib/lib{self.shared_stem}.so")
        cases = (
            (
                {requirement_id: {
                    "strategy": "defer",
                    "rustc_link_name": None,
                    "rustc_link_kind": None,
                }},
                "native_link_strategy_not_rustc_link_lib",
            ),
            (
                {requirement_id: {"rustc_link_name": "different"}},
                "native_link_proposal_name_mismatch",
            ),
            (
                {requirement_id: {"rustc_link_kind": "static"}},
                "native_link_proposal_kind_mismatch",
            ),
        )
        for overrides, reason in cases:
            with self.subTest(reason=reason):
                item = resolve_traced_native_artifacts(
                    link_trace,
                    shared_context,
                    candidate(shared_context, overrides),
                    guest_roots=self.roots,
                )["requirements"][0]
                self.assertEqual("blocked", item["status"])
                self.assertEqual(reason, item["reason_code"])
                self.assertIsNone(item["inspection"])

        import_context = context(
            (f"lib{self.static_stem}.a", "import-or-static-library"),
        )
        item = resolve_traced_native_artifacts(
            trace(f"/usr/lib/lib{self.static_stem}.a"),
            import_context,
            candidate(import_context),
            guest_roots=self.roots,
        )["requirements"][0]
        self.assertEqual("native_link_linux_format_unsupported", item["reason_code"])

        non_linux_name = context((self.shared_stem, "shared-library"))
        item = resolve_traced_native_artifacts(
            trace(f"/usr/lib/lib{self.shared_stem}.so"),
            non_linux_name,
            candidate(non_linux_name),
            guest_roots=self.roots,
        )["requirements"][0]
        self.assertEqual("native_link_portable_name_unsupported", item["reason_code"])


if __name__ == "__main__":
    unittest.main()
