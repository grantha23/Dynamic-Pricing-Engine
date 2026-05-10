"""
dashboard/utils.py — Shared utilities for the Dynamic Pricing Dashboard
"""

import os
import json
import time
import logging
import random
import functools
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List, Any, Callable

import pandas as pd
import numpy as np
import requests

logger = logging.getLogger(__name__)

API_BASE_URL = os.environ.get("PRICING_API_URL", "http://localhost:8000")
REQUEST_TIMEOUT = 0.5  # seconds — local API, instant mock fallback if unavailable

CATEGORIES = ["electronics", "apparel", "home", "books", "food"]
SEGMENTS = ["premium", "regular", "budget"]
SEASONS = ["spring", "summer", "monsoon", "winter"]
COMPETITORS = ["Competitor_A", "Competitor_B", "Competitor_C"]

# ── Currency / Number Formatting ───────────────────────────────────────────────

def format_currency(value: float) -> str:
    """Format as Indian rupees: ₹1,23,456.78"""
    if abs(value) >= 1e7:
        return f"₹{value/1e7:.2f}Cr"
    if abs(value) >= 1e5:
        return f"₹{value/1e5:.2f}L"
    return f"₹{value:,.2f}"


def format_percentage(value: float, decimals: int = 2) -> str:
    """Format as percentage with sign: +3.25%"""
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.{decimals}f}%"


def get_color_by_change(change_pct: float) -> str:
    """Return color string based on price change direction."""
    if change_pct > 0.5:
        return "green"
    elif change_pct < -0.5:
        return "red"
    return "orange"


# ── API Calls ──────────────────────────────────────────────────────────────────

