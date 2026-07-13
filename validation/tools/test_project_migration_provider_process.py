from pathlib import Path
import unittest
from unittest import mock

from validation.tools._ai_candidate_harness_parts.provider_process import (
    opencode_log_candidates,
)


class ProjectMigrationProviderProcessTests(unittest.TestCase):
    def test_explicit_environment_uses_only_declared_log_roots(self) -> None:
        environment = {
            "HOME": "/isolated/home",
            "XDG_DATA_HOME": "/isolated/data",
            "LOCALAPPDATA": "/isolated/local",
        }

        with mock.patch.object(
            Path, "home", side_effect=AssertionError("host HOME was consulted")
        ):
            candidates = opencode_log_candidates(environment=environment)

        self.assertEqual(
            candidates,
            [
                Path("/isolated/data/opencode/log/opencode.log"),
                Path("/isolated/home/.local/share/opencode/log/opencode.log"),
                Path("/isolated/local/opencode/log/opencode.log"),
            ],
        )

    def test_explicit_environment_without_home_has_no_host_fallback(self) -> None:
        with mock.patch.object(
            Path, "home", side_effect=AssertionError("host HOME was consulted")
        ):
            candidates = opencode_log_candidates(environment={})

        self.assertEqual(candidates, [])


if __name__ == "__main__":
    unittest.main()
