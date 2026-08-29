"""Runtime entrypoint for the DBFox Visualization System DLC."""

from dbfox_dlc_api import BackendExtensionHost

from .contributions import register as register_contributions


def register(host: BackendExtensionHost) -> None:
    register_contributions(host)