def _api_get(endpoint: str, params: Optional[Dict] = None) -> Optional[Dict]:
    try:
        resp = requests.get(f"{API_BASE_URL}{endpoint}", params=params, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None


def _api_post(endpoint: str, payload: Dict) -> Optional[Dict]:
    try:
        resp = requests.post(
            f"{API_BASE_URL}{endpoint}",
            json=payload,
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None


def check_api_health() -> Dict[str, Any]:
    data = _api_get("/health")
    if data:
        return data
    return {"status": "unhealthy", "model_loaded": False, "predictions_served": 0, "uptime_seconds": 0, "model_accuracy_mae": 0, "model_version": "N/A", "last_update": "N/A"}


def fetch_model_metrics() -> Dict[str, Any]:
    data = _api_get("/model-metrics")
    if data:
        return data
    # Fallback mock
    return {
        "model_version": "xgboost_v1.0",
        "training_date": datetime.now().isoformat(),
        "mae": 120.68, "rmse": 252.71, "r2": 0.9995, "mape": 2.43,
        "top_10_features": {"competitor_price": 0.50, "base_price": 0.36, "competitor_elasticity": 0.12},
        "total_predictions_served": 0,
    }


def apply_price_change(product_id: int, base_price: float, multiplier: float, reason: str) -> Optional[Dict]:
    """Submit a manual price adjustment to the API."""
    payload = {"product_id": product_id, "base_price": base_price, "multiplier": multiplier, "reason": reason}
    return _api_post("/price-adjustment", payload)


def log_action(action_type: str, details: str):
    """Log user actions to a local file for audit trail."""
    log_path = os.path.join(os.path.dirname(__file__), "logs", "audit.log")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    ts = datetime.now(timezone.utc).isoformat()
    with open(log_path, "a") as f:
        f.write(f"{ts} | {action_type} | {details}\n")


# ── Synthetic Data Generators (used when API is unavailable) ──────────────────

def generate_mock_products(n: int = 200, seed: int = 42) -> pd.DataFrame:
    """Generate synthetic product recommendations for demo/testing."""
    rng = np.random.default_rng(seed)
    product_ids = rng.integers(1, 50001, size=n)
    categories = rng.choice(CATEGORIES, size=n, p=[0.25, 0.30, 0.20, 0.15, 0.10])
    base_prices = np.array([
        rng.uniform(
            {"electronics": 2000, "apparel": 200, "home": 500, "books": 100, "food": 50}[c],
            {"electronics": 50000, "apparel": 5000, "home": 15000, "books": 2000, "food": 2000}[c],
        )
        for c in categories
    ])
    demand = rng.exponential(100, size=n).clip(0, 1000)
    inventory = rng.integers(0, 10001, size=n)
    competitor_price = base_prices * rng.uniform(0.85, 1.15, size=n)
    demand_ratio = demand / 1000.0
    inventory_ratio = inventory / 10000.0
    price_change_pct = rng.uniform(-20, 25, size=n)
    recommended_price = base_prices * (1 + price_change_pct / 100)
    recommended_price = recommended_price.clip(base_prices * 0.5, base_prices * 2.5)
    confidence = rng.uniform(0.80, 0.99, size=n)
    segment = rng.choice(SEGMENTS, size=n)

    df = pd.DataFrame({
        "product_id":        product_ids,
        "category":          categories,
        "customer_segment":  segment,
        "base_price":        base_prices.round(2),
        "current_price":     base_prices.round(2),
        "recommended_price": recommended_price.round(2),
        "price_change_pct":  price_change_pct.round(2),
        "demand":            demand.round(1),
        "inventory":         inventory,
        "demand_ratio":      demand_ratio.round(4),
        "inventory_ratio":   inventory_ratio.round(4),
        "competitor_price":  competitor_price.round(2),
        "confidence_score":  confidence.round(4),
    })
    df["action"] = "Hold"
    return df


def generate_mock_monitoring_data(seed: int = 42) -> Dict[str, Any]:
    """Generate realistic monitoring KPIs and event log — deterministic with seed."""
    rng = np.random.default_rng(seed)
    now = datetime.now()
    kpis = {
        "total_active_skus":       int(rng.integers(45000, 52000)),
        "daily_revenue_impact":    float(rng.uniform(5e5, 2e6)),
        "stockout_prevention_pct": float(rng.uniform(78, 95)),
        "avg_update_latency_ms":   float(rng.uniform(80, 450)),
        "model_mae":               1.28,
    }

    reasons = [
        "High demand surge", "Low inventory alert", "Competitor undercut",
        "Flash sale detected", "Slow-moving SKU", "Premium segment boost",
    ]
    events = []
    for i in range(50):
        ts = now - timedelta(minutes=i * 3)
        base   = float(rng.uniform(500, 20000))
        change = float(rng.uniform(-0.20, 0.25))
        new_price = base * (1 + change)
        events.append({
            "timestamp":      ts.strftime("%H:%M:%S"),
            "product_id":     int(rng.integers(1, 50000)),
            "category":       CATEGORIES[int(rng.integers(0, len(CATEGORIES)))],
            "action":         "Increase" if change > 0.005 else ("Decrease" if change < -0.005 else "Hold"),
            "prev_price":     round(base, 2),
            "new_price":      round(new_price, 2),
            "change_pct":     round(change * 100, 2),
            "reason":         reasons[int(rng.integers(0, len(reasons)))],
            "revenue_impact": round(float(rng.uniform(-500, 2000)), 2),
        })

    rev_trend = []
    for h in range(24):
        rev_trend.append({
            "hour":        (now - timedelta(hours=23 - h)).strftime("%H:00"),
            "electronics": round(float(rng.uniform(10000, 100000)), 2),
            "apparel":     round(float(rng.uniform(5000, 50000)), 2),
            "home":        round(float(rng.uniform(3000, 30000)), 2),
            "books":       round(float(rng.uniform(1000, 10000)), 2),
            "food":        round(float(rng.uniform(2000, 20000)), 2),
        })

    return {"kpis": kpis, "events": events, "revenue_trend": rev_trend}


def generate_competitor_data(n_products: int = 100) -> pd.DataFrame:
    """Generate competitor price comparison data."""
    rng = np.random.default_rng(0)
    product_ids = rng.integers(1, 50001, size=n_products)
    categories = rng.choice(CATEGORIES, size=n_products, p=[0.25, 0.30, 0.20, 0.15, 0.10])
    our_prices = rng.uniform(500, 30000, size=n_products).round(2)

    rows = []
    for i, (pid, cat, our_p) in enumerate(zip(product_ids, categories, our_prices)):
        comp_a = our_p * rng.uniform(0.80, 1.20)
        comp_b = our_p * rng.uniform(0.75, 1.25)
        avg_comp = (comp_a + comp_b) / 2
        gap_pct = (our_p - avg_comp) / avg_comp * 100
        position = "cheaper" if gap_pct < -5 else ("expensive" if gap_pct > 5 else "matched")
        rows.append({
            "product_id":       pid,
            "category":         cat,
            "our_price":        round(our_p, 2),
            "competitor_a":     round(comp_a, 2),
            "competitor_b":     round(comp_b, 2),
            "avg_competitor":   round(avg_comp, 2),
            "gap_pct_a":        round((our_p - comp_a) / comp_a * 100, 2),
            "gap_pct_b":        round((our_p - comp_b) / comp_b * 100, 2),
            "avg_gap_pct":      round(gap_pct, 2),
            "position":         position,
            "action":           "Undercut" if gap_pct > 15 else ("Match" if gap_pct > 5 else "Premium"),
        })
    return pd.DataFrame(rows)


def generate_revenue_data(days: int = 7, seed: int = 42) -> pd.DataFrame:
    """Generate revenue analytics data — deterministic with seed."""
    rng = np.random.default_rng(seed)
    rows = []
    for d in range(days):
        date = (datetime.now() - timedelta(days=days - 1 - d)).strftime("%Y-%m-%d")
        for cat in CATEGORIES:
            for seg in SEGMENTS:
                base_rev = float(rng.uniform(50000, 500000))
                baseline = base_rev * float(rng.uniform(0.85, 0.95))
                units    = int(rng.integers(50, 500))
                rows.append({
                    "date":          date,
                    "category":      cat,
                    "segment":       seg,
                    "revenue":       round(base_rev, 2),
                    "baseline":      round(baseline, 2),
                    "revenue_lift":  round((base_rev - baseline) / baseline * 100, 2),
                    "units_sold":    units,
                    "avg_order_val": round(base_rev / units, 2),
                })
    return pd.DataFrame(rows)


# ── Cache decorator ─────────────────────────────────────────────────────────────

_cache_store: Dict[str, tuple] = {}

def cache_data(ttl_seconds: int = 60):
    """Simple TTL-based cache decorator for dashboard data fetchers."""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            key = f"{func.__name__}:{args}:{kwargs}"
            if key in _cache_store:
                result, ts = _cache_store[key]
                if time.time() - ts < ttl_seconds:
                    return result
            result = func(*args, **kwargs)
            _cache_store[key] = (result, time.time())
            return result
        return wrapper
    return decorator


@cache_data(ttl_seconds=60)
def fetch_recommendations(n: int = 200) -> pd.DataFrame:
    """Fetch price recommendations (from API or synthetic data)."""
    health = check_api_health()
    if health.get("model_loaded"):
        # Try to get real predictions from API for a sample
        pass  # In production, you'd call batch-predict here
    return generate_mock_products(n)


@cache_data(ttl_seconds=600)
def fetch_monitoring_data() -> Dict[str, Any]:
    health = check_api_health()
    data = generate_mock_monitoring_data(seed=42)
    if health.get("model_loaded"):
        data["kpis"]["predictions_served"] = health.get("predictions_served", 0)
        data["kpis"]["uptime_seconds"] = health.get("uptime_seconds", 0)
    return data


@cache_data(ttl_seconds=60)
def fetch_competitor_prices() -> pd.DataFrame:
    return generate_competitor_data()


@cache_data(ttl_seconds=600)
def fetch_revenue_data(days: int = 7) -> pd.DataFrame:
    return generate_revenue_data(days, seed=42)
