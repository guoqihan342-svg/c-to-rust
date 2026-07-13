from __future__ import annotations

import copy
import hashlib
from pathlib import Path
import tempfile
import unittest

from validation.tools._ai_candidate_harness_parts.context_callees import (
    build_external_callee_source_context,
    callee_source_input_bindings,
)
from validation.tools._ai_candidate_harness_parts.provider_readiness_callees import (
    external_callee_source_context_status,
)


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def write_crlf_source(root: Path, source_lf: str) -> tuple[Path, str, str]:
    path = root / "src" / "renamed_unit.c"
    path.parent.mkdir(parents=True, exist_ok=True)
    lf_bytes = source_lf.encode("utf-8")
    crlf_bytes = source_lf.replace("\n", "\r\n").encode("utf-8")
    path.write_bytes(crlf_bytes)
    return path, sha256(lf_bytes), sha256(crlf_bytes)


def spec_for(declared_sha256: str) -> dict[str, object]:
    return {
        "source": {
            "source_file_hashes": {"src/renamed_unit.c": declared_sha256},
        },
        "c_boundary": {
            "external_direct_callees": [
                {
                    "name": "renamed_helper",
                    "source_ref": "src/renamed_unit.c#renamed_helper",
                    "source_files": [
                        {
                            "path": "src/renamed_unit.c",
                            "sha256": declared_sha256,
                        }
                    ],
                    "definition_status": "real_source_bound",
                }
            ]
        },
    }


def readiness_pack(
    context: dict[str, object],
    bindings: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "c_boundary": {
            "required_callee_sections": ["external_direct_callees"],
            "payload": {
                "external_direct_callees": [
                    {
                        "name": "renamed_helper",
                        "definition_status": "real_source_bound",
                    }
                ]
            },
        },
        "external_callee_source_context": context,
        "bindings": {"inputs": bindings},
    }


class AiExternalCalleeNewlineBindingTests(unittest.TestCase):
    def test_crlf_checkout_binds_lf_declared_hash(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ai-callee-newline-") as tmp:
            root = Path(tmp)
            source = "int renamed_helper(int value) {\n    return value + 1;\n}\n"
            _path, declared_sha, actual_sha = write_crlf_source(root, source)

            context = build_external_callee_source_context(
                spec_for(declared_sha),
                source_root=root,
                known_roots=(str(root),),
            )
            block = context["blocks"][0]
            source_file = block["source_file"]

            self.assertEqual(context["status"], "bound")
            self.assertEqual(source_file["sha256"], actual_sha)
            self.assertEqual(source_file["declared_sha256"], declared_sha)
            self.assertEqual(source_file["hash_match_mode"], "newline_equivalent")
            bindings = callee_source_input_bindings(context)
            self.assertEqual(bindings[0]["declared_sha256"], declared_sha)
            self.assertEqual(bindings[0]["hash_match_mode"], "newline_equivalent")
            self.assertEqual(
                external_callee_source_context_status(readiness_pack(context, bindings)),
                "ready",
            )

    def test_newline_binding_tamper_and_content_drift_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ai-callee-newline-drift-") as tmp:
            root = Path(tmp)
            source = "int renamed_helper(int value) {\n    return value + 1;\n}\n"
            path, declared_sha, _actual_sha = write_crlf_source(root, source)
            context = build_external_callee_source_context(
                spec_for(declared_sha),
                source_root=root,
                known_roots=(str(root),),
            )
            bindings = callee_source_input_bindings(context)
            tampered = copy.deepcopy(context)
            tampered["blocks"][0]["source_file"]["hash_match_mode"] = "exact"
            self.assertEqual(
                external_callee_source_context_status(readiness_pack(tampered, bindings)),
                "invalid",
            )

            path.write_bytes(path.read_bytes().replace(b"value + 1", b"value + 2"))
            drifted = build_external_callee_source_context(
                spec_for(declared_sha),
                source_root=root,
                known_roots=(str(root),),
            )
            self.assertEqual(drifted["status"], "unavailable")
            self.assertEqual(drifted["blocked"][0]["reason"], "source_file_sha256_mismatch")

    def test_behavior_dependencies_use_the_same_newline_binding(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ai-callee-behavior-newline-") as tmp:
            root = Path(tmp)
            source = (
                "#define READY(value) ((value)->ready)\n"
                "typedef enum { RESULT_OK, RESULT_FAILED } result_t;\n"
                "int renamed_helper(struct state *value) {\n"
                "    if (!READY(value)) { return RESULT_FAILED; }\n"
                "    return RESULT_OK;\n"
                "}\n"
            )
            _path, declared_sha, _actual_sha = write_crlf_source(root, source)
            context = build_external_callee_source_context(
                spec_for(declared_sha),
                source_root=root,
                known_roots=(str(root),),
            )

            self.assertEqual(context["status"], "bound")
            self.assertEqual(len(context["dependencies"]), 2)
            self.assertEqual(len(context["source_backed_behavior"]["rules"]), 1)
            for dependency in context["dependencies"]:
                self.assertEqual(
                    dependency["source_file"]["hash_match_mode"],
                    "newline_equivalent",
                )


if __name__ == "__main__":
    unittest.main()
