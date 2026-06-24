## Context

The reverse-query-reopen slice validates that a TSDB reverse query keeps order and visible entry status before and after reopen. The existing test already locks the query outputs and accepted-difference fields, but it leaves the reopen operation report under-specified.

reverse-query-reopen 切片验证 TSDB 反向 query 在 reopen 前后保持顺序和可见状态。现有测试已经锁定 query 输出和 accepted-difference 字段，但 reopen 操作自身的报告字段还不够严格。

## Goals / Non-Goals

**Goals:**

- Make the existing Rust replay test assert the reopen step's `status`, `code`, and `image_hash` field.
- Keep the assertion narrow and string-based, matching the style already used in `differential_replay.rs`.
- Persist targeted test evidence.

**Non-Goals:**

- Do not change `TsDb`, replay serialization, fixture contents, C oracle behavior, or schema-aware diff logic.
- Do not add a new L3 semantic slice.
- Do not regenerate historical C oracle evidence for this small test hardening.

## TDD Note

This slice changes tests only. No production code will be edited. The red check is a targeted test run with an intentionally stricter assertion before any production change; if the current implementation already emits the required fields, the implementation remains unchanged and the green check proves the existing behavior is now locked by the test.

本切片只改测试，不改生产代码。若当前实现已经输出所需字段，测试加固会直接变绿；这不是业务实现跳过 TDD，而是把已存在行为纳入自动化回归保护。

## Risks / Trade-offs

- The assertion stays string-based to match the surrounding tests and avoid adding JSON parsing dependencies.
- The test checks that `image_hash` is present without pinning the hash value, because file-backed image hashes are layout metadata and accepted as non-semantic.
