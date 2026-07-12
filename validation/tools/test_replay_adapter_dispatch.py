from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest

from validation.tools import auto_migrate


REPO_ROOT = Path(__file__).resolve().parents[2]


class ReplayAdapterDispatchTests(unittest.TestCase):
    CASES = (
        ("flashdb-real-fdb-blob-make.json", "fdb_blob_make_replay_supported"),
        ("flashdb-real-fdb-kv-to-blob.json", "fdb_kv_to_blob_replay_supported"),
        ("flashdb-real-fdb-kv-set.json", "fdb_kv_set_replay_supported"),
        ("flashdb-real-fdb-kv-del.json", "fdb_kv_del_replay_supported"),
    )

    def test_semantic_adapter_dispatch_survives_function_rename(self) -> None:
        for filename, support_name in self.CASES:
            with self.subTest(filename=filename):
                spec = self.load_spec(filename)
                original = spec["function_name"]
                renamed = f"renamed_{original}"
                spec["function_name"] = renamed
                for signature in spec["c_boundary"]["signatures"]:
                    if signature.get("function") == original:
                        signature["function"] = renamed
                for api in spec["rust_boundary"]["public_api"]:
                    if api.get("name") == original:
                        api["name"] = renamed

                self.assertTrue(getattr(auto_migrate, support_name)(spec))
                source = auto_migrate.rust_replay_fixture_cases_source(
                    spec,
                    auto_migrate.oracle_fixture_binding(spec),
                )
                self.assertIn(f"{renamed}(", source)

    def test_semantic_adapter_requires_declared_contract(self) -> None:
        for filename, support_name in self.CASES:
            with self.subTest(filename=filename):
                spec = self.load_spec(filename)
                without_contract = copy.deepcopy(spec)
                without_contract.pop("replay_contract")
                self.assertFalse(getattr(auto_migrate, support_name)(without_contract))

    def test_ai_candidate_replay_requires_exact_applied_draft_binding(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ai-replay-route-") as tmp:
            evidence_dir = Path(tmp)
            slice_id = "generic"
            draft = evidence_dir / f"l3-{slice_id}-rust-draft.rs"
            draft.write_text("pub fn translated() {}\n", encoding="utf-8")
            draft_sha = auto_migrate.sha256(draft)
            manifest = {
                "schema_version": 8,
                "slice_id": slice_id,
                "status": "generated",
                "selected_candidate_id": "ai-1",
                "candidates": [
                    {
                        "candidate_id": "ai-1",
                        "applied": True,
                        "rust_draft_sha256": draft_sha,
                        "applied_artifact": {
                            "path": draft.name,
                            "sha256": draft_sha,
                        },
                    }
                ],
            }
            (evidence_dir / f"l3-{slice_id}-ai-candidate-manifest.json").write_text(
                json.dumps(manifest),
                encoding="utf-8",
            )

            self.assertTrue(
                auto_migrate.ai_generated_candidate_replay_supported(
                    evidence_dir,
                    slice_id,
                    draft,
                )
            )
            draft.write_text("pub fn drifted() {}\n", encoding="utf-8")
            self.assertFalse(
                auto_migrate.ai_generated_candidate_replay_supported(
                    evidence_dir,
                    slice_id,
                    draft,
                )
            )

    def test_compile_link_sources_exclude_headers_and_fixtures(self) -> None:
        for filename in ("zlib-adler32-step.json", "libuv-ip4-addr.json"):
            with self.subTest(filename=filename):
                spec = self.load_spec(filename)
                source_root = auto_migrate.compile_source_root(spec)
                files = auto_migrate.compile_link_source_files(spec, source_root)

                self.assertTrue(files)
                self.assertTrue(
                    all(item["role"] in {"source", "link_dependency"} for item in files)
                )
                self.assertTrue(
                    all(Path(item["path"]).suffix.lower() not in {".h", ".json"} for item in files)
                )

    @staticmethod
    def load_spec(filename: str) -> dict:
        return json.loads(
            (REPO_ROOT / "validation" / "slice-specs" / filename).read_text(
                encoding="utf-8"
            )
        )


if __name__ == "__main__":
    unittest.main()
