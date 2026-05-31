"""Spend Forecasting Engine — Phase 10.

Uses simple linear extrapolation of the last N days of GatewayRequestRecord
and TokenTelemetryRecord spend to project 7, 30, and 90-day cost.

Deterministic. No LLM. No external services.
"""

from __future__ import annotations
import logging
from datetime import datetime, timezone, timedelta
from typing import Any

from sqlalchemy.orm import Session
from sqlalchemy import func

logger = logging.getLogger("qorvexis.business.forecasting")


class ForecastingEngine:

    def get_forecast(self, db: Session, org_id: str | None = None) -> dict[str, Any]:
        """Projects 7, 30, and 90-day spend from recent daily averages."""
        try:
            daily_spend = self._get_daily_spend(db)

            if not daily_spend:
                return self._empty_forecast()

            # Use last 7 days for short-term and all available for long-term
            recent = daily_spend[-7:] if len(daily_spend) >= 7 else daily_spend
            avg_daily = sum(d["spend"] for d in recent) / len(recent)

            # Trend: compare first half vs second half of recent data
            if len(recent) >= 4:
                mid = len(recent) // 2
                avg_first = sum(d["spend"] for d in recent[:mid]) / mid
                avg_second = sum(d["spend"] for d in recent[mid:]) / (len(recent) - mid)
                trend_pct = ((avg_second - avg_first) / max(avg_first, 0.001)) * 100
            else:
                trend_pct = 0.0

            # Projected daily (apply trend)
            trend_multiplier = 1 + (trend_pct / 100)
            projected_daily = avg_daily * max(trend_multiplier, 0.1)

            return {
                "forecast_7d":  round(projected_daily * 7, 4),
                "forecast_30d": round(projected_daily * 30, 4),
                "forecast_90d": round(projected_daily * 90, 4),
                "avg_daily_spend": round(avg_daily, 4),
                "projected_daily_spend": round(projected_daily, 4),
                "trend_pct": round(trend_pct, 2),
                "trend_direction": "increasing" if trend_pct > 5 else "decreasing" if trend_pct < -5 else "stable",
                "data_points": len(daily_spend),
                "confidence": "high" if len(daily_spend) >= 14 else "medium" if len(daily_spend) >= 7 else "low",
            }
        except Exception as exc:
            logger.warning("forecasting.error detail=%s", exc)
            return self._empty_forecast()

    def _get_daily_spend(self, db: Session, org_id: str | None = None) -> list[dict]:
        """Combines gateway + token intelligence spend into a daily series."""
        # Fetch last 30 days from both tables
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        daily: dict[str, float] = {}

        try:
            from app.gateway.gateway_models import GatewayRequestRecord
            gw_rows = db.query(
                func.date(GatewayRequestRecord.created_at).label("day"),
                func.sum(GatewayRequestRecord.estimated_cost).label("spend"),
            ).filter(GatewayRequestRecord.created_at >= cutoff).group_by("day").all()

            for row in gw_rows:
                day = str(row.day)
                daily[day] = daily.get(day, 0.0) + float(row.spend or 0.0)
        except Exception:
            pass

        try:
            from app.token_intelligence.models.token_tracking import TokenTelemetryRecord
            ti_rows = db.query(
                func.date(TokenTelemetryRecord.created_at).label("day"),
                func.sum(TokenTelemetryRecord.estimated_cost).label("spend"),
            ).filter(TokenTelemetryRecord.created_at >= cutoff).group_by("day").all()

            for row in ti_rows:
                day = str(row.day)
                daily[day] = daily.get(day, 0.0) + float(row.spend or 0.0)
        except Exception:
            pass

        return [{"date": d, "spend": s} for d, s in sorted(daily.items())]

    def _empty_forecast(self) -> dict:
        return {
            "forecast_7d": 0.0,
            "forecast_30d": 0.0,
            "forecast_90d": 0.0,
            "avg_daily_spend": 0.0,
            "projected_daily_spend": 0.0,
            "trend_pct": 0.0,
            "trend_direction": "stable",
            "data_points": 0,
            "confidence": "low",
        }


forecasting_engine = ForecastingEngine()
