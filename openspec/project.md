# Project Context

## Purpose

This repository currently contains a Python reference implementation for the DWCCA unified API contract. New product ideas should be specified with OpenSpec before implementation so behavior, architecture, and rollout tasks are aligned before code changes begin.

## OpenSpec Workflow

1. Create a unique verb-led change ID under `openspec/changes/`.
2. Draft `proposal.md` for why the change exists, what is in scope, and expected impact.
3. Draft behavior-first delta specs under `openspec/changes/<change-id>/specs/<capability>/spec.md`.
4. Draft `design.md` for architecture decisions and implementation sequencing.
5. Draft `tasks.md` as the step-by-step checklist.
6. Validate the change with `openspec validate <change-id> --strict` when the OpenSpec CLI is available.
7. Do not implement product code until the proposal is reviewed and approved.

## Conventions

- Specs describe externally visible behavior with MUST/SHALL language and concrete scenarios.
- Keep implementation details in `design.md` and delivery steps in `tasks.md`.
- Prefer small, reviewable stages with clear acceptance criteria.
