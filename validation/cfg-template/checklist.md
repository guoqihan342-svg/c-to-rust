英文镜像见 `checklist.en.md`。

# CFG Checklist

- [ ] Every translated function has an entry block and exit block list.
- [ ] Basic blocks include kind, statements, and source span.
- [ ] Edges include fallthrough, true/false branch, loop back, return, break, or continue relationships.
- [ ] Branches and returns are recorded with source spans.
- [ ] Unsupported `goto`, computed goto, switch fallthrough, setjmp/longjmp, inline assembly, and multi-entry loops are recorded.
- [ ] Unsupported control flow blocks automatic Rust draft success unless a supported relooper path is recorded.
- [ ] CFG drift invalidates Rust draft, PatchPlan, oracle/replay generation, diff, unsafe, and final verification evidence.
