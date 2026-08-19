"""DBFox Runtime DLC Platform — Package Foundation (R1).

Provides package format validation, cryptographic envelope verification,
content-addressed package storage, and installed DLC registry.

Zero code execution occurs during package verification and installation.
"""

from engine.dlc.errors import DlcError, DlcErrorCode
from engine.dlc.integrity import DlcIntegrity
from engine.dlc.manifest import DlcManifest
from engine.dlc.registry import InstalledDlcRecord, InstalledDlcRegistry
from engine.dlc.service import DlcInstallationResult, DlcPackageService
from engine.dlc.store import DlcPackageStore
from engine.dlc.trust import DlcTrustStore, DlcTrustVerifier
from engine.dlc.verifier import DlcPackageVerifier

__all__ = [
    "DlcError",
    "DlcErrorCode",
    "DlcInstallationResult",
    "DlcIntegrity",
    "DlcManifest",
    "DlcPackageService",
    "DlcPackageStore",
    "DlcPackageVerifier",
    "DlcTrustStore",
    "DlcTrustVerifier",
    "InstalledDlcRecord",
    "InstalledDlcRegistry",
]
