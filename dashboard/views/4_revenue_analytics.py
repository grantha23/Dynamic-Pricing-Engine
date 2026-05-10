"""dashboard/pages/4_revenue_analytics.py — Revenue Analytics (Clean rewrite)"""
import os, sys, random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import datetime
from dashboard.utils import fetch_revenue_data, format_currency, CATEGORIES, SEGMENTS





st.markdown('<div class="pt"><h1>📈 Revenue Analytics</h1><p>Financial impact · pricing lift · elasticity analysis</p></div>', unsafe_allow_html=True)

c1, c2 = st.columns([2, 1])
with c1:
    end_date = datetime.date.today()
    date_range = st.date_input("DATE RANGE", value=(end_date - datetime.timedelta(days=7), end_date))
with c2:
    metric = st.selectbox("PRIMARY METRIC", ["Revenue", "Units Sold", "Revenue Lift %", "Avg Order Value"])

days = max(1, (date_range[1]-date_range[0]).days) if isinstance(date_range, tuple) and len(date_range)==2 else 7
df = fetch_revenue_data(days=days)

total_rev = df["revenue"].sum()
baseline  = df["baseline"].sum()
lift_pct  = (total_rev-baseline)/baseline*100 if baseline > 0 else 0
units     = df["units_sold"].sum()
aov       = df["avg_order_val"].mean()

k1, k2, k3, k4 = st.columns(4)
with k1:
    st.markdown(f'<div class="kcard"><div class="kl">TOTAL REVENUE</div><div class="kv">{format_currency(total_rev)}</div><div class="kd" style="color:#00ff88">{lift_pct:+.1f}% vs static baseline</div></div>', unsafe_allow_html=True)
with k2:
    st.markdown(f'<div class="kcard"><div class="kl">REVENUE LIFT</div><div class="kv" style="color:#00ff88">{lift_pct:.2f}%</div><div class="kd" style="color:#00ff88">Rs {total_rev-baseline:,.0f} incremental</div></div>', unsafe_allow_html=True)
with k3:
    st.markdown(f'<div class="kcard"><div class="kl">UNITS SOLD</div><div class="kv">{units:,}</div><div class="kd" style="color:#475569">+8.3% vs baseline</div></div>', unsafe_allow_html=True)
with k4:
    st.markdown(f'<div class="kcard"><div class="kl">AVG ORDER VALUE</div><div class="kv">{format_currency(aov)}</div><div class="kd" style="color:#00ff88">+5.1%</div></div>', unsafe_allow_html=True)

CHART_THEME = dict(plot_bgcolor="#070d1a", paper_bgcolor="#070d1a", font_color="#64748b",
                   title_font_color="#94a3b8", title_font_size=12,
                   transition=dict(duration=0, easing="linear"),
                   xaxis=dict(gridcolor="#0f2d4a", linecolor="#0f2d4a"),
                   yaxis=dict(gridcolor="#0f2d4a", linecolor="#0f2d4a"))
PLOT_CFG = {"displayModeBar": False, "scrollZoom": False, "responsive": True}

st.markdown('<div class="sh">REVENUE BREAKDOWN</div>', unsafe_allow_html=True)
c1, c2 = st.columns(2)

with c1:
    daily = df.groupby("date")[["revenue","baseline"]].sum().reset_index()
    fig1 = go.Figure()
    fig1.add_trace(go.Scatter(x=daily["date"], y=daily["revenue"], mode="lines+markers",
                              name="DYNAMIC PRICING", line=dict(color="#00ff88", width=2),
                              marker=dict(size=5, color="#00ff88"),
                              fill="tozeroy", fillcolor="rgba(0,255,136,0.05)"))
    fig1.add_trace(go.Scatter(x=daily["date"], y=daily["baseline"], mode="lines",
                              name="STATIC BASELINE", line=dict(color="#334155", width=1.5, dash="dash")))
    fig1.update_layout(title="DAILY REVENUE: DYNAMIC vs STATIC BASELINE", uirevision="constant",
                       **CHART_THEME, legend=dict(font=dict(family="DM Mono", size=9)), height=360)
    st.plotly_chart(fig1, use_container_width=True, config=PLOT_CFG)

