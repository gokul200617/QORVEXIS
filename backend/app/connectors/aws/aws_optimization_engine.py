"""AWS infrastructure optimization engine — Phase 8D.

THE VALUE LAYER.

Evaluates EC2 instances against 5 deterministic intelligence rules
to generate actionable, quantified optimization recommendations.

Each recommendation includes:
  * WHY it was triggered (specific evidence)
  * IMPACT description
  * ESTIMATED SAVINGS (monthly USD)
  * AFFECTED RESOURCES (instance IDs)

This module performs NO AWS API calls.
It processes structured data from aws_client and aws_cost_engine.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from app.connectors.aws.aws_models import AWSRecommendation, AWSEC2Instance

logger = logging.getLogger("qorvexis.connectors.aws.optimization_engine")

# ── Instance type cost estimates (USD/hour, on-demand, approx) ───────────────
# Used to estimate savings potential when exact billing data is unavailable.
_INSTANCE_HOURLY_COSTS: dict[str, float] = {
    # micro/nano/small
    "t2.micro": 0.0116, "t2.small": 0.023, "t2.medium": 0.0464,
    "t3.micro": 0.0104, "t3.small": 0.0208, "t3.medium": 0.0416,
    "t3.large": 0.0832, "t3.xlarge": 0.1664, "t3.2xlarge": 0.3328,
    # compute optimized
    "c5.large": 0.085, "c5.xlarge": 0.17, "c5.2xlarge": 0.34,
    "c5.4xlarge": 0.68, "c5.9xlarge": 1.53, "c5.18xlarge": 3.06,
    # memory optimized
    "r5.large": 0.126, "r5.xlarge": 0.252, "r5.2xlarge": 0.504,
    "r5.4xlarge": 1.008, "r5.8xlarge": 2.016,
    # general purpose
    "m5.large": 0.096, "m5.xlarge": 0.192, "m5.2xlarge": 0.384,
    "m5.4xlarge": 0.768, "m5.8xlarge": 1.536, "m5.16xlarge": 3.072,
    # large GPU/compute
    "p3.2xlarge": 3.06, "p3.8xlarge": 12.24, "p3.16xlarge": 24.48,
    "g4dn.xlarge": 0.526, "g4dn.2xlarge": 1.052,
}

_LARGE_INSTANCE_PREFIXES = ("c5.4x", "c5.9x", "c5.18x", "r5.4x", "r5.8x",
                              "m5.4x", "m5.8x", "m5.16x", "p3", "g4dn")


def _hourly_cost(instance_type: str) -> float:
    return _INSTANCE_HOURLY_COSTS.get(instance_type, 0.10)  # default $0.10/hr


def _monthly_cost(instance_type: str) -> float:
    return round(_hourly_cost(instance_type) * 730, 2)


class AWSOptimizationEngine:
    """Evaluates infrastructure against 5 deterministic optimization rules."""

    # ── Rule thresholds ───────────────────────────────────────────────────────
    UNDERUTILIZED_CPU_THRESHOLD    = 10.0   # %
    OVERSIZED_CPU_THRESHOLD        = 20.0   # %
    IDLE_STOPPED_DAYS_THRESHOLD    = 7      # days
    COST_CONCENTRATION_TOP_N       = 3      # instances
    COST_CONCENTRATION_SHARE       = 0.60   # 60% threshold
    LOW_EFFICIENCY_SPEND_THRESHOLD = 50.0   # USD/month
    LOW_EFFICIENCY_CPU_THRESHOLD   = 15.0   # %

    def analyze(
        self,
        instances: list[AWSEC2Instance],
        monthly_spend: float = 0.0,
    ) -> list[AWSRecommendation]:
        """Run all 5 optimization rules against the instance fleet.

        Args:
            instances:     List of AWSEC2Instance objects with utilization data.
            monthly_spend: Total monthly AWS spend from Cost Explorer.

        Returns:
            Sorted list of AWSRecommendation objects (highest savings first).
        """
        recommendations: list[AWSRecommendation] = []

        running = [i for i in instances if i.is_running]
        stopped = [i for i in instances if i.is_stopped]

        # ── Rule 1: Underutilized Instances ───────────────────────────────────
        rec = self._rule_underutilized(running)
        if rec:
            recommendations.append(rec)

        # ── Rule 2: Oversized Compute ─────────────────────────────────────────
        rec = self._rule_oversized_compute(running)
        if rec:
            recommendations.append(rec)

        # ── Rule 3: Idle Resources ────────────────────────────────────────────
        rec = self._rule_idle_resources(stopped)
        if rec:
            recommendations.append(rec)

        # ── Rule 4: Cost Concentration ────────────────────────────────────────
        rec = self._rule_cost_concentration(running, monthly_spend)
        if rec:
            recommendations.append(rec)

        # ── Rule 5: Low Efficiency Infrastructure ────────────────────────────
        rec = self._rule_low_efficiency(running, monthly_spend)
        if rec:
            recommendations.append(rec)

        recommendations.sort(key=lambda r: r.estimated_monthly_savings_usd, reverse=True)
        logger.info(
            "aws.optimization_engine.analyze recommendations=%s instances=%s",
            len(recommendations),
            len(instances),
        )
        return recommendations

    # ── Rule implementations ──────────────────────────────────────────────────

    def _rule_underutilized(self, running: list[AWSEC2Instance]) -> Optional[AWSRecommendation]:
        """Rule 1: CPU utilization < 10% sustained → downsize or consolidate."""
        culprits = [
            i for i in running
            if i.cpu_utilization < self.UNDERUTILIZED_CPU_THRESHOLD
        ]
        if not culprits:
            return None

        avg_cpu = round(sum(i.cpu_utilization for i in culprits) / len(culprits), 1)
        # Savings estimate: 50% of current cost by downsizing one tier
        monthly_savings = round(
            sum(_monthly_cost(i.instance_type) * 0.5 for i in culprits), 2
        )

        return AWSRecommendation(
            rule_id="underutilized_instances",
            title="Underutilized EC2 Instances Detected",
            why=(
                f"{len(culprits)} running EC2 instance{'s' if len(culprits) > 1 else ''} "
                f"averaged {avg_cpu}% CPU utilization over the analysis window — "
                f"well below the {self.UNDERUTILIZED_CPU_THRESHOLD}% threshold indicating "
                f"active use."
            ),
            impact=(
                "Underutilized instances represent direct waste — you are paying for "
                "capacity that is not being used. Downsizing to a smaller instance type "
                "or consolidating workloads can recover this spend."
            ),
            estimated_monthly_savings_usd=monthly_savings,
            affected_resources=[i.instance_id for i in culprits],
            severity="high",
        )

    def _rule_oversized_compute(self, running: list[AWSEC2Instance]) -> Optional[AWSRecommendation]:
        """Rule 2: Large instance type + low CPU utilization → rightsizing."""
        culprits = [
            i for i in running
            if any(i.instance_type.startswith(prefix) for prefix in _LARGE_INSTANCE_PREFIXES)
            and i.cpu_utilization < self.OVERSIZED_CPU_THRESHOLD
        ]
        if not culprits:
            return None

        avg_cpu = round(sum(i.cpu_utilization for i in culprits) / len(culprits), 1)
        # Savings estimate: 40% of current cost by moving to a smaller tier
        monthly_savings = round(
            sum(_monthly_cost(i.instance_type) * 0.40 for i in culprits), 2
        )

        return AWSRecommendation(
            rule_id="oversized_compute",
            title="Oversized Compute Instances — Rightsizing Opportunity",
            why=(
                f"{len(culprits)} large compute instance{'s' if len(culprits) > 1 else ''} "
                f"({''.join(set(i.instance_type for i in culprits[:3]))}) "
                f"are running at an average of {avg_cpu}% CPU utilization. "
                f"These instance types are designed for high-demand workloads but are operating "
                f"well below their capacity."
            ),
            impact=(
                "Rightsizing to an appropriately sized instance type preserves workload "
                "performance while eliminating unnecessary compute spend. "
                "This is typically the highest-value optimization in EC2 cost reduction."
            ),
            estimated_monthly_savings_usd=monthly_savings,
            affected_resources=[i.instance_id for i in culprits],
            severity="high",
        )

    def _rule_idle_resources(self, stopped: list[AWSEC2Instance]) -> Optional[AWSRecommendation]:
        """Rule 3: Stopped instances older than threshold → cleanup opportunity."""
        now = datetime.now(timezone.utc)
        threshold = timedelta(days=self.IDLE_STOPPED_DAYS_THRESHOLD)

        old_stopped = [
            i for i in stopped
            if i.launch_time and (now - i.launch_time) > threshold
        ]
        if not old_stopped:
            return None

        # EBS volume costs for stopped instances — estimate $0.10/hr equivalent
        monthly_savings = round(len(old_stopped) * 10.0, 2)

        return AWSRecommendation(
            rule_id="idle_resources",
            title="Idle Stopped Instances — Cleanup Opportunity",
            why=(
                f"{len(old_stopped)} EC2 instance{'s' if len(old_stopped) > 1 else ''} "
                f"{'have' if len(old_stopped) > 1 else 'has'} been in stopped state "
                f"for more than {self.IDLE_STOPPED_DAYS_THRESHOLD} days. "
                f"Stopped instances still incur EBS storage charges and occupy resource "
                f"quotas without providing value."
            ),
            impact=(
                "Terminating idle stopped instances eliminates EBS volume charges and "
                "simplifies infrastructure management. "
                "Ensure data is snapshotted or backed up before termination."
            ),
            estimated_monthly_savings_usd=monthly_savings,
            affected_resources=[i.instance_id for i in old_stopped],
            severity="medium",
        )

    def _rule_cost_concentration(
        self,
        running: list[AWSEC2Instance],
        monthly_spend: float,
    ) -> Optional[AWSRecommendation]:
        """Rule 4: Top N instances driving majority of spend → investigate."""
        if len(running) < 4 or monthly_spend <= 0:
            return None

        # Sort by estimated instance cost (proxy for actual billing)
        sorted_instances = sorted(running, key=lambda i: _monthly_cost(i.instance_type), reverse=True)
        top_n = sorted_instances[:self.COST_CONCENTRATION_TOP_N]
        top_cost = sum(_monthly_cost(i.instance_type) for i in top_n)
        fleet_cost = sum(_monthly_cost(i.instance_type) for i in running)

        if fleet_cost == 0:
            return None

        concentration_ratio = top_cost / fleet_cost
        if concentration_ratio < self.COST_CONCENTRATION_SHARE:
            return None

        return AWSRecommendation(
            rule_id="cost_concentration",
            title="High Cost Concentration — Review Top Instances",
            why=(
                f"Your top {self.COST_CONCENTRATION_TOP_N} instances account for "
                f"{round(concentration_ratio * 100, 1)}% of estimated compute spend "
                f"across {len(running)} running instances. "
                f"This concentration indicates these instances may be over-provisioned "
                f"or carrying workloads that could be distributed more efficiently."
            ),
            impact=(
                "High cost concentration creates billing risk — a change in utilization "
                "of a single instance has outsized impact on your bill. "
                "Review these instances for rightsizing or workload redistribution."
            ),
            estimated_monthly_savings_usd=round(top_cost * 0.25, 2),  # conservative 25% saving estimate
            affected_resources=[i.instance_id for i in top_n],
            severity="medium",
        )

    def _rule_low_efficiency(
        self,
        running: list[AWSEC2Instance],
        monthly_spend: float,
    ) -> Optional[AWSRecommendation]:
        """Rule 5: High spend + low average utilization → general optimization opportunity."""
        if not running or monthly_spend < self.LOW_EFFICIENCY_SPEND_THRESHOLD:
            return None

        avg_cpu = sum(i.cpu_utilization for i in running) / len(running)
        if avg_cpu >= self.LOW_EFFICIENCY_CPU_THRESHOLD:
            return None

        savings_estimate = round(monthly_spend * 0.30, 2)

        return AWSRecommendation(
            rule_id="low_efficiency_infrastructure",
            title="Low-Efficiency Infrastructure Pattern Detected",
            why=(
                f"Your AWS infrastructure shows ${monthly_spend:.2f}/month in compute spend "
                f"with an average fleet CPU utilization of {avg_cpu:.1f}% across "
                f"{len(running)} running instances. "
                f"This pattern — high spend with low utilization — is the most common "
                f"source of cloud waste."
            ),
            impact=(
                "A comprehensive rightsizing initiative combining instance type optimization, "
                "workload consolidation, and Reserved Instance purchasing could significantly "
                "reduce your AWS compute costs while maintaining or improving performance."
            ),
            estimated_monthly_savings_usd=savings_estimate,
            affected_resources=[i.instance_id for i in running[:10]],
            severity="critical",
        )

    # ── Scoring helpers ───────────────────────────────────────────────────────

    def compute_health_score(self, instances: list[AWSEC2Instance]) -> float:
        """Compute an infrastructure health score (0–100)."""
        if not instances:
            return 100.0

        running = [i for i in instances if i.is_running]
        stopped = [i for i in instances if i.is_stopped]

        if not running:
            return 40.0  # all stopped → degraded but not critical

        avg_cpu = sum(i.cpu_utilization for i in running) / len(running)
        idle_ratio = len(stopped) / len(instances)

        score = 100.0
        if avg_cpu < self.UNDERUTILIZED_CPU_THRESHOLD:
            score -= 30
        elif avg_cpu < 25:
            score -= 15
        if idle_ratio > 0.5:
            score -= 20
        elif idle_ratio > 0.25:
            score -= 10

        return max(0.0, round(score, 1))

    def compute_optimization_score(self, recommendations: list[AWSRecommendation]) -> float:
        """Compute an optimization score (0–100, higher = more optimized)."""
        if not recommendations:
            return 95.0

        penalty = sum(
            20 if r.severity == "critical"
            else 10 if r.severity == "high"
            else 5
            for r in recommendations
        )
        return max(0.0, round(100.0 - penalty, 1))

    def compute_waste_score(self, instances: list[AWSEC2Instance], monthly_spend: float) -> float:
        """Compute a waste score (0–100, higher = more waste)."""
        if not instances or monthly_spend <= 0:
            return 0.0

        running = [i for i in instances if i.is_running]
        if not running:
            return 0.0

        low_util = [i for i in running if i.cpu_utilization < self.UNDERUTILIZED_CPU_THRESHOLD]
        waste_ratio = len(low_util) / len(running)
        return round(waste_ratio * 100, 1)


# ── Singleton ─────────────────────────────────────────────────────────────────
aws_optimization_engine = AWSOptimizationEngine()
