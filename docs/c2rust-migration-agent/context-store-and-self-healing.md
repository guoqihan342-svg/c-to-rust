英文镜像见 `context-store-and-self-healing.en.md`。

# Cross-File Context Store and Compile Self-Healing

中文说明：跨文件上下文管理是这个 Agent 的核心。不能把整个仓库一次性塞给 AI，也不能在单点重构时破坏模块调用关系。

English summary: the Agent maintains a local structured context store and uses rustc JSON error stacks to repair builds through minimal PatchPlans.

## SQLite Schema

Initial tables:

```sql
CREATE TABLE files (
  id INTEGER PRIMARY KEY,
  path TEXT NOT NULL,
  language TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  source_commit TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE symbols (
  id INTEGER PRIMARY KEY,
  file_id INTEGER NOT NULL,
  name TEXT NOT NULL,
  kind TEXT NOT NULL,
  span_start INTEGER,
  span_end INTEGER,
  signature TEXT,
  visibility TEXT,
  evidence_json TEXT NOT NULL
);

CREATE TABLE call_edges (
  id INTEGER PRIMARY KEY,
  caller_symbol_id INTEGER NOT NULL,
  callee_symbol_id INTEGER,
  callee_name TEXT NOT NULL,
  call_kind TEXT NOT NULL,
  evidence_json TEXT NOT NULL
);

CREATE TABLE type_layouts (
  id INTEGER PRIMARY KEY,
  type_name TEXT NOT NULL,
  size_bytes INTEGER,
  align_bytes INTEGER,
  fields_json TEXT,
  repr TEXT,
  evidence_json TEXT NOT NULL
);

CREATE TABLE macro_cfg_facts (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  value TEXT,
  applies_to TEXT,
  evidence_json TEXT NOT NULL
);

CREATE TABLE pointer_facts (
  id INTEGER PRIMARY KEY,
  symbol_id INTEGER,
  pointer_kind TEXT NOT NULL,
  mutability TEXT,
  ownership_hint TEXT,
  nullability TEXT,
  evidence_json TEXT NOT NULL
);

CREATE TABLE rust_items (
  id INTEGER PRIMARY KEY,
  file_id INTEGER NOT NULL,
  item_path TEXT NOT NULL,
  item_kind TEXT NOT NULL,
  signature TEXT,
  unsafe_count INTEGER DEFAULT 0,
  evidence_json TEXT NOT NULL
);

CREATE TABLE error_events (
  id INTEGER PRIMARY KEY,
  rustc_code TEXT,
  primary_file TEXT,
  primary_span TEXT,
  root_cause_key TEXT,
  message_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE patch_events (
  id INTEGER PRIMARY KEY,
  patch_plan_id TEXT NOT NULL,
  rollback_id TEXT NOT NULL,
  files_json TEXT NOT NULL,
  result TEXT NOT NULL,
  evidence_json TEXT NOT NULL
);

CREATE TABLE test_traces (
  id INTEGER PRIMARY KEY,
  test_name TEXT NOT NULL,
  oracle TEXT NOT NULL,
  input_hash TEXT NOT NULL,
  result_hash TEXT NOT NULL,
  evidence_json TEXT NOT NULL
);

CREATE TABLE unsafe_ledger (
  id INTEGER PRIMARY KEY,
  file TEXT NOT NULL,
  span TEXT NOT NULL,
  category TEXT NOT NULL,
  reason TEXT NOT NULL,
  alternative_considered TEXT,
  tests_covering_json TEXT NOT NULL,
  evidence_json TEXT NOT NULL
);
```

## Evidence Fields

Every stored fact must include:

- `source_tool`
- `source_version`
- `schema_version`
- `source_commit`
- `file_hash`
- `span`
- `confidence`
- `created_at`

Low-confidence facts can guide exploration, but cannot justify API changes, unsafe additions, or semantic equivalence.

## JSONL Event Format

Append-only events are written to files such as `operations.jsonl`, `patches.jsonl`, `tests.jsonl`, and `unsafe.jsonl`:

```json
{
  "event_id": "evt-000001",
  "event_type": "patch_attempt",
  "schema_version": "0.1.0",
  "source_commit": "93d175549da579b8abac07bd175ce4c3f9dde829",
  "tool": "c2rust-migration-agent",
  "input_hash": "sha256:...",
  "payload": {},
  "result": {},
  "created_at": "2026-06-24T00:00:00+08:00"
}
```

## ContextPack

Default depth is 1-hop:

```json
{
  "target_item": "kvdb.set",
  "owning_module": "kvdb",
  "direct_callers": [],
  "direct_callees": [],
  "public_types": [],
  "type_layouts": [],
  "macro_cfg_facts": [],
  "pointer_facts": [],
  "related_tests": [],
  "current_diff": "",
  "rustc_error_stack": [],
  "unsafe_ledger_summary": {}
}
```

Controlled 2-hop expansion is allowed only when direct facts cannot explain trait, lifetime, ownership, or cross-module signature failures.

## Impact-Set Workflow

Before changing a cross-module signature, the Agent must produce an impact set:

- target symbol and owning module
- direct callers and callees
- public API adapters affected
- tests that must be updated
- fixture or golden image changes
- unsafe ledger impact
- rollback id

No caller edits are allowed outside the approved impact set.

## rustc Error Stack Model

Compile validation uses:

```bash
cargo check --message-format=json
```

The parser stores:

- `code`: rustc code such as `E0308`
- `primary_span`
- `related_spans`
- `rendered_message`
- `suggested_replacements`
- `root_cause_key`
- `affected_items`

Initial classifiers:

- `E0308`: type mismatch, newtype mismatch, slice/value mismatch, `Result`/`Option` mismatch
- `E0499`, `E0502`: conflicting borrow, borrow scope too wide
- `E0382`: moved value
- `E0277`: trait bound missing
- `E0599`: method not found or trait not in scope
- missing imports and module paths
- cfg/feature mismatch
- lifetime errors
- unsafe/layout errors
- semantic test failures

## PatchPlan

```json
{
  "id": "patch-0001",
  "files": [
    "flashDB_rust/src/kvdb.rs"
  ],
  "spans": [
    {
      "file": "flashDB_rust/src/kvdb.rs",
      "start": 120,
      "end": 140
    }
  ],
  "reason": "Narrow mutable borrow scope for iterator update",
  "expected_error_delta": {
    "remove": [
      "E0502"
    ],
    "allow_new_errors": false
  },
  "risk": "medium",
  "rollback_id": "good-0003",
  "ai_used": false,
  "forbidden_changes": [
    "add unregistered unsafe",
    "change public API outside impact set"
  ],
  "verification_commands": [
    "cargo check --message-format=json",
    "cargo test"
  ]
}
```

Rule-based repair runs before AI. Retry limits are bounded per root cause. When the limit is exceeded, rollback to the last known good state and record migration debt.
