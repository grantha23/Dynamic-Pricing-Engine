"""
dashboard/sidebar.py
Shared sidebar renderer — call render_sidebar(current_file=__file__) from every page.
Uses st.page_link() for full active-state control — no CSS aria-current dependency.
"""
import os
import time
import streamlit as st
from dashboard.utils import check_api_health

# ── Global CSS (injected on every page) ──────────────────────────────────────
GLOBAL_CSS = """<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Syne:wght@700;800&family=DM+Mono:wght@400;500&display=swap');

html,body,[data-testid="stAppViewContainer"]{background:#030712!important;font-family:'Syne',sans-serif!important;color:#e2e8f0!important}
#MainMenu,footer,header{visibility:hidden}
[data-testid="stDecoration"]{display:none}

/* Smooth page transition — eliminates flash */
[data-testid="stAppViewContainer"]{animation:fadein 0.18s ease-in!important}
[data-testid="stSidebar"]{animation:fadein 0.15s ease-in!important}
@keyframes fadein{from{opacity:0}to{opacity:1}}

/* ── Anti-shake: lock Plotly chart containers to prevent resize loops ── */
div[data-testid="stPlotlyChart"]{overflow:hidden!important;contain:layout style!important}
div[data-testid="stPlotlyChart"] > div{overflow:hidden!important}
div[data-testid="stPlotlyChart"] iframe{display:block!important;overflow:hidden!important}
.js-plotly-plot .plotly .svg-container{overflow:hidden!important}

/* Prevent white flash on sidebar content area */
[data-testid="stSidebarContent"]{background:#070d1a!important}
[data-testid="stMain"]{background:#030712!important}

/* Style st.navigation() nav links — DON'T hide, just theme them */
[data-testid="stSidebarNav"]{padding:0 8px!important;margin-top:0!important}
[data-testid="stSidebarNavLink"]{
    display:flex!important;align-items:center!important;gap:10px!important;
    padding:8px 12px!important;border-radius:4px!important;
    border:1px solid transparent!important;margin-bottom:2px!important;
    text-decoration:none!important;transition:all 0.15s!important;background:transparent!important;
}
[data-testid="stSidebarNavLink"]:hover{background:#0d1f35!important;border-color:#00ff8820!important}
[data-testid="stSidebarNavLink"][aria-current="page"]{
    background:rgba(0,255,136,0.07)!important;border-color:rgba(0,255,136,0.25)!important;
    border-left:3px solid #00ff88!important;padding-left:10px!important;
}
[data-testid="stSidebarNavLink"] p,[data-testid="stSidebarNavLink"] span{
    font-family:'Syne',sans-serif!important;font-size:13px!important;
    font-weight:600!important;color:#4b6a8a!important;line-height:1!important;
}
[data-testid="stSidebarNavLink"]:hover p,[data-testid="stSidebarNavLink"]:hover span{color:#94a3b8!important}
[data-testid="stSidebarNavLink"][aria-current="page"] p,
[data-testid="stSidebarNavLink"][aria-current="page"] span{color:#00ff88!important}
[data-testid="stSidebarNavSeparator"]{border-color:#0f2d4a!important;margin:6px 8px!important}

/* Sidebar shell */
[data-testid="stSidebar"]{background:#070d1a!important;border-right:1px solid #0f2d4a!important}
[data-testid="stSidebar"]>div:first-child{padding-top:0!important}
[data-testid="stSidebar"] p,[data-testid="stSidebar"] span,[data-testid="stSidebar"] label{color:#4b6a8a}

/* Sidebar metric cards */
[data-testid="stSidebar"] [data-testid="metric-container"]{background:#0a1628!important;border:1px solid #1a3a5c!important;border-radius:3px!important;padding:10px!important;position:relative;overflow:hidden}
[data-testid="stSidebar"] [data-testid="metric-container"]::before{content:'';position:absolute;top:0;left:0;width:2px;height:100%;background:#00ff88}
[data-testid="stSidebar"] [data-testid="stMetricValue"]{font-family:'Space Mono',monospace!important;font-size:16px!important;color:#e2e8f0!important}
[data-testid="stSidebar"] [data-testid="stMetricLabel"]{font-family:'DM Mono',monospace!important;font-size:8px!important;letter-spacing:2px!important;text-transform:uppercase!important;color:#334155!important}
[data-testid="stSidebar"] [data-testid="stMetricDelta"]{font-family:'DM Mono',monospace!important;font-size:9px!important}

/* Streamlit page_link inside sidebar */
[data-testid="stSidebar"] [data-testid="stPageLink"]{
    display:block!important;padding:0!important;margin:0 0 1px!important;
    border-radius:4px!important;border:1px solid transparent!important;
    transition:all 0.15s!important;text-decoration:none!important;
}
[data-testid="stSidebar"] [data-testid="stPageLink"]:hover{
    background:#0d1f35!important;border-color:#00ff8820!important;
}
[data-testid="stSidebar"] [data-testid="stPageLink"] p,
[data-testid="stSidebar"] [data-testid="stPageLink"] span{
    font-family:'Syne',sans-serif!important;font-size:13px!important;
    font-weight:600!important;color:#4b6a8a!important;
    text-decoration:none!important;
}
[data-testid="stSidebar"] [data-testid="stPageLink"]:hover p,
[data-testid="stSidebar"] [data-testid="stPageLink"]:hover span{color:#94a3b8!important}

/* Global metric cards (main content) */
[data-testid="metric-container"]{background:#0a1628!important;border:1px solid #1e3a5f!important;border-radius:4px!important;padding:14px!important;position:relative;overflow:hidden}
[data-testid="metric-container"]::before{content:'';position:absolute;top:0;left:0;width:3px;height:100%;background:#00ff88}
[data-testid="stMetricValue"]{font-family:'Space Mono',monospace!important;font-size:22px!important;color:#00ff88!important}
[data-testid="stMetricLabel"]{font-family:'DM Mono',monospace!important;font-size:9px!important;letter-spacing:2px!important;text-transform:uppercase!important;color:#475569!important}
[data-testid="stMetricDelta"]{font-family:'DM Mono',monospace!important;font-size:11px!important}

/* Buttons */
.stButton button{background:transparent!important;border:1px solid #00ff8855!important;color:#00ff88!important;font-family:'DM Mono',monospace!important;font-size:11px!important;letter-spacing:1px!important;text-transform:uppercase!important;border-radius:2px!important}
.stButton button:hover{background:#00ff8812!important;border-color:#00ff88!important;box-shadow:0 0 16px #00ff8815!important}

/* Dataframes */
[data-testid="stDataFrame"]{border:1px solid #0f2d4a!important;border-radius:4px!important}
[data-testid="stDataFrame"] *{font-family:'DM Mono',monospace!important;font-size:12px!important}

/* Inputs */
.stSelectbox>div>div,.stMultiSelect>div>div{background:#070d1a!important;border:1px solid #1e3a5f!important;border-radius:2px!important;font-family:'DM Mono',monospace!important;font-size:12px!important;color:#e2e8f0!important}

/* Chart container — do NOT constrain height or add borders that collapse plotly */
.stPlotlyChart{border:1px solid #0f2d4a;border-radius:4px;overflow:visible!important}
.stPlotlyChart>div{overflow:visible!important}

/* Shared layout classes */
.sh{font-family:'DM Mono',monospace;font-size:9px;letter-spacing:3px;text-transform:uppercase;color:#1e3a5f;border-bottom:1px solid #0f2d4a;padding-bottom:6px;margin:20px 0 12px}
.pt h1{font-family:'Syne',sans-serif!important;font-size:24px!important;font-weight:800!important;color:#f1f5f9!important;border-left:3px solid #00ff88;padding-left:12px}
.pt p{font-family:'DM Mono',monospace!important;font-size:10px!important;color:#334155!important;padding-left:15px;margin-top:4px}
.kcard{background:#070d1a;border:1px solid #0f2d4a;border-radius:4px;padding:16px;position:relative;overflow:hidden}
.kcard::before{content:'';position:absolute;top:0;left:0;width:100%;height:2px;background:linear-gradient(90deg,#00ff88,transparent)}
.kcard .kv{font-family:'Space Mono',monospace;font-size:20px;font-weight:700;color:#e2e8f0;margin-top:4px}
.kcard .kl{font-family:'DM Mono',monospace;font-size:9px;letter-spacing:2px;text-transform:uppercase;color:#334155}
.kcard .kd{font-family:'DM Mono',monospace;font-size:10px;margin-top:6px}
.live-dot{display:inline-block;width:6px;height:6px;border-radius:50%;background:#00ff88;animation:ldpulse 1.5s ease-in-out infinite}
@keyframes ldpulse{0%,100%{opacity:1}50%{opacity:.3}}
.alert-ok{background:#00ff880f;border-left:3px solid #00ff88;color:#00ff88;padding:9px 13px;border-radius:2px;font-family:'DM Mono',monospace;font-size:11px;margin-bottom:6px}
.alert-err{background:#ff4d6d0f;border-left:3px solid #ff4d6d;color:#ff4d6d;padding:9px 13px;border-radius:2px;font-family:'DM Mono',monospace;font-size:11px;margin-bottom:6px}
.alert-warn{background:#f59e0b0f;border-left:3px solid #f59e0b;color:#fbbf24;padding:9px 13px;border-radius:2px;font-family:'DM Mono',monospace;font-size:11px;margin-bottom:6px}
hr{border-color:#0f2d4a!important}
[data-testid="stSidebar"] ::-webkit-scrollbar{width:2px}
[data-testid="stSidebar"] ::-webkit-scrollbar-thumb{background:#1e3a5f;border-radius:2px}
[data-testid="stMainBlockContainer"]{padding-top:20px!important}
</style>"""

