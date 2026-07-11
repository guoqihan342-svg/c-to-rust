英文镜像见 `full-regression-runner.en.md`。

# Full Regression Runner

中文说明：`scripts/run-full-regression.ps1` 是根目录级总控回归入口，用来把 FlashDB Rust、L2 slices、bounded translator、auto-translation evidence、Superpowers gates 和仓库 whitespace 检查串成可重复轮次。它不把合成负载冒充真实生产数据，也不声称 `cargo-llvm-cov` 分支覆盖率。

English summary: `scripts/run-full-regression.ps1` is the repository-level regression orchestrator for repeated validation rounds. It records machine-readable evidence under `target/full-regression/` and keeps correctness claims bounded to the executed gates.

## Recommended Local Gate

Run one full round with a 10000-loop FlashDB release stress pass:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run-full-regression.ps1 -Rounds 1 -StressLoops 10000
```

On Ubuntu, run the same script with the current PowerShell executable, usually `pwsh`, and bind the competition environment profile:

```bash
pwsh -File ./scripts/run-full-regression.ps1 \
  -Rounds 1 \
  -StressLoops 10000 \
  -EnvironmentProfile config/competition-env/environment.json
```

This runs:

- L0 catalog validation.
- `crates/c2r-translator` fmt, tests, and clippy unless `-SkipClippy` is set.
- `validation/l2_slices` fmt and tests.
- Python auto-migration unit tests.
- auto-translation evidence schema plus semantic-pass validators for the accepted libuv and zlib slices.
- `flashDB_rust` fmt, check, tests, clippy unless `-SkipClippy` is set, smoke, replay/diff, unsafe scan, version manifest, and release stress.
- evidence search for traceability.
- `git diff --check`.

## 10000 Full Rounds

To run 10000 complete validation rounds, use:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run-full-regression.ps1 -Rounds 10000 -StressLoops 10000
```

This is intentionally expensive. Each round writes logs and JSONL events under:

```text
target/full-regression/<run-id>/
```

If a run is interrupted, resume with the same run id and a later start round:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run-full-regression.ps1 -RunId <run-id> -StartRound 231 -Rounds 10000 -StressLoops 10000
```

By default the runner stops at the first failed step. Use `-ContinueOnFailure` only when collecting a failure matrix.

## Evidence Files

Each run emits:

- `events.jsonl`: one machine-readable event per step.
- `summary.json`: final status, failed step when present, coverage boundary, environment profile path/hash, and evidence root.
- `round-00001/*.log`: command output per step.
- round-local JSON reports for smoke, fixture replay/diff, version manifest, evidence search, catalog validation, and release stress.

All of these live under `target/`, which is ignored by git.

## Claim Boundaries

- Production data: default coverage uses committed fixtures plus deterministic production-like stress. It is not real production data. Real or de-identified production fixtures must be replayed and diffed before claiming production-data equivalence.
- Abnormal data: covered by Rust tests, abnormal fixtures, and the FlashDB stress abnormal scenario.
- Performance: release stress records duration, counters, bytes processed, and image hashes. It is performance smoke evidence, not a stable benchmark threshold.
- Reliability: file-backed stress reopens images and checks persisted values. It is not crash-power-loss or hardware reliability proof.
- Branch coverage: cargo tests and Superpowers gates cover main behavior paths, but this runner does not claim line or branch coverage percentage.
- C/Rust equivalence: accepted L3 evidence is checked where committed. Full FlashDB C semantic equivalence still depends on the C oracle boundary and fixture scope.
