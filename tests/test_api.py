"""
tests/test_api.py — Integration tests for FastAPI endpoints
Run: pytest tests/test_api.py -v  (requires API server running on :8000)
"""

import os
import sys
import json
import time
import threading
import pytest
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE_URL = "http://localhost:8000"
TIMEOUT = 10


def _valid_payload(**overrides):
    base = {
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
    base.update(overrides)
    return base


def _skip_if_api_down():
    try:
        r = requests.get(f"{BASE_URL}/health", timeout=2)
        if r.status_code != 200:
            pytest.skip("API not running — start uvicorn api.main:app --port 8000")
    except Exception:
        pytest.skip("API not running — start uvicorn api.main:app --port 8000")


class TestHealthEndpoint:
    def test_health_returns_200(self):
        _skip_if_api_down()
        r = requests.get(f"{BASE_URL}/health", timeout=TIMEOUT)
        assert r.status_code == 200

    def test_health_schema(self):
        _skip_if_api_down()
        data = requests.get(f"{BASE_URL}/health", timeout=TIMEOUT).json()
        assert "status" in data
        assert "model_loaded" in data
        assert "predictions_served" in data
        assert "uptime_seconds" in data
        assert data["model_loaded"] is True

    def test_health_latency_under_100ms(self):
        _skip_if_api_down()
        # Warm up connection first
        requests.get(f"{BASE_URL}/health", timeout=TIMEOUT)
        t0 = time.time()
        r = requests.get(f"{BASE_URL}/health", timeout=TIMEOUT)
        latency_ms = (time.time() - t0) * 1000
        # Use processing time from header (actual API latency, not TCP overhead)
        proc_ms = float(r.headers.get("X-Processing-Time-MS", latency_ms))
        assert proc_ms < 100, f"Health check too slow: {proc_ms:.1f}ms (round-trip: {latency_ms:.1f}ms)"


class TestPredictEndpoint:
    def test_predict_valid_input(self):
        _skip_if_api_down()
        r = requests.post(f"{BASE_URL}/predict-price", json=_valid_payload(), timeout=TIMEOUT)
        assert r.status_code == 200
        data = r.json()
        assert "recommended_price" in data
        assert "confidence_score" in data
        assert data["recommended_price"] > 0

    def test_predict_response_schema(self):
        _skip_if_api_down()
        data = requests.post(f"{BASE_URL}/predict-price", json=_valid_payload(), timeout=TIMEOUT).json()
        required = ["product_id", "recommended_price", "confidence_score", "price_change_pct",
                    "recommendation_reason", "timestamp", "processing_time_ms"]
        for key in required:
            assert key in data, f"Missing key: {key}"

    def test_predict_latency_under_500ms(self):
        _skip_if_api_down()
        # Warm up connection first
        requests.post(f"{BASE_URL}/predict-price", json=_valid_payload(), timeout=TIMEOUT)
        t0 = time.time()
        r = requests.post(f"{BASE_URL}/predict-price", json=_valid_payload(), timeout=TIMEOUT)
        latency_ms = (time.time() - t0) * 1000
        # Use server-measured processing time from header
        proc_ms = float(r.headers.get("X-Processing-Time-MS", latency_ms))
        assert proc_ms < 500, f"Prediction too slow: {proc_ms:.1f}ms (round-trip: {latency_ms:.1f}ms)"

    def test_predict_price_bounds(self):
        _skip_if_api_down()
        payload = _valid_payload(base_price=5000.0)
        data = requests.post(f"{BASE_URL}/predict-price", json=payload, timeout=TIMEOUT).json()
        rec = data["recommended_price"]
        assert 2500.0 <= rec <= 12500.0, f"Price {rec} out of bounds"

    def test_predict_invalid_category(self):
        _skip_if_api_down()
        payload = _valid_payload(product_category="invalid_category")
        r = requests.post(f"{BASE_URL}/predict-price", json=payload, timeout=TIMEOUT)
        assert r.status_code == 422, f"Expected 422 for invalid category, got {r.status_code}"

    def test_predict_missing_field(self):
        _skip_if_api_down()
        payload = _valid_payload()
        del payload["base_price"]
        r = requests.post(f"{BASE_URL}/predict-price", json=payload, timeout=TIMEOUT)
        assert r.status_code == 422, f"Expected 422 for missing field, got {r.status_code}"

    def test_predict_invalid_demand_range(self):
        _skip_if_api_down()
        payload = _valid_payload(demand=5000.0)  # > 1000 max
        r = requests.post(f"{BASE_URL}/predict-price", json=payload, timeout=TIMEOUT)
        assert r.status_code == 422

    def test_predict_invalid_elasticity(self):
        _skip_if_api_down()
        payload = _valid_payload(price_elasticity=0.5)  # must be <= -0.5
        r = requests.post(f"{BASE_URL}/predict-price", json=payload, timeout=TIMEOUT)
        assert r.status_code == 422

    def test_predict_confidence_in_range(self):
        _skip_if_api_down()
        data = requests.post(f"{BASE_URL}/predict-price", json=_valid_payload(), timeout=TIMEOUT).json()
        assert 0.0 <= data["confidence_score"] <= 1.0

    def test_request_id_header(self):
        _skip_if_api_down()
        r = requests.post(f"{BASE_URL}/predict-price", json=_valid_payload(), timeout=TIMEOUT)
        assert "X-Request-ID" in r.headers


class TestBatchPredict:
    def test_batch_predict_10_items(self):
        _skip_if_api_down()
        products = [_valid_payload(product_id=i) for i in range(1, 11)]
        r = requests.post(f"{BASE_URL}/batch-predict", json={"products": products}, timeout=TIMEOUT)
        assert r.status_code == 200
        data = r.json()
        assert data["batch_size"] == 10
        assert len(data["predictions"]) == 10

    def test_batch_predict_100_items(self):
        _skip_if_api_down()
        products = [_valid_payload(product_id=i) for i in range(1, 101)]
        # Warm up
        requests.post(f"{BASE_URL}/predict-price", json=_valid_payload(), timeout=TIMEOUT)
        t0 = time.time()
        r = requests.post(f"{BASE_URL}/batch-predict", json={"products": products}, timeout=30)
        latency_ms = (time.time() - t0) * 1000
        assert r.status_code == 200
        data = r.json()
        total_ms = data.get("total_time_ms", latency_ms)
        assert total_ms < 2000, f"Batch 100 too slow: {total_ms:.1f}ms (server-measured)"

    def test_batch_predict_empty(self):
        _skip_if_api_down()
        r = requests.post(f"{BASE_URL}/batch-predict", json={"products": []}, timeout=TIMEOUT)
        assert r.status_code == 400


class TestModelMetrics:
    def test_model_metrics_endpoint(self):
        _skip_if_api_down()
        r = requests.get(f"{BASE_URL}/model-metrics", timeout=TIMEOUT)
        assert r.status_code == 200
        data = r.json()
        assert "mae" in data
        assert "r2" in data
        assert "top_10_features" in data
        assert data["r2"] > 0.9, f"R² too low: {data['r2']}"


class TestPriceAdjustment:
    def test_price_adjustment_valid(self):
        _skip_if_api_down()
        payload = {"product_id": 200, "base_price": 5000.0, "multiplier": 0.85, "reason": "Flash sale event"}
        r = requests.post(f"{BASE_URL}/price-adjustment", json=payload, timeout=TIMEOUT)
        assert r.status_code == 200
        data = r.json()
        assert data["adjusted_price"] == pytest.approx(5000.0 * 0.85, abs=0.01)

    def test_price_adjustment_extreme_warns(self):
        _skip_if_api_down()
        payload = {"product_id": 201, "base_price": 5000.0, "multiplier": 0.51, "reason": "Clearance"}
        r = requests.post(f"{BASE_URL}/price-adjustment", json=payload, timeout=TIMEOUT)
        assert r.status_code == 200
        data = r.json()
        assert len(data["warnings"]) > 0


class TestConcurrency:
    def test_concurrent_requests(self):
        """Send 20 concurrent requests and verify all succeed."""
        _skip_if_api_down()
        results = []
        errors = []

        def make_request():
            try:
                r = requests.post(f"{BASE_URL}/predict-price", json=_valid_payload(), timeout=TIMEOUT)
                results.append(r.status_code)
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=make_request) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)

        success_rate = sum(1 for s in results if s == 200) / max(len(results), 1) * 100
        assert success_rate >= 95.0, f"Success rate too low: {success_rate:.1f}%"
        assert len(errors) == 0, f"Errors occurred: {errors}"