# Nav items — (label, icon, path_relative_to_dashboard_root)
NAV_ITEMS = [
    ("Dashboard",           "⚡", "app.py"),
    ("Recommendations",     "📋", "pages/1_recommendations.py"),
    ("Monitoring",          "📡", "pages/2_monitoring.py"),
    ("Competitor Analysis", "🏪", "pages/3_competitor_analysis.py"),
    ("Revenue Analytics",   "📈", "pages/4_revenue_analytics.py"),
    ("Admin Controls",      "⚙️", "pages/5_admin_controls.py"),
]


def _active_nav_html(label: str, icon: str) -> str:
    """Render an active (current page) nav item as styled HTML — no clickable link."""
    return f"""
    <div style="
        display:flex;align-items:center;gap:10px;
        padding:8px 12px;border-radius:4px;margin-bottom:1px;
        background:rgba(0,255,136,0.07);
        border:1px solid rgba(0,255,136,0.25);
        border-left:3px solid #00ff88;
        padding-left:10px;
    ">
      <span style="font-size:14px;width:18px;text-align:center">{icon}</span>
      <span style="font-family:'Syne',sans-serif;font-size:13px;font-weight:700;color:#00ff88;line-height:1">{label}</span>
    </div>"""


def render_sidebar(current_file: str = "") -> dict:
    """
    Render the full sidebar. Call as:
        from dashboard.sidebar import render_sidebar
        health = render_sidebar(__file__)
    """
    st.markdown(GLOBAL_CSS, unsafe_allow_html=True)

    # Determine which nav item is active from the caller's __file__
    current_basename = os.path.basename(current_file) if current_file else "app.py"
    basename_map = {
        "app.py":                    "Dashboard",
        "1_recommendations.py":      "Recommendations",
        "2_monitoring.py":           "Monitoring",
        "3_competitor_analysis.py":  "Competitor Analysis",
        "4_revenue_analytics.py":    "Revenue Analytics",
        "5_admin_controls.py":       "Admin Controls",
    }
    active_label = basename_map.get(current_basename, "Dashboard")

    # Auto-refresh state
    if "last_refresh" not in st.session_state:
        st.session_state.last_refresh = time.time()

    # Cache health check — avoid 5s network timeout on EVERY render
    _health_key = "_health_cache"
    _health_ts_key = "_health_cache_ts"
    now = time.time()
    if (
        _health_key not in st.session_state
        or now - st.session_state.get(_health_ts_key, 0) > 10
    ):
        st.session_state[_health_key] = check_api_health()
        st.session_state[_health_ts_key] = now
    health = st.session_state[_health_key]
    status = health.get("status", "unhealthy")
    api_color = "#00ff88" if status == "healthy" else ("#f59e0b" if status == "degraded" else "#ff4d6d")

    with st.sidebar:
        # ── Logo ──────────────────────────────────────────────────────────────
        st.markdown("""
        <div style="padding:20px 16px 14px;border-bottom:1px solid #0f2d4a;margin-bottom:0">
          <div style="font-family:'Syne',sans-serif;font-size:19px;font-weight:800;color:#00ff88;letter-spacing:-0.5px;line-height:1">
            ⚡ PriceOps
          </div>
          <div style="font-family:'DM Mono',monospace;font-size:8px;color:#1e3a5f;letter-spacing:2.5px;text-transform:uppercase;margin-top:4px">
            Dynamic Pricing Engine v1.0
          </div>
        </div>
        <div style="font-family:'DM Mono',monospace;font-size:8px;letter-spacing:3px;text-transform:uppercase;color:#1e3a5f;padding:10px 12px 4px">
          Navigation
        </div>
        """, unsafe_allow_html=True)

        # ── Nav Links ─────────────────────────────────────────────────────────
        # Base path = dashboard directory (where app.py lives)
        dash_dir = os.path.dirname(os.path.abspath(__file__))

        for label, icon, rel_path in NAV_ITEMS:
            if label == active_label:
                # Active page — render as styled HTML (not a link)
                st.markdown(_active_nav_html(label, icon), unsafe_allow_html=True)
            else:
                # Inactive — use st.page_link for navigation
                abs_path = os.path.join(dash_dir, rel_path)
                try:
                    st.page_link(abs_path, label=f"{icon}  {label}")
                except Exception:
                    # Fallback if page_link fails
                    st.markdown(f"""
                    <div style="padding:8px 12px;border-radius:4px;margin-bottom:1px;border:1px solid transparent">
                      <span style="font-size:13px;color:#4b6a8a;font-family:'Syne',sans-serif;font-weight:600">{icon}  {label}</span>
                    </div>""", unsafe_allow_html=True)

        # ── Divider ───────────────────────────────────────────────────────────
        st.markdown('<div style="height:1px;background:#0f2d4a;margin:10px 0"></div>', unsafe_allow_html=True)

        # ── Live Status ───────────────────────────────────────────────────────
        st.markdown(f"""
        <div style="padding:8px 12px 4px;display:flex;align-items:center;gap:8px">
          <div class="live-dot"></div>
          <span style="font-family:'DM Mono',monospace;font-size:9px;color:#00ff88;letter-spacing:1.5px">LIVE</span>
          <span style="font-family:'DM Mono',monospace;font-size:9px;color:{api_color};margin-left:auto">
            API {status.upper()}
          </span>
        </div>
        """, unsafe_allow_html=True)

        # ── System Metrics ────────────────────────────────────────────────────
        st.markdown('<div style="padding:0 8px"><div style="font-family:\'DM Mono\',monospace;font-size:8px;letter-spacing:2px;text-transform:uppercase;color:#1e3a5f;padding:4px 4px 4px">System</div>', unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        with c1:
            st.metric("Served", f"{health.get('predictions_served', 0):,}")
        with c2:
            st.metric("Uptime", f"{health.get('uptime_seconds', 0)/3600:.1f}h")
        st.markdown("</div>", unsafe_allow_html=True)

        # ── Model Stats ───────────────────────────────────────────────────────
        mae = health.get("model_accuracy_mae", 0)
        ver = health.get("model_version", "N/A")
        st.markdown(f"""
        <div style="padding:0 12px;font-family:'DM Mono',monospace;font-size:10px;color:#334155;line-height:2.2">
          <div style="font-family:'DM Mono',monospace;font-size:8px;letter-spacing:2px;text-transform:uppercase;color:#1e3a5f;margin-bottom:2px">Model</div>
          <div>VER &nbsp;<span style="color:#94a3b8">{ver}</span></div>
          <div>MAE &nbsp;<span style="color:#00ff88">Rs {mae:.1f}</span></div>
          <div>R2 &nbsp;&nbsp;<span style="color:#00ff88">0.9995</span></div>
          <div>MAPE <span style="color:#00ff88">2.43%</span></div>
        </div>
        """, unsafe_allow_html=True)

        # ── Divider ───────────────────────────────────────────────────────────
        st.markdown('<div style="height:1px;background:#0f2d4a;margin:10px 0"></div>', unsafe_allow_html=True)

        # ── Refresh ───────────────────────────────────────────────────────────
        st.markdown('<div style="padding:0 8px"><div style="font-family:\'DM Mono\',monospace;font-size:8px;letter-spacing:2px;text-transform:uppercase;color:#1e3a5f;padding:0 4px 4px">Auto-Refresh</div>', unsafe_allow_html=True)
        rate_map = {"30s": 30, "1m": 60, "5m": 300, "Off": 0}
        rate_sel = st.selectbox("Interval", list(rate_map.keys()), index=0,
                                label_visibility="collapsed", key="sb_rate_sel")
        if st.button("Refresh Now", use_container_width=True, key="sb_refresh_btn"):
            st.session_state.last_refresh = time.time()
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

        # ── Footer ────────────────────────────────────────────────────────────
        st.markdown("""
        <div style="text-align:center;font-family:'DM Mono',monospace;font-size:8px;color:#1e3a5f;letter-spacing:1px;padding:16px 0 8px">
          PRICEOPS v1.0 · XGBoost · FastAPI
        </div>
        """, unsafe_allow_html=True)

    # Handle auto-refresh
    rate = rate_map.get(rate_sel, 30)
    if rate > 0 and time.time() - st.session_state.last_refresh >= rate:
        st.session_state.last_refresh = time.time()
        st.rerun()

    return health
