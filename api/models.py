"""
api/models.py — Pydantic request/response schemas for the Dynamic Pricing API
"""

from pydantic import BaseModel, Field, field_validator
from typing import List, Dict, Optional
from enum import Enum


class ProductCategory(str, Enum):
    electronics = "electronics"
    apparel = "apparel"
    home = "home"
    books = "books"
    food = "food"


class Season(str, Enum):
    spring = "spring"
    summer = "summer"
    monsoon = "monsoon"
    winter = "winter"


class CustomerSegment(str, Enum):
    premium = "premium"
    regular = "regular"
    budget = "budget"


class PricePredictionRequest(BaseModel):
    product_id: int = Field(..., gt=0, description="Unique product identifier")
    product_category: ProductCategory
    base_price: float = Field(..., gt=0, description="Base/list price in INR")
    demand: float = Field(..., ge=0, le=1000, description="Demand in orders/hour")
    inventory: int = Field(..., ge=0, description="Units currently in stock")
    competitor_price: float = Field(..., gt=0, description="Competitor's current price")
    hour_of_day: int = Field(..., ge=0, le=23)
    day_of_week: int = Field(..., ge=0, le=6)
    is_weekend: bool
    is_holiday: bool
    season: Season
    customer_segment: CustomerSegment
    price_elasticity: float = Field(..., ge=-3.0, le=-0.5, description="Price elasticity coefficient")

    class Config:
        json_schema_extra = {
            "example": {
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
        }


class PricePredictionResponse(BaseModel):
    product_id: int
    recommended_price: float
    confidence_score: float = Field(..., ge=0, le=1)
    price_change_pct: float
    recommendation_reason: str
    timestamp: str
    processing_time_ms: float
    request_id: Optional[str] = None


class HealthCheckResponse(BaseModel):
    status: str  # "healthy" | "degraded" | "unhealthy"
    model_loaded: bool
    last_update: str
    predictions_served: int
    uptime_seconds: float
    model_accuracy_mae: float
    model_version: str


class BatchPredictionRequest(BaseModel):
    products: List[PricePredictionRequest] = Field(..., max_length=1000)


class BatchPredictionResponse(BaseModel):
    predictions: List[PricePredictionResponse]
    total_time_ms: float
    batch_size: int


class ModelMetricsResponse(BaseModel):
    model_version: str
    training_date: str
    mae: float
    rmse: float
    r2: float
    mape: float
    top_10_features: Dict[str, float]
    total_predictions_served: int


class PriceAdjustmentRequest(BaseModel):
    product_id: int = Field(..., gt=0)
    base_price: float = Field(..., gt=0)
    multiplier: float = Field(..., ge=0.5, le=2.0)
    reason: str = Field(..., min_length=3, max_length=500)


class PriceAdjustmentResponse(BaseModel):
    product_id: int
    original_price: float
    adjusted_price: float
    multiplier: float
    reason: str
    timestamp: str
    warnings: List[str]


class PricingHistoryRequest(BaseModel):
    product_id: int = Field(..., gt=0)
    days: int = Field(7, ge=1, le=30)


class PricingHistoryItem(BaseModel):
    timestamp: str
    product_id: int
    event_type: str  # "ml_prediction" | "manual_adjustment"
    price: float
    change_pct: Optional[float] = None
    reason: Optional[str] = None


class PricingHistoryResponse(BaseModel):
    product_id: int
    days: int
    history: List[PricingHistoryItem]
    total_events: int
