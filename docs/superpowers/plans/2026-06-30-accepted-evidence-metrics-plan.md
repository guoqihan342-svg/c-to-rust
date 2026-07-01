英文镜像见 `2026-06-30-accepted-evidence-metrics-plan.en.md`。

# Accepted Evidence Metrics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split accepted-evidence semantic pass reporting from translator-generated draft coverage.

**Architecture:** Keep `translator_coverage_matrix.py` as the capability ledger aggregator and add a separate accepted-evidence count. Keep `milestone_release_report.py` strict: `translation_coverage_numerator` continues to count only translator-generated semantic-pass deltas, while accepted-evidence passes are exposed as supporting context.

**Tech Stack:** Python unittest, repo-local validation tools, JSON capability ledger fixtures.

---

### Task 1: Coverage Matrix Accepted Evidence Count

**Files:**
- Modify: `validation/tools/test_translator_coverage_matrix.py`
- Modify: `validation/tools/translator_coverage_matrix.py`

- [ ] **Step 1: Write the failing test**

Add a unit test that creates an L4/refused capability-delta fixture with `semantic_pass=false`, plus an adjacent final-verification payload with `semantic_pass=true`, `accepted_evidence_authoritative=true`, and `generated_draft_semantic_pass=false`. Assert that `accepted_evidence_semantic_pass_count == 1` while `translator_generated_semantic_pass_count == 0`.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -B -m unittest validation.tools.test_translator_coverage_matrix.TranslatorCoverageMatrixTests.test_capability_delta_ledger_counts_accepted_evidence_semantic_pass_without_translation_acceptance -q`

Expected: FAIL because `accepted_evidence_semantic_pass_count` or `translator_generated_semantic_pass_count` is absent.

- [ ] **Step 3: Implement minimal aggregation**

In `build_capability_delta_ledger`, count one accepted-evidence semantic pass per ledger when adjacent final-verification proves `semantic_pass=true`, `accepted_evidence_authoritative=true`, and `generated_draft_semantic_pass=false`. Keep the translator-generated count separate as `translator_generated_semantic_pass_count`, with `semantic_pass_count` only as a compatibility alias.

- [ ] **Step 4: Run test to verify it passes**

Run the same unittest command. Expected: OK.

### Task 2: Milestone Report Separation

**Files:**
- Modify: `validation/tools/test_milestone_release_report.py`
- Modify: `validation/tools/milestone_release_report.py`

- [ ] **Step 1: Write the failing test**

Add tests where the coverage ledger has `accepted_evidence_semantic_pass_count=1` and `translator_generated_semantic_pass_count=0`. Assert `metrics.accepted_evidence_semantic_pass_count == 1`, `metrics.translation_coverage_numerator == 0`, and the `no_translator_generated_semantic_pass` blocker remains. Add another test proving a conflicting legacy `semantic_pass_count` does not override the canonical translator-generated count.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -B -m unittest validation.tools.test_milestone_release_report.MilestoneReleaseReportTests.test_report_exposes_accepted_evidence_without_translation_numerator -q`

Expected: FAIL because the milestone report does not expose the new metric or still uses the legacy semantic count directly.

- [ ] **Step 3: Implement minimal reporting**

Read `translator_generated_semantic_pass_count` as the canonical numerator, fall back to `semantic_pass_count` for legacy coverage JSON, default missing `accepted_evidence_semantic_pass_count` to `0`, and keep readiness blockers based only on `translation_coverage_numerator`.

- [ ] **Step 4: Run test to verify it passes**

Run the same unittest command. Expected: OK.

### Task 3: Roadmap Boundary Update

**Files:**
- Modify: `docs/c2rust-migration-agent/future-vision-and-mvp.md`
- Modify: `docs/c2rust-migration-agent/future-vision-and-mvp.en.md`

- [ ] **Step 1: Update current status text**

In the P0 capability ledger/report item, mention that accepted-evidence semantic passes are counted separately and do not affect the translator-generated coverage numerator.

- [ ] **Step 2: Verify doc mirror**

Run: `python -B -m unittest validation.tools.test_doc_mirror_contract -q`

Expected: OK.
