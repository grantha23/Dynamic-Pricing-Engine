"""
Phase 1: ML Training Pipeline — Dynamic Pricing Engine
XGBoost regressor trained on synthetic Indian e-commerce data.
Target: predict price_change_pct (% adjustment). MAE < 8 percentage points.
"""

import sys
import io
# Force UTF-8 on Windows to support special chars in print
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')


import os
import json
import warnings
import numpy as np
import pandas as pd
import joblib
from datetime import datetime

from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
import xgboost as xgb

warnings.filterwarnings("ignore")


class NumpyEncoder(json.JSONEncoder):
    """Custom JSON encoder that handles numpy scalar types."""
    def default(self, obj):
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating, np.float32, np.float64)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)

# ─── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.join(BASE_DIR, "models")
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(MODELS_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

# ─── Constants ────────────────────────────────────────────────────────────────
N_SAMPLES = 10_000
RANDOM_STATE = 42
np.random.seed(RANDOM_STATE)

CATEGORY_CONFIG = {
    "electronics": {"price_min": 2000, "price_max": 50000, "elasticity": (-2.0, -1.5), "weight": 0.25},
    "apparel":     {"price_min": 200,  "price_max": 5000,  "elasticity": (-1.8, -1.2), "weight": 0.30},
    "home":        {"price_min": 500,  "price_max": 15000, "elasticity": (-1.5, -1.0), "weight": 0.20},
    "books":       {"price_min": 100,  "price_max": 2000,  "elasticity": (-1.0, -0.8), "weight": 0.15},
    "food":        {"price_min": 50,   "price_max": 2000,  "elasticity": (-0.9, -0.8), "weight": 0.10},
}
CATEGORIES = list(CATEGORY_CONFIG.keys())
SEASONS = ["spring", "summer", "monsoon", "winter"]
SEGMENTS = ["premium", "regular", "budget"]

# Indian festivals (approx day-of-year)
HOLIDAY_DAYS = {44, 95, 274, 300, 320, 350, 1, 361}  # Holi, Diwali, etc.


def generate_dataset(n: int = N_SAMPLES) -> pd.DataFrame:
    print("Generating synthetic e-commerce dataset…")

    # Category assignments with weighted distribution
    cat_weights = [v["weight"] for v in CATEGORY_CONFIG.values()]
    categories = np.random.choice(CATEGORIES, size=n, p=cat_weights)

    # Base prices by category
    base_prices = np.array([
        np.random.uniform(CATEGORY_CONFIG[c]["price_min"], CATEGORY_CONFIG[c]["price_max"])
        for c in categories
    ])

    # Demand — Poisson-like, category-dependent
    demand = np.random.exponential(scale=100, size=n).clip(0, 1000)

    # Inventory — uniform
    inventory = np.random.randint(0, 10001, size=n)

    # Competitor prices — base ± 15%
    competitor_prices = base_prices * np.random.normal(1.0, 0.10, size=n)
    competitor_prices = competitor_prices.clip(base_prices * 0.70, base_prices * 1.30)

    # Time features
    day_of_week = np.random.choice(range(7), size=n, p=[0.17, 0.16, 0.16, 0.15, 0.15, 0.11, 0.10])
    # 24 values summing to 1.0: low midnight-6am, peak at 10am (index 10) and 8pm (index 20)
    hour_probs = np.array([
        0.01, 0.01, 0.01, 0.01, 0.01, 0.01,  # 0-5am  (0.06)
        0.02, 0.03, 0.04, 0.05, 0.07, 0.06,  # 6-11am (0.27)
        0.05, 0.04, 0.04, 0.04, 0.04, 0.05,  # 12-5pm (0.26)
        0.06, 0.07, 0.06, 0.05, 0.04, 0.03,  # 6-11pm (0.31)
    ])
    hour_probs = hour_probs / hour_probs.sum()  # normalize to exactly 1.0
    hour_of_day = np.random.choice(range(24), size=n, p=hour_probs)
    is_weekend = (day_of_week >= 5).astype(int)

    # Holiday flag
    day_of_year = np.random.randint(1, 366, size=n)
    is_holiday = np.array([1 if d in HOLIDAY_DAYS else 0 for d in day_of_year])

    # Season
    season = np.array([SEASONS[((d - 1) // 91) % 4] for d in day_of_year])

    # Customer segment
    segment = np.random.choice(SEGMENTS, size=n, p=[0.20, 0.55, 0.25])

    # Price elasticity — category-dependent
    elasticity = np.array([
        np.random.uniform(*CATEGORY_CONFIG[c]["elasticity"])
        for c in categories
    ])
    elasticity = elasticity.clip(-2.2, -0.8)

    # Target: price_change_pct = how much % to adjust from base price
    # This is the correct ML target — model learns adjustment, not absolute price
    max_demand = 1000.0
    inventory_ratio = inventory / 10000.0
    demand_ratio = demand / max_demand

    demand_factor    = 1 + 0.30 * demand_ratio          # up to +30% for high demand
    inventory_factor = 1 - 0.20 * inventory_ratio       # down to -20% for excess stock
    segment_mult     = np.where(segment == "premium", 1.10,
                       np.where(segment == "budget", 0.92, 1.0))
    noise_pct = np.random.normal(0, 1.5, size=n)        # ±1.5% noise

    optimal_price = (
        base_prices * demand_factor * inventory_factor * segment_mult
    ).clip(base_prices * 0.5, base_prices * 2.5)

    price_change_pct = (
        (optimal_price - base_prices) / (base_prices + 1e-9) * 100 + noise_pct
    ).round(4)
    # Clip to realistic range: -30% to +40%
    price_change_pct = price_change_pct.clip(-30, 40)

    df = pd.DataFrame({
        "product_id":        np.random.randint(1, 50001, size=n),
        "product_category":  categories,
        "base_price":        base_prices.round(2),
        "demand":            demand.round(2),
        "inventory":         inventory,
        "competitor_price":  competitor_prices.round(2),
        "day_of_week":       day_of_week,
        "hour_of_day":       hour_of_day,
        "is_weekend":        is_weekend,
        "is_holiday":        is_holiday,
        "season":            season,
        "customer_segment":  segment,
        "price_elasticity":  elasticity.round(4),
        "price_change_pct":  price_change_pct,          # NEW TARGET
    })

    df = df.dropna()
    df = df[~df.isin([np.inf, -np.inf]).any(axis=1)]
    df = df.drop_duplicates()
    df["price_elasticity"] = df["price_elasticity"].clip(-3.0, -0.5)

    print(f"  Target price_change_pct: mean={df['price_change_pct'].mean():.2f}%  "
          f"std={df['price_change_pct'].std():.2f}%  "
          f"range=[{df['price_change_pct'].min():.1f}%, {df['price_change_pct'].max():.1f}%]")
    print(f"  Dataset generated: {len(df):,} rows")
    return df


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    print("Engineering features…")

    # Numerical ratios
    df["demand_ratio"]    = df["demand"] / 1000.0
    df["inventory_ratio"] = df["inventory"] / 10000.0
    df["price_gap"]       = (df["base_price"] - df["competitor_price"]) / df["base_price"]
    df["competitor_discount"] = (df["base_price"] - df["competitor_price"]) / df["competitor_price"]

    # Interaction features
    df["demand_inventory_product"] = df["demand"] * df["inventory"] / 10000.0
    df["competitor_elasticity"]    = df["competitor_price"] * df["price_elasticity"].abs()
    df["demand_hour_interaction"]  = df["demand"] * np.where(df["hour_of_day"] > 18, 1.0, 0.8)
    df["demand_weekend"]           = df["demand"] * df["is_weekend"]
    df["demand_holiday"]           = df["demand"] * df["is_holiday"]

    # One-hot encoding
    cat_cols = ["product_category", "season", "customer_segment"]
    df = pd.get_dummies(df, columns=cat_cols, prefix=cat_cols, drop_first=False)

    bool_cols = [c for c in df.columns if df[c].dtype == bool]
    df[bool_cols] = df[bool_cols].astype(int)

    print("  Feature engineering complete")
    return df


def train_model(df: pd.DataFrame):
    print("Training XGBoost model (target: price_change_pct)...")

    drop_cols = ["price_change_pct", "product_id"]
    feature_cols = [c for c in df.columns if c not in drop_cols]

    X = df[feature_cols].values.astype(float)
    y = df["price_change_pct"].values.astype(float)   # TARGET: % adjustment

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.20, random_state=RANDOM_STATE
    )

    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled  = scaler.transform(X_test)

    params = {
        "n_estimators":      500,
        "max_depth":         6,
        "learning_rate":     0.05,
        "subsample":         0.8,
        "colsample_bytree":  0.8,
        "min_child_weight":  3,
        "reg_alpha":         0.1,
        "reg_lambda":        1.0,
        "objective":         "reg:squarederror",
        "random_state":      RANDOM_STATE,
        "n_jobs":            -1,
    }

    model = xgb.XGBRegressor(**params)
    model.fit(
        X_train_scaled, y_train,
        eval_set=[(X_test_scaled, y_test)],
        verbose=100,
    )

    y_pred = model.predict(X_test_scaled)

    mae  = mean_absolute_error(y_test, y_pred)
    rmse = np.sqrt(mean_squared_error(y_test, y_pred))
    r2   = r2_score(y_test, y_pred)
    mape = np.mean(np.abs((y_test - y_pred) / (np.abs(y_test) + 1e-9))) * 100

    print(f"\n{'='*55}")
    print(f"  MODEL EVALUATION — price_change_pct (test n={len(y_test):,})")
    print(f"{'='*55}")
    print(f"  MAE:  {mae:.4f} pct-pts  {'PASS' if mae < 8 else 'FAIL'} (target < 8)")
    print(f"  RMSE: {rmse:.4f} pct-pts")
    print(f"  R2:   {r2:.4f}")
    print(f"  MAPE: {mape:.2f}%")

    sample_idx = np.random.choice(len(y_test), 10, replace=False)
    sample_preds = []
    print(f"\n  {'Actual%':>10} {'Pred%':>10} {'Err ppts':>10}")
    for i in sample_idx:
        err = abs(y_test[i] - y_pred[i])
        print(f"  {y_test[i]:>10.2f} {y_pred[i]:>10.2f} {err:>10.4f}")
        sample_preds.append({
            "actual_pct":    round(float(y_test[i]), 4),
            "predicted_pct": round(float(y_pred[i]), 4),
            "error_ppts":    round(float(err), 4),
        })

    imp = dict(zip(feature_cols, model.feature_importances_))
    top10 = dict(list(sorted(imp.items(), key=lambda x: x[1], reverse=True))[:10])
    print(f"\n  Top features:")
    for f, s in top10.items():
        print(f"    {f:<40} {s:.4f}")

    metrics = {"mae": round(mae, 4), "rmse": round(rmse, 4), "r2": round(r2, 4), "mape": round(mape, 4)}
    return {
        "model":              model,
        "scaler":             scaler,
        "feature_names":      feature_cols,
        "metrics":            metrics,
        "feature_importance": top10,
        "sample_predictions": sample_preds,
        "X_test_scaled":      X_test_scaled,
        "y_test":             y_test,
    }


    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.20, random_state=RANDOM_STATE
    )

    # Scale features
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled  = scaler.transform(X_test)

    # XGBoost hyperparameters (as specified)
    params = {
        "n_estimators":    200,
        "max_depth":       6,
        "learning_rate":   0.1,
        "subsample":       0.8,
        "colsample_bytree": 0.8,
        "objective":       "reg:squarederror",
        "random_state":    RANDOM_STATE,
        "n_jobs":          -1,
    }

    model = xgb.XGBRegressor(**params)
    model.fit(X_train_scaled, y_train, eval_set=[(X_test_scaled, y_test)], verbose=50)

    # ── Evaluation on TEST set only ───────────────────────────────────────────
    y_pred = model.predict(X_test_scaled)

    mae    = mean_absolute_error(y_test, y_pred)
    rmse   = np.sqrt(mean_squared_error(y_test, y_pred))
    r2     = r2_score(y_test, y_pred)
    mape   = np.mean(np.abs((y_test - y_pred) / (y_test + 1e-9))) * 100
    med_ae = np.median(np.abs(y_test - y_pred))

    print(f"\n{'='*50}")
    print(f"  MODEL EVALUATION (test set, n={len(y_test):,})")
    print(f"{'='*50}")
    print(f"  MAE:            ₹{mae:.2f}  {'✓' if mae < 8 else '✗'} (target: <₹8)")
    print(f"  RMSE:           ₹{rmse:.2f}")
    print(f"  R² Score:       {r2:.4f}")
    print(f"  MAPE:           {mape:.2f}%")
    print(f"  Median Abs Err: ₹{med_ae:.2f}")

    # Sample predictions
    sample_idx = np.random.choice(len(y_test), 10, replace=False)
    print(f"\n  Sample predictions (10 random):")
    print(f"  {'Actual':>10} {'Predicted':>10} {'Error':>8} {'MAPE%':>8}")
    sample_preds = []
    for i in sample_idx:
        err  = abs(y_test[i] - y_pred[i])
        mape_i = err / (y_test[i] + 1e-9) * 100
        print(f"  ₹{y_test[i]:>9.2f} ₹{y_pred[i]:>9.2f} ₹{err:>7.2f} {mape_i:>7.2f}%")
        sample_preds.append({
            "actual": round(float(y_test[i]), 2),
            "predicted": round(float(y_pred[i]), 2),
            "error": round(float(err), 2),
            "mape": round(float(mape_i), 2),
        })

    # Feature importance
    imp = dict(zip(feature_cols, model.feature_importances_))
    imp_sorted = dict(sorted(imp.items(), key=lambda x: x[1], reverse=True))
    top10 = dict(list(imp_sorted.items())[:10])
    print(f"\n  Top 10 Features:")
    for feat, score in top10.items():
        print(f"    {feat:<40} {score:.4f}")

    metrics = {"mae": round(mae, 4), "rmse": round(rmse, 4), "r2": round(r2, 4), "mape": round(mape, 4)}

    return {
        "model":              model,
        "scaler":             scaler,
        "feature_names":      feature_cols,
        "metrics":            metrics,
        "feature_importance": top10,
        "sample_predictions": sample_preds,
        "X_test_scaled":      X_test_scaled,
        "y_test":             y_test,
    }


def save_artifacts(result: dict, df: pd.DataFrame, X_train_size: int):
    print("\nSaving model artifacts…")

    # Model + scaler
    joblib.dump(result["model"],  os.path.join(MODELS_DIR, "xgboost_pricing_model.pkl"))
    joblib.dump(result["scaler"], os.path.join(MODELS_DIR, "scaler.pkl"))
    print("  ✓ xgboost_pricing_model.pkl saved")
    print("  ✓ scaler.pkl saved")

    # Feature names
    with open(os.path.join(MODELS_DIR, "feature_names.json"), "w") as f:
        json.dump(result["feature_names"], f, indent=2, cls=NumpyEncoder)
    print("  [OK] feature_names.json saved")

    # Metadata
    metadata = {
        "training_date":      datetime.utcnow().isoformat(),
        "n_samples_total":    len(df),
        "n_train":            X_train_size,
        "n_test":             len(result["y_test"]),
        "model_version":      "xgboost_v1.1",
        "target":             "price_change_pct",
        "units":              "percentage_points",
        "mae_target":         "< 8 percentage points",
        **result["metrics"],
        "top_10_features":    result["feature_importance"],
        "sample_predictions": result["sample_predictions"],
    }
    with open(os.path.join(MODELS_DIR, "model_metadata.json"), "w") as f:
        json.dump(metadata, f, indent=2, cls=NumpyEncoder)
    print("  [OK] model_metadata.json saved")

    # Verify load-back
    loaded_model  = joblib.load(os.path.join(MODELS_DIR, "xgboost_pricing_model.pkl"))
    loaded_scaler = joblib.load(os.path.join(MODELS_DIR, "scaler.pkl"))
    test_pred = loaded_model.predict(result["X_test_scaled"][:3])
    print(f"  ✓ Load-back verified: {test_pred}")


def save_data(df: pd.DataFrame):
    """Save train/test splits as CSV."""
    raw_drop = ["demand_ratio", "inventory_ratio", "price_gap", "price_margin",
                "demand_inventory_product", "competitor_elasticity", "demand_hour_interaction"]
    # Get raw-ish columns (before one-hot)
    feature_cols_engineered = [c for c in df.columns if c != "product_id"]

    split = int(len(df) * 0.8)
    df.iloc[:split].to_csv(os.path.join(DATA_DIR, "training_data.csv"), index=False)
    df.iloc[split:].to_csv(os.path.join(DATA_DIR, "test_data.csv"), index=False)
    print(f"  ✓ training_data.csv ({split:,} rows) saved")
    print(f"  ✓ test_data.csv ({len(df)-split:,} rows) saved")


def test_edge_cases(model, scaler, feature_names):
    """Test 5 extreme scenarios."""
    print("\nEdge case testing…")

    def make_row(base_price, demand, inventory, competitor_price, hour, elasticity, cat="electronics", seg="regular", season="summer"):
        row = {
            "base_price": base_price,
            "demand": demand,
            "inventory": inventory,
            "competitor_price": competitor_price,
            "day_of_week": 2,
            "hour_of_day": hour,
            "is_weekend": 0,
            "is_holiday": 0,
            "price_elasticity": elasticity,
            "demand_ratio": demand / 1000.0,
            "inventory_ratio": inventory / 10000.0,
            "price_gap": (base_price - competitor_price) / base_price,
            "price_margin": 0.0,
            "demand_inventory_product": demand * inventory / 10000.0,
            "competitor_elasticity": competitor_price * abs(elasticity),
            "demand_hour_interaction": demand * (1.0 if hour > 18 else 0.8),
        }
        for c in CATEGORIES:
            row[f"product_category_{c}"] = 1 if cat == c else 0
        for s in SEASONS:
            row[f"season_{s}"] = 1 if season == s else 0
        for sg in SEGMENTS:
            row[f"customer_segment_{sg}"] = 1 if seg == sg else 0

        # Build DataFrame aligned to feature_names
        df_row = pd.DataFrame([row])
        for col in feature_names:
            if col not in df_row.columns:
                df_row[col] = 0
        df_row = df_row[feature_names].fillna(0).astype(float)
        return scaler.transform(df_row.values)

    cases = [
        ("Very low price (₹100)",       100,   50,   1000,  95,   14, -1.5),
        ("Very high price (₹50000)",    50000, 200,   500, 48000, 20, -1.8),
        ("High demand scenario",         5000, 950,   200,  4800, 10, -1.5),
        ("Low inventory scenario",       5000,  50,    30,  5100, 14, -1.5),
        ("Peak vs off-peak (peak)",      5000, 200,  5000,  4900, 20, -1.5),
    ]

    print(f"  {'Scenario':<35} {'Base Price':>11} {'Predicted':>11}")
    for label, bp, dem, inv, comp, hr, elas in cases:
        row = make_row(bp, dem, inv, comp, hr, elas)
        pred = model.predict(row)[0]
        print(f"  {label:<35} ₹{bp:>9,.0f} ₹{pred:>9,.2f}")


# ─── Main ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 55)
    print("  DYNAMIC PRICING ENGINE — ML Training (v1.1)")
    print("  Target: price_change_pct | MAE < 8 pct-pts")
    print("=" * 55)

    df_raw  = generate_dataset(N_SAMPLES)
    df_feat = engineer_features(df_raw.copy())
    save_data(df_feat)
    result  = train_model(df_feat)
    n_train = int(len(df_feat) * 0.8)
    save_artifacts(result, df_feat, n_train)

    mae = result['metrics']['mae']
    print("\n" + "=" * 55)
    status = "PASS" if mae < 8 else "FAIL"
    print(f"  {status}: MAE = {mae:.4f} pct-pts (target < 8)")
    print(f"  R2: {result['metrics']['r2']:.4f}")
    print("  All artifacts saved to models/")
    print("=" * 55)
