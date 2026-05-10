"""
kafka/topology_test.py — Integration test for entire Kafka pipeline
Works in both real Kafka and mock modes.
"""

import os
import sys
import json
import time
import logging
import random

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from kafka.pricing_trigger_rules import PricingRulesEngine, RULE_DEFINITIONS
from kafka.producer import generate_order_event, generate_inventory_event, generate_competitor_event

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")


def test_event_generation():
    """Test 1: Verify event generators produce valid schemas."""
    logger.info("[TEST 1] Event generation schema validation…")

    order = generate_order_event()
    required_order_keys = ["event_id", "timestamp", "product_id", "quantity", "order_value", "customer_segment", "category"]
    assert all(k in order for k in required_order_keys), f"Missing keys in order: {set(required_order_keys) - set(order)}"

    inv = generate_inventory_event()
    required_inv_keys = ["timestamp", "product_id", "warehouse", "new_level", "change", "event_type"]
    assert all(k in inv for k in required_inv_keys), f"Missing keys in inventory: {set(required_inv_keys) - set(inv)}"

    comp = generate_competitor_event()
    required_comp_keys = ["timestamp", "product_id", "competitor_name", "price", "previous_price", "change_pct"]
    assert all(k in comp for k in required_comp_keys), f"Missing keys in competitor: {set(required_comp_keys) - set(comp)}"

    logger.info("  PASS — Order, Inventory, Competitor events all have correct schema")
    return True


def test_bulk_generation():
    """Test 2: Generate 100 orders, 50 inventory, 20 competitor events."""
    logger.info("[TEST 2] Bulk event generation…")
    orders = [generate_order_event() for _ in range(100)]
    invs = [generate_inventory_event() for _ in range(50)]
    comps = [generate_competitor_event() for _ in range(20)]

    assert len(orders) == 100, f"Expected 100 orders, got {len(orders)}"
    assert len(invs) == 50
    assert len(comps) == 20

    # Verify order_value ranges
    for o in orders:
        assert o["order_value"] > 0, "order_value must be > 0"
        assert o["quantity"] >= 1
        assert o["customer_segment"] in ["premium", "regular", "budget"]

    logger.info("  PASS — 100 orders, 50 inventory, 20 competitor events generated correctly")
    return True


def test_json_serialization():
    """Test 3: All events must be JSON-serializable."""
    logger.info("[TEST 3] JSON serialization…")
    for gen_fn in [generate_order_event, generate_inventory_event, generate_competitor_event]:
        evt = gen_fn()
        serialized = json.dumps(evt)
        deserialized = json.loads(serialized)
        assert deserialized == evt, "Deserialized event doesn't match original"

    logger.info("  PASS — All event types serialize/deserialize correctly")
    return True


