from __future__ import annotations

import json
from pathlib import Path
import unittest

from validation.tools._project_migration_harness.project_prompt import (
    render_project_worker_prompt,
)
from validation.tools._project_migration_harness.runtime_security import (
    validate_context_page,
)
from validation.tools.project_migration_runtime_test_support import RuntimeHarnessCase


class ProjectMigrationModelInputSecurityTests(RuntimeHarnessCase):
    def test_source_secret_blocks_prompt_before_model_launch(self) -> None:
        plan = self.plan(
            'int unit(void) { const char *api_key = "do-not-send"; return api_key[0]; }\n'
        )
        ledger = self.ledger()
        launch = self.dispatch(plan, ledger)["launches"][0]
        request = self.load(launch["request"])

        with self.assertRaisesRegex(ValueError, "secret"):
            render_project_worker_prompt(request, harness_root=self.harness)

    def test_context_fact_allowlist_rejects_value_bearing_injection(self) -> None:
        plan = self.plan()
        ledger = self.ledger()
        launch = self.dispatch(plan, ledger)["launches"][0]
        request = self.load(launch["request"])
        page_ref = request["context"]["pages"][0]
        page = json.loads(
            (self.harness / Path(*page_ref["path"].split("/"))).read_text(
                encoding="utf-8"
            )
        )
        page["facts"][0]["payload"]["expected"] = "hidden-test-answer"

        with self.assertRaisesRegex(ValueError, "not allowlisted"):
            validate_context_page(page)


if __name__ == "__main__":
    unittest.main()
