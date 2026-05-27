"""Connector lifecycle status states."""

from enum import Enum


class ConnectorStatus(str, Enum):
    CONNECTED    = "connected"
    DISCONNECTED = "disconnected"
    DEGRADED     = "degraded"
    SYNCING      = "syncing"
    ERROR        = "error"
    VALIDATING   = "validating"
