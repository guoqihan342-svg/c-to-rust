from __future__ import annotations

import copy
from pathlib import Path
import unittest
from unittest import mock

from validation.tools._project_migration_harness import native_link_actual_paths
from validation.tools._project_migration_harness.artifacts import content_sha256
from validation.tools._project_migration_harness.native_link_actual_resolution import (
    resolve_traced_native_artifacts,
)
from validation.tools.project_migration_native_link_actual_test_support import (
    NativeLinkActualTestCase,
    archive,
    ar_member,
    candidate,
    context,
    elf,
    trace,
)


class NativeLinkActualResolutionTests(NativeLinkActualTestCase):
    def test_fixed_mapping_contract_and_unmapped_guest_root(self) -> None:
        link_context = context((f"lib{self.shared_stem}.so", "shared-library"))
        link_candidate = candidate(link_context)
        link_trace = trace(f"/toolchain/lib/lib{self.shared_stem}.so")
        item = resolve_traced_native_artifacts(
            link_trace, link_context, link_candidate, guest_roots=self.roots,
        )["requirements"][0]
        self.assertEqual("native_link_guest_root_unsupported", item["reason_code"])

        invalid_roots = (
            {"/usr": self.roots["/usr"]},
            {**self.roots, "/opt": self.base / "opt"},
            {**self.roots, "/usr": Path("relative-root")},
            {**self.roots, "/usr": str(self.roots["/usr"])},
        )
        for roots in invalid_roots:
            with self.subTest(keys=sorted(roots)):
                with self.assertRaisesRegex(ValueError, "guest_roots_invalid"):
                    resolve_traced_native_artifacts(
                        link_trace, link_context, link_candidate,
                        guest_roots=roots,
                    )

    def test_missing_and_non_regular_actual_files_block(self) -> None:
        link_context = context((f"lib{self.shared_stem}.so", "shared-library"))
        link_candidate = candidate(link_context)
        guest = f"/usr/lib/lib{self.shared_stem}.so"
        link_trace = trace(guest)
        item = resolve_traced_native_artifacts(
            link_trace, link_context, link_candidate, guest_roots=self.roots,
        )["requirements"][0]
        self.assertEqual("native_link_actual_artifact_missing", item["reason_code"])

        host = self._host_path(guest)
        host.mkdir(parents=True)
        item = resolve_traced_native_artifacts(
            link_trace, link_context, link_candidate, guest_roots=self.roots,
        )["requirements"][0]
        self.assertEqual(
            "native_link_actual_artifact_not_regular", item["reason_code"],
        )

    def test_cross_root_symlink_is_allowed_but_escape_is_blocked(self) -> None:
        link_context = context((f"lib{self.shared_stem}.so", "shared-library"))
        link_candidate = candidate(link_context)
        guest = f"/usr/lib/lib{self.shared_stem}.so"
        link_trace = trace(guest)
        file_name = Path(guest).name
        self._write_path(
            self.roots["/lib"] / file_name,
            elf(object_type=3, machine=62),
        )
        link = self.roots["/usr"] / "lib"
        self._symlink_directory(link, self.roots["/lib"])
        item = resolve_traced_native_artifacts(
            link_trace, link_context, link_candidate, guest_roots=self.roots,
        )["requirements"][0]
        self.assertEqual("passed", item["status"])

        self._remove_directory_link(link)
        external = self.base / "outside-mapped-roots"
        external.mkdir()
        self._write_path(
            external / file_name, elf(object_type=3, machine=62),
        )
        self._symlink_directory(link, external)
        item = resolve_traced_native_artifacts(
            link_trace, link_context, link_candidate, guest_roots=self.roots,
        )["requirements"][0]
        self.assertEqual(
            "native_link_actual_artifact_path_escape", item["reason_code"],
        )
        self.assertIsNone(item["inspection"])

    def test_toctou_mutation_is_fail_closed(self) -> None:
        link_context = context((f"lib{self.shared_stem}.so", "shared-library"))
        link_candidate = candidate(link_context)
        guest = f"/usr/lib/lib{self.shared_stem}.so"
        self._write_guest(guest, elf(object_type=3, machine=62))
        real_inspect = native_link_actual_paths.inspect_native_object

        def inspect_then_mutate(path: Path) -> dict:
            report = real_inspect(path)
            path.write_bytes(
                elf(object_type=3, machine=62, suffix=b"changed-after-read"),
            )
            return report

        with mock.patch.object(
            native_link_actual_paths,
            "inspect_native_object",
            side_effect=inspect_then_mutate,
        ):
            item = resolve_traced_native_artifacts(
                trace(guest), link_context, link_candidate,
                guest_roots=self.roots,
            )["requirements"][0]
        self.assertEqual("native_link_actual_artifact_unstable", item["reason_code"])
        self.assertIsNone(item["inspection"])

    def test_object_format_type_and_abi_failures_block(self) -> None:
        shared_context = context(
            (f"lib{self.shared_stem}.so", "shared-library"),
        )
        shared_candidate = candidate(shared_context)
        shared_guest = f"/usr/lib/lib{self.shared_stem}.so"
        shared_trace = trace(shared_guest)
        invalid_shared = (
            (b"not-an-object", "native_link_actual_artifact_inspection_failed"),
            (
                elf(object_type=3, machine=0),
                "native_link_actual_artifact_inspection_failed",
            ),
            (
                archive(ar_member(
                    "object.o/", elf(object_type=1, machine=62),
                )),
                "native_link_actual_artifact_type_mismatch",
            ),
        )
        for data, reason in invalid_shared:
            with self.subTest(reason=reason, size=len(data)):
                self._write_guest(shared_guest, data)
                item = resolve_traced_native_artifacts(
                    shared_trace, shared_context, shared_candidate,
                    guest_roots=self.roots,
                )["requirements"][0]
                self.assertEqual(reason, item["reason_code"])
                if reason == "native_link_actual_artifact_type_mismatch":
                    self.assertEqual(
                        "unix-ar", item["inspection"]["object_format"],
                    )
                else:
                    self.assertIsNone(item["inspection"])

        static_context = context(
            (f"lib{self.static_stem}.a", "static-archive"),
        )
        static_guest = f"/lib/lib{self.static_stem}.a"
        self._write_guest(
            static_guest,
            archive(
                ar_member("one.o/", elf(object_type=1, machine=62)),
                ar_member("two.o/", elf(
                    object_type=1, machine=3, class_bits=32,
                )),
            ),
        )
        item = resolve_traced_native_artifacts(
            trace((static_guest, "one.o"), (static_guest, "two.o")),
            static_context,
            candidate(static_context),
            guest_roots=self.roots,
        )["requirements"][0]
        self.assertEqual(
            "native_link_actual_artifact_inspection_failed", item["reason_code"],
        )

    def test_tampered_trace_context_candidate_and_guest_path_are_rejected(self) -> None:
        link_trace = trace(f"/usr/lib/lib{self.shared_stem}.so.3")
        altered_trace = copy.deepcopy(link_trace)
        altered_trace["entries"][0]["path"] = "/usr/lib/libchanged.so"
        altered_context = copy.deepcopy(self.context)
        altered_context["requirements"][0]["dependency_count"] = 2
        altered_candidate = copy.deepcopy(self.candidate)
        altered_candidate["proposals"][0]["rustc_link_name"] = "changed"
        cases = (
            (altered_trace, self.context, self.candidate),
            (link_trace, altered_context, self.candidate),
            (link_trace, self.context, altered_candidate),
        )
        for values in cases:
            with self.subTest(value=next(
                name for name, value in zip(
                    ("trace", "context", "candidate"), values,
                ) if value not in (link_trace, self.context, self.candidate)
            )):
                with self.assertRaises(ValueError):
                    resolve_traced_native_artifacts(
                        *values, guest_roots=self.roots,
                    )

        escaped_trace = copy.deepcopy(link_trace)
        escaped_trace["entries"][0]["path"] = "/usr/../../private/library.so"
        escaped_trace["entry_set_sha256"] = content_sha256(
            escaped_trace["entries"],
        )
        with self.assertRaisesRegex(ValueError, "guest_(?:path|root)"):
            resolve_traced_native_artifacts(
                escaped_trace, self.context, self.candidate,
                guest_roots=self.roots,
            )


if __name__ == "__main__":
    unittest.main()
