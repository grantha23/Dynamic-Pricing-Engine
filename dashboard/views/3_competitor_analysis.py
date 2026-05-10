"""
dashboard/pages/3_competitor_analysis.py — Competitor Analysis (Trading Terminal UI)
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from dashboard.utils import fetch_competitor_prices, CATEGORIES





st.markdown('<div class="pt"><h1>🏪 Competitor Analysis</h1><p>Real-time price intelligence · gap analysis · market positioning</p></div>', unsafe_allow_html=True)

df = fetch_competitor_prices()

# KPI strip
k1, k2, k3, k4 = st.columns(4)
overpriced = (df["avg_gap_pct"] > 10).sum()
cheaper    = (df["avg_gap_pct"] < -5).sum()
matched    = len(df) - overpriced - cheaper
with k1:
    st.markdown(f'<div class="kcard"><div class="kl">TOTAL PRODUCTS</div><div class="kv">{len(df):,}</div><div class="kd" style="color:#475569">under monitoring</div></div>', unsafe_allow_html=True)
with k2:
    st.markdown(f'<div class="kcard"><div class="kl">OVERPRICED vs COMPS</div><div class="kv" style="color:#ff4d6d">{overpriced:,}</div><div class="kd" style="color:#ff4d6d">revenue at risk</div></div>', unsafe_allow_html=True)
with k3:
    st.markdown(f'<div class="kcard"><div class="kl">WE ARE CHEAPER</div><div class="kv" style="color:#00ff88">{cheaper:,}</div><div class="kd" style="color:#00ff88">uplift potential</div></div>', unsafe_allow_html=True)
with k4:
    st.markdown(f'<div class="kcard"><div class="kl">PRICE MATCHED</div><div class="kv" style="color:#f59e0b">{matched:,}</div><div class="kd" style="color:#475569">within +/-5%</div></div>', unsafe_allow_html=True)

# Filters
st.markdown('<div class="sh">FILTERS</div>', unsafe_allow_html=True)
fc1, fc2, fc3 = st.columns(3)
with fc1: sel_cats = st.multiselect("CATEGORY", CATEGORIES, default=CATEGORIES)
with fc2: pos_filter = st.selectbox("POSITION", ["All", "Overpriced (>10%)", "Matched (+/-5%)", "Cheaper (<-5%)"])
with fc3: sort_gap = st.selectbox("SORT BY GAP", ["Largest Overprice", "Largest Underprice", "Category"])

if sel_cats: df = df[df["category"].isin(sel_cats)]
if pos_filter == "Overpriced (>10%)":  df = df[df["avg_gap_pct"] > 10]
elif pos_filter == "Matched (+/-5%)":  df = df[df["avg_gap_pct"].between(-5, 5)]
elif pos_filter == "Cheaper (<-5%)":   df = df[df["avg_gap_pct"] < -5]
if sort_gap == "Largest Overprice":    df = df.sort_values("avg_gap_pct", ascending=False)
elif sort_gap == "Largest Underprice": df = df.sort_values("avg_gap_pct", ascending=True)
else:                                  df = df.sort_values("category")

# Charts
st.markdown('<div class="sh">PRICE GAP ANALYSIS</div>', unsafe_allow_html=True)
c1, c2 = st.columns(2)

CHART_THEME = dict(
    plot_bgcolor="#070d1a", paper_bgcolor="#070d1a", font_color="#64748b",
    title_font_color="#94a3b8", title_font_size=12,
    transition=dict(duration=0, easing="linear"),
    xaxis=dict(gridcolor="#0f2d4a", linecolor="#0f2d4a"),
    yaxis=dict(gridcolor="#0f2d4a", linecolor="#0f2d4a"),
)
PLOT_CFG = {"displayModeBar": False, "scrollZoom": False, "responsive": True}

with c1:
    cat_gap = df.groupby("category")["avg_gap_pct"].mean().reset_index()
    cols_bar = ["#00ff88" if v < -5 else ("#ff4d6d" if v > 10 else "#f59e0b") for v in cat_gap["avg_gap_pct"]]
    fig1 = go.Figure(go.Bar(
        x=cat_gap["category"].str.upper(), y=cat_gap["avg_gap_pct"],
        marker_color=cols_bar, marker_line_width=0,
        text=cat_gap["avg_gap_pct"].apply(lambda x: f"{x:+.1f}%"),
        textposition="outside", textfont=dict(family="DM Mono", size=10),
    ))
    fig1.add_hline(y=0, line_color="#1e3a5f", line_width=1)
    fig1.add_hrect(y0=-5, y1=5, fillcolor="rgba(245,158,11,0.03)", line_width=0)
    fig1.update_layout(title="AVG PRICE GAP vs COMPETITOR (+ = WE ARE EXPENSIVE)", **CHART_THEME, height=360)
    st.plotly_chart(fig1, use_container_width=True)

with c2:
    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(
        x=df["our_price"], y=df["avg_competitor"],
        mode="markers",
        marker=dict(
            color=df["avg_gap_pct"],
            colorscale=[[0, "#00ff88"], [0.5, "#f59e0b"], [1, "#ff4d6d"]],
            size=4, showscale=True,
            colorbar=dict(title=dict(text="Gap %", font=dict(family="DM Mono", size=9)),
                         tickfont=dict(family="DM Mono", size=8), thickness=8),
        ),
        text=df["category"],
        hovertemplate="Our: %{x:,.0f}<br>Comp: %{y:,.0f}<br>Category: %{text}<extra></extra>",
    ))
    min_p = min(df["our_price"].min(), df["avg_competitor"].min())
    max_p = max(df["our_price"].max(), df["avg_competitor"].max())
    fig2.add_trace(go.Scatter(
        x=[min_p, max_p], y=[min_p, max_p],
        mode="lines", line=dict(color="#1e3a5f", dash="dash", width=1), showlegend=False,
    ))
    fig2.update_layout(
        title="OUR PRICE vs AVG COMPETITOR (DIAGONAL = PARITY)",
        xaxis_title="OUR PRICE", yaxis_title="COMPETITOR PRICE", **CHART_THEME, height=360)
    st.plotly_chart(fig2, use_container_width=True)

# Opportunity list
st.markdown('<div class="sh">TOP OPPORTUNITIES</div>', unsafe_allow_html=True)
tc1, tc2 = st.columns(2)

with tc1:
    st.markdown("**🔴 URGENT: Reduce Price (Most Overpriced)**")
    top_over = df[df["avg_gap_pct"] > 5].nlargest(8, "avg_gap_pct")
    for _, row in top_over.iterrows():
        st.markdown(f"""<div class="opp-card">
          <div><div class="opp-id">#{row['product_id']}</div><div class="opp-cat">{row['category'].upper()}</div></div>
          <div style="text-align:center"><div class="opp-gap gap-over">+{row['avg_gap_pct']:.1f}%</div>
          <div style="font-family:'DM Mono',monospace;font-size:9px;color:#475569">above comp</div></div>
          <div><span class="action-tag at-match">MATCH</span></div>
        </div>""", unsafe_allow_html=True)

with tc2:
    st.markdown("**🟢 OPPORTUNITY: Raise Price (We Are Cheaper)**")
    top_under = df[df["avg_gap_pct"] < -5].nsmallest(8, "avg_gap_pct")
    for _, row in top_under.iterrows():
        st.markdown(f"""<div class="opp-card">
          <div><div class="opp-id">#{row['product_id']}</div><div class="opp-cat">{row['category'].upper()}</div></div>
          <div style="text-align:center"><div class="opp-gap gap-under">{row['avg_gap_pct']:.1f}%</div>
          <div style="font-family:'DM Mono',monospace;font-size:9px;color:#475569">below comp</div></div>
          <div><span class="action-tag at-prem">PREMIUM</span></div>
        </div>""", unsafe_allow_html=True)

# Full table
st.markdown('<div class="sh">FULL COMPARISON TABLE</div>', unsafe_allow_html=True)
disp = df[["product_id", "category", "our_price", "competitor_a", "competitor_b",
           "avg_competitor", "avg_gap_pct", "position"]].copy()
disp.columns = ["ID", "Category", "Our Price", "Comp A", "Comp B", "Avg Comp", "Gap %", "Position"]
for c in ["Our Price", "Comp A", "Comp B", "Avg Comp"]:
    disp[c] = disp[c].apply(lambda x: f"Rs {x:,.0f}")
disp["Gap %"] = disp["Gap %"].apply(lambda x: f"{x:+.1f}%")
st.dataframe(disp, use_container_width=True, height=350)
st.download_button("Download CSV", df.to_csv(index=False).encode(), "competitor_prices.csv", mime="text/csv")
