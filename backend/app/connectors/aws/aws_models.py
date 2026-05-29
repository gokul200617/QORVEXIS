"""AWS connector data models — Phase 8D.

Defines the structured types used across the AWS connector:
  * AWSCredentials      — in-memory credential holder (never persisted plaintext)
  * AWSAccountMetadata  — discovered account identity and region
  * AWSEC2Instance      — per-instance snapshot
  * AWSSyncState        — synchronization lifecycle tracking
  * AWSRecommendation   — optimization engine output

These types are internal to the connector module and are translated to
frontend-safe payloads before crossing the API boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


# ── Sync status literals ──────────────────────────────────────────────────────

class SyncStatus:
    IDLE      = "idle"
    SYNCING   = "syncing"
    COMPLETED = "completed"
    DEGRADED  = "degraded"
    FAILED    = "failed"


# ── Credential container (in-memory only) ────────────────────────────────────

@dataclass
class AWSCredentials:
    """Holds raw AWS credentials in-memory only.

    NEVER serialize or log these fields.
    Only the masked_access_key may leave this object.
    """
    access_key: str
    secret_key: str
    region:     str

    @property
    def masked_access_key(self) -> str:
        """Returns a safely masked version of the access key."""
        if len(self.access_key) > 8:
            return f"AKIA...{self.access_key[-4:]}"
        return "AKIA...xxxx"


# ── Account metadata ─────────────────────────────────────────────────────────

@dataclass
class AWSAccountMetadata:
    """Discovered AWS account identity — safe to expose via API."""
    account_id:          str = ""
    account_alias:       Optional[str] = None
    region:              str = ""
    connector_id:        str = ""
    connector_name:      str = ""
    connector_status:    str = "disconnected"
    last_sync_timestamp: Optional[datetime] = None

    def to_dict(self) -> dict:
        return {
            "account_id":          self.account_id,
            "account_alias":       self.account_alias,
            "region":              self.region,
            "connector_id":        self.connector_id,
            "connector_name":      self.connector_name,
            "connector_status":    self.connector_status,
            "last_sync_timestamp": (
                self.last_sync_timestamp.isoformat()
                if self.last_sync_timestamp else None
            ),
        }


# ── EC2 instance snapshot ────────────────────────────────────────────────────

@dataclass
class AWSEC2Instance:
    """Lightweight EC2 instance snapshot — only fields relevant to intelligence."""
    instance_id:       str
    instance_type:     str
    state:             str          # running | stopped | terminated | pending | …
    launch_time:       Optional[datetime] = None
    region:            str = ""
    availability_zone: str = ""
    cpu_utilization:   float = 0.0   # % average from CloudWatch
    network_in_bytes:  float = 0.0
    network_out_bytes: float = 0.0

    @property
    def is_running(self) -> bool:
        return self.state == "running"

    @property
    def is_stopped(self) -> bool:
        return self.state == "stopped"

    def to_dict(self) -> dict:
        return {
            "instance_id":       self.instance_id,
            "instance_type":     self.instance_type,
            "state":             self.state,
            "launch_time":       self.launch_time.isoformat() if self.launch_time else None,
            "region":            self.region,
            "availability_zone": self.availability_zone,
            "cpu_utilization":   round(self.cpu_utilization, 2),
            "network_in_bytes":  self.network_in_bytes,
            "network_out_bytes": self.network_out_bytes,
        }


# ── Sync state tracker ───────────────────────────────────────────────────────

@dataclass
class AWSSyncState:
    """Tracks the full lifecycle of a connector synchronization cycle."""
    sync_status:           str = SyncStatus.IDLE
    last_sync:             Optional[datetime] = None
    sync_duration_ms:      Optional[int] = None
    resources_discovered:  int = 0
    sync_errors:           list[str] = field(default_factory=list)
    successful_sync_count: int = 0
    failed_sync_count:     int = 0

    def mark_syncing(self) -> None:
        self.sync_status = SyncStatus.SYNCING
        self.sync_errors = []

    def mark_completed(self, resources: int, duration_ms: int) -> None:
        self.sync_status          = SyncStatus.COMPLETED
        self.last_sync            = datetime.now(timezone.utc)
        self.sync_duration_ms     = duration_ms
        self.resources_discovered = resources
        self.successful_sync_count += 1

    def mark_failed(self, error: str) -> None:
        self.sync_status = SyncStatus.FAILED
        self.sync_errors.append(error)
        self.failed_sync_count += 1

    def mark_degraded(self, error: str) -> None:
        self.sync_status = SyncStatus.DEGRADED
        self.sync_errors.append(error)
        self.failed_sync_count += 1

    def to_dict(self) -> dict:
        return {
            "sync_status":           self.sync_status,
            "last_sync":             self.last_sync.isoformat() if self.last_sync else None,
            "sync_duration_ms":      self.sync_duration_ms,
            "resources_discovered":  self.resources_discovered,
            "sync_errors":           self.sync_errors[-5:],  # last 5 only
            "successful_sync_count": self.successful_sync_count,
            "failed_sync_count":     self.failed_sync_count,
        }


# ── Optimization recommendation ──────────────────────────────────────────────

@dataclass
class AWSRecommendation:
    """A single optimization recommendation from the engine."""
    rule_id:                       str
    title:                         str
    why:                           str
    impact:                        str
    estimated_monthly_savings_usd: float = 0.0
    affected_resources:            list[str] = field(default_factory=list)
    severity:                      str = "medium"   # low | medium | high | critical

    def to_dict(self) -> dict:
        return {
            "rule_id":                       self.rule_id,
            "title":                         self.title,
            "why":                           self.why,
            "impact":                        self.impact,
            "estimated_monthly_savings_usd": round(self.estimated_monthly_savings_usd, 2),
            "affected_resources":            self.affected_resources,
            "severity":                      self.severity,
        }
