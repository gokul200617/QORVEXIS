"""AWS Connector — Phase 8D.

Concrete implementation of BaseConnector for AWS infrastructure intelligence.

PRIMARY EXECUTION PATH: Real boto3 API calls via AWSClient.
SIMULATION MODE: Only activated when explicitly requested — valid credentials
                 NEVER fall back to simulated data silently.

Connector lifecycle:
  authenticate() → validate() → collect_metrics() → normalize() → sync()

Failure behavior:
  Any AWS failure → connector DEGRADED
  Orchestration, OpenAI, token intelligence → UNAFFECTED
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Optional

from app.connectors.aws.aws_client import AWSClient
from app.connectors.aws.aws_cost_engine import aws_cost_engine
from app.connectors.aws.aws_models import (
    AWSAccountMetadata,
    AWSCredentials,
    AWSEC2Instance,
)
from app.connectors.aws.aws_optimization_engine import aws_optimization_engine
from app.connectors.aws.aws_usage_service import aws_usage_service
from app.connectors.aws.aws_validation import aws_validation
from app.connectors.base.base_connector import BaseConnector
from app.connectors.base.connector_status import ConnectorStatus
from app.connectors.base.connector_types import ConnectorType
from app.connectors.normalization.normalization_engine import normalization_engine

# Import normalizer so it registers itself with the engine
import app.connectors.aws.aws_normalizer  # noqa: F401

logger = logging.getLogger("qorvexis.connectors.aws.connector")


class AWSConnector(BaseConnector):
    """Read-only AWS infrastructure intelligence connector.

    Collects EC2 telemetry, CloudWatch utilization, and Cost Explorer data.
    Performs NO mutations to AWS resources.
    """

    def __init__(
        self,
        connector_id: str,
        name: str,
        access_key: str,
        secret_key: str,
        region: str,
        simulation_mode: bool = False,
    ) -> None:
        self._connector_id   = connector_id
        self._name           = name
        self._region         = region
        self._simulation_mode = simulation_mode
        self._status         = ConnectorStatus.DISCONNECTED
        self._account_id:    Optional[str] = None

        # Store credentials in-memory only — never logged or returned
        self._credentials = AWSCredentials(
            access_key=access_key,
            secret_key=secret_key,
            region=region,
        )

        # Build client only if not in simulation mode
        self._client: Optional[AWSClient] = None
        if not simulation_mode:
            self._client = AWSClient(
                access_key=access_key,
                secret_key=secret_key,
                region=region,
            )

        # Register with usage service
        aws_usage_service.register_connector(connector_id, name)
        logger.info(
            "aws.connector.init id=%s region=%s simulation=%s",
            connector_id,
            region,
            simulation_mode,
        )

    # ── Identity properties ───────────────────────────────────────────────────

    @property
    def connector_id(self) -> str:
        return self._connector_id

    @property
    def connector_name(self) -> str:
        return self._name

    @property
    def connector_type(self) -> ConnectorType:
        return ConnectorType.CLOUD_PROVIDER

    # ── Lifecycle methods ─────────────────────────────────────────────────────

    def authenticate(self) -> bool:
        """Confirm credentials are set (actual validation happens in validate())."""
        if self._simulation_mode:
            logger.info("aws.connector.authenticate simulation_mode=True")
            self._status = ConnectorStatus.CONNECTED
            return True

        if not self._client:
            logger.warning("aws.connector.authenticate no_client")
            return False

        return True

    def validate(self) -> bool:
        """Validate credentials via STS GetCallerIdentity.

        REAL CREDENTIALS: Calls real AWS STS. No silent fallback.
        SIMULATION MODE: Bypasses validation, returns True.
        """
        if self._simulation_mode:
            logger.info("aws.connector.validate simulation_mode=True — skipping real validation")
            self._status = ConnectorStatus.CONNECTED
            return True

        passed, result = aws_validation.validate(self._connector_id, self._client)

        if passed:
            self._account_id = result
            self._status     = ConnectorStatus.CONNECTED
            logger.info("aws.connector.validate.passed account=%s", self._account_id)
        else:
            self._status = ConnectorStatus.ERROR
            logger.warning("aws.connector.validate.failed reason=%s", result)

        return passed

    def collect_metrics(self) -> dict:
        """Collect EC2 + CloudWatch + Cost Explorer data.

        Marks sync_status=syncing before fetch, completed/degraded after.
        All AWS failures are caught and surfaced as degraded state,
        NOT propagated to crash orchestration or other connectors.
        """
        aws_usage_service.mark_syncing()
        t0 = time.monotonic()

        if self._simulation_mode:
            data = self._collect_simulated()
            duration_ms = int((time.monotonic() - t0) * 1000)
            self._record_successful_sync(data, duration_ms)
            return data

        # ── Real AWS API calls ────────────────────────────────────────────────
        try:
            # 1. EC2 discovery
            raw_instances = self._client.discover_ec2_instances()

            # 2. CloudWatch CPU for running instances
            running_ids = [
                i["instance_id"] for i in raw_instances
                if i.get("state") == "running"
            ]
            cpu_map     = {}
            network_map = {}
            if running_ids:
                cpu_map     = self._client.get_cloudwatch_cpu(running_ids)
                network_map = self._client.get_cloudwatch_network(running_ids)

            # 3. Build AWSEC2Instance objects
            instances = self._build_instances(raw_instances, cpu_map, network_map)

            # 4. Cost Explorer
            ce_response  = self._client.get_cost_explorer_summary()
            cost_summary = aws_cost_engine.compute_summary(ce_response)

            # 5. Optimization engine
            recommendations = aws_optimization_engine.analyze(
                instances,
                monthly_spend=cost_summary.get("monthly_spend", 0.0),
            )
            health_score       = aws_optimization_engine.compute_health_score(instances)
            optimization_score = aws_optimization_engine.compute_optimization_score(recommendations)
            waste_score        = aws_optimization_engine.compute_waste_score(
                instances, cost_summary.get("monthly_spend", 0.0)
            )

            # 6. Account metadata
            account_meta_raw = self._client.get_account_metadata(
                connector_id=self._connector_id,
                connector_name=self._name,
            )
            account_metadata = AWSAccountMetadata(
                account_id=account_meta_raw.get("account_id", ""),
                account_alias=account_meta_raw.get("account_alias"),
                region=self._region,
                connector_id=self._connector_id,
                connector_name=self._name,
            )

            duration_ms = int((time.monotonic() - t0) * 1000)

            data = {
                "instances":           [i.to_dict() for i in instances],
                "cost_summary":        cost_summary,
                "recommendations":     [r.to_dict() for r in recommendations],
                "health_score":        health_score,
                "optimization_score":  optimization_score,
                "waste_score":         waste_score,
                "account_metadata":    account_metadata.to_dict(),
                "simulation_mode":     False,
            }

            # Update usage service cache
            aws_usage_service.record_sync_success(
                instances=instances,
                cost_summary=cost_summary,
                recommendations=recommendations,
                account_metadata=account_metadata,
                health_score=health_score,
                optimization_score=optimization_score,
                waste_score=waste_score,
                duration_ms=duration_ms,
            )

            self._status = ConnectorStatus.CONNECTED
            logger.info(
                "aws.connector.collect_metrics.success instances=%s recs=%s duration_ms=%s",
                len(instances),
                len(recommendations),
                duration_ms,
            )
            return data

        except Exception as exc:
            duration_ms = int((time.monotonic() - t0) * 1000)
            error_msg   = str(exc)
            logger.warning(
                "aws.connector.collect_metrics.degraded error=%s duration_ms=%s",
                error_msg,
                duration_ms,
            )
            self._status = ConnectorStatus.DEGRADED
            aws_usage_service.record_sync_failure(error_msg, degraded=True)

            # Return a degraded-but-safe payload
            return {
                "instances":          [],
                "cost_summary":       {},
                "recommendations":    [],
                "health_score":       0.0,
                "optimization_score": 0.0,
                "waste_score":        0.0,
                "account_metadata":   {},
                "simulation_mode":    False,
                "degraded":           True,
                "error":              error_msg,
            }

    def normalize(self, raw_data: dict) -> dict:
        """Map raw AWS telemetry to NormalizedTelemetry using the normalization engine."""
        telemetry = normalization_engine.normalize(
            raw=raw_data,
            connector_id=self.connector_id,
            connector_name=self.connector_name,
            connector_type="aws",
        )
        return telemetry.to_dict()

    def health_check(self) -> ConnectorStatus:
        """Lightweight health check — STS ping in real mode, instant in simulation."""
        if self._simulation_mode:
            return ConnectorStatus.CONNECTED

        try:
            if self._client:
                self._client.validate_credentials()
                self._status = ConnectorStatus.CONNECTED
        except Exception as exc:
            logger.warning("aws.connector.health_check.failed detail=%s", exc)
            self._status = ConnectorStatus.DEGRADED

        return self._status

    def disconnect(self) -> None:
        """Clear in-memory credential references."""
        self._client      = None
        self._credentials = None
        self._status      = ConnectorStatus.DISCONNECTED
        logger.info("aws.connector.disconnected id=%s", self._connector_id)

    # ── Private helpers ───────────────────────────────────────────────────────

    def _build_instances(
        self,
        raw_instances: list[dict],
        cpu_map: dict[str, float],
        network_map: dict[str, dict],
    ) -> list[AWSEC2Instance]:
        """Build AWSEC2Instance objects from raw + CloudWatch data."""
        instances = []
        for raw in raw_instances:
            iid = raw["instance_id"]
            launch_time = None
            if raw.get("launch_time"):
                try:
                    launch_time = datetime.fromisoformat(
                        raw["launch_time"].replace("Z", "+00:00")
                    )
                except ValueError:
                    pass

            net = network_map.get(iid, {})
            instances.append(AWSEC2Instance(
                instance_id=iid,
                instance_type=raw.get("instance_type", "unknown"),
                state=raw.get("state", "unknown"),
                launch_time=launch_time,
                region=raw.get("region", self._region),
                availability_zone=raw.get("availability_zone", ""),
                cpu_utilization=cpu_map.get(iid, 0.0),
                network_in_bytes=net.get("in", 0.0),
                network_out_bytes=net.get("out", 0.0),
            ))
        return instances

    def _collect_simulated(self) -> dict:
        """Generate realistic simulated AWS data for demo mode."""
        import random
        from datetime import timedelta

        logger.info("aws.connector.simulation_mode — generating demo data")

        now = datetime.now(timezone.utc)
        instance_types = ["t3.medium", "t3.large", "m5.xlarge", "c5.2xlarge", "t2.micro"]
        states         = ["running"] * 7 + ["stopped"] * 3  # 70% running

        sim_instances: list[AWSEC2Instance] = []
        for i in range(10):
            state      = random.choice(states)
            itype      = random.choice(instance_types)
            cpu_util   = random.uniform(3.0, 85.0) if state == "running" else 0.0
            age_days   = random.randint(1, 45)
            launch_t   = now - timedelta(days=age_days)

            sim_instances.append(AWSEC2Instance(
                instance_id=f"i-{hex(random.randint(0x100000, 0xFFFFFF))[2:]}xxxxxx",
                instance_type=itype,
                state=state,
                launch_time=launch_t,
                region=self._region,
                availability_zone=f"{self._region}a",
                cpu_utilization=round(cpu_util, 2),
                network_in_bytes=random.uniform(1e6, 1e9),
                network_out_bytes=random.uniform(5e5, 5e8),
            ))

        # Simulated cost summary
        monthly = round(random.uniform(200, 2000), 2)
        daily   = round(monthly / 30, 2)
        cost_summary = {
            "monthly_spend":  monthly,
            "daily_spend":    daily,
            "daily_costs":    [
                {"date": (now - timedelta(days=d)).date().isoformat(),
                 "amount": round(random.uniform(daily * 0.8, daily * 1.2), 2)}
                for d in range(7, 0, -1)
            ],
            "service_breakdown": {
                "Amazon EC2": round(monthly * 0.65, 2),
                "AWS Data Transfer": round(monthly * 0.12, 2),
                "Amazon S3": round(monthly * 0.08, 2),
                "Amazon CloudWatch": round(monthly * 0.05, 2),
                "Other": round(monthly * 0.10, 2),
            },
            "top_services": [],
            "category_breakdown": {
                "ec2":        round(monthly * 0.65, 2),
                "networking": round(monthly * 0.12, 2),
                "storage":    round(monthly * 0.08, 2),
                "other":      round(monthly * 0.15, 2),
            },
            "spend_trend": {"direction": "stable", "change_pct": random.uniform(-5, 5)},
        }

        recommendations = aws_optimization_engine.analyze(sim_instances, monthly)
        health_score    = aws_optimization_engine.compute_health_score(sim_instances)
        opt_score       = aws_optimization_engine.compute_optimization_score(recommendations)
        waste_score     = aws_optimization_engine.compute_waste_score(sim_instances, monthly)

        account_metadata = AWSAccountMetadata(
            account_id="123456789012",
            account_alias="demo-account",
            region=self._region,
            connector_id=self._connector_id,
            connector_name=self._name,
        )

        # Record in usage service
        aws_usage_service.record_sync_success(
            instances=sim_instances,
            cost_summary=cost_summary,
            recommendations=recommendations,
            account_metadata=account_metadata,
            health_score=health_score,
            optimization_score=opt_score,
            waste_score=waste_score,
            duration_ms=50,
        )

        return {
            "instances":          [i.to_dict() for i in sim_instances],
            "cost_summary":       cost_summary,
            "recommendations":    [r.to_dict() for r in recommendations],
            "health_score":       health_score,
            "optimization_score": opt_score,
            "waste_score":        waste_score,
            "account_metadata":   account_metadata.to_dict(),
            "simulation_mode":    True,
        }

    def _record_successful_sync(self, data: dict, duration_ms: int) -> None:
        """Already handled inside _collect_simulated / collect_metrics."""
        pass
