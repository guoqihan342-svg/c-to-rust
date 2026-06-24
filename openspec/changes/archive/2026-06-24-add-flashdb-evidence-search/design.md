## Context

FlashDB L3 migration evidence is already persisted under `validation/evidence/flashdb/`, but retrieval is mostly manual. Agents currently need to remember filename conventions or run ad hoc text searches across JSON, JSONL, Markdown, and log files. That is enough for a human in a small slice, but it becomes weak when multiple L3 slices, version manifests, patch events, error events, and final verification logs need to be traced quickly.

FlashDB L3 迁移证据已经落在 `validation/evidence/flashdb/`，但检索主要依赖人工记文件名或临时 `rg`。当多个 L3 切片、version manifest、patch event、error event 和最终验证日志并存时，Agent 需要一个稳定的小命令来快速定位证据来源。

## Goals / Non-Goals

**Goals:**

- Add a dependency-free Rust CLI command that searches local evidence files.
- Return deterministic JSON with command metadata, query metadata, match count, and per-match `path`, `line`, and `snippet`.
- Support stdout-only use and `--report <path>` persistence with the same JSON bytes.
- Keep the command synchronous, bounded by `--limit`, and unsafe-free.
- Cover `.json`, `.jsonl`, `.log`, and `.md` files because those are the evidence formats currently in use.

**Non-Goals:**

- Do not add AI calls or semantic embedding search.
- Do not create a long-lived index, cache database, daemon, or background worker.
- Do not parse every evidence schema in this slice; line-oriented text matching is enough for traceability.
- Do not wire this command into CI scripts until the command contract is stable.

## Decisions

1. Use `evidence-search` as a subcommand in `flashDB_rust/src/cli.rs`.

   Rationale: the existing CLI is intentionally small and dependency-free. Adding a separate module is unnecessary for this first slice; if the command grows beyond simple file walking and line matching, it can be extracted later.

2. Use `--evidence-dir <path>`, `--query <text>`, optional `--limit <N>`, and existing `--report <path>`.

   Rationale: `--evidence-dir` is explicit enough for future projects, while `--query` avoids locking the command to substring-only naming. The first implementation will still use deterministic substring search.

3. Search supported text evidence extensions only.

   Rationale: this keeps the command fast and avoids accidentally reading binary flash images or build artifacts. The initial set is `.json`, `.jsonl`, `.log`, and `.md`.

4. Produce compact JSON manually, matching the existing CLI style.

   Rationale: the crate currently has no runtime dependencies. Keeping the command std-only preserves build speed, avoids version drift, and keeps the unsafe ratio unchanged.

5. Sort directory entries and stop at `--limit`.

   Rationale: deterministic output is more useful for regression tests and future evidence comparison. A bounded limit prevents large evidence directories from producing noisy reports.

6. Stream evidence files line by line and enforce hard resource bounds.

   Rationale: `.log` and single-line `.json` evidence can grow large. Reading one line at a time, rejecting `--limit 0`, rejecting limits above 10000, skipping symlink directories, and bounding recursion/file counts keeps the command usable in large local evidence trees without adding async, threads, or cache state.

7. Escape JSON control characters manually.

   Rationale: evidence logs can contain tabs, carriage returns, and other control bytes. The command must emit valid JSON while staying dependency-free.

## Risks / Trade-offs

- Exact substring search can miss equivalent structured values with different formatting -> keep this slice small, then add schema-aware field filtering only when a real workflow needs it.
- Manual JSON formatting can be error-prone -> reuse the existing `escape_json` helper and cover path, query, line, and snippet escaping in tests.
- Recursing arbitrary directories can be slow -> search only known text extensions and stop after `--limit`.
- First version does not rank matches -> deterministic path and line order is simpler and reproducible.
