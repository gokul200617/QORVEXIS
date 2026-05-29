"""AWS provider-specific normalizer — Phase 8D.

Converts the raw AWS infrastructure payload (EC2 + CloudWatch + Cost)
into the Qorvexis NormalizedTelemetry schema.

Registers itself with the normalization engine under the "aws" type,
so the base engine automatically routes AWS connector data through
this transform.
"""

from __future__ import annotations

import logging

from app.connectors.normalization.normalization_engine import normalization_engine

logger = logging.getLogger("qorvexis.connectors.aws.normalizer")


def transform_aws_infrastructure(raw: dict) -> dict:
    """Transform the AWS infrastructure payload into NormalizedTelemetry fields.

    Args:
        raw: Dict produced by AWSConnector.collect_metrics()
             Expected keys:
               instances        — list of AWSEC2Instance.to_dict()
               cost_summary     — output of aws_cost_engine.compute_summary()
               health_score     — float
               optimization_score — float
               waste_score      — float

    Returns:
        Dict with fields matching NormalizedTelemetry field names.
    """
    instances         = raw.get("instances", [])
    cost_summary      = raw.get("cost_summary", {})
    health_score      = raw.get("health_score", 100.0)
    optimization_score = raw.get("optimization_score", 95.0)
    waste_score       = raw.get("waste_score", 0.0)

    running_instances = [i for i in instances if i.get("state") == "running"]
    total_instances   = len(instances)

    # Average CPU across running instances
    cpu_utilizations = [
        i["cpu_utilization"]
        for i in running_instances
        if i.get("cpu_utilization", 0) > 0
    ]
    avg_cpu = (
        sum(cpu_utilizations) / len(cpu_utilizations)
        if cpu_utilizations else 0.0
    )

    monthly_spend = cost_summary.get("monthly_spend", 0.0)
    daily_spend   = cost_summary.get("daily_spend", 0.0)

    logger.debug(
        "aws.normalizer.transform running=%s avg_cpu=%.1f monthly=%.2f",
        len(running_instances),
        avg_cpu,
        monthly_spend,
    )

    return {
        "cpu_utilization_pct":  round(avg_cpu, 2),
        "estimated_cost_usd":   daily_spend,
        "estimated_monthly_usd": monthly_spend,
        "health_score":         health_score,
        "efficiency_score":     optimization_score,
        "waste_score":          waste_score,
        "reliability_score":    100.0 if total_instances > 0 else 0.0,
        # Pass extras through for downstream services
        "_aws_instance_count":  total_instances,
        "_aws_running_count":   len(running_instances),
    }


# Register transform with the engine — runs automatically when connector_type="aws"
normalization_engine.register_transform("aws", transform_aws_infrastructure)
logger.info("aws.normalizer.registered")
