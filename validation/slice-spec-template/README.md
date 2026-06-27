# Slice Spec Template

This template defines the machine-readable input contract for a bounded automatic C-to-Rust translation run.

中文说明：slice spec 是自动翻译入口证据，只描述已经通过 L1 native validation 的 C function slice、可复现 build profile、fixture contract 和 Rust 边界；它不代表翻译已经正确。

## Required Evidence

- Target id, slice id, L1 evidence, source commit, repo commit, C files, function signatures, build profile, fixture contract, Rust boundary, accepted metadata differences, non-goals, and cache invalidation keys.
- Build profile must record include paths, defines, target ABI, preprocessing mode, tool versions, and clang type extraction availability.
- Rust public API must not expose raw pointers by default, and unsafe usage must require ledger evidence.

## Pointer And Memory Model

English: `c_boundary.pointer_contract` is the input contract used by the automatic translator to derive pointer graph and alias gate evidence. It records input buffers, output pointers, inout pointers, length companions, read/write effects, and whether aliasing has been proven. `memory_model` records the higher-level ownership, length, alias, and effect assumptions that the generated Rust boundary depends on.

中文：`c_boundary.pointer_contract` 是自动翻译器推导 pointer graph 和 alias gate 的输入契约，用来记录 input buffer、output pointer、inout pointer、长度伴随参数、读写 effect，以及 aliasing 是否已被证明。`memory_model` 记录生成 Rust 边界依赖的 ownership、length、alias 和 effect 假设。

English: scalar-only slices may omit `pointer_contract`, but pointer-bearing slices should record it before code generation. Missing or stale pointer contracts must keep alias-sensitive translation at candidate or blocked status.

中文：纯标量 slice 可以省略 `pointer_contract`；含指针 slice 应在代码生成前记录它。如果 pointer contract 缺失或过期，alias-sensitive 翻译只能保持 candidate 或 blocked，不能直接声称成功。

## Files

- `slice-spec.schema.json`
- `slice-spec.example.json`
- `checklist.md`
