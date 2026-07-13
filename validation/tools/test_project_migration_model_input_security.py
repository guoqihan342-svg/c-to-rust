from __future__ import annotations

import json
from pathlib import Path
import unittest

from validation.tools._project_migration_harness.project_prompt import (
    render_project_worker_prompt,
)
from validation.tools._project_migration_harness.artifacts import (
    content_sha256,
    write_json_artifact,
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

    def test_rehashed_receipt_with_wrong_assignment_is_rejected(self) -> None:
        plan = self.plan()
        ledger = self.ledger()
        launch = self.dispatch(plan, ledger)["launches"][0]
        request = self.load(launch["request"])
        receipt = self.load(request["context_materialization"])
        receipt["assignments"][0]["assignment_sha256"] = "0" * 64
        reference = write_json_artifact(
            self.harness,
            "target/run/context/materializations/forged.json",
            receipt,
        )
        request["context_materialization"] = reference
        payload = {
            key: value for key, value in request.items()
            if key not in {"effective_input_sha256", "execution_binding"}
        }
        request["effective_input_sha256"] = content_sha256(payload)

        with self.assertRaisesRegex(ValueError, "assignment drifted"):
            render_project_worker_prompt(request, harness_root=self.harness)


if __name__ == "__main__":
    unittest.main()
