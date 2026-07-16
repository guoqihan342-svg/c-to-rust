from __future__ import annotations

import os
from pathlib import Path
import sys
import time
import unittest

from validation.tools._ai_candidate_harness_parts.provider_process import (
    MAX_PROVIDER_STDERR_BYTES,
    MAX_PROVIDER_STDOUT_BYTES,
    subprocess_runner_with_environment,
)


class ProviderProcessTreeTests(unittest.TestCase):
    @unittest.skipIf(os.name == "nt", "POSIX process-group assertion")
    def test_timeout_kills_descendant_tree_with_bounded_drain(self) -> None:
        child = "import time; time.sleep(30)"
        parent = (
            "import subprocess,sys,time; "
            f"p=subprocess.Popen([sys.executable,'-c',{child!r}]); "
            "print(p.pid, flush=True); time.sleep(30)"
        )
        started = time.monotonic()

        execution = subprocess_runner_with_environment(
            [sys.executable, "-c", parent], 1,
            environment=os.environ.copy(), cwd=Path.cwd(),
        )

        elapsed = time.monotonic() - started
        self.assertTrue(execution.timed_out)
        self.assertEqual(124, execution.returncode)
        self.assertLess(elapsed, 8)
        child_pid = int(execution.stdout.strip().splitlines()[0])
        deadline = time.monotonic() + 2
        while _pid_running(child_pid) and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertFalse(_pid_running(child_pid))

    def test_started_callback_exception_does_not_wait_for_child_pipe(self) -> None:
        started = time.monotonic()

        with self.assertRaisesRegex(RuntimeError, "ledger callback failed"):
            subprocess_runner_with_environment(
                [sys.executable, "-c", "import time; time.sleep(30)"], 30,
                environment=os.environ.copy(), cwd=Path.cwd(),
                on_started=lambda: (_ for _ in ()).throw(
                    RuntimeError("ledger callback failed")
                ),
            )

        self.assertLess(time.monotonic() - started, 8)

    def test_provider_output_is_bounded_before_materializing_in_memory(self) -> None:
        script = (
            "import sys; "
            f"sys.stdout.buffer.write(b'x'*{MAX_PROVIDER_STDOUT_BYTES + 4096}); "
            f"sys.stderr.buffer.write(b'y'*{MAX_PROVIDER_STDERR_BYTES + 4096})"
        )

        execution = subprocess_runner_with_environment(
            [sys.executable, "-c", script], 30,
            environment=os.environ.copy(), cwd=Path.cwd(),
        )

        self.assertEqual(0, execution.returncode)
        self.assertEqual(MAX_PROVIDER_STDOUT_BYTES + 1, len(execution.stdout))
        self.assertEqual(MAX_PROVIDER_STDERR_BYTES + 1, len(execution.stderr))


def _pid_running(pid: int) -> bool:
    stat = Path(f"/proc/{pid}/stat")
    try:
        fields = stat.read_text(encoding="ascii").split()
    except OSError:
        return False
    return len(fields) > 2 and fields[2] != "Z"


if __name__ == "__main__":
    unittest.main()
