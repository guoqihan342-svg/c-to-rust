from __future__ import annotations

from pathlib import Path

from validation.tools._project_migration_harness.c2rust_project_baseline_process import (
    ProcessOutcome,
)


class FakeRunner:
    def __init__(
        self, sources: dict[str, str] | None = None, *,
        transpile_returncode: int = 0, transpile_stderr: bytes = b"",
        failing_bin: str | None = None,
    ) -> None:
        self.sources = sources or {}
        self.transpile_returncode = transpile_returncode
        self.transpile_stderr = transpile_stderr
        self.failing_bin = failing_bin
        self.calls: list[list[str]] = []
        self.working_directories: list[Path] = []
        self.environments: list[dict[str, str]] = []

    def __call__(
        self, argv: list[str], cwd: Path, environment: dict[str, str],
        timeout_seconds: int,
    ) -> ProcessOutcome:
        command = list(argv)
        self.calls.append(command)
        self.working_directories.append(cwd)
        self.environments.append(dict(environment))
        self._assert_contract(cwd, environment, timeout_seconds)
        if "--emit-build-files" in command:
            assert Path(command[1]).name == "compile_commands.json"
            if self.transpile_returncode:
                return ProcessOutcome(
                    self.transpile_returncode, b"transpile-out", b"transpile-error",
                )
            self._emit(Path(command[command.index("--output-dir") + 1]))
            return ProcessOutcome(0, b"generated", self.transpile_stderr)
        if "run" in command and "--bin" in command:
            name = command[command.index("--bin") + 1]
            return ProcessOutcome(
                9 if name == self.failing_bin else 0, b"run", b"",
            )
        return ProcessOutcome(0, b"check", b"")

    def _emit(self, root: Path) -> None:
        (root / "src").mkdir(parents=True)
        (root / "Cargo.toml").write_text(
            "[package]\nname = \"generated-project\"\n"
            "version = \"0.0.0\"\nedition = \"2021\"\n\n"
            "[lib]\npath = \"src/lib.rs\"\n",
            encoding="utf-8",
        )
        modules = [
            Path(relative).stem for relative in sorted(self.sources)
            if Path(relative).parent.as_posix() == "src"
        ]
        (root / "src/lib.rs").write_text(
            "".join(f"pub mod {name};\n" for name in modules)
            + "pub fn library_probe() -> i32 { 1 }\n",
            encoding="utf-8",
        )
        for relative, source in self.sources.items():
            target = root.joinpath(*Path(relative).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(source, encoding="utf-8")

    @staticmethod
    def _assert_contract(
        cwd: Path, environment: dict[str, str], timeout_seconds: int,
    ) -> None:
        assert cwd.is_dir()
        assert timeout_seconds > 0
        assert environment["CARGO_NET_OFFLINE"] == "true"
        assert Path(environment["RUSTC"]).name == "rustc"


__all__ = ["FakeRunner"]
