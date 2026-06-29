import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from validation.tools.flashdb_l3_self_healing import main


class FlashDbL3SelfHealingTests(unittest.TestCase):
    def test_default_retry_limit_is_five_repair_rounds(self) -> None:
        with tempfile.TemporaryDirectory(prefix="flashdb-self-healing-test-") as tmp:
            root = Path(tmp)
            input_path = root / "rustc.jsonl"
            input_path.write_text(
                json.dumps({"reason": "build-finished", "success": True}) + "\n",
                encoding="utf-8",
            )
            rust_check = root / "rust-check.json"
            error_events = root / "error-events.jsonl"
            patches = root / "patch-events.jsonl"
            policy = root / "self-healing-policy.json"

            argv = [
                "flashdb_l3_self_healing.py",
                "--input",
                str(input_path),
                "--rust-check",
                str(rust_check),
                "--error-events",
                str(error_events),
                "--patches",
                str(patches),
                "--policy",
                str(policy),
                "--repo-commit",
                "repo123",
                "--source-commit",
                "source123",
                "--rollback-id",
                "rollback-default",
                "--cwd",
                str(root),
                "--exit-code",
                "0",
            ]

            with patch("sys.argv", argv):
                self.assertEqual(main(), 0)

            payload = json.loads(policy.read_text(encoding="utf-8"))
            self.assertEqual(payload["retry_limit_per_root_cause"], 5)
