import json
import hashlib
import importlib.util
import jsonschema
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
AUTO_MIGRATE = REPO_ROOT / "validation" / "tools" / "auto_migrate.py"
VALIDATOR = REPO_ROOT / "validation" / "tools" / "validate_auto_translation_evidence.py"
_VALIDATOR_MODULE = None


def load_validator_module():
    global _VALIDATOR_MODULE
    if _VALIDATOR_MODULE is not None:
        return _VALIDATOR_MODULE
    spec = importlib.util.spec_from_file_location("validate_auto_translation_evidence_under_test", VALIDATOR)
    if spec is None or spec.loader is None:
        raise AssertionError("could not load validate_auto_translation_evidence module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _VALIDATOR_MODULE = module
    return module

from pathlib import Path as _C2RPartPath

_C2R_PARTS_DIR = _C2RPartPath(__file__).with_name("_test_validate_auto_translation_evidence_parts")
for _C2R_PART_NAME in (
    "class_part_00.py",
    "class_part_01.py",
    "class_part_02.py",
    "class_part_03.py",
    "class_part_04.py",
    "class_part_05.py",
    "class_part_06.py",
    "class_part_07.py",
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

class ValidateAutoTranslationEvidenceTests(
    _ValidateAutoTranslationEvidenceTestsPart00,
    _ValidateAutoTranslationEvidenceTestsPart01,
    _ValidateAutoTranslationEvidenceTestsPart02,
    _ValidateAutoTranslationEvidenceTestsPart03,
    _ValidateAutoTranslationEvidenceTestsPart04,
    _ValidateAutoTranslationEvidenceTestsPart05,
    _ValidateAutoTranslationEvidenceTestsPart06,
    _ValidateAutoTranslationEvidenceTestsPart07,
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
