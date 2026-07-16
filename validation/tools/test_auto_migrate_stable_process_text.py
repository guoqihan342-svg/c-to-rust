from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
AUTO_MIGRATE = REPO_ROOT / "validation" / "tools" / "auto_migrate.py"


def load_auto_migrate_module():
    spec = importlib.util.spec_from_file_location("stable_text_auto_migrate", AUTO_MIGRATE)
    if spec is None or spec.loader is None:
        raise AssertionError("could not load auto_migrate module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class StableProcessTextTests(unittest.TestCase):
    def test_replaces_every_platform_path_alias(self) -> None:
        module = load_auto_migrate_module()
        with tempfile.TemporaryDirectory(prefix="c2r-stable-path-") as tmp:
            aliases = module.process_path_alias_variants(tmp)
            self.assertIn(tmp, aliases)
            for alias in aliases:
                actual = module.stable_process_text(
                    f'{alias}\\generated_replay.rs\n',
                    {tmp: "<generated-replay>"},
                )
                self.assertEqual(
                    actual,
                    "<generated-replay>\\generated_replay.rs\n",
                )
            diagnostic = json.dumps(
                {"file_name": f"{tmp}\\generated_replay.rs"},
                separators=(",", ":"),
            )
            self.assertEqual(
                module.stable_process_text(diagnostic, {tmp: "<generated-replay>"}),
                '{"file_name":"<generated-replay>\\\\generated_replay.rs"}\n',
            )


if __name__ == "__main__":
    unittest.main()