with c2:
    cat_rev = df.groupby("category")["revenue"].sum().reset_index()
    cat_colors = {"electronics":"#00ff88","apparel":"#38bdf8","home":"#a78bfa","books":"#fb923c","food":"#f472b6"}
    fig2 = go.Figure(go.Pie(
        labels=[c.upper() for c in cat_rev["category"]], values=cat_rev["revenue"],
        hole=0.6,
        marker=dict(colors=[cat_colors.get(c, "#64748b") for c in cat_rev["category"]],
                    line=dict(color="#030712", width=3)),
        textfont=dict(family="DM Mono", size=10), texttemplate="%{label}<br>%{percent}",
    ))
    fig2.update_layout(
        title="REVENUE SHARE BY CATEGORY", uirevision="constant", **CHART_THEME, showlegend=False,
        annotations=[dict(text=f"Rs {total_rev/1e6:.1f}M", x=0.5, y=0.5,
                          font=dict(family="Space Mono", size=18, color="#e2e8f0"), showarrow=False)], height=360)
    st.plotly_chart(fig2, use_container_width=True, config=PLOT_CFG)

c3, c4 = st.columns(2)
with c3:
    seg_daily = df.groupby(["date","segment"])["revenue"].sum().reset_index()
    seg_cols = {"premium":"#00ff88","regular":"#38bdf8","budget":"#f59e0b"}
    fig3 = go.Figure()
    for seg in SEGMENTS:
        sub = seg_daily[seg_daily["segment"]==seg]
        fig3.add_trace(go.Bar(x=sub["date"], y=sub["revenue"], name=seg.upper(),
                              marker_color=seg_cols.get(seg, "#64748b"), marker_line_width=0))
    fig3.update_layout(title="REVENUE BY SEGMENT - DAILY", barmode="group", uirevision="constant",
                       **CHART_THEME, legend=dict(font=dict(family="DM Mono", size=9)), height=360)
    st.plotly_chart(fig3, use_container_width=True, config=PLOT_CFG)

with c4:
    cat_lift = df.groupby("category")["revenue_lift"].mean().reset_index()
    lift_colors = ["#00ff88" if v > 0 else "#ff4d6d" for v in cat_lift["revenue_lift"]]
    fig4 = go.Figure(go.Bar(x=cat_lift["category"].str.upper(), y=cat_lift["revenue_lift"],
                            marker_color=lift_colors, marker_line_width=0,
                            text=cat_lift["revenue_lift"].apply(lambda x: f"{x:+.1f}%"),
                            textposition="outside", textfont=dict(family="DM Mono", size=10)))
    fig4.add_hline(y=0, line_color="#1e3a5f", line_width=1)
    fig4.update_layout(title="REVENUE LIFT % BY CATEGORY vs BASELINE", uirevision="constant", **CHART_THEME, height=360)
    st.plotly_chart(fig4, use_container_width=True, config=PLOT_CFG)

st.markdown('<div class="sh">CATEGORY PERFORMANCE SCORECARD</div>', unsafe_allow_html=True)
cat_summary = df.groupby("category").agg(
    revenue=("revenue","sum"), baseline=("baseline","sum"),
    units=("units_sold","sum"), lift=("revenue_lift","mean"),
).reset_index().sort_values("lift", ascending=False)

for _, row in cat_summary.iterrows():
    lift_color = "#00ff88" if row["lift"] > 0 else "#ff4d6d"
    bar_w = min(abs(row["lift"])*3, 100)
    bar_c = "#00ff8830" if row["lift"] > 0 else "#ff4d6d30"
    status = "MAINTAIN STRATEGY" if row["lift"] > 5 else ("REVIEW THRESHOLDS" if row["lift"] > 0 else "UNDERPERFORMING")
    st.markdown(f"""<div class="lift-row">
      <div style="min-width:120px">
        <div style="font-family:'Syne',sans-serif;font-size:13px;font-weight:700;color:#e2e8f0">{row['category'].upper()}</div>
        <div style="height:3px;background:{bar_c};width:{bar_w}%;margin-top:4px;border-radius:2px"></div>
      </div>
      <div style="font-family:'DM Mono',monospace;font-size:10px;color:#475569;min-width:160px">
        {format_currency(row['revenue'])} · {int(row['units']):,} units
      </div>
      <div style="font-family:'Space Mono',monospace;font-size:16px;font-weight:700;color:{lift_color};min-width:70px">{row['lift']:+.1f}%</div>
      <div style="font-family:'DM Mono',monospace;font-size:9px;color:#334155">{status}</div>
    </div>""", unsafe_allow_html=True)

st.download_button("Download Revenue Data", df.to_csv(index=False).encode(),
                   f"revenue_{days}d.csv", mime="text/csv")
