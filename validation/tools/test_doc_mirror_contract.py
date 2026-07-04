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
    Path("openspec/project.md"),
    Path("openspec/specs"),
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
    Path("openspec/changes"),
    Path("validation/evidence"),
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


class DocMirrorContractTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
