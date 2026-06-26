# Core Translation Architecture

This page records the current `c-to-rust` core translation pipeline, key code locations, and FlashDB crc32 generic-emitter progress. The Chinese mirror is `core-translation-architecture.md`.

## Architecture

```mermaid
flowchart TD
    C["C source / compile_commands.json"] --> Clang["clang_frontend.rs<br/>clang AST dump frontend"]
    Clang --> Skeleton["clang skeleton AST subset"]
    Skeleton --> IR["typed IR: IrFunction / IrStmt / IrExpr / IrType"]
    Clang --> Globals["readonly globals: Vec<IrGlobal><br/>static const integer arrays"]
    IR --> EmitCtx["typed_ir.rs<br/>emit_rust_from_ir_with_globals(function, globals)"]
    Globals --> EmitCtx
    EmitCtx --> RouteMeta["translation_route.rs<br/>CandidateRouteDecision"]
    RouteMeta --> Generic["GenericTypedIr<br/>generic typed IR emitter"]
    RouteMeta --> Unsupported["Unsupported<br/>no Rust candidate"]
    Generic --> Rust["safe Rust draft"]
    Rust --> Rustc["rustc smoke / cargo tests"]
    Rustc --> Validation["validation pipeline<br/>route_decision / validation_profile / evidence gates"]

    Generic --> Supported["current generic coverage:
    scalar decl/assign/if/while,
    comparison conditions,
    const pointer slices,
    readonly global const integer arrays,
    table index via slice param or global,
    nested byte *p++ prelude,
    size_t while(size--)"]
    Validation --> Semantic["semantic_pass is decided only by validation"]
```

## Core Code Map

- `crates/c2r-translator/src/clang_frontend.rs`
  - Reads real clang AST dump JSON.
  - Lowers supported C AST nodes into a compact clang skeleton.
  - Converts skeleton nodes into typed IR.
  - Also collects top-level `static const` fixed-length integer array initializers as `ClangLoweringReport.globals: Vec<IrGlobal>`.
  - Important functions: `lower_function_from_clang_ast_dump_report`, `lower_function_from_clang_parse_spec_report`, `readonly_globals_from_ast`, `readonly_global_from_toplevel_var_decl`, `integer_literal_init_list_values`, `expr_skeleton_from_ast_with_options`, `lower_stmt`, `lower_expr`.
- `crates/c2r-translator/src/typed_ir.rs`
  - Defines `IrFunction`, `IrStmt`, `IrExpr`, `IrType`, `IrGlobal`, and `IrGlobalInit`.
  - `emit_rust_from_ir()` remains the no-globals compatibility entrypoint.
  - `emit_rust_from_ir_with_globals(function, globals)` is the main entrypoint for the clang lowering path and returns `EmittedRust { rust, route }`.
  - The generic emitter now emits readonly global integer arrays as Rust `const` items and supports table indexing such as `CRC32_TABLE[...]`.
  - The typed IR legacy crc32 matcher, canned emitter, and `DeprecatedLegacyCrc32` fallback have been removed. A crc32 IR without modeled globals now fails closed instead of silently using a template.
- `crates/c2r-translator/src/translation_route.rs`
  - Defines route metadata for typed IR candidate generation.
  - `GenericTypedIr` is the normal typed IR emitter.
  - `Unsupported` means no Rust candidate; the error keeps route metadata and the fail-closed reason.
- `crates/c2r-translator/src/lib.rs`
  - `try_translate_slice_with_clang_lowered_ir()` passes both `ClangLoweringReport.function_ir` and `report.globals` into `emit_rust_from_ir_with_globals()`.
  - `write_translation_artifacts()` can produce a Rust draft driven by clang-lowered typed IR when the `clang-lowering-report` feature is enabled.
  - The old string translator still keeps a crc32 byte-cursor template path in `is_crc32_byte_cursor_loop()` and the local `emit_crc32_byte_cursor_rust()`. It no longer bridges into typed IR and no longer records `typed-ir-crc32-emitter` provenance.
- `crates/c2r-translator/tests/bounded_translation.rs`
  - Main behavior contract for the bounded translator.
  - Covers direct typed IR tests, real clang AST smoke tests, the real FlashDB crc32 parse spec, fail-closed boundaries, and rustc smoke compilation.
- `CONTEXT.md`
  - Chronological handoff log for this branch.
  - Use the latest numbered section first when resuming work.

## Current Core Translation Status

The typed IR candidate generation layer now has two explicit outcomes:

- `GenericTypedIr`: the generic typed IR emitter. Real FlashDB `fdb_calc_crc32` now reaches this route through clang lowering plus globals and passes rustc smoke.
- `Unsupported`: no Rust candidate; the error carries route metadata and the fail-closed reason.

Candidate route selects the candidate generation implementation only. It does not decide `semantic_pass` and does not replace the evidence `route_decision` in `validation/tools/auto_migrate.py`. Acceptance still belongs to validation profile gates such as C oracle, Rust replay, schema diff, negative diff, unsafe ledger, and final verification.

Generic typed IR emission now covers:

- scalar declarations, assignment, return, `if`, and `while`;
- comparison expressions only in conditions;
- initialized scalar locals from clang AST;
- no-brace `if` / `while` bodies from clang AST;
- readonly integer pointer parameters as Rust slices, for example `const uint32_t *table -> table: &[u32]`;
- `static const` readonly integer array initializers as Rust `const`, for example `crc32_table[] -> const CRC32_TABLE: [u32; 256]`;
- `const void *buf` as `&[u8]` only when a proven `const uint8_t *p` cursor and byte read exist;
- nested byte cursor reads such as `(uint32_t)*p++` through prelude temporaries;
- assignment RHS prelude, covering `crc = table[(crc ^ (uint32_t)*p++) & 0xff] ^ (crc >> 8);`;
- narrow `size_t` postfix-decrement while conditions, lowering `while (size--)` into a Rust `loop` that preserves postfix side effects.

Still incomplete:

- The old string translator still has a crc32 byte-cursor recognizer and canned Rust template. That is a legacy parser path, not a typed IR fallback.
- The current work proves candidate generation plus rustc smoke, not semantic acceptance for the real FlashDB slice.
- Complex function pointers, unmodeled alias writes, volatile/hardware registers, macro side effects, and cross-thread/interrupt semantics should still fail closed or route higher.

## Next Implementation Cut

1. Extend validation evidence so `ClangLoweringReport.globals` and the `GenericTypedIr` route are bound into route decision/profile evidence.
2. Run full C/Rust oracle, negative diff, unsafe ledger, and final verification for the real FlashDB crc32 slice.
3. Clean up the old string translator crc32 recognizer and canned template separately, or downgrade it to an explicit legacy compatibility path.
4. Keep extending generic typed IR instead of adding FlashDB-specific logic.
