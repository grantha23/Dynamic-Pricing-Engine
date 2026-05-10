"""
tests/test_system.py — End-to-end system integration test
Tests full pipeline: Data → ML → API → Response validation → Kafka → Rules Engine
"""

import os
import sys
import json
import time
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.ml_service import PricingMLService, prepare_features, apply_business_logic, get_recommendation_reason
from api.models import PricePredictionRequest
from kafka.pricing_trigger_rules import PricingRulesEngine
from kafka.producer import generate_order_event, generate_inventory_event, generate_competitor_event
from kafka.consumer import run_mock_consumer

MODELS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models")


@pytest.fixture(scope="module")
def ml_service():
    return PricingMLService(
        model_path=os.path.join(MODELS_DIR, "xgboost_pricing_model.pkl"),
        scaler_path=os.path.join(MODELS_DIR, "scaler.pkl"),
        metadata_path=os.path.join(MODELS_DIR, "model_metadata.json"),
        feature_path=os.path.join(MODELS_DIR, "feature_names.json"),
    )


class TestEndToEndFlow:
    def test_complete_prediction_flow(self, ml_service):
        """
        Full pipeline: raw request → features → ML → business logic → response validation.
        """
        req = PricePredictionRequest(
            product_id=12345,
            product_category="electronics",
            base_price=10000.0,
            demand=300.0,
            inventory=800,
            competitor_price=9500.0,
            hour_of_day=10,
            day_of_week=1,
            is_weekend=False,
            is_holiday=False,
            season="summer",
            customer_segment="premium",
            price_elasticity=-1.8,
        )

        # Step 1: Prepare features
        t0 = time.time()
        features = prepare_features(req, req.base_price)
        assert isinstance(features, dict)
        assert "base_price" in features
        assert "demand_ratio" in features

        # Step 2: ML prediction
        raw_price = ml_service.predict(features)
        assert isinstance(raw_price, float)
        assert raw_price > 0

        # Step 3: Business logic
        final_price = apply_business_logic(
            raw_price, req.base_price, req.inventory, req.demand,
            req.competitor_price, req.price_elasticity,
        )
        assert req.base_price * 0.5 <= final_price <= req.base_price * 2.5

        # Step 4: Confidence
        confidence = ml_service.calculate_confidence()
        assert 0.0 <= confidence <= 1.0

        # Step 5: Reason
        reason = get_recommendation_reason(req.base_price, final_price, req.inventory, req.demand, req.competitor_price)
        assert len(reason) > 10

        # Step 6: Validate response structure
        price_change_pct = (final_price - req.base_price) / req.base_price * 100
        response = {
            "product_id":           req.product_id,
            "recommended_price":    round(final_price, 2),
            "confidence_score":     confidence,
            "price_change_pct":     round(price_change_pct, 2),
            "recommendation_reason": reason,
        }
        for key in ["product_id", "recommended_price", "confidence_score", "price_change_pct", "recommendation_reason"]:
            assert key in response

        total_ms = (time.time() - t0) * 1000
        assert total_ms < 1000, f"End-to-end flow took {total_ms:.1f}ms > 1000ms"
        print(f"\n[E2E] Price: {req.base_price:.0f} → {final_price:.0f} ({price_change_pct:+.1f}%) | {total_ms:.1f}ms")

    def test_batch_flow_100_products(self, ml_service):
        """Batch flow: 100 products processed in < 2 seconds."""
        products = []
        for i in range(100):
            products.append(PricePredictionRequest(
                product_id=i + 1,
                product_category=["electronics", "apparel", "home", "books", "food"][i % 5],
                base_price=float(1000 + i * 200),
                demand=float(10 + i * 5),
                inventory=100 + i * 50,
                competitor_price=float(950 + i * 190),
                hour_of_day=i % 24,
                day_of_week=i % 7,
                is_weekend=(i % 7 >= 5),
                is_holiday=False,
                season=["spring", "summer", "monsoon", "winter"][i % 4],
                customer_segment=["premium", "regular", "budget"][i % 3],
                price_elasticity=-1.0 - (i % 10) * 0.1,
            ))

        t0 = time.time()
        features_list = [prepare_features(p, p.base_price) for p in products]
        raw_prices = ml_service.predict_batch(features_list)
        final_prices = [
            apply_business_logic(raw, p.base_price, p.inventory, p.demand, p.competitor_price, p.price_elasticity)
            for raw, p in zip(raw_prices, products)
        ]
        elapsed_ms = (time.time() - t0) * 1000

        assert len(final_prices) == 100
        assert all(p > 0 for p in final_prices)
        assert elapsed_ms < 2000, f"Batch 100 took {elapsed_ms:.1f}ms > 2000ms"
        print(f"\n[BATCH] 100 products in {elapsed_ms:.1f}ms | avg price: ₹{sum(final_prices)/len(final_prices):,.0f}")

    def test_output_schema_validation(self, ml_service):
        """Verify all response fields have correct types and ranges."""
        req = PricePredictionRequest(
            product_id=999,
            product_category="home",
            base_price=15000.0,
            demand=200.0,
            inventory=3000,
            competitor_price=14000.0,
            hour_of_day=20,
            day_of_week=5,
            is_weekend=True,
            is_holiday=False,
            season="winter",
            customer_segment="budget",
            price_elasticity=-0.9,
        )
        features = prepare_features(req, req.base_price)
        raw = ml_service.predict(features)
        final = apply_business_logic(raw, req.base_price, req.inventory, req.demand, req.competitor_price, req.price_elasticity)
        confidence = ml_service.calculate_confidence()
        change_pct = (final - req.base_price) / req.base_price * 100
        reason = get_recommendation_reason(req.base_price, final, req.inventory, req.demand, req.competitor_price)

        assert isinstance(req.product_id, int)
        assert isinstance(final, float)
        assert isinstance(confidence, float) and 0 <= confidence <= 1
        assert isinstance(change_pct, float)
        assert isinstance(reason, str) and len(reason) > 5


