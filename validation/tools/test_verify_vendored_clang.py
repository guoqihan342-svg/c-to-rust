import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
VERIFY_RUNNER = REPO_ROOT / "validation" / "tools" / "verify_vendored_clang.py"


def load_verify_module():
    spec = importlib.util.spec_from_file_location("verify_vendored_clang_under_test", VERIFY_RUNNER)
    if spec is None or spec.loader is None:
        raise AssertionError("could not load vendored clang verifier")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_minimal_profile(repo_root: Path) -> None:
    profile_dir = repo_root / "config" / "competition-env"
    profile_dir.mkdir(parents=True)
    (profile_dir / "environment.json").write_text(
        json.dumps({"profile_id": "huawei-competition-ubuntu-24.04"}, sort_keys=True),
        encoding="utf-8",
    )


class FakeClangRunner:
    def __init__(self) -> None:
        self.commands: list[list[str]] = []

    def __call__(self, command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        self.commands.append(command)
        command_text = " ".join(command)
        if "--version" in command:
            return subprocess.CompletedProcess(command, 0, "clang version 18.1.8\n", "")
        if "-print-resource-dir" in command:
            return subprocess.CompletedProcess(command, 0, "/repo/tools/llvm/lib/clang/18\n", "")
        if "-E" in command and "-v" in command:
            stderr = "\n".join(
                [
                    "clang version 18.1.8",
                    "#include <...> search starts here:",
                    " /repo/tools/llvm/lib/clang/18/include",
                    " /usr/include",
                    "End of search list.",
                ]
            )
            return subprocess.CompletedProcess(command, 0, "", stderr)
        if "-ast-dump=json" in command_text:
            return subprocess.CompletedProcess(command, 0, '{"kind":"TranslationUnitDecl"}\n', "")
        return subprocess.CompletedProcess(command, 1, "", f"unexpected command: {command_text}")


class VerifyVendoredClangTests(unittest.TestCase):
    def test_missing_clang_writes_missing_summary_without_failing_by_default(self) -> None:
        module = load_verify_module()
        with tempfile.TemporaryDirectory(prefix="vendored-clang-test-") as tmp:
            repo_root = Path(tmp)
            write_minimal_profile(repo_root)
            out_path = repo_root / "target" / "summary" / "vendored-clang-verification.json"

            result = module.verify_vendored_clang(
                repo_root=repo_root,
                out=out_path,
                proof_class="local-simulation",
                environment={},
                command_runner=FakeClangRunner(),
            )

            self.assertEqual(result.exit_code, 0)
            summary = json.loads(out_path.read_text(encoding="utf-8"))
            self.assertEqual(summary["status"], "missing")
            self.assertEqual(summary["reason"], "missing_clang_path")
            self.assertEqual(summary["clang"]["source"], "missing")
            self.assertFalse(summary["clang_lane_verified"])
            self.assertEqual(summary["checks"], {})

    def test_require_clang_turns_missing_clang_into_failure(self) -> None:
        module = load_verify_module()
        with tempfile.TemporaryDirectory(prefix="vendored-clang-test-") as tmp:
            repo_root = Path(tmp)
            write_minimal_profile(repo_root)
            out_path = repo_root / "target" / "summary" / "vendored-clang-verification.json"

            result = module.verify_vendored_clang(
                repo_root=repo_root,
                out=out_path,
                proof_class="ci-approximation",
                require_clang=True,
                environment={},
                command_runner=FakeClangRunner(),
            )

            summary = json.loads(out_path.read_text(encoding="utf-8"))
            self.assertEqual(result.exit_code, 1)
            self.assertEqual(summary["status"], "missing")
            self.assertEqual(summary["final_gate"]["status"], "failed")
            self.assertIn("missing_clang_path", summary["final_gate"]["reasons"])

    def test_competition_exact_requires_clang_even_without_require_flag(self) -> None:
        module = load_verify_module()
        with tempfile.TemporaryDirectory(prefix="vendored-clang-test-") as tmp:
            repo_root = Path(tmp)
            write_minimal_profile(repo_root)
            out_path = repo_root / "target" / "summary" / "vendored-clang-verification.json"

            result = module.verify_vendored_clang(
                repo_root=repo_root,
                out=out_path,
                proof_class="competition-exact",
                environment={},
                command_runner=FakeClangRunner(),
            )

            summary = json.loads(out_path.read_text(encoding="utf-8"))
            self.assertEqual(result.exit_code, 1)
            self.assertTrue(summary["clang_required"])
            self.assertEqual(summary["final_gate"]["status"], "failed")
            self.assertIn("missing_clang_path", summary["final_gate"]["reasons"])

    def test_vendored_clang_records_resource_dir_include_paths_and_minimum_tu_ast(self) -> None:
        module = load_verify_module()
        with tempfile.TemporaryDirectory(prefix="vendored-clang-test-") as tmp:
            repo_root = Path(tmp)
            write_minimal_profile(repo_root)
            clang = repo_root / "tools" / "llvm" / "bin" / "clang-18"
            clang.parent.mkdir(parents=True)
            clang.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            clang.chmod(0o755)
            out_path = repo_root / "target" / "summary" / "vendored-clang-verification.json"
            fake_runner = FakeClangRunner()

            result = module.verify_vendored_clang(
                repo_root=repo_root,
                out=out_path,
                proof_class="wsl-local-simulation",
                environment={},
                command_runner=fake_runner,
            )

            self.assertEqual(result.exit_code, 0)
            summary = json.loads(out_path.read_text(encoding="utf-8"))
            self.assertEqual(summary["status"], "passed")
            self.assertEqual(summary["clang"]["source"], "vendored:tools/llvm/bin/clang-18")
            self.assertEqual(summary["clang"]["path"], "tools/llvm/bin/clang-18")
            self.assertEqual(summary["clang"]["version"], "clang version 18.1.8")
            self.assertEqual(summary["checks"]["binary_exists"]["status"], "passed")
            self.assertEqual(summary["checks"]["resource_dir"]["resource_dir"], "/repo/tools/llvm/lib/clang/18")
            self.assertEqual(
                summary["checks"]["include_search_paths"]["paths"],
                ["/repo/tools/llvm/lib/clang/18/include", "/usr/include"],
            )
            self.assertEqual(summary["checks"]["minimum_tu_ast_dump"]["status"], "passed")
            self.assertTrue(summary["checks"]["minimum_tu_ast_dump"]["contains_translation_unit"])
            self.assertTrue(summary["clang_lane_verified"])
            self.assertTrue(all(not Path(log["log_path"]).is_absolute() for log in summary["command_logs"]))
            command_texts = [" ".join(command) for command in fake_runner.commands]
            self.assertTrue(any("-print-resource-dir" in text for text in command_texts))
            self.assertTrue(any("-E -v" in text for text in command_texts))
            self.assertTrue(any("-fsyntax-only -Xclang -ast-dump=json" in text for text in command_texts))

    def test_clang_path_command_name_is_resolved_from_path(self) -> None:
        module = load_verify_module()
        with tempfile.TemporaryDirectory(prefix="vendored-clang-test-") as tmp:
            repo_root = Path(tmp)
            write_minimal_profile(repo_root)
            bin_dir = repo_root / "fake-bin"
            bin_dir.mkdir()
            clang = bin_dir / ("clang.exe" if sys.platform == "win32" else "clang")
            clang.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            clang.chmod(0o755)
            out_path = repo_root / "target" / "summary" / "vendored-clang-verification.json"

            result = module.verify_vendored_clang(
                repo_root=repo_root,
                out=out_path,
                proof_class="local-simulation",
                environment={"CLANG_PATH": clang.name, "PATH": str(bin_dir)},
                command_runner=FakeClangRunner(),
            )

            summary = json.loads(out_path.read_text(encoding="utf-8"))
            self.assertEqual(result.exit_code, 0)
            self.assertEqual(summary["status"], "passed")
            self.assertEqual(summary["clang"]["source"], "CLANG_PATH")
            self.assertTrue(summary["clang"]["path"].endswith(clang.name))


if __name__ == "__main__":
    unittest.main()
