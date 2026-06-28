英文镜像见 `checklist.en.md`。

# Slice Spec Checklist

- [ ] `target_id` and `slice_id` are stable.
- [ ] Accepted L1 native evidence is referenced.
- [ ] Source root, source commit, repo commit, C files, signatures, and file hashes are recorded.
- [ ] Build profile records include paths, defines, compiler command source, target ABI, preprocessing mode, tool versions, and clang availability.
- [ ] Fixture cases map to function inputs and observable outputs.
- [ ] Pointer-bearing slices record `c_boundary.pointer_contract` with input buffers, output pointers, inout pointers, length companions, read effects, write effects, and aliasing proof status.
- [ ] `memory_model` records alias contract, ownership contract, length companions, and effect graph assumptions when the Rust boundary depends on pointer or struct memory behavior.
- [ ] C oracle and Rust replay will use the same fixture hash.
- [ ] Public Rust API does not expose raw pointers by default.
- [ ] Accepted metadata differences, non-goals, and forbidden claims are explicit.
- [ ] Cache keys cover source, fixture, build profile, schema, and tool versions.
- [ ] Cache keys cover pointer contract and memory model fields when present.

中文检查：含指针 slice 的 `pointer_contract` 是后续 alias gate 的输入；如果它没有记录读写 effect、长度伴随参数或 aliasing 证明状态，不能把 safe Rust wrapper 当成已接受翻译结果。
