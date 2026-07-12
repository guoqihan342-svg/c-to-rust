from __future__ import annotations

import importlib
from pathlib import Path
import sys
import unittest

from validation.tools import replay_call_plan
from validation.tools import replay_call_plan_dispatch
from validation.tools import replay_call_plan_fixture
from validation.tools import replay_call_plan_render_literal
from validation.tools import replay_call_plan_schema
from validation.tools import replay_call_plan_v1_builder


class ReplayCallPlanSplitCompatibilityTests(unittest.TestCase):
    def test_facade_preserves_public_and_direct_import_symbols(self) -> None:
        self.assertEqual(
            [
                "build_replay_call_plan",
                "render_declarative_replay_cases",
                "replay_call_plan_marker",
                "validate_replay_call_plan",
            ],
            replay_call_plan.__all__,
        )
        self.assertIs(
            replay_call_plan.build_replay_call_plan,
            replay_call_plan_dispatch.build_replay_call_plan,
        )
        self.assertIs(
            replay_call_plan._fixture_binding,
            replay_call_plan_fixture._fixture_binding,
        )
        self.assertEqual(
            replay_call_plan_fixture.MAX_FIXTURE_BYTES,
            replay_call_plan.MAX_FIXTURE_BYTES,
        )
        self.assertIs(
            replay_call_plan._encoded_literal,
            replay_call_plan_render_literal._encoded_literal,
        )
        self.assertIs(
            replay_call_plan.validate_replay_call_plan,
            replay_call_plan_schema.validate_replay_call_plan,
        )
        self.assertIs(
            replay_call_plan._build_bound_plan,
            replay_call_plan_v1_builder._build_bound_plan,
        )

    def test_helpers_import_without_facade_bootstrap_or_fragment_loading(self) -> None:
        module_names = [
            "validation.tools.replay_call_plan_dispatch",
            "validation.tools.replay_call_plan_fixture",
            "validation.tools.replay_call_plan_render_literal",
            "validation.tools.replay_call_plan_schema",
            "validation.tools.replay_call_plan_v1_builder",
        ]
        facade = sys.modules.pop("validation.tools.replay_call_plan", None)
        try:
            for module_name in module_names:
                module = importlib.reload(importlib.import_module(module_name))
                source = Path(module.__file__).read_text(encoding="utf-8")
                self.assertNotIn("exec(", source)
                self.assertNotIn(".pyfrag", source)
            self.assertNotIn("validation.tools.replay_call_plan", sys.modules)
        finally:
            if facade is not None:
                sys.modules["validation.tools.replay_call_plan"] = facade


if __name__ == "__main__":
    unittest.main()
