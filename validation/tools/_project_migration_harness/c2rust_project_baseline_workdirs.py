from __future__ import annotations

from pathlib import Path
from typing import Any


def translated_source_working_directories(
    repository: Path, entries: tuple[dict[str, Any], ...],
) -> dict[str, str]:
    records: list[tuple[Path, str, str]] = []
    source_paths: dict[str, str] = {}
    exact_working_directories: dict[str, str] = {}
    for entry in entries:
        source = Path(entry["file"]).resolve(strict=True)
        working_directory = Path(entry["directory"]).resolve(strict=True)
        source_relative = source.relative_to(repository)
        working_relative = working_directory.relative_to(repository).as_posix()
        translated = _c2rust_translated_path(source_relative)
        source_identity = source_relative.as_posix()
        previous_source = source_paths.setdefault(translated, source_identity)
        if previous_source != source_identity:
            raise ValueError("c2rust_translated_source_path_ambiguous")
        previous_working_directory = exact_working_directories.setdefault(
            translated, working_relative,
        )
        if previous_working_directory != working_relative:
            raise ValueError("c2rust_source_working_directory_ambiguous")
        records.append((source_relative, source_identity, working_relative))

    result: dict[str, str] = {}
    candidate_sources: dict[str, str] = {}
    ambiguous: set[str] = set()
    for source_relative, source_identity, working_relative in records:
        for translated in _c2rust_translated_candidates(source_relative):
            previous_source = candidate_sources.setdefault(
                translated, source_identity,
            )
            if previous_source != source_identity:
                ambiguous.add(translated)
                continue
            result.setdefault(translated, working_relative)
    for translated in ambiguous:
        result.pop(translated, None)
    return result


def repository_working_directory(repository: Path, value: object) -> Path:
    if (
        not isinstance(value, str) or not value or "\\" in value
        or Path(value).is_absolute() or ".." in Path(value).parts
    ):
        raise ValueError("c2rust_source_working_directory_invalid")
    try:
        directory = repository.joinpath(*Path(value).parts).resolve(strict=True)
        directory.relative_to(repository)
    except (OSError, ValueError) as error:
        raise ValueError(
            "c2rust_source_working_directory_escapes_repository"
        ) from error
    if not directory.is_dir():
        raise ValueError("c2rust_source_working_directory_invalid")
    return directory


def portable_package_workdir(root: Path, package: Path) -> str:
    relative = package.relative_to(root).as_posix()
    return "generated-project" if relative == "." else f"generated-project/{relative}"


def portable_repository_workdir(root: Path, directory: Path) -> str:
    relative = directory.relative_to(root).as_posix()
    return "repository-root" if relative == "." else f"repository/{relative}"


def _c2rust_translated_path(source_relative: Path) -> str:
    directories = [
        _c2rust_module_component(part) for part in source_relative.parts[:-1]
    ]
    stem = _c2rust_module_component(source_relative.stem)
    return Path("src", *directories, f"{stem}.rs").as_posix()


def _c2rust_translated_candidates(source_relative: Path) -> tuple[str, ...]:
    return tuple(
        _c2rust_translated_path(Path(*source_relative.parts[index:]))
        for index in range(len(source_relative.parts))
    )


def _c2rust_module_component(value: str) -> str:
    return "".join(
        character if character.isalnum() else "_" for character in value
    )


__all__ = [
    "portable_package_workdir", "portable_repository_workdir",
    "repository_working_directory", "translated_source_working_directories",
]
