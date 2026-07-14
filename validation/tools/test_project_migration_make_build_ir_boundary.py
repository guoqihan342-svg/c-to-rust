from __future__ import annotations

import ast
from pathlib import Path
import subprocess
import unittest


PACKAGE = "validation.tools._project_migration_harness"


def _module(name: str) -> str:
    return f"{PACKAGE}.{name}"


def _edges(*specs: tuple[str, str, str]) -> dict[tuple[str, str], frozenset[str]]:
    return {(_module(source), _module(target)): frozenset(symbols.split())
            for source, target, symbols in specs}


GENERIC_FACADES = {_module("build_adapter"), _module("build_ir_reopen")}
MAKE_MODULE_NAMES = (
    "make_build_ir_adapter", "make_build_ir_external", "make_build_ir_projection",
    "make_build_ir_reopen", "make_dry_run_binding", "make_dry_run_contract",
    "make_dry_run_host_evidence", "make_dry_run_parser",
    "make_dry_run_report_io", "make_dry_run_result", "make_dry_run_runner",
)
MAKE_MODULES = {_module(name) for name in MAKE_MODULE_NAMES}
ADAPTER_ZONE = GENERIC_FACADES | MAKE_MODULES
FACADE_EXPORTS = {
    _module("build_adapter"): frozenset(
        "BuildInputSelection BuildInputSelectionLike MAKE_REPORT_INPUT_KIND MAX_BUILD_INPUT_BYTES discover_selected_project "
        "materialize_selected_build_ir_stage normalize_build_input_selection".split()
    ),
    _module("build_ir_reopen"): frozenset("accepted_provenance_role accepted_raw_roles reproject_bound_build_ir".split()),
}
FACADE_IMPORTS = _edges(
    ("discovery", "build_adapter", "BuildInputSelectionLike discover_selected_project"),
    ("orchestrator", "build_adapter", "BuildInputSelectionLike materialize_selected_build_ir_stage"),
    ("project_migration_cli", "build_adapter", "BuildInputSelection MAKE_REPORT_INPUT_KIND"),
    ("build_ir_validation", "build_ir_reopen", "accepted_provenance_role accepted_raw_roles reproject_bound_build_ir"),
)
PRIVATE_IMPORTS = _edges(
    ("build_adapter", "make_build_ir_adapter",
     "MAKE_INPUT_KIND MakeReportSelection discover_make_project materialize_make_build_ir_stage"),
    ("build_ir_reopen", "make_build_ir_reopen",
     "accepted_make_provenance_role accepted_make_raw_roles reproject_bound_make_build_ir"),
    ("make_build_ir_adapter", "make_build_ir_projection",
     "MAKE_RAW_ROLE normalize_make_translation_units project_make_build_ir"),
    ("make_build_ir_adapter", "make_dry_run_parser", "MAX_COMMANDS"),
    ("make_build_ir_adapter", "make_dry_run_report_io",
     "MAX_REPORT_BYTES reopen_make_dry_run_report verify_make_dry_run_report_inputs"),
    ("make_build_ir_projection", "make_build_ir_external",
     "MAKE_BUILD_BOUNDARIES project_make_external_dependencies"),
    ("make_build_ir_reopen", "make_build_ir_adapter", "reproject_make_build_ir"),
    ("make_build_ir_reopen", "make_build_ir_projection", "MAKE_RAW_ROLE"),
    ("make_dry_run_contract", "make_dry_run_binding", "fixed_make_argv validated_targets"),
    ("make_dry_run_contract", "make_dry_run_parser",
     "MAX_STDOUT_BYTES PARSER_NAME PARSER_VERSION parse_make_dry_run_stdout validate_make_dry_run_commands"),
    ("make_dry_run_contract", "make_dry_run_result", "MakeDryRunOutcome validate_successful_make_outcome"),
    ("make_dry_run_report_io", "make_dry_run_binding", "make_input_sha256"),
    ("make_dry_run_report_io", "make_dry_run_contract",
     "MAX_STDERR_BYTES canonical_make_dry_run_report_bytes validate_make_dry_run_report"),
    ("make_dry_run_report_io", "make_dry_run_host_evidence",
     "canonical_make_host_preflight_bytes validate_make_host_preflight"),
    ("make_dry_run_report_io", "make_dry_run_parser", "MAX_STDOUT_BYTES parse_make_dry_run_stdout"),
    ("make_dry_run_report_io", "make_dry_run_runner", "canonical_make_dry_run_plan_bytes validate_make_dry_run_plan"),
    ("make_dry_run_runner", "make_dry_run_host_evidence",
     "MAKE_REQUIRED_CAPABILITIES create_make_host_preflight validate_make_host_preflight"),
    ("make_dry_run_runner", "make_dry_run_binding",
     "fixed_make_argv make_input_sha256"),
    ("make_dry_run_runner", "make_dry_run_contract", "MAX_STDERR_BYTES"),
    ("make_dry_run_runner", "make_dry_run_parser", "MAX_STDOUT_BYTES"),
    ("make_dry_run_runner", "make_dry_run_result",
     "MakeDryRunExecution MakeDryRunOutcome"),
)
DYNAMIC_MODULES = {"builtins", "importlib", "marshal", "runpy", "zipimport"}
BUILTIN_SINKS = {"__import__", "compile", "eval", "exec"}
LOADER_SINKS = {
    "SourceFileLoader", "SourcelessFileLoader", "import_module",
    "module_from_spec", "run_module", "run_path", "spec_from_file_location",
    "zipimporter",
}
DYNAMIC_SINKS = BUILTIN_SINKS | LOADER_SINKS


