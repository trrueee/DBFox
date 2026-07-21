"""Secure, typed boundaries for database connectivity."""

from engine.connectivity.factory import ConnectionFactory
from engine.connectivity.profile import ConnectionProfile, ConnectionPurpose
from engine.connectivity.resources import ConnectionEndpoint, ConnectionResources

__all__ = [
    "ConnectionEndpoint",
    "ConnectionFactory",
    "ConnectionProfile",
    "ConnectionPurpose",
    "ConnectionResources",
]
