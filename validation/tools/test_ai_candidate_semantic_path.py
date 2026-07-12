from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
AUTO_MIGRATE = REPO_ROOT / "validation" / "tools" / "auto_migrate.py"


class AiCandidateSemanticPathTests(unittest.TestCase):
    def test_exact_ai_candidate_can_pass_fresh_candidate_bound_gates(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ai-semantic-path-") as tmp:
            root = Path(tmp)
            provider = root / "fake_opencode.py"
            provider.write_text(
                "import json\n"
                "candidate = {\n"
                "    'schema_version': 1,\n"
                "    'candidate': {\n"
                "        'language': 'rust',\n"
                "        'source': '// AI candidate\\npub fn add_one(value: i32) -> i32 {\\n    value.wrapping_add(1)\\n}\\n',\n"
                "    },\n"
                "    'assumptions': [],\n"
                "}\n"
                "print(json.dumps({'type': 'message.part.updated', 'part': {'type': 'text', 'text': json.dumps(candidate)}}))\n",
                encoding="utf-8",
            )
            provider_command = f'"{sys.executable}" "{provider}"'
            out_root = root / "evidence"
            result = subprocess.run(
                [
                    sys.executable,
                    str(AUTO_MIGRATE),
                    "--slice-spec",
                    str(REPO_ROOT / "validation" / "slice-specs" / "demo-add-one.json"),
                    "--out-root",
                    str(out_root),
                    "--emit-clang-lowering-report",
                    "--ai-first-candidate",
                    "--ai-model",
                    "opencode/deepseek-v4-flash-free",
                    "--ai-agent",
                    "c2rust-candidate",
                    "--ai-opencode-command",
                    provider_command,
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
            )

            self.assertEqual(result.returncode, 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}")
            evidence_dir = out_root / "demo" / "auto-translation" / "add-one"
            route = json.loads(
                (evidence_dir / "l3-add-one-route-decision.json").read_text(encoding="utf-8")
            )
            profile = json.loads(
                (evidence_dir / "l3-add-one-validation-profile.json").read_text(encoding="utf-8")
            )
            manifest = json.loads(
                (evidence_dir / "l3-add-one-ai-candidate-manifest.json").read_text(encoding="utf-8")
            )
            context = json.loads(
                (evidence_dir / "l3-add-one-ai-context-pack.json").read_text(encoding="utf-8")
            )
            prompt = (evidence_dir / "l3-add-one-ai-prompt.txt").read_text(encoding="utf-8")
            auto_manifest = json.loads(
                (evidence_dir / "l3-add-one-auto-translation-manifest.json").read_text(encoding="utf-8")
            )
            router = json.loads(
                (evidence_dir / "l3-add-one-ai-router.json").read_text(encoding="utf-8")
            )

            candidate_id = "opencode-deepseek-v4-flash-1"
            self.assertEqual(route["candidate_generation"]["selected_candidate_id"], candidate_id)
            self.assertEqual(route["translator"]["kind"], "agent")
            self.assertFalse(manifest["generator"]["competition_eligible"])
            self.assertEqual(8, manifest["schema_version"])
            self.assertEqual(4, context["schema_version"])
            self.assertEqual("bound", context["replay_api_contract"]["status"])
            self.assertIn("add_one(case.value)", context["replay_api_contract"]["source"]["content"])
            self.assertNotIn(
                "l3-add-one-test-translation-generated.json",
                {
                    item.get("name")
                    for item in context["bindings"]["inputs"]
                    if item.get("kind") == "deterministic_artifact"
                },
            )
            self.assertIn("Required generated replay API contract:", prompt)
            self.assertIn("add_one(case.value)", prompt)
            self.assertEqual(
                manifest["generator"]["evaluation_scope"],
                "auxiliary-local-validation",
            )
            self.assertTrue(manifest["candidates"][0]["applied"])
            self.assertEqual(manifest["candidates"][0]["candidate_id"], candidate_id)
            self.assertFalse(manifest["candidates"][0]["semantic_pass"])
            self.assertFalse(profile["generated_draft_semantic_pass"])
            self.assertEqual(
                auto_manifest["ai_exact_validation"]["path"],
                "l3-add-one-ai-router.json",
            )
            self.assertTrue(auto_manifest["ai_exact_validation"]["semantic_pass"])
            self.assertEqual(router["selected_candidate_id"], candidate_id)
            self.assertTrue(router["semantic_pass"])
            routed_ai = router["candidate_set"][0]
            self.assertEqual("opencode/deepseek-v4-flash-free", routed_ai["resolved_model"])
            self.assertFalse(routed_ai["competition_eligible"])
            self.assertEqual("auxiliary-local-validation", routed_ai["evaluation_scope"])
            self.assertEqual("c2rust-candidate", routed_ai["agent"])
            typed_ir = route["candidate_generation"]["typed_ir"]
            self.assertEqual(typed_ir["output_ref"]["status"], "candidate_context_only")
            self.assertNotEqual(
                typed_ir["rust_draft_sha256"],
                manifest["candidates"][0]["rust_draft_sha256"],
            )

    def test_compile_failure_uses_one_bounded_repair_before_common_gates(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ai-semantic-repair-") as tmp:
            root = Path(tmp)
            provider = root / "fake_opencode.py"
            provider.write_text(
                "import json, sys\n"
                "from pathlib import Path\n"
                "prompt_path = next(arg.split('=', 1)[1] for arg in sys.argv if arg.startswith('--file='))\n"
                "prompt = Path(prompt_path).read_text(encoding='utf-8')\n"
                "if 'Repair only the supplied Rust candidate' in prompt:\n"
                "    payload = {\n"
                "        'schema_version': 1,\n"
                "        'repair': {\n"
                "            'kind': 'candidate',\n"
                "            'language': 'rust',\n"
                "            'source': 'pub fn add_one(value: i32) -> i32 {\\n    value.wrapping_add(1)\\n}\\n',\n"
                "        },\n"
                "        'assumptions': [],\n"
                "    }\n"
                "else:\n"
                "    payload = {\n"
                "        'schema_version': 1,\n"
                "        'candidate': {\n"
                "            'language': 'rust',\n"
                "            'source': 'pub fn add_one(value: i32) -> i32 { value.wrapping_add( }\\n',\n"
                "        },\n"
                "        'assumptions': [],\n"
                "    }\n"
                "print(json.dumps({'type': 'message.part.updated', 'part': {'type': 'text', 'text': json.dumps(payload)}}))\n",
                encoding="utf-8",
            )
            provider_command = f'"{sys.executable}" "{provider}"'
            out_root = root / "evidence"
            result = subprocess.run(
                [
                    sys.executable,
                    str(AUTO_MIGRATE),
                    "--slice-spec",
                    str(REPO_ROOT / "validation" / "slice-specs" / "demo-add-one.json"),
                    "--out-root",
                    str(out_root),
                    "--emit-clang-lowering-report",
                    "--ai-first-candidate",
                    "--ai-opencode-command",
                    provider_command,
                    "--ai-repair-rounds",
                    "1",
                    "--ai-deterministic-fallback",
                    "off",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
            )

            self.assertEqual(result.returncode, 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}")
            evidence_dir = out_root / "demo" / "auto-translation" / "add-one"
            profile = json.loads(
                (evidence_dir / "l3-add-one-validation-profile.json").read_text(encoding="utf-8")
            )
            manifest = json.loads(
                (evidence_dir / "l3-add-one-ai-candidate-manifest.json").read_text(encoding="utf-8")
            )
            repair = json.loads(
                (evidence_dir / "l3-add-one-ai-repair-report.json").read_text(encoding="utf-8")
            )
            candidate = manifest["candidates"][0]
            auto_manifest = json.loads(
                (evidence_dir / "l3-add-one-auto-translation-manifest.json").read_text(encoding="utf-8")
            )
            router = json.loads(
                (evidence_dir / "l3-add-one-ai-router.json").read_text(encoding="utf-8")
            )

            self.assertEqual(
                repair["status"],
                "candidate_ready_for_common_validation",
                json.dumps(repair, indent=2, sort_keys=True),
            )
            self.assertEqual(candidate["repair_rounds"], 1)
            self.assertNotEqual(candidate["initial_output_hash"], candidate["output_hash"])
            self.assertFalse(candidate["semantic_pass"])
            self.assertFalse(profile["generated_draft_semantic_pass"])
            self.assertTrue(auto_manifest["ai_exact_validation"]["semantic_pass"])
            self.assertEqual(router["selected_candidate_id"], "opencode-glm51-1")

    def test_semantic_failure_uses_bounded_repair_and_replays_exact_candidate(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ai-semantic-gate-repair-") as tmp:
            root = Path(tmp)
            provider = root / "fake_opencode.py"
            provider.write_text(
                "import json, sys\n"
                "from pathlib import Path\n"
                "prompt_path = next(arg.split('=', 1)[1] for arg in sys.argv if arg.startswith('--file='))\n"
                "prompt = Path(prompt_path).read_text(encoding='utf-8')\n"
                "if 'Repair only the supplied Rust candidate' in prompt:\n"
                "    assert '\"gate\":\"generated_replay\"' in prompt or '\"gate\":\"schema_diff\"' in prompt\n"
                "    payload = {\n"
                "        'schema_version': 1,\n"
                "        'repair': {\n"
                "            'kind': 'candidate',\n"
                "            'language': 'rust',\n"
                "            'source': 'pub fn add_one(value: i32) -> i32 {\\n    value.wrapping_add(1)\\n}\\n',\n"
                "        },\n"
                "        'assumptions': [],\n"
                "    }\n"
                "else:\n"
                "    payload = {\n"
                "        'schema_version': 1,\n"
                "        'candidate': {\n"
                "            'language': 'rust',\n"
                "            'source': 'pub fn add_one(value: i32) -> i32 {\\n    value\\n}\\n',\n"
                "        },\n"
                "        'assumptions': [],\n"
                "    }\n"
                "print(json.dumps({'type': 'message.part.updated', 'part': {'type': 'text', 'text': json.dumps(payload)}}))\n",
                encoding="utf-8",
            )
            provider_command = f'"{sys.executable}" "{provider}"'
            out_root = root / "evidence"
            result = subprocess.run(
                [
                    sys.executable,
                    str(AUTO_MIGRATE),
                    "--slice-spec",
                    str(REPO_ROOT / "validation" / "slice-specs" / "demo-add-one.json"),
                    "--out-root",
                    str(out_root),
                    "--emit-clang-lowering-report",
                    "--ai-first-candidate",
                    "--ai-opencode-command",
                    provider_command,
                    "--ai-repair-rounds",
                    "2",
                    "--ai-deterministic-fallback",
                    "off",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
            )

            self.assertEqual(result.returncode, 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}")
            evidence_dir = out_root / "demo" / "auto-translation" / "add-one"
            profile = json.loads(
                (evidence_dir / "l3-add-one-validation-profile.json").read_text(encoding="utf-8")
            )
            manifest = json.loads(
                (evidence_dir / "l3-add-one-ai-candidate-manifest.json").read_text(encoding="utf-8")
            )
            repair = json.loads(
                (evidence_dir / "l3-add-one-ai-repair-report.json").read_text(encoding="utf-8")
            )
            candidate = manifest["candidates"][0]
            auto_manifest = json.loads(
                (evidence_dir / "l3-add-one-auto-translation-manifest.json").read_text(encoding="utf-8")
            )
            router = json.loads(
                (evidence_dir / "l3-add-one-ai-router.json").read_text(encoding="utf-8")
            )

            self.assertEqual(repair["status"], "candidate_ready_for_common_validation")
            self.assertEqual(candidate["repair_rounds"], 1)
            self.assertEqual(repair["rounds"][0]["validation_status"], "passed")
            self.assertFalse(profile["generated_draft_semantic_pass"])
            self.assertTrue(auto_manifest["ai_exact_validation"]["semantic_pass"])
            self.assertEqual(router["selected_candidate_id"], "opencode-glm51-1")
            self.assertEqual(router["canonical_draft_sha256"], candidate["rust_draft_sha256"])


if __name__ == "__main__":
    unittest.main()
