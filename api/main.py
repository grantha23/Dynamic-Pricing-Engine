"""
api/main.py — FastAPI application for the Dynamic Pricing Engine
Run: uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
"""

import os
import sys
import time
import uuid
import logging
from datetime import datetime, timezone
from collections import defaultdict
from typing import Dict, List, Any, Optional

# Add project root to sys.path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

from fastapi import FastAPI, HTTPException, Request, Response, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.models import (
    PricePredictionRequest, PricePredictionResponse,
    HealthCheckResponse, BatchPredictionRequest, BatchPredictionResponse,
    ModelMetricsResponse, PriceAdjustmentRequest, PriceAdjustmentResponse,
    PricingHistoryRequest, PricingHistoryResponse, PricingHistoryItem,
)
from api.ml_service import PricingMLService, prepare_features, apply_business_logic, get_recommendation_reason

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("pricing.api")

# ─── App ──────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Dynamic Pricing Engine API",
    description="Real-time XGBoost-powered price optimization for e-commerce",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8501", "http://127.0.0.1:8501", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── State ────────────────────────────────────────────────────────────────────
class AppState:
    ml_service: Optional[PricingMLService] = None
    start_time: float = time.time()
    predictions_served: int = 0
    latency_samples: List[float] = []
    error_count: int = 0
    # In-memory history store: {product_id: [PricingHistoryItem, ...]}
    pricing_history: Dict[int, List[Dict]] = defaultdict(list)
    # Manual adjustment overrides: {product_id: adjusted_price}
    manual_adjustments: Dict[int, float] = {}

state = AppState()

# ─── Simple in-memory rate limiting ───────────────────────────────────────────
_rate_limit_store: Dict[str, List[float]] = defaultdict(list)
RATE_LIMIT_REQUESTS = 1000
RATE_LIMIT_WINDOW = 60  # seconds

def check_rate_limit(ip: str) -> bool:
    now = time.time()
    window_start = now - RATE_LIMIT_WINDOW
    # Clean old entries
    _rate_limit_store[ip] = [t for t in _rate_limit_store[ip] if t > window_start]
    if len(_rate_limit_store[ip]) >= RATE_LIMIT_REQUESTS:
        return False
    _rate_limit_store[ip].append(now)
    return True

# ─── Simple in-memory cache ───────────────────────────────────────────────────
_prediction_cache: Dict[str, tuple] = {}  # key → (price_response, timestamp)
CACHE_TTL = 60  # seconds

def _cache_key(req: PricePredictionRequest) -> str:
    return f"{req.product_id}|{req.product_category}|{req.base_price}|{req.demand}|{req.inventory}|{req.competitor_price}"

def _get_cached(key: str) -> Optional[PricePredictionResponse]:
    if key in _prediction_cache:
        resp, ts = _prediction_cache[key]
        if time.time() - ts < CACHE_TTL:
            return resp
        del _prediction_cache[key]
    return None

def _set_cached(key: str, resp: PricePredictionResponse):
    _prediction_cache[key] = (resp, time.time())

# ─── Middleware ───────────────────────────────────────────────────────────────
@app.middleware("http")
async def request_middleware(request: Request, call_next):
    request_id = str(uuid.uuid4())[:8]
    request.state.request_id = request_id
    start = time.time()

    response: Response = await call_next(request)

    latency_ms = (time.time() - start) * 1000
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Processing-Time-MS"] = f"{latency_ms:.1f}"

    logger.info(
        "%s %s | %d | %.1fms | req=%s",
        request.method, request.url.path,
        response.status_code, latency_ms, request_id,
    )
    return response

# ─── Startup / Shutdown ───────────────────────────────────────────────────────
@app.on_event("startup")
async def startup_event():
    logger.info("Loading ML model artifacts…")
    models_dir = os.path.join(ROOT_DIR, "models")
    try:
        state.ml_service = PricingMLService(
            model_path=os.path.join(models_dir, "xgboost_pricing_model.pkl"),
            scaler_path=os.path.join(models_dir, "scaler.pkl"),
            metadata_path=os.path.join(models_dir, "model_metadata.json"),
            feature_path=os.path.join(models_dir, "feature_names.json"),
        )
        logger.info("Model loaded successfully — version: %s", state.ml_service.get_model_version())
    except Exception as e:
        logger.error("STARTUP FAILED: %s", e)
        # Don't crash; health endpoint will report degraded

@app.on_event("shutdown")
async def shutdown_event():
    logger.info(
        "Shutdown | predictions_served=%d | errors=%d",
        state.predictions_served, state.error_count,
    )

