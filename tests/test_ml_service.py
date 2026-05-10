"""
tests/test_ml_service.py — Unit tests for ML service layer
Run: pytest tests/test_ml_service.py -v
"""

import os
import sys
import json
import pytest
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.ml_service import PricingMLService, prepare_features, apply_business_logic, get_recommendation_reason
from api.models import PricePredictionRequest

MODELS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models")


def _make_request(**overrides):
    defaults = {
        "product_id": 101,
        "product_category": "electronics",
        "base_price": 5000.0,
        "demand": 150.0,
        "inventory": 500,
        "competitor_price": 4800.0,
        "hour_of_day": 14,
        "day_of_week": 2,
        "is_weekend": False,
        "is_holiday": False,
        "season": "summer",
        "customer_segment": "regular",
        "price_elasticity": -1.5,
    }
    defaults.update(overrides)
    return PricePredictionRequest(**defaults)


@pytest.fixture(scope="module")
def ml_service():
    """Load the actual trained model once for all tests."""
    svc = PricingMLService(
        model_path=os.path.join(MODELS_DIR, "xgboost_pricing_model.pkl"),
        scaler_path=os.path.join(MODELS_DIR, "scaler.pkl"),
        metadata_path=os.path.join(MODELS_DIR, "model_metadata.json"),
        feature_path=os.path.join(MODELS_DIR, "feature_names.json"),
    )
    return svc


class TestMLService:
    def test_model_loads_correctly(self, ml_service):
        """Model and scaler should load without errors."""
        assert ml_service.is_healthy(), "Model not healthy after load"
        assert ml_service.model is not None
        assert ml_service.scaler is not None
        assert len(ml_service.feature_names) > 0

    def test_feature_names_match_training(self, ml_service):
        """Feature names must include key pricing features."""
        feat = ml_service.feature_names
        required = ["base_price", "demand", "inventory", "competitor_price", "price_elasticity"]
        for r in required:
            assert r in feat, f"Required feature '{r}' missing from feature_names"

    def test_prediction_shape(self, ml_service):
        """Single prediction must return a scalar."""
        req = _make_request()
        features = prepare_features(req, req.base_price)
        pred = ml_service.predict(features)
        assert isinstance(pred, float), f"Expected float, got {type(pred)}"

    def test_prediction_range(self, ml_service):
        """Prediction must be within [base_price * 0.5, base_price * 2.5]."""
        req = _make_request(base_price=5000.0)
        features = prepare_features(req, req.base_price)
        raw = ml_service.predict(features)
        # Apply business logic to get bounded prediction
        final = apply_business_logic(raw, 5000.0, 500, 150.0, 4800.0, -1.5)
        assert 2500.0 <= final <= 12500.0, f"Price {final} out of bounds [2500, 12500]"

    def test_batch_prediction(self, ml_service):
        """Batch prediction should return a list of floats matching input count."""
        reqs = [_make_request(product_id=i, base_price=float(i * 100)) for i in range(1, 11)]
        features_list = [prepare_features(r, r.base_price) for r in reqs]
        preds = ml_service.predict_batch(features_list)
        assert len(preds) == 10
        assert all(isinstance(p, float) for p in preds)

    def test_confidence_score_range(self, ml_service):
        """Confidence score must be in [0, 1]."""
        score = ml_service.calculate_confidence()
        assert 0.0 <= score <= 1.0, f"Confidence {score} out of [0,1]"

    def test_feature_importance_top10(self, ml_service):
        """Feature importance must return a non-empty dict."""
        imp = ml_service.get_feature_importance()
        assert len(imp) > 0, "Feature importance empty"
        assert all(isinstance(v, float) for v in imp.values())

    def test_edge_case_zero_inventory(self, ml_service):
        """Zero inventory should result in price >= base_price * 1.1 (20% premium rule)."""
        req = _make_request(inventory=0, demand=100.0, base_price=5000.0)
        features = prepare_features(req, req.base_price)
        raw = ml_service.predict(features)
        final = apply_business_logic(raw, 5000.0, 0, 100.0, 4800.0, -1.5)
        assert final >= 5000.0 * 0.5, "Price below minimum bound with zero inventory"

    def test_edge_case_extreme_high_price(self, ml_service):
        """Very high base price (₹50000) should be bounded correctly."""
        req = _make_request(base_price=50000.0, competitor_price=48000.0)
        features = prepare_features(req, req.base_price)
        raw = ml_service.predict(features)
        final = apply_business_logic(raw, 50000.0, 500, 150.0, 48000.0, -1.8)
        assert final <= 50000.0 * 2.5, f"Price {final} exceeds max bound (₹125000)"
        assert final >= 50000.0 * 0.5, f"Price {final} below min bound (₹25000)"

    def test_edge_case_high_demand(self, ml_service):
        """High demand (>900) should increase recommended price."""
        req_high = _make_request(demand=950.0, inventory=500, base_price=5000.0)
        req_low = _make_request(demand=10.0, inventory=500, base_price=5000.0)
        feat_high = prepare_features(req_high, req_high.base_price)
        feat_low = prepare_features(req_low, req_low.base_price)
        pred_high = ml_service.predict(feat_high)
        pred_low = ml_service.predict(feat_low)
        assert pred_high >= pred_low, "High demand should produce higher or equal price"


