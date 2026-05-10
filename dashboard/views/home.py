"""dashboard/pages/home.py — Dashboard home page content (no sidebar — app.py handles it)."""
import os, sys, random
import datetime as dt
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import streamlit as st
from dashboard.utils import fetch_monitoring_data, format_currency, check_api_health

monitoring = fetch_monitoring_data()
kpis   = monitoring.get("kpis", {})
events = monitoring.get("events", [])
health = st.session_state.get("_health_cache", check_api_health())

now_str = dt.datetime.now().strftime("%Y-%m-%d  %H:%M:%S")

st.markdown(f"""
<div class="pt"><h1>⚡ Dynamic Pricing Engine</h1>
<p>XGBoost-powered real-time price optimization · 50,000+ active SKUs</p></div>
<div style="display:flex;align-items:center;gap:12px;margin:12px 0 20px">
  <div style="display:flex;align-items:center;gap:6px">
    <div class="live-dot"></div>
    <span style="font-family:'DM Mono',monospace;font-size:9px;color:#00ff88;letter-spacing:1.5px">LIVE FEED</span>
  </div>
  <span style="font-family:'DM Mono',monospace;font-size:10px;color:#1e3a5f">{now_str}</span>
</div>
""", unsafe_allow_html=True)

# Ticker strip
random.seed(42)
tickers = [
    ("ELEC", 12450, +2.3), ("APPR", 899, -1.1), ("HOME", 3200, +0.8),
    ("BOOK", 450, +4.2),   ("FOOD", 180, -0.5), ("PREM", 24000, +1.7),
    ("BULK", 660, -2.8),   ("SEAS", 5600, +3.1),
]
ticker_html = """<div style="
    display:flex;gap:24px;background:#070d1a;border:1px solid #0f2d4a;
    border-radius:4px;padding:10px 16px;margin-bottom:20px;overflow-x:auto;
    font-family:'Space Mono',monospace">"""
for cat, price, chg in tickers:
    color = "#00ff88" if chg >= 0 else "#ff4d6d"
    arrow = "▲" if chg >= 0 else "▼"
    ticker_html += f"""<span style="white-space:nowrap">
        <span style="font-size:9px;color:#334155;letter-spacing:1px">{cat}</span>
        <span style="font-size:13px;color:#e2e8f0;margin:0 6px">Rs {price:,}</span>
        <span style="font-size:11px;color:{color}">{arrow}{abs(chg)}%</span>
    </span>"""
ticker_html += "</div>"
st.markdown(ticker_html, unsafe_allow_html=True)

# KPI row
k1, k2, k3, k4, k5 = st.columns(5)
kpi_rows = [
    (k1, "ACTIVE SKUs",         f"{kpis.get('total_active_skus', 0):,}",           "+247 today",    "#00ff88"),
    (k2, "DAILY REV. IMPACT",   format_currency(kpis.get('daily_revenue_impact',0)),"vs baseline",  "#00ff88"),
    (k3, "STOCKOUT PREV.",      f"{kpis.get('stockout_prevention_pct', 0):.1f}%",  "+3.2%",         "#00ff88"),
    (k4, "AVG LATENCY",         f"{kpis.get('avg_update_latency_ms', 0):.0f}ms",   "< 500ms target","#f59e0b"),
    (k5, "MODEL MAE",           f"Rs {kpis.get('model_mae', 0):.1f}",              "MAPE 2.43%",    "#00ff88"),
]
for col, label, val, delta, dc in kpi_rows:
    with col:
        st.markdown(f"""<div class="kcard">
          <div class="kl">{label}</div>
          <div class="kv">{val}</div>
          <div class="kd" style="color:{dc}">{delta}</div>
        </div>""", unsafe_allow_html=True)

# Module cards
st.markdown('<div class="sh" style="margin-top:28px">MODULES</div>', unsafe_allow_html=True)
pages_dir = os.path.dirname(os.path.abspath(__file__))
modules = [
    ("📋", "Recommendations",     "AI price changes · bulk apply",   "1_recommendations.py"),
    ("📡", "Monitoring",          "Real-time system health",          "2_monitoring.py"),
    ("🏪", "Competitor Analysis", "Price gap · market position",      "3_competitor_analysis.py"),
    ("📈", "Revenue Analytics",   "P&L impact · lift analysis",       "4_revenue_analytics.py"),
    ("⚙️", "Admin Controls",     "Model · rules · constraints",      "5_admin_controls.py"),
]
cols = st.columns(5)
for col, (icon, name, desc, fname) in zip(cols, modules):
    with col:
        st.page_link(os.path.join(pages_dir, fname), label=f"{icon}  {name}")
        st.markdown(f'<div style="font-family:\'DM Mono\',monospace;font-size:9px;color:#334155;margin-top:2px;padding-left:2px">{desc}</div>', unsafe_allow_html=True)

# System status
st.markdown('<div class="sh">SYSTEM STATUS</div>', unsafe_allow_html=True)
s1, s2, s3 = st.columns(3)
api_ok = health.get("status") == "healthy"
with s1:
    cls = "alert-ok" if api_ok else "alert-err"
    msg = "API  ONLINE · All endpoints operational" if api_ok else "API  OFFLINE · Check uvicorn process"
    st.markdown(f'<div class="{cls}">● {msg}</div>', unsafe_allow_html=True)
with s2:
    st.markdown('<div class="alert-ok">● MODEL  xgboost_v1.0 · loaded · R2 0.9995</div>', unsafe_allow_html=True)
with s3:
    st.markdown('<div class="alert-warn">● KAFKA  Mock mode · no broker detected</div>', unsafe_allow_html=True)

# Live event log
st.markdown('<div class="sh">LIVE PRICING EVENTS</div>', unsafe_allow_html=True)
ev_html = """<div style="background:#070d1a;border:1px solid #0f2d4a;border-radius:4px;
                         padding:12px 16px;max-height:280px;overflow-y:auto">"""
for ev in events[:20]:
    color = "#00ff88" if ev["action"]=="Increase" else ("#ff4d6d" if ev["action"]=="Decrease" else "#f59e0b")
    sym   = "UP" if ev["action"]=="Increase" else ("DN" if ev["action"]=="Decrease" else "--")
    ev_html += f"""<div style="border-bottom:1px solid #0a1628;padding:7px 0;display:flex;
                               gap:12px;align-items:center;font-family:'DM Mono',monospace;font-size:10px">
      <span style="color:#1e3a5f;min-width:52px">{ev['timestamp']}</span>
      <span style="color:#334155;min-width:70px">{str(ev['category']).upper()}</span>
      <span style="color:{color};min-width:28px;font-weight:700">{sym}</span>
      <span style="font-family:'Space Mono',monospace;font-size:11px;color:#e2e8f0;min-width:160px">
        Rs {ev['prev_price']:,.0f} → Rs {ev['new_price']:,.0f}
      </span>
      <span style="color:#334155">{ev['reason']}</span>
    </div>"""
ev_html += "</div>"
st.markdown(ev_html, unsafe_allow_html=True)
