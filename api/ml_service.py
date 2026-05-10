"""
api/ml_service.py — Model loading, feature preparation, prediction, and business logic
"""

import os
import sys
import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

import numpy as np
import pandas as pd
import joblib

logger = logging.getLogger(__name__)

# ─── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS_DIR = os.path.join(BASE_DIR, "models")

CATEGORIES = ["electronics", "apparel", "home", "books", "food"]
SEASONS = ["spring", "summer", "monsoon", "winter"]
SEGMENTS = ["premium", "regular", "budget"]


class PricingMLService:
    """Wraps the trained XGBoost model with prediction and business logic."""

    def __init__(self, model_path: str, scaler_path: str, metadata_path: str, feature_path: str):
        self.model = None
        self.scaler = None
        self.feature_names: List[str] = []
        self.metadata: Dict[str, Any] = {}
        self._load(model_path, scaler_path, metadata_path, feature_path)

    def _load(self, model_path, scaler_path, metadata_path, feature_path):
        """Load all model artifacts from disk."""
        try:
            self.model = joblib.load(model_path)
            self.scaler = joblib.load(scaler_path)
            with open(feature_path, "r") as f:
                self.feature_names = json.load(f)
            with open(metadata_path, "r") as f:
                self.metadata = json.load(f)
            logger.info("Model loaded successfully — version: %s", self.metadata.get("model_version", "unknown"))
        except Exception as e:
            logger.error("Failed to load model artifacts: %s", e)
            raise RuntimeError(f"Model load failed: {e}") from e

    def is_healthy(self) -> bool:
        return self.model is not None and self.scaler is not None

    def get_mae(self) -> float:
        return float(self.metadata.get("mae", 0.0))

    def get_model_version(self) -> str:
        return str(self.metadata.get("model_version", "unknown"))

    def get_training_date(self) -> str:
        return str(self.metadata.get("training_date", "unknown"))

    def get_feature_importance(self) -> Dict[str, float]:
        return {k: float(v) for k, v in self.metadata.get("top_10_features", {}).items()}

    def calculate_confidence(self) -> float:
        """Confidence score derived from R² of training."""
        r2 = float(self.metadata.get("r2", 0.9))
        return round(min(max(r2, 0.0), 1.0), 4)

    def predict(self, features_dict: Dict[str, Any]) -> float:
        """Single prediction: dict → scaled array → model → float."""
        arr = self._dict_to_array(features_dict)
        scaled = self.scaler.transform(arr)
        return float(self.model.predict(scaled)[0])

    def predict_batch(self, features_list: List[Dict[str, Any]]) -> List[float]:
        """Batch prediction — vectorized for performance."""
        rows = [self._dict_to_array(f)[0] for f in features_list]
        arr = np.array(rows)
        scaled = self.scaler.transform(arr)
        preds = self.model.predict(scaled)
        return [float(p) for p in preds]

    def _dict_to_array(self, d: Dict[str, Any]) -> np.ndarray:
        """Convert a features dict to a numpy row aligned to training feature order."""
        row = {k: 0 for k in self.feature_names}

        # Numerical
        for col in [
            "base_price", "demand", "inventory", "competitor_price",
            "day_of_week", "hour_of_day", "is_weekend", "is_holiday",
            "price_elasticity", "demand_ratio", "inventory_ratio",
            "price_gap", "competitor_discount", "demand_inventory_product",
            "competitor_elasticity", "demand_hour_interaction",
            "demand_weekend", "demand_holiday",
        ]:
            if col in row and col in d:
                row[col] = float(d[col])

        # One-hot: product_category
        for cat in CATEGORIES:
            key = f"product_category_{cat}"
            if key in row:
                row[key] = 1 if d.get("product_category") == cat else 0

        # One-hot: season
        for s in SEASONS:
            key = f"season_{s}"
            if key in row:
                row[key] = 1 if d.get("season") == s else 0

        # One-hot: customer_segment
        for seg in SEGMENTS:
            key = f"customer_segment_{seg}"
            if key in row:
                row[key] = 1 if d.get("customer_segment") == seg else 0

        return np.array([[row[k] for k in self.feature_names]], dtype=float)


# ─── Feature preparation ───────────────────────────────────────────────────────

