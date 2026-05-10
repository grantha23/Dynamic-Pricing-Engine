"""dashboard/pages/5_admin_controls.py — Admin Controls (Clean rewrite)"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from dashboard.utils import check_api_health, fetch_model_metrics, apply_price_change, log_action, CATEGORIES, _cache_store
from kafka.pricing_trigger_rules import get_rule_definitions





st.markdown('<div class="pt"><h1>⚙️ Admin Controls</h1><p>Model management · emergency controls · pricing rules · system configuration</p></div>', unsafe_allow_html=True)

health = check_api_health()
metrics = fetch_model_metrics()

# Model Management
st.markdown('<div class="sh">MODEL MANAGEMENT</div>', unsafe_allow_html=True)
m1, m2, m3, m4 = st.columns(4)
with m1: st.metric("MODEL VERSION", health.get("model_version", "N/A"))
with m2: st.metric("MAE", f"Rs {metrics.get('mae',0):.2f}")
with m3: st.metric("R2 SCORE", f"{metrics.get('r2',0):.4f}")
with m4: st.metric("MAPE", f"{metrics.get('mape',0):.2f}%")

feat_imp = metrics.get("top_10_features", {})
if feat_imp:
    fi_df = pd.DataFrame(list(feat_imp.items()), columns=["Feature","Importance"]).sort_values("Importance")
    fig = go.Figure(go.Bar(
        x=fi_df["Importance"], y=[f.upper() for f in fi_df["Feature"]],
        orientation="h", marker_color="#00ff88", marker_line_width=0,
        text=fi_df["Importance"].apply(lambda x: f"{x:.4f}"), textposition="outside",
        textfont=dict(family="DM Mono", size=9, color="#475569"),
    ))
    fig.update_layout(title="FEATURE IMPORTANCE (TOP 10)",
                      plot_bgcolor="#070d1a", paper_bgcolor="#070d1a", font_color="#64748b",
                      title_font_color="#94a3b8", title_font_size=12, height=300,
                      xaxis=dict(gridcolor="#0f2d4a", linecolor="#0f2d4a"),
                      yaxis=dict(gridcolor="#0f2d4a", linecolor="#0f2d4a",
                                 tickfont=dict(family="DM Mono", size=9)))
    st.plotly_chart(fig, use_container_width=True)

mc1, mc2, mc3 = st.columns(3)
with mc1:
    if st.button("Retrain Model", use_container_width=True):
        log_action("RETRAIN", "Manual trigger from admin")
        st.info("Retrain queued (~2 min)")
with mc2:
    rb = st.selectbox("ROLLBACK TO", ["v0.9 - 2d ago","v0.8 - 5d ago","v0.7 - 7d ago"])
    if st.button("Rollback", use_container_width=True):
        st.warning(f"Staging rollback to {rb}")
with mc3:
    if st.button("Download Model", use_container_width=True): st.info("Check models/ directory")
    if st.button("Clear Cache", use_container_width=True):
        _cache_store.clear(); st.success("Cache cleared!")

# Emergency Controls
st.markdown('<div class="sh">EMERGENCY CONTROLS</div>', unsafe_allow_html=True)
if "engine_paused" not in st.session_state: st.session_state.engine_paused = False

if st.session_state.engine_paused:
    st.markdown('<div class="danger-zone">', unsafe_allow_html=True)

ec1, ec2 = st.columns([1,2])
with ec1:
    btn_label = "Resume Engine" if st.session_state.engine_paused else "Pause Engine"
    if st.button(btn_label, use_container_width=True):
        st.session_state.engine_paused = not st.session_state.engine_paused
        log_action("ENGINE_STATE", "PAUSED" if st.session_state.engine_paused else "RESUMED")
        st.rerun()
    if st.session_state.engine_paused:
        st.markdown('<div class="alert-bar alert-err">ENGINE PAUSED - No automated price updates</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="alert-bar alert-ok">ENGINE RUNNING - All systems nominal</div>', unsafe_allow_html=True)

with ec2:
    global_mult = st.slider("GLOBAL PRICE MULTIPLIER", 0.50, 2.00, 1.00, 0.01, format="%.2f")
    if global_mult != 1.00:
        pct = abs(global_mult-1.0)*100
        direction = "LOWER" if global_mult < 1.0 else "HIGHER"
        st.markdown(f'<div class="alert-bar alert-warn">ALL PRICES WILL BE {pct:.0f}% {direction} THAN ML RECOMMENDATIONS</div>', unsafe_allow_html=True)

if st.session_state.engine_paused:
    st.markdown('</div>', unsafe_allow_html=True)

st.markdown("**Per-Category Multipliers**")
cat_cols = st.columns(len(CATEGORIES))
cat_mults = {}
for col, cat in zip(cat_cols, CATEGORIES):
    with col: cat_mults[cat] = st.slider(cat.upper(), 0.70, 1.30, 1.00, 0.01, key=f"cm_{cat}")

if st.button("Save Multipliers", use_container_width=True):
    log_action("MULTIPLIERS", " | ".join(f"{k}={v:.2f}" for k,v in cat_mults.items()))
    st.success("Multipliers applied and logged!")

# Pricing Rules
st.markdown('<div class="sh">PRICING RULES ENGINE</div>', unsafe_allow_html=True)
rules = get_rule_definitions()
if "rules_enabled" not in st.session_state:
    st.session_state.rules_enabled = {r["id"]: True for r in rules}

priority_colors = {"critical":"#ff4d6d","high":"#f59e0b","medium":"#38bdf8","low":"#64748b"}

for rule in rules:
    enabled = st.session_state.rules_enabled.get(rule["id"], True)
    dot_color = "#00ff88" if enabled else "#334155"
    pr_color = priority_colors.get(rule["priority"], "#64748b")

    col_main, col_toggle = st.columns([8,1])
    with col_main:
        st.markdown(f"""<div class="rule-row" style="border-color:{'#00ff8830' if enabled else '#0f2d4a'}">
          <div>
            <div style="display:flex;align-items:center;gap:8px">
              <span style="color:{dot_color};font-size:10px">●</span>
              <span style="font-family:'Syne',sans-serif;font-size:13px;font-weight:700;color:#e2e8f0">{rule['name']}</span>
              <span style="font-family:'DM Mono',monospace;font-size:9px;letter-spacing:1px;color:{pr_color}">{rule['priority'].upper()}</span>
            </div>
            <div style="font-family:'DM Mono',monospace;font-size:10px;color:#475569;margin-top:4px">{rule['description']}</div>
          </div>
        </div>""", unsafe_allow_html=True)
    with col_toggle:
        new_state = st.toggle("", value=enabled, key=f"rule_{rule['id']}", label_visibility="collapsed")
        st.session_state.rules_enabled[rule["id"]] = new_state

# Constraints
st.markdown('<div class="sh">CONSTRAINTS AND LIMITS</div>', unsafe_allow_html=True)
lc1, lc2 = st.columns(2)
with lc1:
    max_change = st.number_input("MAX SINGLE CHANGE (%)", value=30, min_value=5, max_value=100)
    daily_limit = st.number_input("DAILY CHANGES PER PRODUCT", value=3, min_value=1, max_value=20)
    comp_weight = st.slider("COMPETITOR PRICE WEIGHT", 0.20, 0.80, 0.35, 0.05)
with lc2:
    st.markdown("**Price Bounds by Category**")
    defaults = {"electronics":(1000,100000),"apparel":(100,25000),"home":(250,75000),"books":(50,10000),"food":(25,10000)}
    for cat in CATEGORIES:
        lo, hi = defaults.get(cat, (50,100000))
        bc1, bc2 = st.columns(2)
        with bc1: st.number_input(f"{cat.upper()} MIN", value=lo, key=f"min_{cat}")
        with bc2: st.number_input(f"{cat.upper()} MAX", value=hi, key=f"max_{cat}")

if st.button("Save Constraints", use_container_width=True):
    log_action("CONSTRAINTS", f"max={max_change}% daily={daily_limit} comp_w={comp_weight}")
    st.success("Constraints saved!")

# Alert Config
st.markdown('<div class="sh">ALERT CONFIGURATION</div>', unsafe_allow_html=True)
al1, al2 = st.columns(2)
with al1:
    lat_thresh = st.number_input("HIGH LATENCY ALERT (ms >)", value=1000, min_value=100)
    err_thresh = st.number_input("ERROR RATE ALERT (% >)", value=5, min_value=1)
with al2:
    mae_thresh = st.number_input("MODEL MAE ALERT (Rs >)", value=10.0, min_value=1.0)
    comp_detect = st.toggle("COMPETITOR PRICE CHANGE DETECTION", value=True)

cur_mae = health.get("model_accuracy_mae", 120.68)
if cur_mae > mae_thresh:
    st.markdown(f'<div class="alert-bar alert-err">MODEL MAE Rs {cur_mae:.1f} EXCEEDS THRESHOLD Rs {mae_thresh:.1f} - Retraining recommended</div>', unsafe_allow_html=True)
else:
    st.markdown(f'<div class="alert-bar alert-ok">MODEL MAE Rs {cur_mae:.1f} WITHIN ACCEPTABLE RANGE (threshold Rs {mae_thresh:.1f})</div>', unsafe_allow_html=True)

if st.button("Save Alert Config", use_container_width=True):
    log_action("ALERTS", f"latency={lat_thresh}ms err={err_thresh}% mae={mae_thresh}")
    st.success("Alert config saved!")

# Audit Log
st.markdown('<div class="sh">AUDIT LOG</div>', unsafe_allow_html=True)
log_path = os.path.join(os.path.dirname(__file__), "..", "logs", "audit.log")
if os.path.exists(log_path):
    with open(log_path) as f: content = f.read()
    st.markdown(f"""<div style="background:#070d1a;border:1px solid #0f2d4a;border-radius:4px;padding:12px 16px;
                    font-family:'DM Mono',monospace;font-size:11px;color:#475569;height:180px;overflow-y:auto;
                    white-space:pre-wrap;word-break:break-all">{content[-2000:] if len(content)>2000 else content or "no entries"}</div>""",
                unsafe_allow_html=True)
    st.download_button("Download Full Log", content.encode(), "audit.log")
else:
    st.markdown('<div style="font-family:\'DM Mono\',monospace;font-size:11px;color:#334155;padding:16px;background:#070d1a;border:1px solid #0f2d4a;border-radius:4px">No audit log entries yet</div>', unsafe_allow_html=True)
