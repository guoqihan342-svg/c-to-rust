from __future__ import annotations

import unittest

from validation.tools._project_migration_harness.ninja_link_command import (
    parse_ninja_link_command,
)


class NinjaLinkCommandTests(unittest.TestCase):
    def test_ignores_operators_in_non_link_custom_command(self) -> None:
        command = "tail -n1 report | grep passed > /dev/null && rm report"
        self.assertEqual((None, []), parse_ninja_link_command(command))

    def test_rejects_operator_in_link_command(self) -> None:
        command = "clang unit.o -o program.bin | tee link.log"
        with self.assertRaisesRegex(ValueError, "ninja_shell_operator_unsupported"):
            parse_ninja_link_command(command)

    def test_rejects_compact_operator_in_link_command(self) -> None:
        command = "clang unit.o -o program.bin -lm|true"
        with self.assertRaisesRegex(ValueError, "ninja_shell_operator_unsupported"):
            parse_ninja_link_command(command)

    def test_rejects_operator_with_env_wrapped_link_driver(self) -> None:
        command = "env MODE=release clang unit.o -o program.bin | tee link.log"
        with self.assertRaisesRegex(ValueError, "ninja_shell_operator_unsupported"):
            parse_ninja_link_command(command)

    def test_keeps_quoted_punctuation_in_non_link_custom_command(self) -> None:
        command = "printf '%s' 'passed|verified' && rm report"
        self.assertEqual((None, []), parse_ninja_link_command(command))


if __name__ == "__main__":
    unittest.main()
