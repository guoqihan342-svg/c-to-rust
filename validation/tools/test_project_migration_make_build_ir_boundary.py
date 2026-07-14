from __future__ import annotations

import ast
from pathlib import Path
import subprocess
import unittest


PACKAGE = "validation.tools._project_migration_harness"
ENTRYPOINT = "validation.tools.project_migration_harness"
GENERIC_FACADES = {
    f"{PACKAGE}.build_adapter",
    f"{PACKAGE}.build_ir_reopen",
}
ADAPTER_ZONE = GENERIC_FACADES | {
    f"{PACKAGE}.make_build_ir_adapter",
    f"{PACKAGE}.make_build_ir_external",
    f"{PACKAGE}.make_build_ir_projection",
    f"{PACKAGE}.make_build_ir_reopen",
    f"{PACKAGE}.make_dry_run_binding",
    f"{PACKAGE}.make_dry_run_contract",
    f"{PACKAGE}.make_dry_run_host_evidence",
    f"{PACKAGE}.make_dry_run_parser",
    f"{PACKAGE}.make_dry_run_report_io",
    f"{PACKAGE}.make_dry_run_result",
    f"{PACKAGE}.make_dry_run_runner",
}
PRIVATE_MAKE_MODULES = {
    f"{PACKAGE}.make_build_ir_adapter",
    f"{PACKAGE}.make_build_ir_external",
    f"{PACKAGE}.make_build_ir_projection",
    f"{PACKAGE}.make_build_ir_reopen",
}
DYNAMIC_MODULES = {"builtins", "importlib", "marshal", "runpy", "zipimport"}
BUILTIN_DYNAMIC_CALLS = {"__import__", "compile", "eval", "exec"}
LOADER_CALLS = {
    "SourceFileLoader",
    "SourcelessFileLoader",
    "import_module",
    "module_from_spec",
    "run_module",
    "run_path",
    "spec_from_file_location",
    "zipimporter",
}
DYNAMIC_CALLS = BUILTIN_DYNAMIC_CALLS | LOADER_CALLS
DOWNSTREAM_FACADES = {
    f"{PACKAGE}.discovery": f"{PACKAGE}.build_adapter",
    f"{PACKAGE}.orchestrator": f"{PACKAGE}.build_adapter",
    f"{PACKAGE}.project_migration_cli": f"{PACKAGE}.build_adapter",
    f"{PACKAGE}.build_ir_validation": f"{PACKAGE}.build_ir_reopen",
}


def audit_source(module: str, source: str) -> list[str]:
    tree = ast.parse(source, filename=module)
    if module in ADAPTER_ZONE:
        return []
    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for target in import_targets(module, node):
                if is_private_make_module(target):
                    violations.append(_issue(node, "private-make-import", target))
                root = target.split(".", 1)[0]
                if root in DYNAMIC_MODULES:
                    violations.append(_issue(node, "dynamic-loader-import", target))
        elif isinstance(node, ast.Call):
            sink = dynamic_sink(node)
            if sink is not None:
                violations.append(_issue(node, "dynamic-loader-call", sink))
    return sorted(set(violations))


def import_targets(module: str, node: ast.Import | ast.ImportFrom) -> set[str]:
    if isinstance(node, ast.Import):
        return {alias.name for alias in node.names}
    base = _resolve_from(module, node.level, node.module)
    targets = {base} if base else set()
    targets.update(
        f"{base}.{alias.name}" if base else alias.name
        for alias in node.names
        if alias.name != "*"
    )
    return targets


def is_private_make_module(target: str) -> bool:
    return (
        target in PRIVATE_MAKE_MODULES
        or target.startswith(f"{PACKAGE}.make_dry_run_")
    )


def dynamic_sink(call: ast.Call) -> str | None:
    function = call.func
    dotted = _dotted_name(function)
    leaf = dotted.rsplit(".", 1)[-1] if dotted else None
    owner = dotted.rsplit(".", 1)[0] if dotted and "." in dotted else None
    if isinstance(function, ast.Name) and leaf in DYNAMIC_CALLS:
        return str(dotted)
    if leaf in LOADER_CALLS:
        return str(dotted)
    if leaf in BUILTIN_DYNAMIC_CALLS and owner in {"builtins", "__builtins__"}:
        return str(dotted)
    if isinstance(function, ast.Name) and function.id == "getattr":
        owner = _dotted_name(call.args[0]) if call.args else None
        attribute = call.args[1] if len(call.args) > 1 else None
        if (
            owner in {"__builtins__", *DYNAMIC_MODULES}
            or isinstance(attribute, ast.Constant)
            and attribute.value in DYNAMIC_CALLS
        ):
            return "getattr"
        return None
    if isinstance(function, ast.Subscript):
        key = function.slice
        owner = _dotted_name(function.value)
        if (
            isinstance(key, ast.Constant)
            and key.value in DYNAMIC_CALLS
            and owner in {"__builtins__", *DYNAMIC_MODULES}
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
    if keep < 0:
        return ""
    parts = package[:keep]
    if imported:
        parts.extend(imported.split("."))
    return ".".join(parts)


def _issue(node: ast.AST, rule: str, detail: str) -> str:
    return f"{getattr(node, 'lineno', 0)}:{rule}:{detail}"


def tracked_production_sources(root: Path) -> dict[str, str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"], cwd=root, check=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    sources: dict[str, str] = {}
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
        path = root / Path(relative)
        if path.is_symlink() or not path.is_file():
            raise AssertionError(f"tracked production module is not a regular file: {relative}")
        source = path.read_bytes().decode("utf-8")
        module = relative[:-3].replace("/", ".")
        ast.parse(source, filename=relative)
        sources[module] = source
    return sources


class MakeBuildIRBoundaryTests(unittest.TestCase):
    def test_gate_rejects_private_import_forms_and_dynamic_loaders(self) -> None:
        samples = (
            f"import {PACKAGE}.make_build_ir_adapter as adapter",
            "from .make_build_ir_projection import project_make_build_ir",
            "if TYPE_CHECKING:\n from .make_dry_run_parser import MAX_COMMANDS",
            "from importlib import import_module as load",
            "loader = __import__('validation.tools')",
            "loader = getattr(__builtins__, '__import__')",
        )
        for source in samples:
            with self.subTest(source=source):
                self.assertTrue(audit_source(f"{PACKAGE}.consumer", source))

    def test_gate_allows_common_facades_and_ordinary_data_access(self) -> None:
        source = """
import json
from .build_adapter import BuildInputSelection
payload = json.loads(raw)
commands = payload["commands"]
"""
        self.assertEqual([], audit_source(f"{PACKAGE}.consumer", source))

    def test_adapter_zone_is_explicit_and_tracked_production_is_clean(self) -> None:
        root = Path(__file__).resolve().parents[2]
        sources = tracked_production_sources(root)
        candidates = {
            module for module in sources
            if module in GENERIC_FACADES
            or module.rsplit(".", 1)[-1].startswith("make_")
        }
        self.assertEqual(ADAPTER_ZONE, candidates)
        violations = {
            module: audit_source(module, source)
            for module, source in sources.items()
            if audit_source(module, source)
        }
        self.assertEqual({}, violations)
        for module, facade in DOWNSTREAM_FACADES.items():
            tree = ast.parse(sources[module], filename=module)
            imports = {
                target
                for node in ast.walk(tree)
                if isinstance(node, (ast.Import, ast.ImportFrom))
                for target in import_targets(module, node)
            }
            self.assertIn(facade, imports, module)


if __name__ == "__main__":
    unittest.main()
