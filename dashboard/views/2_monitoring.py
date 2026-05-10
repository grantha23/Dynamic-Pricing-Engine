"""dashboard/pages/2_monitoring.py — Real-time Monitoring (Clean rewrite)"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from dashboard.utils import check_api_health, fetch_monitoring_data, fetch_recommendations, format_currency, CATEGORIES





# Auto-refresh only the clock — not the whole page (avoids chart shaking)
@st.fragment(run_every=30)
def _live_clock():
    import datetime as dt
    now_str = dt.datetime.now().strftime("%Y-%m-%d  %H:%M:%S")
    st.markdown(f"""
<div style="display:flex;align-items:center;gap:10px;margin-bottom:20px">
  <div class="live-dot"></div>
  <span style="font-family:'DM Mono',monospace;font-size:10px;color:#00ff88;letter-spacing:1px">LIVE FEED</span>
  <span style="font-family:'DM Mono',monospace;font-size:10px;color:#334155;margin-left:8px">{now_str}</span>
</div>""", unsafe_allow_html=True)

health = check_api_health()
monitoring = fetch_monitoring_data()
kpis = monitoring.get("kpis", {})
events = monitoring.get("events", [])
rev_trend = monitoring.get("revenue_trend", [])

st.markdown('<div class="pt"><h1>📡 Real-Time Monitoring</h1><p>Live system health · pricing events · revenue analytics</p></div>', unsafe_allow_html=True)
_live_clock()

# KPIs
cols = st.columns(5)
kpi_rows = [
    ("ACTIVE SKUs",    f"{kpis.get('total_active_skus',0):,}", "+247 today", "#00ff88"),
    ("REVENUE IMPACT", format_currency(kpis.get('daily_revenue_impact',0)), "+12.4% vs baseline", "#00ff88"),
    ("STOCKOUT PREV.", f"{kpis.get('stockout_prevention_pct',0):.1f}%", "+3.2%", "#00ff88"),
    ("AVG LATENCY",    f"{kpis.get('avg_update_latency_ms',0):.0f}ms", "< 500ms target", "#f59e0b"),
    ("MODEL MAE",      f"Rs {kpis.get('model_mae',0):.1f}", "MAPE 2.43%", "#00ff88"),
]
for col, (label, val, delta, dc) in zip(cols, kpi_rows):
    with col:
        st.markdown(f'<div class="kcard"><div class="kl">{label}</div><div class="kv">{val}</div><div class="kd" style="color:{dc}">{delta}</div></div>', unsafe_allow_html=True)

CHART_THEME = dict(plot_bgcolor="#070d1a", paper_bgcolor="#070d1a", font_color="#64748b",
                   title_font_color="#94a3b8", title_font_size=12,
                   transition=dict(duration=0, easing="linear"),
                   xaxis=dict(gridcolor="#0f2d4a", linecolor="#0f2d4a"),
                   yaxis=dict(gridcolor="#0f2d4a", linecolor="#0f2d4a"))
PLOT_CFG = {"displayModeBar": False, "scrollZoom": False, "responsive": True}

df_recs = fetch_recommendations(300)
st.markdown('<div class="sh">ANALYTICS</div>', unsafe_allow_html=True)
c1, c2 = st.columns(2)

with c1:
    cat_colors = {"electronics":"#00ff88","apparel":"#38bdf8","home":"#a78bfa","books":"#fb923c","food":"#f472b6"}
    fig1 = go.Figure()
    for cat in CATEGORIES:
        sub = df_recs[df_recs["category"]==cat]["recommended_price"]
        if len(sub):
            fig1.add_trace(go.Violin(y=sub, name=cat.upper(), box_visible=True, meanline_visible=True,
                                     fillcolor=cat_colors.get(cat,"#00ff88"),
                                     line_color=cat_colors.get(cat,"#00ff88"), opacity=0.7))
    fig1.update_layout(title="PRICE DISTRIBUTION BY CATEGORY", showlegend=False, uirevision="constant", **CHART_THEME, height=360)
    st.plotly_chart(fig1, use_container_width=True, config={"displayModeBar": False})

with c2:
    cat_chg = df_recs.groupby("category")["price_change_pct"].mean().reset_index()
    bar_colors = ["#00ff88" if v > 0 else "#ff4d6d" for v in cat_chg["price_change_pct"]]
    fig2 = go.Figure(go.Bar(x=cat_chg["category"].str.upper(), y=cat_chg["price_change_pct"],
                            marker_color=bar_colors, marker_line_width=0,
                            text=cat_chg["price_change_pct"].apply(lambda x: f"{x:+.1f}%"),
                            textposition="outside", textfont=dict(family="DM Mono", size=10)))
    fig2.add_hline(y=0, line_color="#1e3a5f", line_width=1)
    fig2.update_layout(title="AVG PRICE CHANGE BY CATEGORY", uirevision="constant", **CHART_THEME, height=360)
    st.plotly_chart(fig2, use_container_width=True, config={"displayModeBar": False})

c3, c4 = st.columns(2)
with c3:
    if rev_trend:
        df_t = pd.DataFrame(rev_trend)
        fig3 = go.Figure()
        trend_colors = ["#00ff88","#38bdf8","#a78bfa","#fb923c","#f472b6"]
        for cat, col in zip(CATEGORIES, trend_colors):
            if cat in df_t.columns:
                r, g, b = int(col[1:3],16), int(col[3:5],16), int(col[5:7],16)
                fig3.add_trace(go.Scatter(x=df_t["hour"], y=df_t[cat], mode="lines", name=cat.upper(),
                                          line=dict(color=col, width=1.5), fill="tonexty",
                                          fillcolor=f"rgba({r},{g},{b},0.06)"))
        fig3.update_layout(title="REVENUE TREND - LAST 24H", **CHART_THEME,
                           legend=dict(font=dict(family="DM Mono", size=9)),
                           uirevision="constant", height=360)
        st.plotly_chart(fig3, use_container_width=True, config={"displayModeBar": False})

with c4:
    _sample = df_recs.sample(min(200, len(df_recs)), random_state=42)
    fig4 = go.Figure(go.Scatter(
        x=_sample["demand"],
        y=_sample["inventory_ratio"],
        mode="markers",
        marker=dict(color=_sample["price_change_pct"],
                    colorscale=[[0,"#ff4d6d"],[0.5,"#f59e0b"],[1,"#00ff88"]],
                    size=5, showscale=True,
                    colorbar=dict(title=dict(text="Delta%", font=dict(family="DM Mono",size=9)),
                                  tickfont=dict(family="DM Mono",size=8), thickness=8)),
        text=_sample["category"],
    ))
    fig4.update_layout(title="DEMAND vs INVENTORY - PRICE CHANGE HEATMAP",
                       xaxis_title="DEMAND (orders/h)", yaxis_title="INVENTORY RATIO",
                       uirevision="constant", **CHART_THEME, height=360)
    st.plotly_chart(fig4, use_container_width=True, config={"displayModeBar": False})

# Event Log
st.markdown('<div class="sh">LIVE PRICING EVENTS</div>', unsafe_allow_html=True)
if events:
    filt = st.selectbox("FILTER ACTION", ["All","Increase","Decrease","Hold"], label_visibility="collapsed")
    df_ev = pd.DataFrame(events)
    if filt != "All": df_ev = df_ev[df_ev["action"]==filt]
    event_html = '<div style="background:#070d1a;border:1px solid #0f2d4a;border-radius:4px;padding:12px 16px;max-height:380px;overflow-y:auto;">'
    for _, ev in df_ev.head(40).iterrows():
        color = "#00ff88" if ev["action"]=="Increase" else ("#ff4d6d" if ev["action"]=="Decrease" else "#f59e0b")
        sym = "UP" if ev["action"]=="Increase" else ("DN" if ev["action"]=="Decrease" else "--")
        event_html += f"""<div style="border-bottom:1px solid #0a1628;padding:8px 0;display:flex;gap:12px;align-items:center;font-family:'DM Mono',monospace;font-size:10px">
          <span style="color:#334155;min-width:52px">{ev['timestamp']}</span>
          <span style="color:#475569;min-width:70px">{str(ev['category']).upper()}</span>
          <span style="color:{color};min-width:30px">{sym}</span>
          <span style="font-family:'Space Mono',monospace;font-size:11px;color:#e2e8f0;min-width:130px">Rs {ev['prev_price']:,.0f} to Rs {ev['new_price']:,.0f}</span>
          <span style="color:#475569">{ev['reason']}</span>
        </div>"""
    event_html += "</div>"
    st.markdown(event_html, unsafe_allow_html=True)
    st.download_button("Download Event Log", df_ev.to_csv(index=False).encode(), "events.csv", mime="text/csv")

# System Health
st.markdown('<div class="sh">SYSTEM HEALTH</div>', unsafe_allow_html=True)
h1, h2, h3, h4 = st.columns(4)
sc = "#00ff88" if health.get("status")=="healthy" else "#ff4d6d"
with h1:
    st.markdown(f'<div class="kcard"><div class="kl">API STATUS</div><div style="font-family:Space Mono,monospace;font-size:14px;color:{sc};margin-top:6px">{health.get("status","unknown").upper()}</div><div class="kd" style="color:#475569">Uptime {health.get("uptime_seconds",0)/3600:.1f}h</div></div>', unsafe_allow_html=True)
with h2:
    st.markdown(f'<div class="kcard"><div class="kl">MODEL</div><div style="font-family:Space Mono,monospace;font-size:14px;color:#e2e8f0;margin-top:6px">{health.get("model_version","N/A")}</div><div class="kd" style="color:#00ff88">MAE Rs {health.get("model_accuracy_mae",0):.1f}</div></div>', unsafe_allow_html=True)
with h3:
    st.markdown(f'<div class="kcard"><div class="kl">PREDICTIONS</div><div style="font-family:Space Mono,monospace;font-size:14px;color:#e2e8f0;margin-top:6px">{health.get("predictions_served",0):,}</div><div class="kd" style="color:#475569">Since server start</div></div>', unsafe_allow_html=True)
with h4:
    st.markdown('<div class="kcard"><div class="kl">KAFKA</div><div style="font-family:Space Mono,monospace;font-size:14px;color:#f59e0b;margin-top:6px">MOCK MODE</div><div class="kd" style="color:#475569">No broker connected</div></div>', unsafe_allow_html=True)
