# Type Map Checklist

- [ ] Primitive, struct, enum, pointer, integer-width, implicit-cast, typedef, and function signature mappings are represented when present.
- [ ] Each mapping records C type, Rust type, source, confidence, and translation rule id.
- [ ] Source spans are present where the mapping comes from a concrete declaration or expression.
- [ ] Unresolved typedef, macro, ABI, struct layout, enum value, pointer mutability, and implicit cast facts are listed as uncertainty or unsupported evidence.
- [ ] Pointer mappings refer to pointer graph nodes when available.
- [ ] Type map drift invalidates CFG, pointer graph, Rust draft, PatchPlan, oracle, replay, diff, unsafe, and summary evidence.
