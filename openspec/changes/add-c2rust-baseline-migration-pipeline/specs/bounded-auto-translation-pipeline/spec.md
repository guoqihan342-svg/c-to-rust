## ADDED Requirements

### Requirement: C2Rust Baseline Manifest Is Bound To Auto Migration Evidence
The automatic migration pipeline SHALL bind optional C2Rust baseline evidence into the same slice-level evidence manifest as context pack, type map, CFG, pointer graph, Rust draft, Agent candidate, and final verification artifacts.

自动迁移管线必须把可选 C2Rust baseline 证据绑定到与 context pack、type map、CFG、pointer graph、Rust draft、Agent candidate 和 final verification 相同的 slice-level evidence manifest。

#### Scenario: C2Rust baseline manifest is emitted
- **WHEN** `auto_migrate` prepares a slice and C2Rust probing is enabled
- **THEN** the run writes `l3-<slice>-c2rust-baseline-manifest.json` with source commit, slice spec hash, build profile hash, C2Rust command or reference path, tool version or `NOT_FOUND`, status, output hash if generated, and diagnostics

#### Scenario: Missing C2Rust records skipped evidence
- **WHEN** no executable C2Rust command is available for the run
- **THEN** `l3-<slice>-c2rust-baseline-manifest.json` records status `skipped`
- **AND** the final L3 manifest records that C2Rust baseline was unavailable
- **AND** no accepted result may claim C2Rust-generated baseline support

#### Scenario: Baseline drift invalidates cached candidates
- **WHEN** C2Rust version, command arguments, source file hashes, build profile hash, or baseline output hash changes
- **THEN** cached Agent candidates, route decisions, Rust drafts, and validation summaries that depended on the old baseline are invalidated or explicitly reviewed before reuse

### Requirement: Route Decision Artifact Precedes Rust Draft
The automatic migration pipeline SHALL write route-decision evidence before deterministic translation, Agent candidate generation, or Rust draft acceptance.

自动迁移管线必须在确定性翻译、Agent 候选生成或 Rust draft 接受前写入 route-decision 证据。

#### Scenario: Route decision precedes candidate generation
- **WHEN** `auto_migrate` has generated context pack, type map, CFG, pointer graph, and optional C2Rust baseline manifest
- **THEN** it writes `l3-<slice>-route-decision.json`
- **AND** later translation plan, Agent candidate manifest, Rust check, diff, unsafe ledger, and final verification artifacts reference the route-decision hash

#### Scenario: Route level controls translator path only
- **WHEN** a route decision selects Tier 1 deterministic translation or Agent candidate generation
- **THEN** the selected path controls candidate generation cost and context size
- **AND** correctness acceptance still requires the selected validation profile gates to pass

#### Scenario: L4 route blocks false success
- **WHEN** a route decision level is `L4`
- **THEN** the run writes blocked repair evidence
- **AND** no Rust draft, Agent candidate, or C2Rust baseline may be marked accepted for that slice

### Requirement: Validation Profile Evidence Replaces Fixed Loop Requirements
The automatic migration pipeline SHALL record validation profile requirements per run instead of relying on a fixed stress-loop count as a project-level requirement.

自动迁移管线必须按运行记录 validation profile 要求，而不是把固定压力轮数作为项目级要求。

#### Scenario: Profile records required gates
- **WHEN** final verification runs for a slice
- **THEN** the run writes `l3-<slice>-validation-profile.json` with route level, goal, required gates, optional gates, skipped gates, skip reasons, and profile result

#### Scenario: Loop count is not hardcoded
- **WHEN** a run performs regression or stress loops
- **THEN** the chosen loop count is recorded as policy input and evidence output
- **AND** the absence of a fixed 10-round or 10000-round loop count MUST NOT by itself fail the project contract

#### Scenario: Skipped required gate blocks acceptance
- **WHEN** a gate required by the selected validation profile is skipped because tooling is unavailable
- **THEN** the slice remains blocked or incomplete
- **AND** the skipped reason is recorded in validation-profile and final-verification evidence

### Requirement: OpenSpec Capability And Slice Evidence Granularity
The system SHALL use OpenSpec changes for capability or batch governance and slice-level evidence manifests for individual function migration records.

系统必须用 OpenSpec change 管理能力或批次治理，用 slice-level evidence manifest 记录单个函数迁移。

#### Scenario: Slice evidence records per-function migration
- **WHEN** a function is extracted, routed, translated, repaired, accepted, or blocked
- **THEN** the slice evidence directory records the function-level artifacts, route decision, verification profile, and final status
- **AND** a separate OpenSpec change for that single function is optional unless the function migration changes a public project contract

#### Scenario: Capability change governs schema and gate behavior
- **WHEN** route-decision, C2Rust baseline, validation-profile, Agent candidate, or unsafe ledger semantics change
- **THEN** the behavior is captured in OpenSpec requirements before implementation is accepted
