from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
AUTO_MIGRATE = REPO_ROOT / "validation" / "tools" / "auto_migrate.py"
VALIDATOR = REPO_ROOT / "validation" / "tools" / "validate_auto_translation_evidence.py"


class AiCandidateSemanticPathTests(unittest.TestCase):
    def test_exact_ai_candidate_can_pass_existing_oracle_gates(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ai-semantic-path-") as tmp:
            root = Path(tmp)
            provider = root / "fake_opencode.py"
            launcher = root / "fake-opencode.cmd"
            provider.write_text(
                "import json\n"
                "candidate = {\n"
                "    'schema_version': 1,\n"
                "    'candidate': {\n"
                "        'language': 'rust',\n"
                "        'source': 'pub fn add_one(value: i32) -> i32 {\\n    value.wrapping_add(1)\\n}\\n',\n"
                "    },\n"
                "    'assumptions': [],\n"
                "}\n"
                "print(json.dumps({'type': 'message.part.updated', 'part': {'type': 'text', 'text': json.dumps(candidate)}}))\n",
                encoding="utf-8",
            )
            launcher.write_text(
                f'@"{sys.executable}" "{provider}" %*\n',
                encoding="utf-8",
            )
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
                    "--accept-existing-evidence",
                    "--ai-first-candidate",
                    "--ai-opencode-command",
                    str(launcher),
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

            self.assertEqual(route["candidate_generation"]["selected_candidate_id"], "opencode-glm51-1")
            self.assertEqual(route["translator"]["kind"], "agent")
            self.assertTrue(manifest["candidates"][0]["applied"])
            self.assertFalse(manifest["candidates"][0]["semantic_pass"])
            self.assertTrue(profile["generated_draft_semantic_pass"])
            self.assertEqual(profile["generated_draft_acceptance"]["selected_candidate_id"], "opencode-glm51-1")
            self.assertEqual(profile["generated_draft_acceptance"]["status"], "passed")
            typed_ir = route["candidate_generation"]["typed_ir"]
            self.assertEqual(typed_ir["output_ref"]["status"], "candidate_context_only")
            self.assertNotEqual(
                typed_ir["rust_draft_sha256"],
                manifest["candidates"][0]["rust_draft_sha256"],
            )

            validation = subprocess.run(
                [
                    sys.executable,
                    str(VALIDATOR),
                    "--target-id",
                    "demo",
                    "--slice-id",
                    "add-one",
                    "--slice-spec",
                    str(REPO_ROOT / "validation" / "slice-specs" / "demo-add-one.json"),
                    "--evidence-root",
                    str(out_root),
                    "--require-semantic-pass",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
            )
            self.assertEqual(
                validation.returncode,
                0,
                f"stdout:\n{validation.stdout}\nstderr:\n{validation.stderr}",
            )

    def test_compile_failure_uses_one_bounded_repair_before_common_gates(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ai-semantic-repair-") as tmp:
            root = Path(tmp)
            provider = root / "fake_opencode.py"
            launcher = root / "fake-opencode.cmd"
            provider.write_text(
                "import json, sys\n"
                "prompt = sys.argv[-1]\n"
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
            launcher.write_text(f'@"{sys.executable}" "{provider}" %*\n', encoding="utf-8")
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
                    "--accept-existing-evidence",
                    "--ai-first-candidate",
                    "--ai-opencode-command",
                    str(launcher),
                    "--ai-repair-rounds",
                    "1",
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

            self.assertEqual(repair["status"], "candidate_ready_for_common_validation")
            self.assertEqual(candidate["repair_rounds"], 1)
            self.assertNotEqual(candidate["initial_output_hash"], candidate["output_hash"])
            self.assertFalse(candidate["semantic_pass"])
            self.assertTrue(profile["generated_draft_semantic_pass"])

            validation = subprocess.run(
                [
                    sys.executable,
                    str(VALIDATOR),
                    "--target-id",
                    "demo",
                    "--slice-id",
                    "add-one",
                    "--slice-spec",
                    str(REPO_ROOT / "validation" / "slice-specs" / "demo-add-one.json"),
                    "--evidence-root",
                    str(out_root),
                    "--require-semantic-pass",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
            )
            self.assertEqual(
                validation.returncode,
                0,
                f"stdout:\n{validation.stdout}\nstderr:\n{validation.stderr}",
            )


if __name__ == "__main__":
    unittest.main()