def prepare_features(req, base_price: float) -> Dict[str, Any]:
    """
    Convert a PricePredictionRequest into a feature dict ready for PricingMLService.predict().
    Derives all engineered features from raw request fields.
    """
    demand = float(req.demand)
    inventory = int(req.inventory)
    competitor_price = float(req.competitor_price)
    price_elasticity = float(req.price_elasticity)
    hour = int(req.hour_of_day)

    demand_ratio        = demand / 1000.0
    inventory_ratio     = inventory / 10000.0
    price_gap           = (base_price - competitor_price) / (base_price + 1e-9)
    competitor_discount = (base_price - competitor_price) / (competitor_price + 1e-9)

    features = {
        "base_price":               base_price,
        "demand":                   demand,
        "inventory":                inventory,
        "competitor_price":         competitor_price,
        "day_of_week":              int(req.day_of_week),
        "hour_of_day":              hour,
        "is_weekend":               int(req.is_weekend),
        "is_holiday":               int(req.is_holiday),
        "price_elasticity":         price_elasticity,
        "demand_ratio":             demand_ratio,
        "inventory_ratio":          inventory_ratio,
        "price_gap":                price_gap,
        "competitor_discount":      competitor_discount,
        "demand_inventory_product": demand * inventory / 10000.0,
        "competitor_elasticity":    competitor_price * abs(price_elasticity),
        "demand_hour_interaction":  demand * (1.0 if hour > 18 else 0.8),
        "demand_weekend":           demand * int(req.is_weekend),
        "demand_holiday":           demand * int(req.is_holiday),
        "product_category":         req.product_category.value,
        "season":                   req.season.value,
        "customer_segment":         req.customer_segment.value,
    }
    return features


# ─── Business logic ────────────────────────────────────────────────────────────

def apply_business_logic(
    model_prediction: float,   # now a price_change_pct (e.g. -7.5 means -7.5%)
    base_price: float,
    inventory: int,
    demand: float,
    competitor_price: float,
    price_elasticity: float,
) -> float:
    """
    Convert price_change_pct → absolute price, then apply business rules.
    Rules:
      1. Convert: price = base_price * (1 + pct/100)
      2. Inventory bounds: <100 units → +20%; >9000 units → -15%
      3. Competitor blending: 65% ML price + 35% competitor
      4. Hard bounds: [base × 0.5, base × 2.5]
    """
    # Step 1: pct → absolute price
    price_change_pct = float(model_prediction)
    price = base_price * (1 + price_change_pct / 100.0)

    # Rule 2: Inventory constraints
    if inventory < 100:
        price *= 1.20
    elif inventory > 9000:
        price *= 0.85

    # Rule 3: Competitor blending (65% ML, 35% competitor)
    price = 0.65 * price + 0.35 * competitor_price

    # Rule 4: Hard bounds
    price = max(price, base_price * 0.50)
    price = min(price, base_price * 2.50)

    return round(price, 2)


def get_recommendation_reason(
    original_price: float,
    recommended_price: float,
    inventory: int,
    demand: float,
    competitor_price: float,
) -> str:
    """Generate a human-readable explanation for the price recommendation."""
    change_pct = (recommended_price - original_price) / (original_price + 1e-9) * 100
    factors = []

    if demand > 500:
        factors.append(f"very high demand ({demand:.0f} orders/h)")
    elif demand > 200:
        factors.append(f"high demand ({demand:.0f} orders/h)")
    elif demand < 20:
        factors.append(f"low demand ({demand:.0f} orders/h)")

    if inventory < 100:
        factors.append(f"critically low stock ({inventory} units)")
    elif inventory > 9000:
        factors.append(f"excess inventory ({inventory} units)")

    competitor_diff = (original_price - competitor_price) / (competitor_price + 1e-9) * 100
    if competitor_diff > 15:
        factors.append(f"competitor undercuts by {competitor_diff:.1f}%")
    elif competitor_diff < -15:
        factors.append(f"competitor priced {abs(competitor_diff):.1f}% higher")

    if not factors:
        factors = ["market equilibrium maintained"]

    direction = "Increasing" if change_pct > 0.5 else ("Decreasing" if change_pct < -0.5 else "Maintaining")
    pct_str = f"{abs(change_pct):.1f}%" if abs(change_pct) > 0.1 else "stable"
    reason = f"{direction} price {pct_str} due to {' and '.join(factors[:2])}."
    return reason
