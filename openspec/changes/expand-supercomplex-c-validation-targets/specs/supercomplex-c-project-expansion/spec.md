## ADDED Requirements

### Requirement: Expanded super-complex target set
The catalog SHALL contain at least 20 complex C or C-major validation targets.

目录必须包含至少 20 个复杂 C 或 C 为主的验证目标。

#### Scenario: Catalog count is raised
- **WHEN** the catalog verifier runs
- **THEN** it requires at least 20 targets
- **AND** each target retains required validation metadata

### Requirement: Additional high-complexity domains
The expanded catalog SHALL include server, codec/compression, language runtime, terminal/system, and RTOS/embedded targets.

扩展目录必须覆盖服务端、编解码/压缩、语言运行时、终端/系统、RTOS/嵌入式等高复杂度领域。

#### Scenario: New target families are present
- **WHEN** the catalog is inspected
- **THEN** it includes Valkey, zstd, libjpeg-turbo, MicroPython, tmux, Zephyr, and FreeRTOS-Kernel

### Requirement: Remote branch drift detection
The remote probe SHALL fail when a probed default branch does not match `expected_default_branch`.

远程探测必须发现默认分支漂移，而不能静默通过。

#### Scenario: Expected branch mismatch fails
- **WHEN** `validate-c-project-catalog.ps1 -ProbeRemote` observes a different default branch
- **THEN** the report records a failure for that target
- **AND** the command exits non-zero

### Requirement: L1/L2 project cards
The system SHALL provide project cards that translate catalog entries into practical L1/L2 validation actions.

系统必须提供项目卡，把目录条目转化为可执行的 L1/L2 验证动作。

#### Scenario: Project cards define next actions
- **WHEN** an agent selects a target for deeper validation
- **THEN** the project-card document provides native build smoke, migration slice, oracle strategy, and risk notes

### Requirement: No L1/L2 overclaim
The expanded catalog SHALL continue to state that L0 validation is not L1/L2/L3 migration evidence.

扩展目录必须继续明确 L0 不等于迁移成功。

#### Scenario: L0 evidence remains bounded
- **WHEN** L0 evidence is generated
- **THEN** its note says it is not C-to-Rust migration equivalence evidence
