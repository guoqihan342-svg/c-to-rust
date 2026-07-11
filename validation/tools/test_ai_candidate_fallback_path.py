from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
AUTO_MIGRATE = REPO_ROOT / "validation" / "tools" / "auto_migrate.py"


class AiCandidateFallbackPathTests(unittest.TestCase):
    def test_failed_ai_candidate_uses_gate_verified_zero_token_fallback(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ai-exact-fallback-") as tmp:
            root = Path(tmp)
            provider = root / "fake_opencode.py"
            provider.write_text(
                "import json\n"
                "payload = {\n"
                "    'schema_version': 1,\n"
                "    'candidate': {\n"
                "        'language': 'rust',\n"
                "        'source': 'pub fn add_one(value: i32) -> i32 { value }\\n',\n"
                "    },\n"
                "    'assumptions': [],\n"
                "}\n"
                "print(json.dumps({'type': 'message.part.updated', 'part': {'type': 'text', 'text': json.dumps(payload)}}))\n",
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
                    "--ai-first-candidate",
                    "--ai-opencode-command",
                    f'"{sys.executable}" "{provider}"',
                    "--ai-repair-rounds",
                    "2",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
            )
            self.assertEqual(result.returncode, 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}")

            evidence_dir = out_root / "demo" / "auto-translation" / "add-one"
            router = json.loads(
                (evidence_dir / "l3-add-one-ai-router.json").read_text(encoding="utf-8")
            )
            ai_manifest = json.loads(
                (evidence_dir / "l3-add-one-ai-candidate-manifest.json").read_text(encoding="utf-8")
            )
            canonical = evidence_dir / "l3-add-one-rust-draft.rs"
            typed = evidence_dir / "l3-add-one-pre-ai-rust-candidate.rs"

            self.assertEqual(router["selected_candidate_id"], "typed-ir:clang-lowered")
            self.assertTrue(router["semantic_pass"])
            self.assertEqual(router["metrics"]["fallbacks_attempted"], 1)
            self.assertEqual(router["provider_invocations"], 1)
            self.assertFalse(ai_manifest["candidates"][0]["applied"])
            self.assertFalse((evidence_dir / "l3-add-one-ai-repair-report.json").exists())
            self.assertEqual(canonical.read_bytes(), typed.read_bytes())


if __name__ == "__main__":
    unittest.main()