def audit_source(module: str, source: str) -> list[str]:
    tree = ast.parse(source, filename=module)
    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for target, symbol in import_records(module, node):
                root = target.split(".", 1)[0]
                if root in DYNAMIC_MODULES:
                    violations.append(_issue(node, "dynamic-loader-import", target))
                if is_private_make_module(target):
                    allowed = PRIVATE_IMPORTS.get((module, target), frozenset())
                    if symbol not in allowed:
                        violations.append(_issue(node, "private-make-import", _label(target, symbol)))
                if target in GENERIC_FACADES:
                    allowed = FACADE_IMPORTS.get((module, target), frozenset())
                    if symbol is None:
                        violations.append(_issue(node, "facade-module-import", target))
                    elif symbol == "*":
                        violations.append(_issue(node, "facade-star-import", target))
                    else:
                        if symbol not in FACADE_EXPORTS[target]:
                            violations.append(_issue(node, "facade-non-export", _label(target, symbol)))
                        if symbol not in allowed:
                            violations.append(_issue(node, "facade-symbol-not-allowed", _label(target, symbol)))
        elif isinstance(node, ast.Call):
            sink = dynamic_sink(node)
            if sink is not None:
                violations.append(_issue(node, "dynamic-loader-call", sink))
    return sorted(set(violations))


def import_records(
    module: str, node: ast.Import | ast.ImportFrom,
) -> list[tuple[str, str | None]]:
    if isinstance(node, ast.Import):
        return [(alias.name, None) for alias in node.names]
    base = _resolve_from(module, node.level, node.module)
    records = []
    for alias in node.names:
        candidate = f"{base}.{alias.name}" if base else alias.name
        if node.module is None or candidate in ADAPTER_ZONE or is_private_make_module(candidate):
            records.append((candidate, None))
        else:
            records.append((base, alias.name))
    return records


def is_private_make_module(target: str) -> bool:
    return target.startswith(f"{PACKAGE}.make_") and target.count(".") == PACKAGE.count(".") + 1


def dynamic_sink(call: ast.Call) -> str | None:
    dotted = _dotted_name(call.func)
    leaf = dotted.rsplit(".", 1)[-1] if dotted else None
    owner = dotted.rsplit(".", 1)[0] if dotted and "." in dotted else None
    if isinstance(call.func, ast.Name) and leaf in DYNAMIC_SINKS:
        return str(dotted)
    if leaf in LOADER_SINKS or (
        leaf in BUILTIN_SINKS and owner in {"builtins", "__builtins__"}
    ):
        return str(dotted)
    if isinstance(call.func, ast.Name) and call.func.id == "getattr":
        target = _dotted_name(call.args[0]) if call.args else None
        attribute = call.args[1] if len(call.args) > 1 else None
        if target in {"__builtins__", *DYNAMIC_MODULES} or (
            isinstance(attribute, ast.Constant) and attribute.value in DYNAMIC_SINKS
        ):
            return "getattr"
    if isinstance(call.func, ast.Subscript):
        key = call.func.slice
        owner = _dotted_name(call.func.value)
        if isinstance(key, ast.Constant) and key.value in DYNAMIC_SINKS and (
            owner in {"__builtins__", *DYNAMIC_MODULES}
        ):
            return str(key.value)
    return None


