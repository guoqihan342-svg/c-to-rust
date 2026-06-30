import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


class JudgeDemoEntrypointTest(unittest.TestCase):
    def test_public_docs_bind_before_after_demo_entrypoint(self) -> None:
        chinese_doc = REPO_ROOT / "docs/c2rust-migration-agent/judge-demo.md"
        english_doc = REPO_ROOT / "docs/c2rust-migration-agent/judge-demo.en.md"
        self.assertTrue(chinese_doc.exists(), "missing Chinese judge demo entrypoint")
        self.assertTrue(english_doc.exists(), "missing English judge demo mirror")

        chinese = chinese_doc.read_text(encoding="utf-8")
        english = english_doc.read_text(encoding="utf-8")
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        docs_readme = (REPO_ROOT / "docs/c2rust-migration-agent/README.md").read_text(encoding="utf-8")
        roadmap_index = (REPO_ROOT / "docs/c2rust-migration-agent/index/roadmap.md").read_text(encoding="utf-8")
        future_vision = (REPO_ROOT / "docs/c2rust-migration-agent/future-vision-and-mvp.md").read_text(
            encoding="utf-8"
        )

        self.assertEqual(chinese.splitlines()[0], "英文镜像见 `judge-demo.en.md`。")
        self.assertIn("docs/c2rust-migration-agent/judge-demo.md", readme)
        self.assertIn("judge-demo.md", docs_readme)
        self.assertIn("target/competition-out-demo-before-after-exhibit/summary/before-after-exhibit.json", readme)
        self.assertIn("translation_coverage_numerator", readme)

        required_fragments = [
            "config/competition-env/planned-batches/demo-store-add-one-before-after.json",
            "python -B -m validation.tools.opencode_agent_harness run-batch-profile",
            "target/competition-out-demo-before-after-exhibit/summary/before-after-exhibit.json",
            "validation/evidence/demo/auto-translation/store-add-one/l3-store-add-one-baseline-unsafe.rs",
            "validation/evidence/demo/auto-translation/store-add-one/l3-store-add-one-final-safe.rs",
            "validation/evidence/demo/auto-translation/store-add-one/l3-store-add-one-accepted-safety.patch",
            "python -B validation/tools/milestone_release_report.py",
            "target/competition-out-demo-before-after-exhibit/summary/milestone-release-report.json",
            "translation_coverage_numerator",
            "generated_draft_semantic_pass=false",
        ]
        for fragment in required_fragments:
            self.assertIn(fragment, chinese)
            self.assertIn(fragment, english)

        public_index_fragments = [
            "python -B -m validation.tools.opencode_agent_harness run-batch-profile",
            "target/competition-out-demo-before-after-exhibit/summary/before-after-exhibit.json",
            "python -B validation/tools/milestone_release_report.py",
            "translation_coverage_numerator",
        ]
        for fragment in public_index_fragments:
            self.assertIn(fragment, roadmap_index)
            self.assertIn(fragment, future_vision)

        forbidden_host_paths = ("C:\\", "F:\\", "/mnt/c/")
        for fragment in forbidden_host_paths:
            self.assertNotIn(fragment, chinese)
            self.assertNotIn(fragment, english)


if __name__ == "__main__":
    unittest.main()
