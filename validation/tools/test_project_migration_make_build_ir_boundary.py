from __future__ import annotations

import ast
from pathlib import Path
import unittest

from validation.tools.project_migration_build_ir_boundary_test_support import (
    ADAPTER_ZONE,
    FACADE_EXPORTS,
    FACADE_IMPORTS,
    GENERIC_FACADES,
    PRIVATE_IMPORTS,
    audit_source,
    declared_all,
    import_records,
    is_private_make_module,
    module_name,
    repository_production_sources,
)


class MakeBuildIRBoundaryTests(unittest.TestCase):
    def test_dynamic_sinks_have_no_adapter_zone_exemption(self) -> None:
        samples = (
            (module_name("build_adapter"), "exec(code)"),
            (module_name("make_dry_run_parser"), "import importlib"),
            (module_name("make_build_ir_adapter"),
             "value = compile(raw, name, 'exec')"),
        )
        for module, source in samples:
            with self.subTest(module=module, source=source):
                self.assertTrue(audit_source(module, source))

    def test_builtin_sink_aliases_are_rejected_before_call(self) -> None:
        samples = (
            (module_name("discovery"), "runner = exec\nrunner(code)"),
            (module_name("make_build_ir_adapter"),
             "loader = __import__\nloader(name)"),
            (module_name("build_adapter"), "runner = builtins.exec"),
            (module_name("orchestrator"),
             "loader = __builtins__['__import__']"),
            (module_name("make_dry_run_parser"),
             "loader = importlib.import_module"),
        )
        for module, source in samples:
            with self.subTest(module=module, source=source):
                self.assertTrue(audit_source(module, source))

    def test_sink_words_in_definitions_stores_and_strings_are_allowed(self) -> None:
        source = """
def exec(value):
    return value

label = "__import__"
compile = label
loader_name = "import_module"
"""
        self.assertEqual([], audit_source(module_name("make_build_ir_payload"), source))

    def test_facade_and_private_edges_reject_escape_forms(self) -> None:
        discovery = module_name("discovery")
        samples = (
            (discovery, "from .build_adapter import MakeReportSelection"),
            (discovery,
             "from . import build_adapter\nx = build_adapter.MakeReportSelection"),
            (discovery, "from .build_adapter import *"),
            (discovery, "from .build_adapter import MAX_BUILD_INPUT_BYTES"),
            (module_name("build_adapter"),
             "from .make_build_ir_adapter import selection_reference"),
        )
        for module, source in samples:
            with self.subTest(module=module, source=source):
                self.assertTrue(audit_source(module, source))

    def test_exact_edges_allow_normal_data_access(self) -> None:
        source = """
import json
from .build_adapter import BuildInputSelectionLike, discover_selected_project
payload = json.loads(raw)
commands = payload["commands"]
"""
        self.assertEqual([], audit_source(module_name("discovery"), source))
        private_source = """
from .make_build_ir_adapter import (
    MAKE_INPUT_KIND, MakeReportSelection, discover_make_project,
    materialize_make_build_ir_stage,
)
"""
        self.assertEqual([], audit_source(module_name("build_adapter"), private_source))

    def test_repository_production_matches_exact_boundary_contract(self) -> None:
        root = Path(__file__).resolve().parents[2]
        sources = repository_production_sources(root)
        candidates = {
            module for module in sources
            if module in GENERIC_FACADES
            or module.rsplit(".", 1)[-1].startswith("make_")
        }
        self.assertEqual(ADAPTER_ZONE, candidates)
        violations = {
            module: issues for module, source in sources.items()
            if (issues := audit_source(module, source))
        }
        self.assertEqual({}, violations)
        actual_edges: dict[tuple[str, str], set[str]] = {}
        for module, source in sources.items():
            for node in ast.walk(ast.parse(source, filename=module)):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    for target, symbol in import_records(module, node):
                        if target in GENERIC_FACADES or is_private_make_module(target):
                            actual_edges.setdefault((module, target), set()).add(
                                symbol or "<module>"
                            )
        expected = {
            edge: set(symbols)
            for edge, symbols in {**FACADE_IMPORTS, **PRIVATE_IMPORTS}.items()
        }
        self.assertEqual(expected, actual_edges)
        for facade, exports in FACADE_EXPORTS.items():
            self.assertEqual(exports, declared_all(sources[facade]))


if __name__ == "__main__":
    unittest.main()
