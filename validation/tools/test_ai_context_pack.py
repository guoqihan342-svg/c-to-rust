from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import jsonschema

from validation.tools import ai_candidate_harness
from validation.tools._ai_candidate_harness_parts.provider_readiness import evaluate_provider_readiness


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

            self.assertEqual(context["schema_version"], 4)
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
            source_root, function, spec = self.make_project(root)
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

    def test_nested_response_files_are_expanded_and_hash_bound(self) -> None:
        with tempfile.TemporaryDirectory(prefix="context-pack-response-files-") as tmp:
            root = Path(tmp)
            source_root, _function, spec = self.make_project(root)
            build = source_root / "build"
            (build / "nested.rsp").write_text(
                "-I../include --target=arm-none-eabi -m32",
                encoding="utf-8",
            )
            (source_root / "shared.rsp").write_text("-DROOT_PARENT=1", encoding="utf-8")
            (build / "flags.rsp").write_text(
                "-DRESPONSE_FEATURE=7 @nested.rsp @../shared.rsp",
                encoding="utf-8",
            )
            self.write_compile_database(
                source_root,
                [
                    {
                        "directory": str(build),
                        "arguments": ["clang", "@flags.rsp", "-c", str(source_root / "src/unit.c")],
                        "file": str(source_root / "src/unit.c"),
                    }
                ],
            )

            replay_path = root / "l3-generic-slice-rust-replay-test-draft.rs"
            replay_path.write_text(
                "#[test]\nfn replay() { let _ = transform(1); }\n",
                encoding="utf-8",
            )
            context = ai_candidate_harness.build_context_pack(
                self.write_spec(root, spec),
                source_root=source_root,
                replay_test_path=replay_path,
            )
            context_schema = json.loads(
                (
                    Path(__file__).resolve().parents[1]
                    / "auto-translation-template"
                    / "ai-context-pack.schema.json"
                ).read_text(encoding="utf-8")
            )
            jsonschema.Draft7Validator(context_schema).validate(context)

            selected = context["compile_context"]["selected_entry"]
            self.assertEqual("expanded", selected["response_files"]["status"])
            self.assertEqual(3, len(selected["response_files"]["files"]))
            self.assertIn({"name": "RESPONSE_FEATURE", "value": "7"}, selected["defines"])
            self.assertIn({"name": "ROOT_PARENT", "value": "1"}, selected["defines"])
            self.assertIn(
                {"kind": "include", "path": "<source-root>/include"},
                selected["include_paths"],
            )
            self.assertEqual("arm-none-eabi", selected["target_abi"]["triple_or_abi"])
            self.assertEqual(32, selected["target_abi"]["pointer_width"])
            response_bindings = [
                item for item in context["bindings"]["inputs"]
                if item["kind"] == "compile_response_file"
            ]
            self.assertEqual(3, len(response_bindings))
            self.assertTrue(all(len(item["sha256"]) == 64 for item in response_bindings))
            self.assertEqual("ready", evaluate_provider_readiness(context)["status"])
            tampered = json.loads(json.dumps(context))
            next(
                item for item in tampered["bindings"]["inputs"]
                if item["kind"] == "compile_response_file"
            )["sha256"] = "0" * 64
            self.assertEqual(
                "response_file_invalid",
                evaluate_provider_readiness(tampered)["compile_context_status"],
            )
            first_context_sha = context["bindings"]["context_payload_sha256"]
            (build / "flags.rsp").write_text(
                "-DRESPONSE_FEATURE=8 @nested.rsp @../shared.rsp",
                encoding="utf-8",
            )
            changed = ai_candidate_harness.build_context_pack(
                self.write_spec(root, spec),
                source_root=source_root,
                replay_test_path=replay_path,
            )
            self.assertNotEqual(first_context_sha, changed["bindings"]["context_payload_sha256"])

    def test_response_file_escape_and_cycle_block_provider(self) -> None:
        for case, flags, nested in (
            ("escape", "@../../outside.rsp", None),
            ("cycle", "@nested.rsp", "@flags.rsp"),
        ):
            with self.subTest(case=case), tempfile.TemporaryDirectory(
                prefix=f"context-pack-response-{case}-"
            ) as tmp:
                root = Path(tmp)
                source_root, _function, spec = self.make_project(root)
                build = source_root / "build"
                (build / "flags.rsp").write_text(flags, encoding="utf-8")
                if nested is not None:
                    (build / "nested.rsp").write_text(nested, encoding="utf-8")
                self.write_compile_database(
                    source_root,
                    [
                        {
                            "directory": str(build),
                            "arguments": ["clang", "@flags.rsp", "-c", str(source_root / "src/unit.c")],
                            "file": str(source_root / "src/unit.c"),
                        }
                    ],
                )
                context = ai_candidate_harness.build_context_pack(
                    self.write_spec(root, spec),
                    source_root=source_root,
                )

                response_files = context["compile_context"]["selected_entry"]["response_files"]
                self.assertEqual("blocked", response_files["status"])
                self.assertEqual(
                    {
                        "status": "blocked",
                        "source_span_status": "real_source_bound",
                        "compile_context_status": "response_file_invalid",
                    },
                    evaluate_provider_readiness(context),
                )

    def test_response_file_budget_overflow_blocks_provider(self) -> None:
        with tempfile.TemporaryDirectory(prefix="context-pack-response-budget-") as tmp:
            root = Path(tmp)
            source_root, _function, spec = self.make_project(root)
            build = source_root / "build"
            (build / "flags.rsp").write_text("-DVALUE=123456", encoding="utf-8")
            self.write_compile_database(
                source_root,
                [
                    {
                        "directory": str(build),
                        "arguments": ["clang", "@flags.rsp", "-c", str(source_root / "src/unit.c")],
                        "file": str(source_root / "src/unit.c"),
                    }
                ],
            )
            with patch(
                "validation.tools._ai_candidate_harness_parts.context_response_files.MAX_RESPONSE_FILE_BYTES",
                4,
            ):
                context = ai_candidate_harness.build_context_pack(
                    self.write_spec(root, spec),
                    source_root=source_root,
                )

            response_files = context["compile_context"]["selected_entry"]["response_files"]
            self.assertEqual("response_file_size_exceeded", response_files["reason"])
            self.assertEqual("blocked", evaluate_provider_readiness(context)["status"])
            manifest = ai_candidate_harness.generate_candidate(
                context,
                out_dir=root / "ai-out",
                runner=lambda _argv, _timeout: self.fail("blocked response file invoked provider"),
            )
            self.assertEqual(0, manifest["provider_invocations"])
            self.assertEqual("context_not_provider_ready", manifest["failure"]["kind"])

    def test_malformed_compile_command_with_response_reference_blocks_provider(self) -> None:
        with tempfile.TemporaryDirectory(prefix="context-pack-response-command-") as tmp:
            root = Path(tmp)
            source_root, _function, spec = self.make_project(root)
            self.write_compile_database(
                source_root,
                [
                    {
                        "directory": str(source_root / "build"),
                        "command": 'clang @"unterminated',
                        "file": str(source_root / "src/unit.c"),
                    }
                ],
            )
            context = ai_candidate_harness.build_context_pack(
                self.write_spec(root, spec),
                source_root=source_root,
            )

            response_files = context["compile_context"]["selected_entry"]["response_files"]
            self.assertEqual("command_argument_parse_invalid", response_files["reason"])
            self.assertEqual("blocked", evaluate_provider_readiness(context)["status"])
            self.write_compile_database(
                source_root,
                [
                    {
                        "directory": str(source_root / "build"),
                        "arguments": ["clang", 7, "@flags.rsp"],
                        "file": str(source_root / "src/unit.c"),
                    }
                ],
            )
            invalid_arguments = ai_candidate_harness.build_context_pack(
                self.write_spec(root, spec),
                source_root=source_root,
            )
            self.assertEqual(
                "command_argument_parse_invalid",
                invalid_arguments["compile_context"]["selected_entry"]["response_files"]["reason"],
            )
            self.assertEqual("blocked", evaluate_provider_readiness(invalid_arguments)["status"])

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

    def test_source_change_during_read_is_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="context-pack-toctou-") as tmp:
            root = Path(tmp)
            source_root, _function, spec = self.make_project(root)
            spec_path = self.write_spec(root, spec)

            initial_sha = spec["source_file_hashes"]["src/unit.c"]
            with patch(
                "validation.tools._ai_candidate_harness_parts.context_source.sha256_path",
                side_effect=[initial_sha, "0" * 64],
            ):
                context = ai_candidate_harness.build_context_pack(
                    spec_path,
                    source_root=source_root,
                )

            span = context["source"]["span"]
            self.assertEqual("source_file_changed_during_read", span["status"])
            self.assertNotIn("content", span)

    def test_boolean_source_coordinates_are_not_integers(self) -> None:
        with tempfile.TemporaryDirectory(prefix="context-pack-bool-coordinates-") as tmp:
            root = Path(tmp)
            source_root, _function, spec = self.make_project(root)
            spec["function_source_span"].update(
                {
                    "byte_start": True,
                    "line_start": True,
                }
            )
            spec_path = self.write_spec(root, spec)

            context = ai_candidate_harness.build_context_pack(
                spec_path,
                source_root=source_root,
            )

            self.assertEqual(
                "source_span_coordinates_missing",
                context["source"]["span"]["status"],
            )

    def test_real_source_without_declared_hashes_is_not_provider_ready(self) -> None:
        with tempfile.TemporaryDirectory(prefix="context-pack-unbound-source-") as tmp:
            root = Path(tmp)
            source_root, _function, spec = self.make_project(root)
            spec.pop("source_file_hashes")
            spec["function_source_span"].pop("sha256")
            spec_path = self.write_spec(root, spec)

            context = ai_candidate_harness.build_context_pack(
                spec_path,
                source_root=source_root,
            )

            self.assertEqual("real_source_bound", context["source"]["span"]["status"])
            self.assertEqual(
                {"status": "blocked", "source_span_status": "source_binding_incomplete"},
                evaluate_provider_readiness(context),
            )

    def test_source_and_span_hashes_accept_lf_crlf_equivalence(self) -> None:
        with tempfile.TemporaryDirectory(prefix="context-pack-newlines-") as tmp:
            root = Path(tmp)
            source_root, function, spec = self.make_project(root)
            source_path = source_root / "src" / "unit.c"
            lf_source = source_path.read_bytes()
            crlf_source = lf_source.replace(b"\n", b"\r\n")
            source_path.write_bytes(crlf_source)
            spec["source_file_hashes"] = {"src/unit.c": sha256(lf_source)}
            spec["function_source_span"] = {
                "file": "src/unit.c",
                "line_start": 3,
                "line_end": 5,
                "byte_start": lf_source.index(function),
                "byte_end": lf_source.index(function) + len(function),
                "sha256": sha256(function),
            }
            spec_path = self.write_spec(root, spec)

            context = ai_candidate_harness.build_context_pack(
                spec_path,
                source_root=source_root,
            )

            source = context["source"]
            self.assertEqual("real_source_bound", source["span"]["status"])
            self.assertEqual("newline_equivalent", source["input"]["hash_match_mode"])
            self.assertEqual("newline_equivalent", source["span"]["hash_match_mode"])
            self.assertEqual(sha256(crlf_source), source["input"]["sha256"])
            self.assertEqual(sha256(lf_source), source["input"]["declared_sha256"])

    def test_exact_fragment_carrier_binds_inline_source_to_real_fragment(self) -> None:
        with tempfile.TemporaryDirectory(prefix="context-pack-carrier-") as tmp:
            root = Path(tmp)
            source_root, function, spec = self.make_project(root)
            source_path = source_root / "src" / "unit.c"
            fragment = b"    return value + FEATURE;\n"
            carrier_source = (
                "int transform_probe(int value) {\n"
                + fragment.decode("utf-8")
                + "}\n"
            )
            spec["function_name"] = "transform_probe"
            spec["c_source"] = carrier_source
            spec["translation_carrier"] = {
                "kind": "exact_source_fragment_wrapper",
                "carrier_function": "transform_probe",
                "carrier_source_sha256": sha256(carrier_source.encode("utf-8")),
                "embedding_mode": "verbatim_once",
                "frontend_contract": "live_clang_slice_source",
                "source_text_normalization": "utf8_universal_newlines",
                "source_file_hash_mode": "raw_bytes",
                "artifact_source_hash_mode": "lf_stable_text",
                "real_source": {
                    "file": "src/unit.c",
                    "containing_function": {
                        "name": "transform",
                        "line_start": 3,
                        "line_end": 5,
                        "sha256": sha256(function.strip()),
                        "hash_mode": "trimmed_normalized_span",
                        "declaration_text": "int transform(",
                    },
                    "fragment": {
                        "line_start": 4,
                        "line_end": 4,
                        "sha256": sha256(fragment),
                        "hash_mode": "normalized_line_span_with_newline",
                        "text": fragment.decode("utf-8"),
                    },
                },
                "claim_boundary": {
                    "scope": "source_fragment_only",
                    "whole_function_semantics_verified": False,
                    "external_callee_semantics_verified": False,
                },
            }
            spec["function_source_span"] = {"file": "src/unit.c"}
            spec_path = self.write_spec(root, spec)

            context = ai_candidate_harness.build_context_pack(
                spec_path,
                source_root=source_root,
            )

            span = context["source"]["span"]
            self.assertEqual("inline_translation_carrier_bound", span["status"])
            self.assertEqual(carrier_source, span["content"])
            self.assertEqual(fragment.decode("utf-8"), span["real_source_fragment"]["content"])

            disabled_carrier = "# \tif(0)\n" + carrier_source + "# endif /* disabled */\n"
            spec["c_source"] = disabled_carrier
            spec["translation_carrier"]["carrier_source_sha256"] = sha256(
                disabled_carrier.encode("utf-8")
            )
            disabled_path = root / "disabled-slice.json"
            disabled_path.write_text(json.dumps(spec), encoding="utf-8")
            disabled = ai_candidate_harness.build_context_pack(
                disabled_path,
                source_root=source_root,
            )
            self.assertEqual(
                "fragment_inside_preprocessor_conditional",
                disabled["source"]["span"]["reason"],
            )

            commented_carrier = "/*\n" + carrier_source + "*/\n"
            spec["c_source"] = commented_carrier
            spec["translation_carrier"]["carrier_source_sha256"] = sha256(
                commented_carrier.encode("utf-8")
            )
            commented_path = root / "commented-slice.json"
            commented_path.write_text(json.dumps(spec), encoding="utf-8")
            commented = ai_candidate_harness.build_context_pack(
                commented_path,
                source_root=source_root,
            )
            self.assertEqual(
                "fragment_inside_comment",
                commented["source"]["span"]["reason"],
            )

            spec["c_source"] = carrier_source
            spec["translation_carrier"]["carrier_source_sha256"] = sha256(
                carrier_source.encode("utf-8")
            )
            spec["translation_carrier"]["real_source"]["fragment"]["sha256"] = "0" * 64
            blocked_path = root / "blocked-slice.json"
            blocked_path.write_text(json.dumps(spec), encoding="utf-8")
            blocked = ai_candidate_harness.build_context_pack(
                blocked_path,
                source_root=source_root,
            )
            self.assertEqual(
                "blocked_translation_carrier_contract",
                blocked["source"]["span"]["status"],
            )
            self.assertEqual("fragment_hash_mismatch", blocked["source"]["span"]["reason"])

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
