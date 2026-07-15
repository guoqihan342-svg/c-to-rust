from __future__ import annotations

import copy
import hashlib
import json
import unittest
from unittest import mock

from validation.tools._project_migration_harness import clang_interface_fact_evidence as subject


SOURCE_SHA = "a" * 64
HEADER_SHA = "b" * 64
COMPILE_SHA = "c" * 64
ABI_SHA = "d" * 64


def ast(*nodes: dict, **extra: object) -> bytes:
    value = {"kind": "TranslationUnitDecl", "inner": list(nodes), **extra}
    return json.dumps(value, separators=(",", ":")).encode("utf-8")


def decl(kind: str, name: str | None, path: str | None, start: int,
         end: int, **extra: object) -> dict:
    loc = {"offset": start, "tokLen": 1}
    if path is not None:
        loc["file"] = path
    value = {
        "kind": kind,
        "loc": loc,
        "range": {
            "begin": {"offset": start, "tokLen": 1},
            "end": {"offset": end - 1, "tokLen": 1},
        },
        **extra,
    }
    if name is not None:
        value["name"] = name
    return value


def parameter(qual_type: str) -> dict:
    return {"kind": "ParmVarDecl", "type": {"qualType": qual_type}}


def function(name: str, path: str | None, start: int, qual_type: str = "int (int)",
             **extra: object) -> dict:
    return decl("FunctionDecl", name, path, start, start + 10,
                type={"qualType": qual_type}, inner=[parameter("int")], **extra)


def build(raw: bytes, sources: dict[str, str] | None = None) -> dict:
    return subject.build_clang_interface_fact_evidence(
        raw, sources or {"src/main.c": SOURCE_SHA}, COMPILE_SHA, ABI_SHA)


