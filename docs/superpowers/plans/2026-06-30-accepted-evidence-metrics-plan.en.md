# Accepted Evidence Metrics Implementation Plan

Chinese original: `2026-06-30-accepted-evidence-metrics-plan.md`.

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

Add a unit test that creates an L4/refused capability-delta fixture with `semantic_pass=false`, an adjacent final-verification payload with `accepted_evidence_authoritative=true`, `semantic_pass=true`, and `generated_draft_semantic_pass=false`. Assert that `accepted_evidence_semantic_pass_count == 1` while `translator_generated_semantic_pass_count == 0`.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -B -m unittest validation.tools.test_translator_coverage_matrix.TranslatorCoverageMatrixTests.test_capability_delta_ledger_counts_accepted_evidence_semantic_pass_without_translation_acceptance -q`

Expected: FAIL with missing `accepted_evidence_semantic_pass_count` or `translator_generated_semantic_pass_count`.

- [ ] **Step 3: Write minimal implementation**

In `build_capability_delta_ledger`, count one accepted-evidence semantic pass per ledger when adjacent final-verification proves `semantic_pass=true`, `accepted_evidence_authoritative=true`, and `generated_draft_semantic_pass=false`. Keep the translator-generated count separate as `translator_generated_semantic_pass_count`.

- [ ] **Step 4: Run test to verify it passes**

Run the same unittest command. Expected: OK.

### Task 2: Milestone Report Separation

**Files:**
- Modify: `validation/tools/test_milestone_release_report.py`
- Modify: `validation/tools/milestone_release_report.py`

- [ ] **Step 1: Write the failing tests**

Add tests proving `accepted_evidence_semantic_pass_count` is exposed without changing `translation_coverage_numerator`, and proving the numerator uses `translator_generated_semantic_pass_count` instead of the legacy `semantic_pass_count` alias.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -B -m unittest validation.tools.test_milestone_release_report -q`

Expected: FAIL before implementation because the report does not expose the accepted-evidence count and still reads the legacy semantic count directly.

- [ ] **Step 3: Write minimal implementation**

Read `translator_generated_semantic_pass_count` as the canonical numerator, fall back to `semantic_pass_count` for legacy coverage JSON, and default missing `accepted_evidence_semantic_pass_count` to `0`.

- [ ] **Step 4: Run tests to verify they pass**

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