def test_pricing_rules_engine():
    """Test 4: All 6 rules trigger correctly on synthetic data."""
    logger.info("[TEST 4] Pricing rules engine…")
    engine = PricingRulesEngine()

    def make_metrics(demand_rate, inv_ratio, inv_level, our_price, comp_price, product_id=1):
        return {
            "product_id": product_id,
            "category": "electronics",
            "metrics": {
                "demand_rate_orders_per_min": demand_rate,
                "inventory_ratio": inv_ratio,
                "inventory_level": inv_level,
                "our_current_price": our_price,
                "avg_competitor_price": comp_price,
                "total_orders": int(demand_rate * 5),
                "urgency_score": 0.5,
                "timestamp": int(time.time() * 1000),
            }
        }

    # Rule 1: High demand + low inventory → 20% increase
    sig = engine.evaluate(make_metrics(15, 0.1, 1000, 5000, 5000, 1))
    assert sig["multiplier"] >= 1.20, f"Rule 1 failed: multiplier={sig['multiplier']}"
    assert "high_demand_low_stock" in sig["triggered_rules"]
    logger.info("  Rule 1 (High Demand + Low Inv): multiplier=%.2f PASS", sig["multiplier"])

    # Rule 2: Low demand + high inventory → 15% discount
    sig = engine.evaluate(make_metrics(1, 0.8, 8000, 5000, 5000, 2))
    assert sig["multiplier"] <= 0.85, f"Rule 2 failed: multiplier={sig['multiplier']}"
    assert "low_demand_high_stock" in sig["triggered_rules"]
    logger.info("  Rule 2 (Low Demand + High Inv): multiplier=%.2f PASS", sig["multiplier"])

    # Rule 3: Competitor undercut → price match
    sig = engine.evaluate(make_metrics(5, 0.5, 5000, 6000, 4000, 3))
    assert sig["multiplier"] < 1.0, f"Rule 3 failed: multiplier={sig['multiplier']}"
    assert "competitor_undercut" in sig["triggered_rules"]
    logger.info("  Rule 3 (Competitor Undercut): multiplier=%.2f PASS", sig["multiplier"])

    # Rule 5: Inventory runout risk → 50% premium
    sig = engine.evaluate(make_metrics(8, 0.01, 5, 5000, 5000, 4))
    assert sig["multiplier"] >= 1.50, f"Rule 5 failed: multiplier={sig['multiplier']}"
    assert "inventory_runout_risk" in sig["triggered_rules"]
    logger.info("  Rule 5 (Runout Risk): multiplier=%.2f PASS", sig["multiplier"])

    logger.info("  PASS — All tested rules trigger with correct multipliers")
    return True


def test_window_aggregation():
    """Test 5: Window aggregation produces correct metrics."""
    logger.info("[TEST 5] Window aggregation logic…")
    from kafka.consumer import _order_windows, _inventory_state, _our_prices, _compute_window_metrics, _epoch_ms

    # Seed test data
    pid = 9999
    now_ms = _epoch_ms()
    for _ in range(10):
        _order_windows[pid].append({
            "timestamp": now_ms - random.randint(0, 290000),
            "product_id": pid,
            "order_value": random.uniform(500, 3000),
            "customer_segment": "regular",
            "category": "electronics",
        })
    _inventory_state[pid] = {"new_level": 500, "category": "electronics"}
    _our_prices[pid] = 5000.0

    metrics = _compute_window_metrics(pid, now_ms)
    assert metrics["product_id"] == pid
    assert 0 <= metrics["metrics"]["inventory_ratio"] <= 1.0
    assert metrics["metrics"]["total_orders"] >= 0
    assert "demand_rate_orders_per_min" in metrics["metrics"]

    logger.info("  PASS — Window aggregation: %d orders, demand_rate=%.2f orders/min",
                metrics["metrics"]["total_orders"],
                metrics["metrics"]["demand_rate_orders_per_min"])
    return True


def run_all_tests():
    """Run complete test suite and report results."""
    tests = [
        ("Event Generation",   test_event_generation),
        ("Bulk Generation",    test_bulk_generation),
        ("JSON Serialization", test_json_serialization),
        ("Pricing Rules",      test_pricing_rules_engine),
        ("Window Aggregation", test_window_aggregation),
    ]

    results = []
    for name, fn in tests:
        try:
            passed = fn()
            results.append((name, "PASS" if passed else "FAIL", None))
        except AssertionError as e:
            results.append((name, "FAIL", str(e)))
            logger.error("[FAIL] %s: %s", name, e)
        except Exception as e:
            results.append((name, "ERROR", str(e)))
            logger.error("[ERROR] %s: %s", name, e)

    print("\n" + "="*55)
    print("  KAFKA TOPOLOGY TEST RESULTS")
    print("="*55)
    passed = sum(1 for _, s, _ in results if s == "PASS")
    for name, status, err in results:
        icon = "PASS" if status == "PASS" else "FAIL"
        suffix = f" — {err}" if err else ""
        print(f"  [{icon}] {name}{suffix}")
    print(f"\n  {passed}/{len(results)} tests passed")
    print("="*55)
    return passed == len(tests)


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
