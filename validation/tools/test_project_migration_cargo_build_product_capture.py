from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest

from validation.tools._project_migration_harness.cargo_build_product_capture import (
    capture_cargo_build_products,
)
from validation.tools._project_migration_harness.anchored_artifact_io import (
    open_directory_anchor,
)


class CargoBuildProductCaptureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="cargo-products-")
        self.addCleanup(self.temporary.cleanup)
        self.execution = Path(self.temporary.name) / "execution"
        (self.execution / "target" / "debug").mkdir(parents=True)

    def test_binary_and_static_library_are_captured_from_target_only(self) -> None:
        binary = self.execution / "target" / "debug" / "app"
        archive = self.execution / "target" / "debug" / "libcore.a"
        binary.write_bytes(b"binary")
        archive.write_bytes(b"archive")
        build = _build(
            _artifact(
                name="app", kind=["bin"], crate_types=["bin"],
                filenames=["/runtime/target/debug/app"],
                executable="/runtime/target/debug/app",
            ),
            _artifact(
                name="core", kind=["staticlib"], crate_types=["staticlib"],
                filenames=["/runtime/target/debug/libcore.a"],
            ),
        )

        products = capture_cargo_build_products(build, self.execution)

        self.assertEqual(["bin", "staticlib"], [
            item["product_kind"] for item in products
        ])
        self.assertEqual({b"binary", b"archive"}, {
            item["data"] for item in products
        })

    def test_guest_product_outside_isolated_target_is_rejected(self) -> None:
        build = _build(_artifact(
            name="app", kind=["bin"], crate_types=["bin"],
            filenames=["/tmp/app"], executable="/tmp/app",
        ))

        with self.assertRaisesRegex(ValueError, "outside_target"):
            capture_cargo_build_products(build, self.execution)

    @unittest.skipIf(os.name == "nt", "symbolic-link privilege varies on Windows")
    def test_symbolic_link_product_is_rejected(self) -> None:
        outside = Path(self.temporary.name) / "outside"
        outside.write_bytes(b"outside")
        product = self.execution / "target" / "debug" / "app"
        product.symlink_to(outside)
        build = _build(_artifact(
            name="app", kind=["bin"], crate_types=["bin"],
            filenames=["/runtime/target/debug/app"],
            executable="/runtime/target/debug/app",
        ))

        with self.assertRaisesRegex(ValueError, "link_rejected"):
            capture_cargo_build_products(build, self.execution)

    def test_declared_library_without_unique_file_is_rejected(self) -> None:
        build = _build(_artifact(
            name="core", kind=["staticlib"], crate_types=["staticlib"],
            filenames=["/runtime/target/debug/core.rmeta"],
        ))

        with self.assertRaisesRegex(ValueError, "ambiguous"):
            capture_cargo_build_products(build, self.execution)

    @unittest.skipIf(os.name == "nt", "open directory replacement differs on Windows")
    def test_target_directory_replacement_after_anchor_is_rejected(self) -> None:
        target = self.execution / "target"
        anchor = open_directory_anchor(target)
        self.addCleanup(anchor.close)
        target.rename(self.execution / "detached-target")
        (target / "debug").mkdir(parents=True)
        (target / "debug" / "app").write_bytes(b"forged")
        build = _build(_artifact(
            name="app", kind=["bin"], crate_types=["bin"],
            filenames=["/runtime/target/debug/app"],
            executable="/runtime/target/debug/app",
        ))

        with self.assertRaisesRegex(ValueError, "identity_drift"):
            capture_cargo_build_products(
                build, self.execution, target_anchor=anchor,
            )


def _build(*artifacts: dict) -> dict:
    raw = b"".join(
        _json(item) + b"\n" for item in (
            *artifacts, {"reason": "build-finished", "success": True},
        )
    )
    return {"status": "passed", "_captured_stdout": raw}


def _artifact(
    *, name: str, kind: list[str], crate_types: list[str],
    filenames: list[str], executable: str | None = None,
) -> dict:
    return {
        "reason": "compiler-artifact",
        "package_id": f"path+file:///workspace/pkg#pkg@0.0.0",
        "manifest_path": "/workspace/pkg/Cargo.toml",
        "target": {
            "kind": kind, "crate_types": crate_types, "name": name,
            "src_path": f"/workspace/pkg/src/{name}.rs", "edition": "2021",
            "doc": True, "doctest": True, "test": True,
        },
        "profile": {
            "opt_level": "0", "debuginfo": 2,
            "debug_assertions": True, "overflow_checks": True,
            "test": False,
        },
        "features": [], "filenames": filenames,
        "executable": executable, "fresh": False,
    }


def _json(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")


if __name__ == "__main__":
    unittest.main()
