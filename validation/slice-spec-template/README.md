# Slice Spec Template

This template defines the machine-readable input contract for a bounded automatic C-to-Rust translation run.

中文说明：slice spec 是自动翻译入口证据，只描述已经通过 L1 native validation 的 C function slice、可复现 build profile、fixture contract 和 Rust 边界；它不代表翻译已经正确。

## Required Evidence

- Target id, slice id, L1 evidence, source commit, repo commit, C files, function signatures, build profile, fixture contract, Rust boundary, accepted metadata differences, non-goals, and cache invalidation keys.
- Build profile must record include paths, defines, target ABI, preprocessing mode, tool versions, and clang type extraction availability.
- Rust public API must not expose raw pointers by default, and unsafe usage must require ledger evidence.

## Files

- `slice-spec.schema.json`
- `slice-spec.example.json`
- `checklist.md`