# ─── Helper ───────────────────────────────────────────────────────────────────
def _ensure_model_loaded():
    if state.ml_service is None or not state.ml_service.is_healthy():
        raise HTTPException(
            status_code=503,
            detail={"error": "Model not ready", "code": "MODEL_NOT_READY"},
        )

def _build_prediction_response(
    req: PricePredictionRequest,
    recommended_price: float,
    processing_ms: float,
    request_id: Optional[str] = None,
) -> PricePredictionResponse:
    price_change_pct = (recommended_price - req.base_price) / (req.base_price + 1e-9) * 100
    reason = get_recommendation_reason(
        req.base_price, recommended_price, req.inventory, req.demand, req.competitor_price
    )
    return PricePredictionResponse(
        product_id=req.product_id,
        recommended_price=round(recommended_price, 2),
        confidence_score=state.ml_service.calculate_confidence(),
        price_change_pct=round(price_change_pct, 2),
        recommendation_reason=reason,
        timestamp=datetime.now(timezone.utc).isoformat(),
        processing_time_ms=round(processing_ms, 2),
        request_id=request_id,
    )

# ─── Endpoints ────────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthCheckResponse, tags=["System"])
async def health_check(request: Request):
    """Health check — returns model status, uptime, and basic metrics."""
    loaded = state.ml_service is not None and state.ml_service.is_healthy()
    status = "healthy" if loaded else "degraded"
    mae = state.ml_service.get_mae() if loaded else 0.0
    version = state.ml_service.get_model_version() if loaded else "unknown"
    training_date = state.ml_service.get_training_date() if loaded else "unknown"

    return HealthCheckResponse(
        status=status,
        model_loaded=loaded,
        last_update=training_date,
        predictions_served=state.predictions_served,
        uptime_seconds=round(time.time() - state.start_time, 2),
        model_accuracy_mae=mae,
        model_version=version,
    )


@app.post("/predict-price", response_model=PricePredictionResponse, tags=["Pricing"])
async def predict_price(req: PricePredictionRequest, request: Request):
    """
    Predict optimal price for a single product.
    Returns recommended price, confidence, change %, and reasoning.
    Target latency: < 500ms p95.
    """
    _ensure_model_loaded()
    request_id = getattr(request.state, "request_id", None)

    # Rate limit check
    client_ip = request.client.host if request.client else "unknown"
    if not check_rate_limit(client_ip):
        raise HTTPException(
            status_code=429,
            detail={"error": "Rate limit exceeded", "code": "RATE_LIMIT"},
            headers={"Retry-After": "60"},
        )

    # Check cache
    cache_key = _cache_key(req)
    cached = _get_cached(cache_key)
    if cached:
        return cached

    t0 = time.time()
    try:
        features = prepare_features(req, req.base_price)
        raw_price = state.ml_service.predict(features)
        recommended_price = apply_business_logic(
            raw_price, req.base_price, req.inventory, req.demand,
            req.competitor_price, req.price_elasticity,
        )
        processing_ms = (time.time() - t0) * 1000
        resp = _build_prediction_response(req, recommended_price, processing_ms, request_id)

        # Store in history
        state.pricing_history[req.product_id].append({
            "timestamp": resp.timestamp,
            "product_id": req.product_id,
            "event_type": "ml_prediction",
            "price": resp.recommended_price,
            "change_pct": resp.price_change_pct,
            "reason": resp.recommendation_reason,
        })

        state.predictions_served += 1
        state.latency_samples.append(processing_ms)
        if len(state.latency_samples) > 10000:
            state.latency_samples = state.latency_samples[-5000:]

        _set_cached(cache_key, resp)
        return resp

    except HTTPException:
        raise
    except Exception as e:
        state.error_count += 1
        logger.exception("Prediction failed for product_id=%d: %s", req.product_id, e)
        raise HTTPException(status_code=500, detail={"error": str(e), "code": "INTERNAL_ERROR"})


@app.post("/batch-predict", response_model=BatchPredictionResponse, tags=["Pricing"])
async def batch_predict(batch_req: BatchPredictionRequest, request: Request):
    """
    Batch price prediction for up to 1000 products.
    Vectorized processing — target < 2000ms for 1000 items.
    """
    _ensure_model_loaded()
    if not batch_req.products:
        raise HTTPException(status_code=400, detail={"error": "products list is empty", "code": "VALIDATION_ERROR"})

    t0 = time.time()
    try:
        features_list = [prepare_features(r, r.base_price) for r in batch_req.products]
        raw_prices = state.ml_service.predict_batch(features_list)

        responses = []
        for req, raw_price in zip(batch_req.products, raw_prices):
            recommended = apply_business_logic(
                raw_price, req.base_price, req.inventory, req.demand,
                req.competitor_price, req.price_elasticity,
            )
            resp = _build_prediction_response(req, recommended, 0.0)
            responses.append(resp)

        total_ms = (time.time() - t0) * 1000
        state.predictions_served += len(responses)
        return BatchPredictionResponse(
            predictions=responses,
            total_time_ms=round(total_ms, 2),
            batch_size=len(responses),
        )
    except HTTPException:
        raise
    except Exception as e:
        state.error_count += 1
        logger.exception("Batch prediction failed: %s", e)
        raise HTTPException(status_code=500, detail={"error": str(e), "code": "INTERNAL_ERROR"})


