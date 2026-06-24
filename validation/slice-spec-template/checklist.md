# Slice Spec Checklist

- [ ] `target_id` and `slice_id` are stable.
- [ ] Accepted L1 native evidence is referenced.
- [ ] Source root, source commit, repo commit, C files, signatures, and file hashes are recorded.
- [ ] Build profile records include paths, defines, compiler command source, target ABI, preprocessing mode, tool versions, and clang availability.
- [ ] Fixture cases map to function inputs and observable outputs.
- [ ] C oracle and Rust replay will use the same fixture hash.
- [ ] Public Rust API does not expose raw pointers by default.
- [ ] Accepted metadata differences, non-goals, and forbidden claims are explicit.
- [ ] Cache keys cover source, fixture, build profile, schema, and tool versions.
