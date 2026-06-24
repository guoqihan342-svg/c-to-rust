## ADDED Requirements

### Requirement: FlashDB Evidence Trace Search CLI
The system SHALL expose a small Rust CLI command that searches local FlashDB migration evidence and returns traceable match metadata without AI calls, unsafe code, or new runtime dependencies.

系统必须提供一个小型 Rust CLI 命令，用于检索本地 FlashDB 迁移证据，并返回可追溯的命中元数据；该命令不得调用 AI，不得引入 unsafe，也不得新增运行时依赖。

#### Scenario: Search returns traceable matches
- **WHEN** `flashdb-rust evidence-search --evidence-dir <dir> --query <text>` is executed against supported evidence files
- **THEN** it prints JSON containing `command:"evidence-search"`, `schema_version:1`, the evidence directory, the query, `match_count`, and a `matches` array with each match's `path`, `line`, and `snippet`

#### Scenario: Search writes an optional report
- **WHEN** `flashdb-rust evidence-search --evidence-dir <dir> --query <text> --report <path>` is executed
- **THEN** it writes the same JSON emitted to stdout to the requested report path and creates the parent directory when needed

#### Scenario: Search report does not match itself
- **WHEN** the requested `--report` path already exists inside the evidence directory and contains the query text
- **THEN** the search excludes that report path from matching before writing the new report

#### Scenario: Search only scans supported evidence text files
- **WHEN** the evidence directory contains `.json`, `.jsonl`, `.log`, `.md`, and unsupported files
- **THEN** only `.json`, `.jsonl`, `.log`, and `.md` files are scanned for matches

#### Scenario: Search is deterministic and bounded
- **WHEN** `--limit <N>` is provided
- **THEN** matches are returned in deterministic path and line order and no more than `N` matches are emitted

#### Scenario: Search rejects invalid limits
- **WHEN** `--limit` is `0` or greater than the maximum supported evidence search limit
- **THEN** the command fails with a CLI error explaining the accepted limit range

#### Scenario: Search snippets are bounded
- **WHEN** a matching evidence line is longer than the snippet budget
- **THEN** the emitted `snippet` is truncated to a bounded excerpt instead of copying the full line

#### Scenario: Search emits valid JSON for control characters
- **WHEN** the query or matching snippet contains tab, carriage return, or other JSON control characters
- **THEN** those characters are escaped in the JSON output

#### Scenario: Search reports missing query input
- **WHEN** `evidence-search` is executed without `--query`
- **THEN** the command fails with a CLI error explaining that `evidence-search` requires `--query`

#### Scenario: Search rejects empty query input
- **WHEN** `evidence-search` is executed with an empty `--query`
- **THEN** the command fails with a CLI error explaining that `evidence-search` requires a non-empty query
