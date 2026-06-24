## Context

The repository has L1 evidence for all 40 validation targets. Failed evidence is intentionally preserved, but the current summary only lists project ids and failure summaries. That is insufficient for deciding whether the next work should install dependencies, repair commands, change smoke scope, retry network-sensitive clones, or skip directly to L2 slices from already-passed projects.

## Goals / Non-Goals

**Goals:**

- Classify all 17 failed L1 attempts from existing evidence and log tails.
- Produce machine-readable JSON and reviewer-friendly Markdown reports.
- Preserve raw evidence paths and failed command details.
- Recommend a concrete next action per failed project.

**Non-Goals:**

- Do not rerun failed builds.
- Do not install dependencies or mutate WSL.
- Do not mark any failed project as fixed.
- Do not change Rust runtime behavior.

## Decisions

### Decision 1: Classify from committed evidence plus external log tails

The classifier reads committed per-project evidence and only small tail excerpts from referenced logs. This keeps token and repository size controlled while preserving a path back to full logs.

### Decision 2: Use deterministic rules with conservative fallbacks

The first version uses explicit rules for timeouts, exit 127, clone failures, root-only restrictions, command mismatch, and dependency/configuration markers. Ambiguous failures stay in `build-failure` or `unknown-failure` instead of overclaiming a cause.

### Decision 3: Keep classification separate from remediation

Fixing failures can require host dependency installation, command changes, retrying upstream clones, or re-scoping smoke commands. Those are separate changes because each can mutate validation meaning.

## Risks / Trade-offs

- [Risk] Log tails may omit the true root cause. -> Mitigation: include full log paths and mark low-confidence classifications where evidence is weak.
- [Risk] Some failures are historical and have older evidence shape. -> Mitigation: handle both modern `commands` evidence and older `failure_summary` formats.
- [Risk] Classification rules can be wrong. -> Mitigation: keep raw failed command, exit code, and excerpt in the report for review.

## Migration Plan

1. Add the classifier.
2. Generate JSON and Markdown reports.
3. Update README with failure classification status and report paths.
4. Run OpenSpec, catalog, Rust tests, and diff verification.
5. Commit and push.
