# Code-Test Translation Template

中文：本模板用于记录 C-to-Rust 迁移切片中的“代码翻译”和“测试翻译”是否同步推进。它把 C 测试、fixture、oracle 期望、Rust 测试文件、测试函数名、覆盖路径、负向用例和失效键放在同一个可审计 manifest 中。

English: this template records whether code translation and test translation advance together for a bounded C-to-Rust migration slice. It binds C tests, fixtures, oracle expectations, Rust test files, Rust test names, coverage paths, negative cases, and invalidation keys in one auditable manifest.

## Purpose

The manifest is a traceability gate. It prevents a slice from claiming L2 or L3 success from translated code alone when the matching Rust tests, replay checks, and negative/regression checks are not recorded.

It does not prove full semantic equivalence by itself. L3 still requires C oracle output, Rust replay output, schema-aware diff, negative diff, unsafe evidence, pointer/config evidence, and final verification.

中文：该 manifest 是追溯门禁，不是完整语义证明。L3 的等价性仍必须由 C oracle、Rust replay、schema diff、negative diff、unsafe、pointer/config 和最终验证共同支撑。

## Required Evidence

Each applicable L2 or L3 slice should record:

- source test inputs: C test names, fixture files, oracle reports, and oracle strategy.
- Rust tests: test files, test function names, cargo command, and framework.
- coverage: main paths, error paths, and negative/regression cases.
- mappings: each source input or oracle expectation mapped to one or more Rust tests.
- evidence links: C oracle, Rust report, diff, negative diff, slice contract, context pack, unsafe ledger, and related gate evidence.
- cache invalidation keys: source commit, repo commit, fixture hashes, test file hashes, test names, cargo command, accepted differences, profile ids, and manifest schema version.
- known gaps: what this test mapping does not prove.

## Applicability

Use `status:"recorded"` when a slice has mapped source tests, fixtures, or oracle expectations to Rust tests.

Use `status:"not_applicable"` only when there is no translatable C test, fixture, or oracle input for the slice. The manifest must then include `not_applicable_reason`, and the L2/L3 claim still needs replacement evidence for behavior.

Use `status:"stale"` or `status:"incomplete"` when any mapped test input, fixture hash, Rust test name, cargo command, accepted-difference boundary, or supporting evidence changed without regeneration.

## Non-Goals

- This template is not a C test translator.
- It does not replace differential fuzzing, symbolic execution, schema-aware diff, or native C oracle evidence.
- It does not claim full branch coverage unless separate coverage evidence proves it.
- It does not cover async, multithreaded, runtime-cache, power-loss, or capacity-pressure behavior unless those paths appear in explicit tests and evidence.