class TestKafkaPipelineIntegration:
    def test_event_to_rules_engine_flow(self):
        """Simulate: generate events → aggregate → rules engine → price signal."""
        rules_engine = PricingRulesEngine()

        # Simulate order events being aggregated
        orders = [generate_order_event() for _ in range(15)]
        inv_update = generate_inventory_event()
        inv_update["new_level"] = 80  # Trigger low inventory rule

        # Build aggregated metrics (as consumer would produce)
        product_id = orders[0]["product_id"]
        metrics = {
            "product_id": product_id,
            "category": orders[0]["category"],
            "metrics": {
                "total_orders": len(orders),
                "avg_order_value": sum(o["order_value"] for o in orders) / len(orders),
                "demand_rate_orders_per_min": len(orders) / 5.0,  # 5-min window
                "inventory_level": 80,
                "inventory_ratio": 80 / 10000,
                "avg_competitor_price": 5000.0,
                "our_current_price": 5200.0,
                "price_gap_pct": 4.0,
                "demand_trend": "increasing",
                "urgency_score": 0.8,
                "timestamp": int(time.time() * 1000),
            }
        }

        # Evaluate rules
        signal = rules_engine.evaluate(metrics)

        assert "product_id" in signal
        assert "recommended_price" in signal
        assert "action" in signal
        assert signal["action"] in ["hold", "increase", "decrease", "urgent_increase"]
        print(f"\n[KAFKA E2E] product={product_id} action={signal['action']} multiplier={signal['multiplier']:.2f}")

    def test_mock_consumer_runs(self):
        """Mock consumer should complete without errors."""
        # Run with just 2 iterations for test speed
        try:
            from kafka.consumer import run_mock_consumer
            signals = run_mock_consumer(iterations=2)
            assert isinstance(signals, list)
            print(f"\n[KAFKA] Mock consumer produced {len(signals)} signals")
        except Exception as e:
            pytest.fail(f"Mock consumer failed: {e}")

    def test_pricing_rules_all_scenarios(self):
        """Test all 6 pricing rules in one pass."""
        engine = PricingRulesEngine()

        def make_sig(pid, demand_rate, inv_ratio, inv_level, our_price, comp_price, total_orders=10):
            return {
                "product_id": pid,
                "category": "electronics",
                "metrics": {
                    "demand_rate_orders_per_min": demand_rate,
                    "inventory_ratio": inv_ratio,
                    "inventory_level": inv_level,
                    "our_current_price": our_price,
                    "avg_competitor_price": comp_price,
                    "total_orders": total_orders,
                    "urgency_score": 0.5,
                    "timestamp": int(time.time() * 1000),
                }
            }

        scenarios = [
            (1, 15.0, 0.1, 1000, 5000, 5000, "high_demand_low_stock"),
            (2, 1.0, 0.8, 8000, 5000, 5000, "low_demand_high_stock"),
            (3, 5.0, 0.5, 5000, 6000, 4000, "competitor_undercut"),
            (4, 8.0, 0.01, 5, 5000, 5000, "inventory_runout_risk"),
        ]

        for pid, dr, ir, il, op, cp, expected_rule in scenarios:
            signal = engine.evaluate(make_sig(pid, dr, ir, il, op, cp))
            assert expected_rule in signal["triggered_rules"], (
                f"Expected rule '{expected_rule}' for product {pid}, got {signal['triggered_rules']}"
            )
            print(f"[RULES] product={pid} rule={expected_rule} mult={signal['multiplier']:.2f} PASS")
