from __future__ import annotations

from dbfox_dlc_api import BackendExtensionHost

from .contributions import register as register_contributions


def register(host: BackendExtensionHost) -> None:
    register_contributions(host)
