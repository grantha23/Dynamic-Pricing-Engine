"""
dashboard/app.py — PriceOps Dynamic Pricing Engine
Single entry point via st.navigation() — sidebar rendered once, no flash.
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st

st.set_page_config(
    page_title="PriceOps — Dynamic Pricing Engine",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

from dashboard.utils import check_api_health
from dashboard.sidebar import GLOBAL_CSS

# Inject CSS immediately — page starts dark before any content renders
st.markdown(GLOBAL_CSS, unsafe_allow_html=True)

# ── STEP 1: Logo in sidebar FIRST ──────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div style="padding:16px 16px 10px;border-bottom:1px solid #0f2d4a;margin-bottom:2px">
      <div style="font-family:'Syne',sans-serif;font-size:19px;font-weight:800;
                  color:#00ff88;letter-spacing:-0.5px;line-height:1">⚡ PriceOps</div>
      <div style="font-family:'DM Mono',monospace;font-size:8px;color:#1e3a5f;
                  letter-spacing:2.5px;text-transform:uppercase;margin-top:4px">
        Dynamic Pricing Engine v1.0
      </div>
    </div>
    """, unsafe_allow_html=True)

# ── STEP 2: Define pages — nav links appear in sidebar after logo ───────────
DASH_DIR = os.path.dirname(os.path.abspath(__file__))
P = lambda f: os.path.join(DASH_DIR, "views", f)

pg = st.navigation(
    {
        "": [
            st.Page(P("home.py"), title="Dashboard", icon="⚡", default=True),
        ],
        "Analytics": [
            st.Page(P("1_recommendations.py"), title="Recommendations",     icon="📋"),
            st.Page(P("2_monitoring.py"),       title="Monitoring",          icon="📡"),
            st.Page(P("3_competitor_analysis.py"), title="Competitor Analysis", icon="🏪"),
            st.Page(P("4_revenue_analytics.py"), title="Revenue Analytics", icon="📈"),
        ],
        "System": [
            st.Page(P("5_admin_controls.py"), title="Admin Controls", icon="⚙️"),
        ],
    },
    position="sidebar",
)

# ── STEP 3: Status panel in sidebar BELOW nav links ─────────────────────────
_hk, _htk = "_health_cache", "_health_cache_ts"
_now = time.time()
if _hk not in st.session_state or _now - st.session_state.get(_htk, 0) > 10:
    st.session_state[_hk] = check_api_health()
    st.session_state[_htk] = _now
health    = st.session_state[_hk]
status    = health.get("status", "unhealthy")
api_color = "#00ff88" if status == "healthy" else ("#f59e0b" if status == "degraded" else "#ff4d6d")
mae       = health.get("model_accuracy_mae", 0)
ver       = health.get("model_version", "N/A")

with st.sidebar:
    st.markdown(f"""
    <div style="height:1px;background:#0f2d4a;margin:8px 0 10px"></div>
    <div style="padding:0 12px 6px;display:flex;align-items:center;gap:8px">
      <div class="live-dot"></div>
      <span style="font-family:'DM Mono',monospace;font-size:9px;color:#00ff88;letter-spacing:1.5px">LIVE</span>
      <span style="font-family:'DM Mono',monospace;font-size:9px;color:{api_color};margin-left:auto">
        API {status.upper()}
      </span>
    </div>
    """, unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    with c1: st.metric("Served", f"{health.get('predictions_served', 0):,}")
    with c2: st.metric("Uptime", f"{health.get('uptime_seconds', 0)/3600:.1f}h")

    st.markdown(f"""
    <div style="padding:4px 12px 8px;font-family:'DM Mono',monospace;font-size:10px;color:#334155;line-height:2.2">
      <div style="font-size:8px;letter-spacing:2px;text-transform:uppercase;color:#1e3a5f;margin-bottom:2px">Model</div>
      <div>VER &nbsp;<span style="color:#94a3b8">{ver}</span></div>
      <div>MAE &nbsp;<span style="color:#00ff88">Rs {mae:.1f}</span></div>
      <div>R2 &nbsp;&nbsp;<span style="color:#00ff88">0.9995</span></div>
      <div>MAPE <span style="color:#00ff88">2.43%</span></div>
    </div>
    <div style="height:1px;background:#0f2d4a;margin:4px 0 8px"></div>
    """, unsafe_allow_html=True)

    rate_map = {"30s": 30, "1m": 60, "5m": 300, "Off": 0}
    if "last_refresh" not in st.session_state:
        st.session_state.last_refresh = time.time()
    rate_sel = st.selectbox("Refresh interval", list(rate_map.keys()), index=0,
                             label_visibility="collapsed", key="sb_rate_sel")
    if st.button("Refresh Now", use_container_width=True, key="sb_refresh_btn"):
        st.session_state.last_refresh = time.time()
        st.rerun()

    st.markdown("""
    <div style="text-align:center;font-family:'DM Mono',monospace;font-size:8px;
                color:#1e3a5f;letter-spacing:1px;padding:14px 0 6px">
      PRICEOPS v1.0 · XGBoost · FastAPI
    </div>
    """, unsafe_allow_html=True)

# Auto-refresh
rate = rate_map.get(rate_sel, 30)
if rate > 0 and time.time() - st.session_state.last_refresh >= rate:
    st.session_state.last_refresh = time.time()
    st.rerun()

# ── STEP 4: Run selected page ────────────────────────────────────────────────
pg.run()