def _dotted_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _dotted_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return None


def _resolve_from(module: str, level: int, imported: str | None) -> str:
    if level == 0:
        return imported or ""
    package = module.split(".")[:-1]
    keep = len(package) - level + 1
    parts = package[:keep] if keep >= 0 else []
    return ".".join([*parts, *(imported.split(".") if imported else [])])


def _label(target: str, symbol: str | None) -> str:
    return f"{target}:{symbol or '<module>'}"


def _issue(node: ast.AST, rule: str, detail: str) -> str:
    return f"{getattr(node, 'lineno', 0)}:{rule}:{detail}"


def declared_all(source: str) -> frozenset[str]:
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "__all__"
            for target in node.targets
        ):
            if isinstance(node.value, (ast.List, ast.Tuple)) and all(
                isinstance(item, ast.Constant) and isinstance(item.value, str)
                for item in node.value.elts
            ):
                return frozenset(item.value for item in node.value.elts)
    raise AssertionError("facade __all__ must be a literal string sequence")


def tracked_production_sources(root: Path) -> dict[str, str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"], cwd=root, check=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    sources = {}
    prefix = "validation/tools/_project_migration_harness/"
    for raw in result.stdout.split(b"\0"):
        if not raw:
            continue
        relative = raw.decode("utf-8")
        if not relative.endswith(".py") or not (
            relative.startswith(prefix)
            or relative == "validation/tools/project_migration_harness.py"
        ):
            continue
        path = root / relative
        if path.is_symlink() or not path.is_file():
            raise AssertionError(f"tracked production module is not regular: {relative}")
        source = path.read_bytes().decode("utf-8")
        ast.parse(source, filename=relative)
        sources[relative[:-3].replace("/", ".")] = source
    return sources


class MakeBuildIRBoundaryTests(unittest.TestCase):
    def test_dynamic_sinks_have_no_adapter_zone_exemption(self) -> None:
        samples = (
            (_module("build_adapter"), "exec(code)"),
            (_module("make_dry_run_parser"), "import importlib"),
            (_module("make_build_ir_adapter"), "value = compile(raw, name, 'exec')"),
        )
        for module, source in samples:
            with self.subTest(module=module, source=source):
                self.assertTrue(audit_source(module, source))

    def test_facade_and_private_edges_reject_escape_forms(self) -> None:
        discovery = _module("discovery")
        samples = (
            (discovery, "from .build_adapter import MakeReportSelection"),
            (discovery, "from . import build_adapter\nx = build_adapter.MakeReportSelection"),
            (discovery, "from .build_adapter import *"),
            (discovery, "from .build_adapter import MAX_BUILD_INPUT_BYTES"),
            (_module("build_adapter"),
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
        self.assertEqual([], audit_source(_module("discovery"), source))
        private_source = """
from .make_build_ir_adapter import (
    MAKE_INPUT_KIND, MakeReportSelection, discover_make_project,
    materialize_make_build_ir_stage,
)
"""
        self.assertEqual([], audit_source(_module("build_adapter"), private_source))

    def test_tracked_production_matches_exact_boundary_contract(self) -> None:
        root = Path(__file__).resolve().parents[2]
        sources = tracked_production_sources(root)
        candidates = {
            module for module in sources
            if module in GENERIC_FACADES or module.rsplit(".", 1)[-1].startswith("make_")
        }
        self.assertEqual(ADAPTER_ZONE, candidates)
        self.assertEqual({}, {
            module: issues for module, source in sources.items()
            if (issues := audit_source(module, source))
        })
        actual_edges: dict[tuple[str, str], set[str]] = {}
        for module, source in sources.items():
            for node in ast.walk(ast.parse(source, filename=module)):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    for target, symbol in import_records(module, node):
                        if target in GENERIC_FACADES or is_private_make_module(target):
                            actual_edges.setdefault((module, target), set()).add(
                                symbol or "<module>"
                            )
        expected = {edge: set(symbols) for edge, symbols in
                    {**FACADE_IMPORTS, **PRIVATE_IMPORTS}.items()}
        self.assertEqual(expected, actual_edges)
        for facade, exports in FACADE_EXPORTS.items():
            self.assertEqual(exports, declared_all(sources[facade]))


if __name__ == "__main__":
    unittest.main()
