from __future__ import annotations

import unittest

from validation.tools._project_migration_harness.native_link_actual_resolution import (
    resolve_traced_native_artifacts,
)
from validation.tools._project_migration_harness.native_link_symbol_reports import (
    extract_native_link_symbol_reports,
)
from validation.tools.project_migration_native_link_actual_test_support import (
    NativeLinkActualTestCase,
    trace,
)
from validation.tools.project_migration_native_object_archive_test_support import (
    ar_member,
    archive,
)
from validation.tools.project_migration_native_object_symbols_test_support import (
    Symbol,
    elf_object,
)


class NativeLinkSymbolReportTests(NativeLinkActualTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.guests = []
        expected = []
        for index, requirement in enumerate(self.context["requirements"]):
            symbol = f"portable_export_{index}"
            expected.append(symbol)
            if requirement["library_format"] == "shared-library":
                data = elf_object(
                    64, "little", object_type=3,
                    tables=[("dynsym", [Symbol(symbol)])],
                )
                guest = f"/usr/lib/{requirement['portable_name']}.9"
                trace_value = guest
            else:
                data = archive(ar_member(
                    "unit.o/",
                    elf_object(
                        64, "little", object_type=1,
                        tables=[("symtab", [Symbol(symbol)])],
                    ),
                ))
                guest = f"/lib64/{requirement['portable_name']}"
                trace_value = (guest, "unit.o")
            self._write_guest(guest, data)
            self.guests.append(guest)
            if index == 0:
                self.link_trace = trace(trace_value)
            else:
                values = [
                    entry["path"] if "archive_member" not in entry
                    else (entry["path"], entry["archive_member"])
                    for entry in self.link_trace["entries"]
                ]
                self.link_trace = trace(*values, trace_value)
        self.expected = expected
        self.actual = resolve_traced_native_artifacts(
            self.link_trace, self.context, self.candidate,
            guest_roots=self.roots,
        )

    def test_extracts_path_free_reports_bound_to_actual_objects(self) -> None:
        reports = extract_native_link_symbol_reports(
            self.link_trace, self.context, self.candidate, self.actual,
            guest_roots=self.roots,
        )
        self.assertEqual(set(self.expected), {
            symbol for report in reports.values() for symbol in report["symbols"]
        })
        self.assertNotIn(str(self.base), str(reports))

    def test_replaced_object_after_resolution_fails_closed(self) -> None:
        self._host_path(self.guests[0]).write_bytes(b"not-an-object")
        with self.assertRaisesRegex(ValueError, "reopen_drift"):
            extract_native_link_symbol_reports(
                self.link_trace, self.context, self.candidate, self.actual,
                guest_roots=self.roots,
            )


if __name__ == "__main__":
    unittest.main()
