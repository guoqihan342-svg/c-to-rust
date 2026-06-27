# Future Vision and MVP Roadmap

Chinese original: `future-vision-and-mvp.md`.

## 1. Goal

Build an end-to-end MVP pipeline: `input.c` → `c2rust-migrator` → `output.rs`. Phase 1 proof is complete (FlashDB crc32 can generate a compilable Rust candidate through real clang AST lowering + typed IR + generic emitter), but significant gaps remain before reaching an industrial-grade C→Rust translator.

## 2. IR Layering Design (Recommended Industrial Standard)

Key principle: **IR must not "decide how Rust should be written"; it must only "describe what C is"**. Correctness comes from C oracle; IR is the intermediate representation that faithfully describes C semantics.

### Layer 1: Semantic IR (Most Important)

**Preserve C semantics. Do not do Rust inference. Do not produce candidates.**

This layer is the translator's core asset. It only answers: "What does this C code do in the C abstract machine?"

- Every C operation preserves its original semantics: integer promotion rules, usual arithmetic conversions, sequence points, lvalue conversions
- No premature judgment on "this pointer can become a slice" or "this struct can become a Rust struct"
- Preserve raw pointer arithmetic, implicit casts, truncation, and promotion information
- Array-to-pointer decay is part of C semantics and must be preserved in the IR
- UB markers (locations of undefined behavior) must also be recorded at this layer

**Current status**: Our typed IR mixes in some Rust inference (e.g., directly marking `const void *` as `&[u8]`). This is acceptable for P0 but should be separated into a dedicated Lowering layer long-term.

### Layer 2: Control IR

**if / loop / goto / switch, with explicit CFG.**

- Control flow transitions from AST to explicit basic blocks + CFG
- `if-else`, `while`, `for`, `do-while`, `switch-case`, `goto`/label all enter a unified CFG
- Each edge carries an explicit condition (or is unconditional)
- `break` and `continue` map to CFG edges; no ad-hoc handling needed
- Support relooper (recovering high-level structured control flow from arbitrary CFG), which is prerequisite for translating `goto` / `switch`

**Current status**: We have a basic `cfg.json` evidence template, but typed IR internally still uses AST-style control flow (`If`, `While`, `For`, `DoWhile`). `switch`, `goto`, and computed goto are completely unsupported.

### Layer 3: Typed Value IR

**integer / pointer / struct / array, explicit casts only.**

- All implicit type conversions (integer promotion, usual arithmetic conversion, array-to-pointer decay, function-to-pointer decay) become **explicit casts** at this layer
- Pointer arithmetic is decomposed into element access: `p + i` becomes `element_at(p, i)` or equivalent
- Struct field access is explicit offset-based or symbolic field access
- Array indexing is explicit base + offset
- The type system only describes C runtime behavior; no Rust type inference

**Current status**: Our typed IR has `Cast { implicit }` to distinguish explicit/implicit casts, integer types have signed/width information, and pointers have `Pointer { pointee }`. However, the clang frontend's handling of `ImplicitCastExpr` is incomplete (some transparently stripped, some preserved), and there is no unified principle of "all implicit casts become explicit."

### Lowering Layer (from Semantic IR to Rust candidate)

This layer converts "describing C" into "generating Rust". Key principles:

1. Do not modify the Semantic IR itself
2. Every lowering rule must be provable (supported by C oracle or typed evidence)
3. When lowering fails, preserve the complete fail-closed reason
4. No "guessing" allowed — if C semantics cannot be safely mapped to safe Rust, refuse translation

Typical lowering rules:
- `const T *p` + read-only access → `p: &[T]` (must prove: no writes, no escape, bounded lifetime)
- `T *out` + write-only access → `out: &mut [T]` (requires noalias proof)
- `uint32_t + uint8_t` → explicit `(byte as u32) + acc` (requires promotion proof)
- `while(size--)` → Rust `loop` + `wrapping_sub` (must preserve postfix side-effect semantics)

## 3. MVP Pipeline Roadmap

```
input.c  →  clang AST dump  →  Semantic IR  →  Lowering  →  Rust candidate
         \                    \              \            \
          source slice         typed IR       route decision  validation gates
          extraction           (current)      (current)       (current)
```

### Phase 1: Completed

- [x] Real clang AST dump parsing (`clang_frontend.rs`)
- [x] typed IR data structures (`IrFunction` / `IrStmt` / `IrExpr` / `IrType`)
- [x] Generic typed IR emitter (scalar + control flow + pointer slice subset)
- [x] Readonly global const array support
- [x] Route decision and validation profile evidence binding
- [x] C oracle harness draft generation
- [x] Rust replay execution and diff gate
- [x] Legacy crc32 specialty code removed
- [x] FlashDB crc32 passes accepted evidence semantic pass

### Phase 2: Near-term (complete IR layering)

- [ ] Separate Semantic IR from Lowering: IR describes C semantics only, not candidates
- [ ] All clang `ImplicitCastExpr` become explicit typed IR casts
- [ ] Array-to-pointer decay as explicit IR node
- [ ] `switch` / `goto` support (requires CFG + relooper)
- [ ] Compound literals, designated initializers
- [ ] Function pointers (at least direct calls and simple passing)
- [ ] `enum` types
- [ ] `union` types (at least tagged union pattern)

### Phase 3: Mid-term (expand real C project coverage)

- [ ] Push more FlashDB functions (`fdb_kv_set`, `fdb_tsl_iter`, etc.) to L3
- [ ] Support real function slices from libuv, zlib-ng, and other projects
- [ ] Select 5+ projects from `validation/projects.json` for full L1→L3
- [ ] Explicit model for usual arithmetic conversions
- [ ] Struct field writes (with alias/noalias proof)
- [ ] Nested structs / anonymous structs
- [ ] Bitfields (at least common patterns)
- [ ] Macro expansion tracking

### Phase 4: Long-term (industrial-grade translator)

- [ ] Full C99/C11 subset coverage
- [ ] Multi-file translation unit support
- [ ] Incremental migration (change one function at a time without breaking the rest)
- [ ] Bidirectional evidence (C→Rust and Rust→C cross-validation)
- [ ] Performance regression gate
- [ ] Automatic fuzz harness generation
- [ ] MIRI validation (Rust UB detection, not as C UB proof)

## 4. Current Core Principles

1. **C oracle is the sole ground truth**. typed IR, clang lowering, and Rust candidates are only descriptions and candidates.
2. **Fail-closed**. When uncertain, refuse translation, record reasons, never pretend success.
3. **Auditable evidence chain**. Every decision step has machine-readable evidence, cross-checked by the validator.
4. **Route only controls candidate path**. Semantic acceptance is decided by validation profile + gates.
5. **IR describes C, does not predict Rust**. Rust type inference and ownership inference are the lowering layer's responsibility.
6. **No restoration of specialty fallbacks**. Old crc32 templates and canned recognizers are deleted; project-specific code must not be reintroduced.
7. **Honest boundaries are more credible than exaggerated demos**. All documentation must honestly list "currently supported" and "explicitly unsupported".
