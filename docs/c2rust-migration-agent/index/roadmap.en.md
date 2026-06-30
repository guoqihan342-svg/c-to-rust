# English Mirror: Roadmap

Chinese original: `roadmap.md`.

This file is the English mirror for `docs/c2rust-migration-agent/index/roadmap.md`. The Chinese source is the authoritative maintenance document; update this file in the same change whenever the Chinese document changes.

## Scope

This mirror covers the categorized document index for the migration-agent documentation set. It is intentionally concise for older plans, templates, and OpenSpec records so that the repository has a stable bilingual entry point without turning historical artifacts into the active backlog.

## Source Outline

The Chinese source currently contains these major headings:

- `# 覆盖与路线`
- `## 评委 Demo / Milestone`

## Judge Demo / Milestone

The current public before/after demo entrypoint is `../judge-demo.md`. Run:

```bash
python -B -m validation.tools.opencode_agent_harness run-batch-profile --profile config/competition-env/planned-batches/demo-store-add-one-before-after.json --run-id competition-demo-before-after-exhibit --out-root target/competition-out-demo-before-after-exhibit
python -B validation/tools/milestone_release_report.py --competition-summary target/competition-out-demo-before-after-exhibit/summary/competition-run-summary.json --batch-profile-report target/competition-out-demo-before-after-exhibit/harness/batch-profile-report.json --output target/competition-out-demo-before-after-exhibit/summary/milestone-release-report.json
```

Key artifacts:

- `target/competition-out-demo-before-after-exhibit/summary/before-after-exhibit.json`
- `target/competition-out-demo-before-after-exhibit/summary/milestone-release-report.json`

Boundary: the demo binds accepted-evidence before/after artifacts and unsafe 3 -> 0, but it does not increase `translation_coverage_numerator`.

## Maintenance Notes

- Keep filenames paired as `roadmap.md` and `roadmap.en.md` in the same directory.
- Keep the first line of the Chinese source pointing to `roadmap.en.md` with the repository-standard mirror notice.
- For project-wide priorities, follow `docs/c2rust-migration-agent/future-vision-and-mvp.md`; local plans, OpenSpec tasks, and validation checklists are scoped artifacts only.
