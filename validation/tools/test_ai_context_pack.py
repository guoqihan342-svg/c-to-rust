from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from validation.tools import ai_candidate_harness


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class AiContextPackTests(unittest.TestCase):
    def make_project(self, root: Path) -> tuple[Path, bytes, dict[str, object]]:
        source_root = root / "input-project"
        source_path = source_root / "src" / "unit.c"
        build_dir = source_root / "build"
        include_dir = source_root / "include"
        source_path.parent.mkdir(parents=True)
        build_dir.mkdir(parents=True)
        include_dir.mkdir(parents=True)
        function = b"int transform(int value) {\n    return value + FEATURE;\n}\n"
        source_bytes = b"#include \"unit.h\"\n\n" + function + b"\nint unrelated(void) { return 0; }\n"
        source_path.write_bytes(source_bytes)
        byte_start = source_bytes.index(function)
        spec: dict[str, object] = {
            "schema_version": 1,
            "target_id": "generic-target",
            "slice_id": "generic-slice",
            "function_name": "transform",
            "source_root": ".",
            "source_file": "src/unit.c",
            "source_file_hashes": {"src/unit.c": sha256(source_bytes)},
            "function_source_span": {
                "file": "src/unit.c",
                "byte_start": byte_start,
                "byte_end": byte_start + len(function),
                "sha256": sha256(function),
            },
            "build_profile": {
                "compiler_command_source": "build/compile_commands.json",
                "include_paths": ["include"],
                "defines": ["DECLARED=2"],
                "target": {
                    "triple_or_abi": "x86_64-unknown-linux-gnu",
                    "endianness": "little",
                    "int_width": 32,
                    "long_width": 64,
                    "pointer_width": 64,
                },
            },
            "c_boundary": {
                "functions": ["transform"],
                "signatures": [{"function": "transform", "return_type": "version.1"}],
            },
            "rust_boundary": {"public_api": [{"name": "transform"}]},
        }
        return source_root, function, spec

    def write_spec(self, root: Path, spec: dict[str, object]) -> Path:
        path = root / "slice.json"
        path.write_text(json.dumps(spec, sort_keys=True), encoding="utf-8")
        return path

    def write_compile_database(self, source_root: Path, entries: list[dict[str, object]]) -> Path:
        path = source_root / "build" / "compile_commands.json"
        path.write_text(json.dumps(entries, sort_keys=True), encoding="utf-8")
        return path

    def test_real_span_and_compile_command_are_hash_bound_and_sanitized(self) -> None:
        with tempfile.TemporaryDirectory(prefix="context-pack-project-") as tmp:
            root = Path(tmp)
            source_root, function, spec = self.make_project(root)
            secret = "synthetic-secret-for-redaction-test"
            self.write_compile_database(
                source_root,
                [
                    {
                        "directory": str(source_root / "build"),
                        "arguments": [
                            "/usr/bin/clang",
                            "-std=c11",
                            "-O2",
                            "-I",
                            str(source_root / "include"),
                            "-isystem",
                            "/opt/vendor/include",
                            "-DFEATURE=3",
                            f"-DAPI_KEY={secret}",
                            "--target=x86_64-unknown-linux-gnu",
                            "-m64",
                            "-c",
                            str(source_root / "src" / "unit.c"),
                        ],
                        "file": str(source_root / "src" / "unit.c"),
                    }
                ],
            )
            spec_path = self.write_spec(root, spec)

            context = ai_candidate_harness.build_context_pack(spec_path, source_root=source_root)
            encoded = json.dumps(context, sort_keys=True)

            self.assertEqual(context["schema_version"], 2)
            self.assertEqual(context["source"]["span"]["status"], "real_source_bound")
            self.assertEqual(context["source"]["span"]["content"].encode(), function)
            self.assertEqual(context["source"]["input"]["sha256"], sha256((source_root / "src/unit.c").read_bytes()))
            self.assertEqual(context["compile_context"]["status"], "selected")
            self.assertEqual(
                context["c_boundary"]["payload"]["signatures"][0]["return_type"],
                "version.1",
            )
            selected = context["compile_context"]["selected_entry"]
            self.assertEqual(selected["working_directory"], "<source-root>/build")
            self.assertEqual(selected["source_file"], "<source-root>/src/unit.c")
            self.assertIn({"name": "FEATURE", "value": "3"}, selected["defines"])
            self.assertEqual(selected["redacted_define_count"], 1)
            self.assertEqual(selected["target_abi"]["pointer_width"], 64)
            self.assertNotIn(str(source_root), encoded)
            self.assertNotIn("/opt/vendor", encoded)
            self.assertNotIn(secret, encoded)

    def test_compile_database_selects_exact_source_entry_deterministically(self) -> None:
        with tempfile.TemporaryDirectory(prefix="context-pack-selection-") as tmp:
            root = Path(tmp)
            source_root, _function, spec = self.make_project(root)
            other = source_root / "src" / "other.c"
            other.write_text("int other(void) { return 1; }\n", encoding="utf-8")
            entries = [
                {
                    "directory": str(source_root / "build"),
                    "command": f"cc -DWRONG=1 -c {other}",
                    "file": str(other),
                },
                {
                    "directory": str(source_root / "build"),
                    "command": f"cc -DRIGHT=1 -I../include -c {source_root / 'src/unit.c'}",
                    "file": str(source_root / "src" / "unit.c"),
                },
            ]
            self.write_compile_database(source_root, list(reversed(entries)))
            spec_path = self.write_spec(root, spec)

            first = ai_candidate_harness.build_context_pack(spec_path, source_root=source_root)
            second = ai_candidate_harness.build_context_pack(spec_path, source_root=source_root)

            selected = first["compile_context"]["selected_entry"]
            self.assertEqual(selected["defines"], [{"name": "RIGHT", "value": "1"}])
            self.assertEqual(
                ai_candidate_harness.canonical_json_bytes(first),
                ai_candidate_harness.canonical_json_bytes(second),
            )

    def test_source_path_escape_is_fail_closed_without_reading_outside(self) -> None:
        with tempfile.TemporaryDirectory(prefix="context-pack-escape-") as tmp:
            root = Path(tmp)
            source_root, _function, spec = self.make_project(root)
            outside = root / "outside.c"
            outside.write_text("int leaked(void) { return 777777; }\n", encoding="utf-8")
            spec["source_file"] = "../outside.c"
            spec["function_source_span"] = {"file": "../outside.c", "line_start": 1, "line_end": 1}
            spec_path = self.write_spec(root, spec)

            context = ai_candidate_harness.build_context_pack(spec_path, source_root=source_root)
            encoded = json.dumps(context, sort_keys=True)

            self.assertEqual(context["source"]["span"]["status"], "blocked_path_outside_source_root")
            self.assertNotIn("777777", encoded)
            self.assertNotIn(str(outside), encoded)

    def test_source_hash_drift_blocks_content(self) -> None:
        with tempfile.TemporaryDirectory(prefix="context-pack-drift-") as tmp:
            root = Path(tmp)
            source_root, _function, spec = self.make_project(root)
            spec["source_file_hashes"] = {"src/unit.c": "0" * 64}
            spec_path = self.write_spec(root, spec)

            context = ai_candidate_harness.build_context_pack(spec_path, source_root=source_root)

            span = context["source"]["span"]
            self.assertEqual(span["status"], "blocked_source_hash_mismatch")
            self.assertNotIn("content", span)
            self.assertEqual(len(context["source"]["input"]["sha256"]), 64)

    def test_deterministic_artifacts_expose_bounded_failure_summary_with_hashes(self) -> None:
        with tempfile.TemporaryDirectory(prefix="context-pack-artifacts-") as tmp:
            root = Path(tmp)
            source_root, _function, spec = self.make_project(root)
            evidence = root / "evidence"
            evidence.mkdir()
            report = {
                "status": "blocked",
                "diagnostics": ["unsupported expression at /opt/private/build/unit.c"],
                "credential": "must-not-leak",
                "types": [{"name": "word_t", "kind": "unsigned"}],
            }
            report_path = evidence / "unit-clang-lowering-report.json"
            report_path.write_text(json.dumps(report), encoding="utf-8")
            large_path = evidence / "unit-pointer-graph.json"
            large_path.write_text(json.dumps({"nodes": ["x" * 33_000]}), encoding="utf-8")
            spec_path = self.write_spec(root, spec)

            context = ai_candidate_harness.build_context_pack(
                spec_path,
                source_root=source_root,
                deterministic_evidence_dir=evidence,
            )
            artifacts = context["deterministic_artifacts"]
            loaded = artifacts[report_path.name]

            self.assertEqual(loaded["status"], "loaded")
            self.assertEqual(loaded["input"]["sha256"], sha256(report_path.read_bytes()))
            self.assertTrue(any(item["value"] == "blocked" for item in loaded["failure_summary"]))
            self.assertNotIn("must-not-leak", json.dumps(loaded))
            self.assertNotIn("/opt/private", json.dumps(loaded))
            self.assertEqual(artifacts[large_path.name]["status"], "omitted_too_large")
            self.assertEqual(artifacts[large_path.name]["input"]["sha256"], sha256(large_path.read_bytes()))
            for artifact in artifacts.values():
                self.assertLessEqual(len(json.dumps(artifact).encode("utf-8")), 32_000)

    def test_context_and_each_included_artifact_stay_within_capacity(self) -> None:
        with tempfile.TemporaryDirectory(prefix="context-pack-budget-") as tmp:
            root = Path(tmp)
            source_root, _function, spec = self.make_project(root)
            evidence = root / "evidence"
            evidence.mkdir()
            for index, suffix in enumerate(
                ("type-map", "cfg", "pointer-graph", "blocked-repairs", "clang-lowering-report")
            ):
                (evidence / f"unit-{suffix}.json").write_text(
                    json.dumps({"status": "blocked", "diagnostics": ["d" * 400] * 20, "nodes": list(range(200))}),
                    encoding="utf-8",
                )
            spec_path = self.write_spec(root, spec)

            context = ai_candidate_harness.build_context_pack(
                spec_path,
                source_root=source_root,
                deterministic_evidence_dir=evidence,
            )
            encoded = ai_candidate_harness.canonical_json_bytes(context)

            self.assertLessEqual(len(encoded), 128_000)
            self.assertEqual(len(context["bindings"]["context_payload_sha256"]), 64)
            without_self_hash = json.loads(json.dumps(context))
            expected_context_sha256 = without_self_hash["bindings"].pop("context_payload_sha256")
            self.assertEqual(
                expected_context_sha256,
                sha256(ai_candidate_harness.canonical_json_bytes(without_self_hash)),
            )
            self.assertTrue(all(len(binding["sha256"]) == 64 for binding in context["bindings"]["inputs"]))
            for artifact in context["deterministic_artifacts"].values():
                self.assertLessEqual(len(json.dumps(artifact).encode("utf-8")), 32_000)


if __name__ == "__main__":
    unittest.main()
