from __future__ import annotations

from dataclasses import dataclass
import re
from collections.abc import Mapping
from typing import Any

from .artifacts import content_sha256
from .sandbox_native_linker import NativeLinkerToolchain


_BASENAME = re.compile(r"[A-Za-z0-9_.+-]+\Z", re.ASCII)
_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_TARGET = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9_.+]{0,62}"
    r"(?:-[A-Za-z0-9][A-Za-z0-9_.+]{0,62}){2,4}\Z",
    re.ASCII,
)


@dataclass(frozen=True, slots=True)
class NativeLinkerContract:
    driver_basename: str
    driver_sha256: str
    linker_basename: str
    linker_sha256: str
    target_triple: str
    binding_sha256: str

    def __post_init__(self) -> None:
        if any(
            type(value) is not str or _BASENAME.fullmatch(value) is None
            for value in (self.driver_basename, self.linker_basename)
        ):
            raise ValueError("native linker contract basename is invalid")
        if any(
            type(value) is not str or _SHA256.fullmatch(value) is None
            for value in (
                self.driver_sha256, self.linker_sha256, self.binding_sha256,
            )
        ):
            raise ValueError("native linker contract SHA-256 is invalid")
        if type(self.target_triple) is not str or _TARGET.fullmatch(
            self.target_triple,
        ) is None:
            raise ValueError("native linker contract target triple is invalid")
        if content_sha256(self.binding_payload()) != self.binding_sha256:
            raise ValueError("native linker contract binding hash drifted")

    def binding_payload(self) -> dict[str, object]:
        return {
            "driver": {
                "basename": self.driver_basename,
                "family": "gnu-compiler",
                "sha256": self.driver_sha256,
            },
            "linker": {
                "basename": self.linker_basename,
                "family": "linker",
                "sha256": self.linker_sha256,
            },
            "target_triple": self.target_triple,
        }

    def payload(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            **self.binding_payload(),
            "binding_sha256": self.binding_sha256,
        }


def native_linker_contract(
    binding: NativeLinkerToolchain,
) -> NativeLinkerContract:
    if not isinstance(binding, NativeLinkerToolchain):
        raise ValueError("native linker toolchain binding is invalid")
    payload = binding.payload()
    driver, linker = payload["driver"], payload["linker"]
    if not isinstance(driver, Mapping) or not isinstance(linker, Mapping):
        raise ValueError("native linker toolchain payload is invalid")
    return NativeLinkerContract(
        driver_basename=str(driver.get("basename")),
        driver_sha256=str(driver.get("sha256")),
        linker_basename=str(linker.get("basename")),
        linker_sha256=str(linker.get("sha256")),
        target_triple=str(payload.get("target_triple")),
        binding_sha256=binding.binding_sha256,
    )


def native_linker_contract_from_payload(value: Any) -> NativeLinkerContract:
    if not isinstance(value, Mapping) or set(value) != {
        "schema_version", "driver", "linker", "target_triple", "binding_sha256",
    } or value.get("schema_version") != 1:
        raise ValueError("native linker contract payload is invalid")
    driver, linker = value.get("driver"), value.get("linker")
    if (
        not isinstance(driver, Mapping) or set(driver) != {"basename", "family", "sha256"}
        or not isinstance(linker, Mapping) or set(linker) != {"basename", "family", "sha256"}
        or driver.get("family") != "gnu-compiler"
        or linker.get("family") != "linker"
    ):
        raise ValueError("native linker contract payload is invalid")
    contract = NativeLinkerContract(
        driver_basename=driver.get("basename"),
        driver_sha256=driver.get("sha256"),
        linker_basename=linker.get("basename"),
        linker_sha256=linker.get("sha256"),
        target_triple=value.get("target_triple"),
        binding_sha256=value.get("binding_sha256"),
    )
    if contract.payload() != dict(value):
        raise ValueError("native linker contract payload is not canonical")
    return contract


__all__ = [
    "NativeLinkerContract", "native_linker_contract",
    "native_linker_contract_from_payload",
]
