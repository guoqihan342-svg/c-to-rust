import json
import hashlib
import importlib.util
import jsonschema
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
AUTO_MIGRATE = REPO_ROOT / "validation" / "tools" / "auto_migrate.py"
VALIDATOR = REPO_ROOT / "validation" / "tools" / "validate_auto_translation_evidence.py"


def load_auto_migrate_module():
    spec = importlib.util.spec_from_file_location("auto_migrate_under_test", AUTO_MIGRATE)
    if spec is None or spec.loader is None:
        raise AssertionError("could not load auto_migrate module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

from pathlib import Path as _C2RPartPath

_C2R_PARTS_DIR = _C2RPartPath(__file__).with_name("_test_auto_migrate_parts")
for _C2R_PART_NAME in (
    "class_part_00.py",
    "class_part_01.py",
    "class_part_02.py",
    "class_part_03.py",
    "class_part_04.py",
    "class_part_05.py",
    "class_part_06.py",
    "class_part_07.py",
    "class_part_08.py",
    "class_part_09.py",
    "class_part_10.py",
    "class_part_11.py",
):
    _C2R_PART_PATH = _C2R_PARTS_DIR / _C2R_PART_NAME
    exec(
        compile(
            _C2R_PART_PATH.read_text(encoding="utf-8"),
            str(_C2R_PART_PATH),
            "exec",
        ),
        globals(),
    )

class AutoMigrateTests(
    _AutoMigrateTestsPart00,
    _AutoMigrateTestsPart01,
    _AutoMigrateTestsPart02,
    _AutoMigrateTestsPart03,
    _AutoMigrateTestsPart04,
    _AutoMigrateTestsPart05,
    _AutoMigrateTestsPart06,
    _AutoMigrateTestsPart07,
    _AutoMigrateTestsPart08,
    _AutoMigrateTestsPart09,
    _AutoMigrateTestsPart10,
    _AutoMigrateTestsPart11,
    unittest.TestCase,
):
    pass

for _C2R_PART_TEMP_NAME in (
    "_C2RPartPath",
    "_C2R_PARTS_DIR",
    "_C2R_PART_NAME",
    "_C2R_PART_PATH",
):
    globals().pop(_C2R_PART_TEMP_NAME, None)
del _C2R_PART_TEMP_NAME


if __name__ == "__main__":
    unittest.main()
