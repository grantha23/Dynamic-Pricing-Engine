"""dashboard/pages/1_recommendations.py — Price Recommendations (Clean rewrite)"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import streamlit as st
import pandas as pd
from datetime import datetime
from dashboard.utils import fetch_recommendations, apply_price_change, log_action, CATEGORIES, SEGMENTS





st.markdown('<div class="pt"><h1>📋 Recommendations</h1><p>AI-powered price optimization · approve and deploy changes at scale</p></div>', unsafe_allow_html=True)

with st.expander("FILTERS", expanded=True):
    c1, c2, c3, c4 = st.columns(4)
    with c1: sel_cats = st.multiselect("CATEGORY", CATEGORIES, default=CATEGORIES)
    with c2: price_range = st.slider("PRICE", 0, 100000, (0, 100000), step=1000)
    with c3: sel_segs = st.multiselect("SEGMENT", SEGMENTS, default=SEGMENTS)
    with c4:
        sort_col = st.selectbox("SORT", ["price_change_pct", "confidence_score", "demand", "recommended_price"])
        desc = st.checkbox("Descending", value=True)
    c5, c6 = st.columns(2)
    with c5: action_f = st.selectbox("ACTION", ["All", "Increase >1%", "Decrease <-1%", "Hold"])
    with c6: inv_f = st.selectbox("STOCK", ["Any", "Low <100", "Critical <10", "Surplus >9000"])

df = fetch_recommendations(400)
if sel_cats: df = df[df["category"].isin(sel_cats)]
if sel_segs: df = df[df["customer_segment"].isin(sel_segs)]
df = df[(df["base_price"] >= price_range[0]) & (df["base_price"] <= price_range[1])]
if action_f == "Increase >1%":    df = df[df["price_change_pct"] > 1]
elif action_f == "Decrease <-1%": df = df[df["price_change_pct"] < -1]
elif action_f == "Hold":          df = df[df["price_change_pct"].between(-1, 1)]
if inv_f == "Low <100":        df = df[df["inventory"] < 100]
elif inv_f == "Critical <10":  df = df[df["inventory"] < 10]
elif inv_f == "Surplus >9000": df = df[df["inventory"] > 9000]
df = df.sort_values(sort_col, ascending=not desc).reset_index(drop=True)

inc = (df["price_change_pct"] > 1).sum()
dec = (df["price_change_pct"] < -1).sum()
k1, k2, k3, k4, k5 = st.columns(5)
with k1: st.metric("TOTAL", f"{len(df):,}")
with k2: st.metric("INCREASE", f"{inc:,}", f"+{inc/max(len(df),1)*100:.0f}%")
with k3: st.metric("DECREASE", f"{dec:,}", f"-{dec/max(len(df),1)*100:.0f}%", delta_color="inverse")
with k4: st.metric("HOLD", f"{len(df)-inc-dec:,}")
with k5: st.metric("AVG CONFIDENCE", f"{df['confidence_score'].mean()*100:.1f}%")

st.markdown('<div class="sh">RECOMMENDATION TABLE</div>', unsafe_allow_html=True)
page = st.number_input("Page", min_value=1, max_value=max(1, (len(df)-1)//50+1), value=1, label_visibility="collapsed")
page_df = df.iloc[(page-1)*50:page*50].copy()
disp = page_df[["product_id","category","customer_segment","base_price","recommended_price","price_change_pct","demand","inventory","confidence_score"]].copy()
disp.columns = ["ID","Category","Segment","Base","Rec","Delta %","Demand /h","Stock","Conf %"]
disp["Base"]    = disp["Base"].apply(lambda x: f"Rs {x:,.0f}")
disp["Rec"]     = disp["Rec"].apply(lambda x: f"Rs {x:,.0f}")
disp["Delta %"] = disp["Delta %"].apply(lambda x: f"{x:+.1f}%")
disp["Conf %"]  = disp["Conf %"].apply(lambda x: f"{x*100:.1f}%")
disp["Demand /h"] = disp["Demand /h"].apply(lambda x: f"{x:.0f}")
st.dataframe(disp, use_container_width=True, height=400)

st.markdown('<div class="sh">ACTIONS</div>', unsafe_allow_html=True)
a1, a2, a3 = st.columns(3)
with a1:
    if st.button("Apply Top 10", use_container_width=True):
        n = 0
        for _, row in df.head(10).iterrows():
            r = apply_price_change(int(row["product_id"]), float(row["base_price"]),
                                   float(row["recommended_price"]/row["base_price"]), "Auto top-10")
            if r: n += 1
        log_action("BULK_TOP10", f"{n} applied")
        st.success(f"Applied {n} changes")
with a2:
    st.download_button("Download CSV", df.to_csv(index=False).encode(),
                       f"recs_{datetime.now().strftime('%Y%m%d_%H%M')}.csv", "text/csv", use_container_width=True)
with a3:
    if st.button("Reject All Shown", use_container_width=True):
        log_action("REJECT_BULK", f"{len(df)} rejected")
        st.info("Logged.")

st.markdown('<div class="sh">PRODUCT DEEP DIVE</div>', unsafe_allow_html=True)
pid = st.selectbox("PRODUCT ID", df["product_id"].unique()[:100], label_visibility="collapsed")
if pid is not None:
    rows = df[df["product_id"] == pid]
    if len(rows):
        p = rows.iloc[0]
        chg = p["price_change_pct"]
        pill = f'<span class="pill pu">Up {chg:+.1f}%</span>' if chg > 1 else (f'<span class="pill pd">Down {chg:+.1f}%</span>' if chg < -1 else f'<span class="pill ph">Hold {chg:+.1f}%</span>')
        inv_c = "r" if p["inventory"] < 100 else ("y" if p["inventory"] < 1000 else "g")
        d1, d2, d3 = st.columns(3)
        with d1:
            st.markdown(f"""<div class="card">
            <div style="font-family:'DM Mono',monospace;font-size:9px;color:#475569;letter-spacing:2px">PRODUCT {p['product_id']}</div>
            <div style="font-family:'Space Mono',monospace;font-size:18px;font-weight:700;color:#f1f5f9;margin:8px 0">
              Rs {p['base_price']:,.0f} to Rs {p['recommended_price']:,.0f}
            </div>
            {pill}
            <div class="mono" style="margin-top:12px">
              <div>CATEGORY   <span>{p['category'].upper()}</span></div>
              <div>SEGMENT    <span>{p['customer_segment'].upper()}</span></div>
              <div>CONFIDENCE <span class="g">{p['confidence_score']*100:.1f}%</span></div>
            </div></div>""", unsafe_allow_html=True)
        with d2:
            st.markdown(f"""<div class="card">
            <div style="font-family:'DM Mono',monospace;font-size:9px;color:#475569;letter-spacing:2px">MARKET SIGNALS</div>
            <div class="mono" style="margin-top:12px">
              <div>DEMAND    <span>{p['demand']:.0f} orders/h</span></div>
              <div>INVENTORY <span class="{inv_c}">{p['inventory']:,} units</span></div>
              <div>COMP PRICE <span>Rs {p['competitor_price']:,.0f}</span></div>
              <div>COMP GAP  <span class="y">{(p['base_price']-p['competitor_price'])/p['competitor_price']*100:+.1f}%</span></div>
            </div></div>""", unsafe_allow_html=True)
        with d3:
            if st.button("Apply Recommendation", key="apply_d", use_container_width=True):
                apply_price_change(int(p["product_id"]), float(p["base_price"]),
                                   float(p["recommended_price"]/p["base_price"]), "Deep dive apply")
                st.success("Applied!")
            custom = st.number_input("Custom Price (Rs)", value=float(p["base_price"]), min_value=1.0)
            if st.button("Set Custom Price", key="set_c", use_container_width=True):
                apply_price_change(int(p["product_id"]), float(p["base_price"]),
                                   custom/p["base_price"], "Custom override")
                st.success(f"Rs {custom:,.0f} set!")
            if st.button("Reject", key="rej_d", use_container_width=True):
                log_action("REJECT", f"product={pid}")
                st.info("Rejected.")
