from __future__ import annotations

import os
import signal
import subprocess
from typing import Any


PROCESS_DRAIN_TIMEOUT_SECONDS = 5


def process_group_popen_kwargs() -> dict[str, Any]:
    if os.name == "nt":
        return {
            "creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
        }
    return {"start_new_session": True}


def terminate_process_tree(process: subprocess.Popen[str]) -> None:
    if os.name == "nt":
        try:
            completed = subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=PROCESS_DRAIN_TIMEOUT_SECONDS,
            )
            if completed.returncode == 0:
                return
        except (OSError, subprocess.SubprocessError):
            pass
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
            return
        except (OSError, ProcessLookupError):
            pass
    try:
        process.kill()
    except OSError:
        pass


def terminate_and_drain(
    process: subprocess.Popen[str],
) -> tuple[str | bytes | None, str | bytes | None]:
    terminate_process_tree(process)
    try:
        return process.communicate(timeout=PROCESS_DRAIN_TIMEOUT_SECONDS)
    except (OSError, subprocess.TimeoutExpired) as error:
        terminate_process_tree(process)
        stdout = error.stdout if isinstance(error, subprocess.TimeoutExpired) else None
        stderr = error.stderr if isinstance(error, subprocess.TimeoutExpired) else None
        for stream in (process.stdout, process.stderr):
            try:
                if stream is not None:
                    stream.close()
            except OSError:
                pass
        try:
            process.wait(timeout=1)
        except (OSError, subprocess.SubprocessError):
            pass
        return stdout, stderr


__all__ = [
    "PROCESS_DRAIN_TIMEOUT_SECONDS", "process_group_popen_kwargs",
    "terminate_and_drain", "terminate_process_tree",
]
