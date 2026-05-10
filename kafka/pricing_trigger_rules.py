"""
kafka/pricing_trigger_rules.py — Business rules engine for dynamic pricing signals
Takes aggregated metrics from consumer and outputs price adjustment signals.
"""

import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


RULE_DEFINITIONS = [
    {
        "id": "high_demand_low_stock",
        "name": "High Demand + Low Inventory",
        "description": "Surge pricing due to demand spike and low stock",
        "priority": "critical",
    },
    {
        "id": "low_demand_high_stock",
        "name": "Low Demand + High Inventory",
        "description": "Clearance pricing to move excess inventory",
        "priority": "medium",
    },
    {
        "id": "competitor_undercut",
        "name": "Competitor Undercut",
        "description": "Competitor undercut — matching price to stay competitive",
        "priority": "high",
    },
    {
        "id": "flash_sale",
        "name": "Flash Sale Detection",
        "description": "Flash sale detected — adjusting to capture additional demand",
        "priority": "high",
    },
    {
        "id": "inventory_runout_risk",
        "name": "Inventory Runout Risk",
        "description": "Last items in stock — premium pricing",
        "priority": "critical",
    },
    {
        "id": "slow_moving_sku",
        "name": "Slow Moving SKU",
        "description": "Slow-moving SKU — aggressive discount needed",
        "priority": "low",
    },
]


class PricingRulesEngine:
    """
    Applies 6 business rules to aggregated product metrics and returns price signals.
    Rules are evaluated in priority order; higher priority rules override lower ones.
    """

    def __init__(self, historical_avg_demand: Optional[Dict[int, float]] = None):
        # {product_id: avg demand rate over history}
        self.historical_avg = historical_avg_demand or {}
        self._seven_day_order_counts: Dict[int, int] = {}  # for slow-mover detection

    def update_historical(self, product_id: int, demand_rate: float):
        """Exponential moving average update for historical demand baseline."""
        alpha = 0.1
        prev = self.historical_avg.get(product_id, demand_rate)
        self.historical_avg[product_id] = alpha * demand_rate + (1 - alpha) * prev

    def evaluate(self, metrics: Dict[str, Any]) -> Dict[str, Any]:
        """
        Evaluate all rules against aggregated product metrics.

        Args:
            metrics: dict from consumer with keys:
                product_id, category, metrics.demand_rate_orders_per_min,
                metrics.inventory_ratio, metrics.inventory_level,
                metrics.avg_competitor_price, metrics.our_current_price,
                metrics.total_orders, metrics.urgency_score

        Returns:
            price signal dict
        """
        product_id = metrics.get("product_id", 0)
        category = metrics.get("category", "unknown")
        inner = metrics.get("metrics", {})

        demand_rate = float(inner.get("demand_rate_orders_per_min", 0.0))
        inventory_ratio = float(inner.get("inventory_ratio", 0.5))
        inventory_level = int(inner.get("inventory_level", 5000))
        our_price = float(inner.get("our_current_price", 1000.0))
        competitor_price = float(inner.get("avg_competitor_price", our_price))
        total_orders = int(inner.get("total_orders", 0))

        historical_avg = self.historical_avg.get(product_id, 5.0)
        self.update_historical(product_id, demand_rate)

        triggered_rules: List[str] = []
        multiplier = 1.0
        urgency = "low"

        # ── Rule 1: High Demand + Low Inventory ─────────────────────────────────
        if demand_rate > 10 and inventory_ratio < 0.2:
            multiplier = max(multiplier, 1.20)
            triggered_rules.append("high_demand_low_stock")
            urgency = "critical"

        # ── Rule 5: Inventory Runout Risk ────────────────────────────────────────
        if inventory_level < 10 and demand_rate > 5:
            multiplier = max(multiplier, 1.50)
            triggered_rules.append("inventory_runout_risk")
            urgency = "critical"

        # ── Rule 2: Low Demand + High Inventory ──────────────────────────────────
        if demand_rate < 2 and inventory_ratio > 0.7 and "high_demand_low_stock" not in triggered_rules:
            multiplier = min(multiplier, 0.85)
            triggered_rules.append("low_demand_high_stock")
            urgency = max(urgency, "medium") if urgency == "low" else urgency

        # ── Rule 3: Competitor Undercut ──────────────────────────────────────────
        if competitor_price > 0 and our_price > competitor_price * 1.20:
            match_multiplier = competitor_price / our_price
            multiplier = min(multiplier, match_multiplier)
            triggered_rules.append("competitor_undercut")
            urgency = "high" if urgency in ("low", "medium") else urgency

        # ── Rule 4: Flash Sale ───────────────────────────────────────────────────
        if historical_avg > 0 and demand_rate > 3 * historical_avg and inventory_ratio < 0.5:
            multiplier = max(0.90, min(multiplier, 1.05))
            triggered_rules.append("flash_sale")
            urgency = "high" if urgency in ("low", "medium") else urgency

        # ── Rule 6: Slow Moving SKU ───────────────────────────────────────────────
        seven_day_total = self._seven_day_order_counts.get(product_id, total_orders)
        if seven_day_total == 0 and inventory_level > 500 and not triggered_rules:
            multiplier = min(multiplier, 0.70)
            triggered_rules.append("slow_moving_sku")
            urgency = "low"

        # Track 7-day orders (accumulate)
        self._seven_day_order_counts[product_id] = (
            self._seven_day_order_counts.get(product_id, 0) + total_orders
        )

        recommended_price = round(our_price * multiplier, 2)

        # Determine action
        if multiplier > 1.10:
            action = "urgent_increase" if urgency == "critical" else "increase"
        elif multiplier < 0.90:
            action = "decrease"
        else:
            action = "hold"

        return {
            "product_id": product_id,
            "category": category,
            "current_price": our_price,
            "recommended_price": recommended_price,
            "multiplier": round(multiplier, 4),
            "urgency": urgency,
            "triggered_rules": triggered_rules,
            "action": action,
            "reason": self._build_reason(triggered_rules),
            "timestamp": inner.get("timestamp", 0),
        }

    def _build_reason(self, triggered_rules: List[str]) -> str:
        if not triggered_rules:
            return "No price change required — market equilibrium."
        name_map = {r["id"]: r["description"] for r in RULE_DEFINITIONS}
        reasons = [name_map.get(rid, rid) for rid in triggered_rules[:2]]
        return " | ".join(reasons)


def get_rule_definitions() -> List[Dict]:
    return RULE_DEFINITIONS