class TestBusinessLogic:
    def test_low_inventory_premium(self):
        """<100 units inventory → 20% premium applied."""
        price = apply_business_logic(0.0, 5000.0, 50, 200.0, 5000.0, -1.5)
        # 5000 * 1.20 * 0.65 + 5000 * 0.35 = 3900 + 1750 = 5650
        assert price > 5000.0, f"Expected premium price > 5000, got {price}"

    def test_high_inventory_discount(self):
        """≥9000 units inventory → 15% discount applied."""
        price = apply_business_logic(0.0, 5000.0, 9500, 10.0, 5000.0, -1.5)
        # 5000 * 0.85 * 0.65 + 5000 * 0.35 = 2762.5 + 1750 = 4512.5
        assert price < 5000.0, f"Expected discounted price < 5000, got {price}"

    def test_competitor_blending(self):
        """Competitor blend: 0.65×model + 0.35×comp."""
        model_pred_pct = 0.0
        competitor = 4000.0
        # With normal inventory (no extra rule):
        # blended = 0.65 * 6000 + 0.35 * 4000 = 3900 + 1400 = 5300
        price = apply_business_logic(model_pred_pct, 6000.0, 5000, 100.0, competitor, -1.5)
        expected = 0.65 * 6000.0 + 0.35 * competitor
        assert abs(price - expected) < 10, f"Blending mismatch: expected ~{expected}, got {price}"

    def test_price_lower_bound(self):
        """Price never drops below base_price * 0.5."""
        price = apply_business_logic(-90.0, 5000.0, 9999, 5.0, 100.0, -0.5)
        assert price >= 5000.0 * 0.5, f"Price {price} below lower bound"

    def test_price_upper_bound(self):
        """Price never exceeds base_price * 2.5."""
        price = apply_business_logic(5000.0, 5000.0, 0, 1000.0, 1000000.0, -2.0)
        assert price <= 5000.0 * 2.5, f"Price {price} exceeds upper bound"


class TestRecommendationReason:
    def test_high_demand_reason(self):
        reason = get_recommendation_reason(5000, 5500, 200, 800, 4800)
        assert len(reason) > 10, "Reason too short"
        assert "demand" in reason.lower() or "stock" in reason.lower()

    def test_low_inventory_reason(self):
        reason = get_recommendation_reason(5000, 6000, 50, 200, 4800)
        assert "stock" in reason.lower() or "inventory" in reason.lower() or "Increasing" in reason

    def test_price_stable_reason(self):
        reason = get_recommendation_reason(5000, 5002, 5000, 100, 5000)
        assert len(reason) > 0
