import unittest
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]

DOC_ROOTS = (
    Path("README.md"),
    Path("config"),
    Path("docs"),
    Path("flashDB_rust/README.md"),
    Path("flashDB_rust/oracle/README.md"),
    Path("validation"),
)

EXCLUDED_PARTS = {
    ".git",
    ".pytest_cache",
    ".venv",
    "archive",
    "node_modules",
    "target",
    "venv",
}

EXCLUDED_RELATIVE_PREFIXES = (
    Path("docs/superpowers"),
    Path("validation/evidence"),
)

CANONICAL_BACKLOG_DOCS = {
    Path("docs/c2rust-migration-agent/future-vision-and-mvp.md"),
    Path("docs/c2rust-migration-agent/future-vision-and-mvp.en.md"),
}

MOJIBAKE_SENSITIVE_DOCS = (
    Path("docs/c2rust-migration-agent/future-vision-and-mvp.md"),
    Path("docs/c2rust-migration-agent/COVERAGE.md"),
)

BACKLOG_ENTRYPOINT_TERMS = (
    "Next Steps",
    "下一步",
    "P0",
    "P1",
    "P2",
    "roadmap",
    "路线图",
    "backlog",
    "全局待办",
    "待办",
    "checklist",
    "Checklist",
)

BACKLOG_SCOPE_BOUNDARY_TERMS = (
    "future-vision-and-mvp.md",
    "not the canonical backlog",
    "非 canonical backlog",
    "scoped artifacts only",
    "局部",
    "历史",
    "不作为当前全局待办",
    "全局待办唯一来源",
    "not become the active backlog",
    "not a second independent backlog",
    "only global backlog source",
    "local plans",
    "historical implementation plans",
    "validation checklists",
)

def _is_excluded(path: Path) -> bool:
    rel = path.relative_to(REPO_ROOT)
    if any(part in EXCLUDED_PARTS for part in rel.parts):
        return True
    return any(
        rel == prefix or rel.is_relative_to(prefix)
        for prefix in EXCLUDED_RELATIVE_PREFIXES
    )


def _iter_chinese_docs():
    docs = []
    tracked = subprocess.run(
        ["git", "ls-files", "-z", "--", *(root.as_posix() for root in DOC_ROOTS)],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        encoding="utf-8",
    ).stdout
    for item in tracked.split("\0"):
        if not item or not item.endswith(".md"):
            continue
        candidate = REPO_ROOT / item
        if candidate.name.endswith(".en.md") or _is_excluded(candidate):
            continue
        docs.append(candidate)
    return sorted(set(docs))


def _iter_maintained_docs():
    tracked = subprocess.run(
        ["git", "ls-files", "-z", "--", *(root.as_posix() for root in DOC_ROOTS)],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        encoding="utf-8",
    ).stdout
    docs = []
    for item in tracked.split("\0"):
        if not item or not item.endswith(".md"):
            continue
        candidate = REPO_ROOT / item
        if _is_excluded(candidate):
            continue
        docs.append(candidate)
    return sorted(set(docs))


def _has_backlog_entrypoint_wording(text: str) -> bool:
    for line in text.splitlines():
        stripped = line.strip().lstrip("#").strip()
        if any(stripped.startswith(term) for term in BACKLOG_ENTRYPOINT_TERMS):
            return True
    return False


class DocMirrorContractTest(unittest.TestCase):
    def test_canonical_chinese_docs_reject_mojibake_markers(self):
        offenders = []

        for rel in MOJIBAKE_SENSITIVE_DOCS:
            text = (REPO_ROOT / rel).read_text(encoding="utf-8")
            markers = []
            if "????" in text:
                markers.append("four consecutive ASCII question marks")
            if "\ufffd" in text:
                markers.append("Unicode replacement character")
            if markers:
                offenders.append(f"{rel}: {', '.join(markers)}")

        if offenders:
            self.fail("Canonical Chinese docs contain mojibake markers:\n" + "\n".join(offenders))

    def test_chinese_docs_have_english_mirror_and_first_line_pointer(self):
        missing_mirrors = []
        missing_headers = []

        for doc in _iter_chinese_docs():
            mirror = doc.with_name(f"{doc.stem}.en.md")
            expected_header = f"英文镜像见 `{mirror.name}`。"
            if not mirror.exists():
                missing_mirrors.append(str(doc.relative_to(REPO_ROOT)))

            first_line = doc.read_text(encoding="utf-8").splitlines()[0:1]
            if first_line != [expected_header]:
                missing_headers.append(
                    f"{doc.relative_to(REPO_ROOT)} expected first line {expected_header!r}"
                )

        if missing_mirrors or missing_headers:
            details = []
            if missing_mirrors:
                details.append(
                    "Missing English mirrors:\n" + "\n".join(missing_mirrors)
                )
            if missing_headers:
                details.append(
                    "Missing first-line mirror headers:\n" + "\n".join(missing_headers)
                )
            self.fail("\n\n".join(details))

    def test_non_canonical_docs_scope_backlog_like_entrypoints(self):
        offenders = []

        for doc in _iter_maintained_docs():
            rel = doc.relative_to(REPO_ROOT)
            if rel in CANONICAL_BACKLOG_DOCS:
                continue
            text = doc.read_text(encoding="utf-8")
            if not _has_backlog_entrypoint_wording(text):
                continue
            if any(term in text for term in BACKLOG_SCOPE_BOUNDARY_TERMS):
                continue
            offenders.append(str(rel))

        if offenders:
            self.fail(
                "Docs with backlog-like headings must declare local, historical, "
                "or non-canonical scope and point to future-vision-and-mvp.md:\n"
                + "\n".join(offenders)
            )


if __name__ == "__main__":
    unittest.main()
