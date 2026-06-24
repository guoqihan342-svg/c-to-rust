## 1. Evidence And Scope

- [x] 1.1 Persist a red scan showing existing mojibake markers in OpenSpec artifacts.
- [x] 1.2 Confirm the repair is documentation-only and does not change Rust runtime, fixture, replay, diff, or C oracle behavior.

## 2. Repair

- [x] 2.1 Repair mojibake prose in `openspec/changes/design-c2rust-migration-agent/specs/unsafe-budget-and-safe-api/spec.md`.
- [x] 2.2 Repair mojibake prose in `openspec/changes/design-c2rust-migration-agent/specs/skeleton-first-migration/spec.md`.
- [x] 2.3 Repair mojibake prose in `openspec/changes/design-c2rust-migration-agent/specs/cross-file-context-management/spec.md`.
- [x] 2.4 Repair mojibake prose in `openspec/changes/design-c2rust-migration-agent/specs/build-and-version-baseline/spec.md`.
- [x] 2.5 Repair mojibake prose in `openspec/changes/design-c2rust-migration-agent/specs/agent-orchestration-interface/spec.md`.
- [x] 2.6 Repair mojibake prose in `openspec/changes/design-c2rust-migration-agent/specs/semantic-equivalence-verification/spec.md`.
- [x] 2.7 Repair mojibake prose in `openspec/changes/design-c2rust-migration-agent/specs/compile-self-healing/spec.md`.

## 3. Verification And Delivery

- [x] 3.1 Rerun the mojibake scan and persist a green scan log.
- [x] 3.2 Run `openspec validate repair-flashdb-l3-spec-bilingual-text --strict`.
- [x] 3.3 Run `openspec validate --all`.
- [x] 3.4 Run `git diff --check`.
- [x] 3.5 Archive the OpenSpec repair change.
- [x] 3.6 Commit and push the verified documentation repair slice.