class ClangInterfaceFactEvidenceTests(unittest.TestCase):
    def test_normal_function_is_normalized_but_never_closes_section(self) -> None:
        node = function("visit", "src/main.c", 0, "int   (int, ...)", variadic=True)
        report = build(ast(node))
        fact = report["functions"][0]
        self.assertEqual("int (int, ...)", fact["qual_type"])
        self.assertEqual(["int"], fact["parameter_types"])
        self.assertTrue(fact["variadic"])
        self.assertEqual("external", fact["linkage"])
        self.assertEqual("parsed", report["status"])
        self.assertIs(report["section_closure"], False)
        self.assertIs(report["semantic_gate"], False)
        self.assertEqual(0, report["translation_coverage_numerator"])

    def test_header_source_redeclarations_merge_consistently(self) -> None:
        header_function = function("api", "include/api.h", 0)
        header_global = decl("VarDecl", "state", None, 12, 20,
                             type={"qualType": "int"}, storageClass="extern")
        forward = decl("RecordDecl", "Item", None, 22, 30, tagUsed="struct")
        source_function = function("api", "src/main.c", 0)
        literal = {"kind": "IntegerLiteral", "type": {"qualType": "int"}, "value": "7"}
        source_global = decl("VarDecl", "state", None, 12, 22,
                             type={"qualType": "int"}, init="c", inner=[literal])
        field = {"kind": "FieldDecl", "name": "flags", "type": {"qualType": "unsigned int"},
                 "isBitfield": True}
        definition = decl("RecordDecl", "Item", None, 24, 45, tagUsed="struct",
                          completeDefinition=True, inner=[field])
        report = build(ast(header_function, header_global, forward, source_function,
                           source_global, definition),
                       {"include/api.h": HEADER_SHA, "src/main.c": SOURCE_SHA})
        self.assertEqual(1, len(report["functions"]))
        self.assertEqual(1, len(report["globals"]))
        self.assertEqual(1, len(report["records"]))
        paths = {item["path"] for item in report["functions"][0]["source_spans"]}
        self.assertEqual({"include/api.h", "src/main.c"}, paths)
        self.assertEqual("7", report["globals"][0]["initializer"]["value"])
        self.assertTrue(report["records"][0]["complete"])
        self.assertEqual([{"name": "flags", "qual_type": "unsigned int", "bitfield": True}],
                         report["records"][0]["fields"])
        self.assertEqual([], report["blockers"])

    def test_conflicting_redeclaration_is_suppressed(self) -> None:
        first = function("api", "src/main.c", 0)
        second = function("api", None, 20, "long (int)")
        report = build(ast(first, second))
        self.assertEqual([], report["functions"])
        self.assertIn("declaration_conflict", {item["code"] for item in report["blockers"]})

    def test_implicit_or_invalid_declaration_is_never_a_fact(self) -> None:
        for marker in ("isImplicit", "isInvalidDecl"):
            node = function("builtin_like", "src/main.c", 0, **{marker: True})
            report = build(ast(node))
            self.assertEqual([], report["functions"])
            self.assertEqual(
                "implicit_or_invalid_declaration", report["blockers"][0]["code"],
            )

    def test_location_escape_becomes_canonical_blocker(self) -> None:
        report = build(ast(function("escape", "../outside.h", 0)))
        self.assertEqual([], report["functions"])
        self.assertEqual("source_path_not_allowed", report["blockers"][0]["code"])
        self.assertNotIn("../outside.h", json.dumps(report))

    def test_anonymous_union_and_incomplete_records_fail_closed(self) -> None:
        anonymous = decl("RecordDecl", None, "src/main.c", 0, 5,
                         tagUsed="struct", completeDefinition=True)
        union = decl("RecordDecl", "Choice", None, 6, 12,
                     tagUsed="union", completeDefinition=True)
        incomplete = decl("RecordDecl", "Opaque", None, 13, 20, tagUsed="struct")
        report = build(ast(anonymous, union, incomplete))
        self.assertEqual(["Opaque"], [item["name"] for item in report["records"]])
        self.assertIs(report["records"][0]["complete"], False)
        codes = {item["code"] for item in report["blockers"]}
        self.assertTrue({"anonymous_declaration_unsupported", "union_record_unsupported",
                         "record_definition_missing"} <= codes)

    def test_initializer_tls_constructor_and_destructor_facts(self) -> None:
        literal = {"id": "unstable", "kind": "IntegerLiteral",
                   "type": {"qualType": "int"}, "value": "3"}
        global_ = decl("VarDecl", "counter", "src/main.c", 0, 12,
                       type={"qualType": "int"}, tls="static", init="c", inner=[literal])
        ctor = function("start", None, 13, "void (int)", storageClass="static")
        ctor["inner"] = [parameter("int"), {"kind": "ConstructorAttr"}]
        dtor = function("stop", None, 24, "void (int)")
        dtor["inner"] = [parameter("int"), {"kind": "DestructorAttr"}]
        report = build(ast(global_, ctor, dtor))
        self.assertEqual("static", report["globals"][0]["tls"])
        initializer = report["globals"][0]["initializer"]
        self.assertEqual("IntegerLiteral", initializer["root_kind"])
        self.assertEqual(64, len(initializer["semantic_sha256"]))
        self.assertEqual({"global_initializer", "constructor", "destructor"},
                         {item["kind"] for item in report["initialization_facts"]})

    def test_strict_json_and_translation_unit_contract(self) -> None:
        duplicate = b'{"kind":"TranslationUnitDecl","kind":"TranslationUnitDecl","inner":[]}'
        with self.assertRaisesRegex(subject.ClangInterfaceFactError, "ast_duplicate_key"):
            build(duplicate)
        for constant in ("NaN", "Infinity", "-Infinity", "1e999"):
            with self.subTest(constant=constant):
                raw = ('{"kind":"TranslationUnitDecl","inner":[],"x":' + constant + '}').encode()
                with self.assertRaisesRegex(subject.ClangInterfaceFactError,
                                            "ast_non_finite_number"):
                    build(raw)
        with self.assertRaisesRegex(subject.ClangInterfaceFactError, "ast_utf8_invalid"):
            build(b'{"kind":"TranslationUnitDecl","inner":[],"x":"\xff"}')
        with self.assertRaisesRegex(subject.ClangInterfaceFactError, "translation_unit_required"):
            build(json.dumps({"kind": "FunctionDecl"}).encode())

    def test_byte_depth_and_node_limits(self) -> None:
        with mock.patch.object(subject, "MAX_AST_BYTES", 8):
            with self.assertRaisesRegex(subject.ClangInterfaceFactError,
                                        "ast_byte_limit_exceeded"):
                build(ast())
        nested: dict = {"kind": "Leaf"}
        for _ in range(4):
            nested = {"kind": "Wrapper", "inner": [nested]}
        with mock.patch.object(subject, "MAX_AST_DEPTH", 3):
            with self.assertRaisesRegex(subject.ClangInterfaceFactError,
                                        "ast_depth_limit_exceeded"):
                build(ast(nested))
        with mock.patch.object(subject, "MAX_AST_NODES", 2):
            with self.assertRaisesRegex(subject.ClangInterfaceFactError,
                                        "ast_node_limit_exceeded"):
                build(ast({"kind": "TypedefDecl"}, {"kind": "TypedefDecl"}))

    def test_hash_bindings_and_tampering_are_detected(self) -> None:
        raw = ast(function("api", "src/main.c", 0))
        report = build(raw)
        self.assertEqual(hashlib.sha256(raw).hexdigest(),
                         report["input_bindings"]["raw_ast_sha256"])
        tampered = copy.deepcopy(report)
        tampered["input_bindings"]["compile_context_sha256"] = "e" * 64
        with self.assertRaisesRegex(subject.ClangInterfaceFactError,
                                    "interface_fact_evidence_mismatch"):
            subject.validate_clang_interface_fact_evidence(
                tampered, raw, {"src/main.c": SOURCE_SHA}, COMPILE_SHA, ABI_SHA)
        changed = build(raw, {"src/main.c": "f" * 64})
        self.assertNotEqual(report["evidence_sha256"], changed["evidence_sha256"])
        with self.assertRaisesRegex(subject.ClangInterfaceFactError,
                                    "compile_context_sha256_invalid"):
            subject.build_clang_interface_fact_evidence(
                raw, {"src/main.c": SOURCE_SHA}, "bad", ABI_SHA)


if __name__ == "__main__":
    unittest.main()
