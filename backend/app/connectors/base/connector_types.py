"""Connector type taxonomy."""

from enum import Enum


class ConnectorType(str, Enum):
    AI_PROVIDER       = "ai_provider"
    CLOUD_PROVIDER    = "cloud_provider"
    OBSERVABILITY     = "observability"
    GPU_INFRASTRUCTURE = "gpu_infrastructure"
    CONTAINER_PLATFORM = "container_platform"
    DATABASE          = "database"
    CUSTOM            = "custom"
