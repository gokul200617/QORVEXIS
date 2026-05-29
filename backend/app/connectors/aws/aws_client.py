"""AWS API client — Phase 8D.

All AWS API access is channelled through this module.

IMPORTANT: Real boto3 API calls are the default execution path.
Simulation mode is ONLY activated when explicitly requested.
Valid credentials NEVER silently fall back to simulated data.

Supported services:
  * STS       — credential validation + account identity
  * EC2       — instance discovery
  * CloudWatch — CPU and network utilization metrics
  * Cost Explorer — daily, monthly, and service-level spend
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger("qorvexis.connectors.aws.client")


class AWSClient:
    """boto3-backed client for AWS observability APIs.

    Only imports boto3 at construction time so that the connector
    module can be imported even if boto3 is not installed — the import
    error surfaces on first instantiation rather than at server startup.
    """

    def __init__(self, access_key: str, secret_key: str, region: str) -> None:
        try:
            import boto3
            from botocore.config import Config
        except ImportError as exc:
            raise ImportError(
                "boto3 is required for AWS connector. "
                "Install with: pip install boto3"
            ) from exc

        self._region = region
        self._config = Config(
            connect_timeout=10,
            read_timeout=15,
            retries={"max_attempts": 2, "mode": "standard"},
        )

        session = boto3.Session(
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
        )

        self._sts = session.client("sts",               config=self._config)
        self._ec2 = session.client("ec2",               config=self._config, region_name=region)
        self._cw  = session.client("cloudwatch",        config=self._config, region_name=region)
        self._ce  = session.client("ce",                config=self._config, region_name="us-east-1")  # CE is global
        self._iam = session.client("iam",               config=self._config)

        logger.info("aws.client.init region=%s", region)

    # ── Credential validation ─────────────────────────────────────────────────

    def validate_credentials(self) -> dict:
        """Call STS GetCallerIdentity to confirm credentials work.

        Returns the identity dict on success.
        Raises ConnectorAuthError on invalid credentials.
        Raises ConnectorIngestionError on network/API errors.
        NEVER falls back to simulation.
        """
        from app.connectors.base.connector_exceptions import (
            ConnectorAuthError,
            ConnectorIngestionError,
        )
        try:
            identity = self._sts.get_caller_identity()
            logger.info(
                "aws.client.validate_credentials.success account=%s",
                identity.get("Account"),
            )
            return {
                "account_id": identity.get("Account", ""),
                "user_id":    identity.get("UserId", ""),
                "arn":        identity.get("Arn", ""),
            }
        except Exception as exc:
            exc_str = str(exc)
            if "InvalidClientTokenId" in exc_str or "AuthFailure" in exc_str \
                    or "credentials" in exc_str.lower() or "ExpiredToken" in exc_str:
                logger.warning("aws.client.validate_credentials.auth_failure detail=%s", exc_str)
                raise ConnectorAuthError(f"AWS credential validation failed: {exc_str}") from exc
            logger.error("aws.client.validate_credentials.error detail=%s", exc_str)
            raise ConnectorIngestionError(f"AWS STS error: {exc_str}") from exc

    # ── Account metadata ─────────────────────────────────────────────────────

    def get_account_metadata(self, connector_id: str = "", connector_name: str = "") -> dict:
        """Fetch account identity from STS and alias from IAM (best-effort)."""
        identity = self.validate_credentials()
        account_id = identity.get("account_id", "")

        # IAM alias is optional — not all accounts have one
        account_alias: Optional[str] = None
        try:
            aliases = self._iam.list_account_aliases().get("AccountAliases", [])
            if aliases:
                account_alias = aliases[0]
        except Exception as exc:
            logger.debug("aws.client.account_alias.unavailable detail=%s", exc)

        return {
            "account_id":     account_id,
            "account_alias":  account_alias,
            "region":         self._region,
            "connector_id":   connector_id,
            "connector_name": connector_name,
        }

    # ── EC2 discovery ─────────────────────────────────────────────────────────

    def discover_ec2_instances(self) -> list[dict]:
        """Return lightweight EC2 instance snapshots for the current region.

        Collects only the fields required for operational intelligence.
        Does NOT perform deep metadata scraping.
        """
        from app.connectors.base.connector_exceptions import ConnectorIngestionError
        try:
            paginator = self._ec2.get_paginator("describe_instances")
            instances = []

            for page in paginator.paginate():
                for reservation in page.get("Reservations", []):
                    for inst in reservation.get("Instances", []):
                        state = inst.get("State", {}).get("Name", "unknown")
                        launch_time = inst.get("LaunchTime")

                        instances.append({
                            "instance_id":       inst.get("InstanceId", ""),
                            "instance_type":     inst.get("InstanceType", "unknown"),
                            "state":             state,
                            "launch_time":       launch_time.isoformat() if launch_time else None,
                            "availability_zone": inst.get("Placement", {}).get("AvailabilityZone", ""),
                            "region":            self._region,
                        })

            logger.info("aws.client.ec2_discovery.complete count=%s", len(instances))
            return instances

        except Exception as exc:
            raise ConnectorIngestionError(f"EC2 discovery failed: {exc}") from exc

    # ── CloudWatch metrics ────────────────────────────────────────────────────

    def get_cloudwatch_cpu(
        self,
        instance_ids: list[str],
        lookback_hours: int = 1,
    ) -> dict[str, float]:
        """Fetch average CPU utilization for the given instances.

        Returns a dict mapping instance_id → average CPU % over the window.
        Uses a single GetMetricData call with one query per instance
        (up to 500 per call — well within EC2 fleet sizes we target).
        """
        from app.connectors.base.connector_exceptions import ConnectorIngestionError
        if not instance_ids:
            return {}

        # Limit to 100 instances to avoid excessively large requests
        instance_ids = instance_ids[:100]

        end_time   = datetime.now(timezone.utc)
        start_time = end_time - timedelta(hours=lookback_hours)

        queries = [
            {
                "Id":         f"cpu_{i}",
                "MetricStat": {
                    "Metric": {
                        "Namespace":  "AWS/EC2",
                        "MetricName": "CPUUtilization",
                        "Dimensions": [{"Name": "InstanceId", "Value": iid}],
                    },
                    "Period": 3600,
                    "Stat":   "Average",
                },
                "ReturnData": True,
            }
            for i, iid in enumerate(instance_ids)
        ]

        try:
            response = self._cw.get_metric_data(
                MetricDataQueries=queries,
                StartTime=start_time,
                EndTime=end_time,
            )

            result: dict[str, float] = {}
            for metric_result in response.get("MetricDataResults", []):
                idx_str = metric_result["Id"].replace("cpu_", "")
                try:
                    idx = int(idx_str)
                    iid = instance_ids[idx]
                    values = metric_result.get("Values", [])
                    result[iid] = round(sum(values) / len(values), 2) if values else 0.0
                except (ValueError, IndexError):
                    pass

            logger.info("aws.client.cloudwatch_cpu.complete instances=%s", len(result))
            return result

        except Exception as exc:
            raise ConnectorIngestionError(f"CloudWatch CPU fetch failed: {exc}") from exc

    def get_cloudwatch_network(
        self,
        instance_ids: list[str],
        lookback_hours: int = 1,
    ) -> dict[str, dict]:
        """Fetch NetworkIn and NetworkOut averages per instance."""
        from app.connectors.base.connector_exceptions import ConnectorIngestionError
        if not instance_ids:
            return {}

        instance_ids = instance_ids[:100]
        end_time   = datetime.now(timezone.utc)
        start_time = end_time - timedelta(hours=lookback_hours)

        queries = []
        for i, iid in enumerate(instance_ids):
            for metric_name, suffix in [("NetworkIn", "ni"), ("NetworkOut", "no")]:
                queries.append({
                    "Id":         f"{suffix}_{i}",
                    "MetricStat": {
                        "Metric": {
                            "Namespace":  "AWS/EC2",
                            "MetricName": metric_name,
                            "Dimensions": [{"Name": "InstanceId", "Value": iid}],
                        },
                        "Period": 3600,
                        "Stat":   "Sum",
                    },
                    "ReturnData": True,
                })

        try:
            response = self._cw.get_metric_data(
                MetricDataQueries=queries,
                StartTime=start_time,
                EndTime=end_time,
            )

            network: dict[str, dict] = {iid: {"in": 0.0, "out": 0.0} for iid in instance_ids}
            for mr in response.get("MetricDataResults", []):
                mid = mr["Id"]
                values = mr.get("Values", [])
                avg = sum(values) / len(values) if values else 0.0
                if mid.startswith("ni_"):
                    idx = int(mid[3:])
                    network[instance_ids[idx]]["in"] = round(avg, 2)
                elif mid.startswith("no_"):
                    idx = int(mid[3:])
                    network[instance_ids[idx]]["out"] = round(avg, 2)

            return network

        except Exception as exc:
            raise ConnectorIngestionError(f"CloudWatch network fetch failed: {exc}") from exc

    # ── Cost Explorer ─────────────────────────────────────────────────────────

    def get_cost_explorer_summary(self, days: int = 30) -> dict:
        """Fetch daily and monthly cost summaries from Cost Explorer.

        Returns a structured dict with:
          * daily_costs   — list of {date, amount} dicts
          * monthly_total — sum over the period
          * service_breakdown — {service_name: total_amount}
        """
        from app.connectors.base.connector_exceptions import ConnectorIngestionError
        try:
            end   = datetime.now(timezone.utc).date()
            start = end - timedelta(days=days)

            # Daily total costs
            daily_resp = self._ce.get_cost_and_usage(
                TimePeriod={"Start": start.isoformat(), "End": end.isoformat()},
                Granularity="DAILY",
                Metrics=["UnblendedCost"],
            )

            daily_costs = []
            monthly_total = 0.0
            for result in daily_resp.get("ResultsByTime", []):
                amount = float(result["Total"].get("UnblendedCost", {}).get("Amount", 0))
                daily_costs.append({
                    "date":   result["TimePeriod"]["Start"],
                    "amount": round(amount, 4),
                })
                monthly_total += amount

            # Service breakdown (monthly grouping)
            service_resp = self._ce.get_cost_and_usage(
                TimePeriod={"Start": start.isoformat(), "End": end.isoformat()},
                Granularity="MONTHLY",
                Metrics=["UnblendedCost"],
                GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
            )

            service_breakdown: dict[str, float] = {}
            for result in service_resp.get("ResultsByTime", []):
                for group in result.get("Groups", []):
                    service = group["Keys"][0]
                    amount  = float(group["Metrics"]["UnblendedCost"]["Amount"])
                    service_breakdown[service] = round(
                        service_breakdown.get(service, 0.0) + amount, 4
                    )

            # Daily spend = last single day
            daily_spend = daily_costs[-1]["amount"] if daily_costs else 0.0

            logger.info(
                "aws.client.cost_explorer.complete monthly=%.2f services=%s",
                monthly_total,
                len(service_breakdown),
            )

            return {
                "daily_costs":       daily_costs,
                "monthly_total":     round(monthly_total, 2),
                "daily_spend":       daily_spend,
                "service_breakdown": service_breakdown,
            }

        except Exception as exc:
            raise ConnectorIngestionError(f"Cost Explorer fetch failed: {exc}") from exc
