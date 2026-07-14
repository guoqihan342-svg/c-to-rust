from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .artifacts import content_sha256


_ISSUER = object()


class _HostContextRefreshPermit:
    __slots__ = ("_authority", "_binding")

    def __init__(self, authority: object, binding: Mapping[str, Any]) -> None:
        if authority is not _ISSUER:
            raise TypeError("context refresh permits are host-issued")
        self._authority = authority
        self._binding = dict(binding)


def _issue_host_context_refresh_permit(
    binding: Mapping[str, Any],
) -> _HostContextRefreshPermit:
    payload = dict(binding)
    return _HostContextRefreshPermit(_ISSUER, {
        **payload, "permit_sha256": content_sha256(payload),
    })


def _host_context_refresh_binding(
    permit: _HostContextRefreshPermit,
) -> dict[str, Any]:
    if (
        type(permit) is not _HostContextRefreshPermit
        or permit._authority is not _ISSUER
    ):
        raise TypeError("context refresh permit is not host-issued")
    binding = dict(permit._binding)
    payload = {
        key: value for key, value in binding.items() if key != "permit_sha256"
    }
    if content_sha256(payload) != binding.get("permit_sha256"):
        raise ValueError("context refresh permit binding drifted")
    return binding


__all__: list[str] = []
