# Dynamic Pricing Engine

## 🚀 Production-Ready ML-Powered Price Optimization

A complete dynamic pricing system for e-commerce with XGBoost ML, FastAPI, Kafka streaming, and an interactive Streamlit dashboard.

---

## 📁 Project Structure

```
pricing-engine/
├── ml_training.py          # XGBoost model training pipeline
├── models/                 # Trained model artifacts (.pkl, .json)
├── data/                   # Training/test datasets
├── api/
│   ├── main.py             # FastAPI application (7 endpoints)
│   ├── models.py           # Pydantic schemas
│   └── ml_service.py       # Model loading + prediction logic
├── kafka/
│   ├── producer.py         # Event generator (orders, inventory, competitors)
│   ├── consumer.py         # 5-min window aggregation
│   ├── pricing_trigger_rules.py  # 6-rule business rules engine
│   └── topology_test.py    # Pipeline integration tests
├── dashboard/
│   ├── app.py              # Streamlit main
│   ├── utils.py            # Shared utilities + mock data
│   └── pages/              # 5 dashboard pages
├── tests/                  # pytest test suite (44 tests)
└── deployment/             # Dockerfile + AWS scripts
```

---

## ⚡ Quick Start

### 1. Install Dependencies
```bash
pip install fastapi uvicorn xgboost scikit-learn pandas numpy joblib streamlit plotly requests
```

### 2. Train the Model (Phase 1)
```bash
python ml_training.py
# Output: models/xgboost_pricing_model.pkl (R² = 0.9995, MAPE = 2.43%)
```

### 3. Start the API (Phase 2)
```bash
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
# API docs: http://localhost:8000/docs
```

### 4. Start the Dashboard (Phase 4)
```bash
streamlit run dashboard/app.py
# Dashboard: http://localhost:8501
```

### 5. Run Tests (Phase 5)
```bash
pytest tests/ -v
# Expected: 44/44 passed
```

### 6. Kafka Pipeline (Phase 3 - Optional)
```bash
# Requires Kafka on localhost:9092 OR runs in mock mode automatically
python kafka/producer.py --rate 10 --duration 300 &
python kafka/consumer.py --duration 300

# Test pipeline (works without Kafka):
python kafka/topology_test.py
```

---

## 🔌 API Reference

| Endpoint | Method | Description |
|---|---|---|
| `/health` | GET | Model status, uptime, predictions served |
| `/predict-price` | POST | Single product price recommendation |
| `/batch-predict` | POST | Up to 1000 products in one call |
| `/model-metrics` | GET | Training metrics + feature importance |
| `/price-adjustment` | POST | Manual emergency price override |
| `/pricing-history` | POST | Product price change history |
| `/stats` | GET | API latency p50/p95/p99 statistics |

### Example Request
```bash
curl -X POST http://localhost:8000/predict-price \
  -H "Content-Type: application/json" \
  -d '{
    "product_id": 101,
    "product_category": "electronics",
    "base_price": 5000,
    "demand": 150,
    "inventory": 500,
    "competitor_price": 4800,
    "hour_of_day": 14,
    "day_of_week": 2,
    "is_weekend": false,
    "is_holiday": false,
    "season": "summer",
    "customer_segment": "regular",
    "price_elasticity": -1.5
  }'
```

### Example Response
```json
{
  "product_id": 101,
  "recommended_price": 4916.93,
  "confidence_score": 0.9995,
  "price_change_pct": -1.66,
  "recommendation_reason": "Decreasing price 1.7% due to market equilibrium maintained.",
  "timestamp": "2026-05-04T16:59:42.131569+00:00",
  "processing_time_ms": 1.32
}
```

---

## 📊 Model Performance

| Metric | Value |
|---|---|
| R² Score | 0.9995 |
| MAPE | 2.43% |
| Processing Time | 1-2ms |
| Batch 100 items | < 50ms |

---

## 🏪 Dashboard Pages

1. **Recommendations** — Review AI price recommendations, apply in bulk, export CSV
2. **Monitoring** — Real-time KPIs, event log, system health
3. **Competitor Analysis** — Price gap analysis, undercut opportunities
4. **Revenue Analytics** — Financial impact, elasticity correlation, lift analysis
5. **Admin Controls** — Model management, emergency controls, rules config

---

## 🔄 Kafka Pricing Rules

| Rule | Trigger | Action |
|---|---|---|
| High Demand + Low Inventory | demand > 10/min AND inventory < 20% | +20% surge |
| Low Demand + High Inventory | demand < 2/min AND inventory > 70% | -15% clearance |
| Competitor Undercut | our price > competitor × 1.20 | Match competitor |
| Flash Sale | demand > 3× historical avg | ±5-10% micro-adj |
| Inventory Runout Risk | inventory < 10 AND demand > 5/min | +50% premium |
| Slow Moving SKU | 0 orders in 7 days AND inventory > 500 | -30% aggressive |

---

## 🚀 AWS Deployment

```bash
# Configure AWS credentials first
aws configure

# Run deployment script
python deployment/aws_deploy.py

# Access
curl http://PUBLIC_IP:8000/health
# Navigate to: http://PUBLIC_IP:8501
```

---

## 🧪 Testing

```bash
# All 44 tests
pytest tests/ -v

# Unit tests only (no API needed)
pytest tests/test_ml_service.py -v

# Integration tests (requires API running)
pytest tests/test_api.py -v

# System E2E tests
pytest tests/test_system.py -v

# Kafka topology tests (works in mock mode)
python kafka/topology_test.py
```

---

## 📈 Success Criteria

- ✅ XGBoost model: R² = 0.9995, MAPE = 2.43%
- ✅ FastAPI: 1-2ms processing time per prediction
- ✅ Batch 100 items: < 50ms
- ✅ Dashboard: 5 pages with interactive Plotly charts
- ✅ Kafka: 6 business rules with mock mode fallback
- ✅ Tests: 44/44 passing
- ✅ Docker + AWS deployment scripts ready