@app.get("/model-metrics", response_model=ModelMetricsResponse, tags=["Model"])
async def model_metrics():
    """Return model training metrics, feature importance, and prediction counters."""
    _ensure_model_loaded()
    meta = state.ml_service.metadata
    return ModelMetricsResponse(
        model_version=state.ml_service.get_model_version(),
        training_date=state.ml_service.get_training_date(),
        mae=float(meta.get("mae", 0)),
        rmse=float(meta.get("rmse", 0)),
        r2=float(meta.get("r2", 0)),
        mape=float(meta.get("mape", 0)),
        top_10_features={k: float(v) for k, v in state.ml_service.get_feature_importance().items()},
        total_predictions_served=state.predictions_served,
    )


@app.post("/price-adjustment", response_model=PriceAdjustmentResponse, tags=["Pricing"])
async def price_adjustment(adj_req: PriceAdjustmentRequest, request: Request):
    """
    Emergency manual price adjustment (e.g., flash sales, clearance).
    Applies a multiplier to base_price and stores in history.
    """
    warnings_list = []
    if adj_req.multiplier < 0.6:
        warnings_list.append(f"Extreme discount applied: {adj_req.multiplier}x (> 40% below base)")
    if adj_req.multiplier > 1.8:
        warnings_list.append(f"Extreme premium applied: {adj_req.multiplier}x (> 80% above base)")

    adjusted_price = round(adj_req.base_price * adj_req.multiplier, 2)
    state.manual_adjustments[adj_req.product_id] = adjusted_price

    ts = datetime.now(timezone.utc).isoformat()
    state.pricing_history[adj_req.product_id].append({
        "timestamp": ts,
        "product_id": adj_req.product_id,
        "event_type": "manual_adjustment",
        "price": adjusted_price,
        "change_pct": round((adj_req.multiplier - 1.0) * 100, 2),
        "reason": adj_req.reason,
    })

    logger.info(
        "Manual adjustment: product_id=%d multiplier=%.2f reason=%s",
        adj_req.product_id, adj_req.multiplier, adj_req.reason,
    )

    return PriceAdjustmentResponse(
        product_id=adj_req.product_id,
        original_price=adj_req.base_price,
        adjusted_price=adjusted_price,
        multiplier=adj_req.multiplier,
        reason=adj_req.reason,
        timestamp=ts,
        warnings=warnings_list,
    )


@app.post("/pricing-history", response_model=PricingHistoryResponse, tags=["History"])
async def pricing_history(hist_req: PricingHistoryRequest):
    """
    Retrieve pricing history for a product (last N days).
    """
    history_raw = state.pricing_history.get(hist_req.product_id, [])
    items = [PricingHistoryItem(**h) for h in history_raw[-200:]]  # cap at 200

    return PricingHistoryResponse(
        product_id=hist_req.product_id,
        days=hist_req.days,
        history=items,
        total_events=len(items),
    )


# ─── Additional utility endpoints ────────────────────────────────────────────

@app.get("/stats", tags=["System"])
async def api_stats():
    """Internal latency and error rate statistics."""
    latencies = state.latency_samples or [0.0]
    samples = sorted(latencies)
    n = len(samples)
    p50 = samples[int(n * 0.50)] if n else 0
    p95 = samples[int(n * 0.95)] if n else 0
    p99 = samples[int(n * 0.99)] if n else 0
    avg = sum(samples) / n if n else 0
    total_req = state.predictions_served + state.error_count
    error_rate = state.error_count / max(total_req, 1) * 100

    return {
        "predictions_served": state.predictions_served,
        "error_count": state.error_count,
        "error_rate_pct": round(error_rate, 3),
        "latency_ms": {
            "avg": round(avg, 1),
            "p50": round(p50, 1),
            "p95": round(p95, 1),
            "p99": round(p99, 1),
        },
        "uptime_seconds": round(time.time() - state.start_time, 1),
        "cache_size": len(_prediction_cache),
    }


@app.get("/", tags=["System"])
async def root():
    return {
        "service": "Dynamic Pricing Engine API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True, log_level="info")
