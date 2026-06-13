import streamlit as st
import sqlite3
import pandas as pd
import sys
import os
import time
import plotly.graph_objects as go
import plotly.express as px
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path, override=True)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

DB_PATH = Path(__file__).resolve().parent.parent / "database" / "trades.db"

st.set_page_config(
    page_title  = "Trading AI Dashboard",
    page_icon   = "chart_with_upwards_trend",
    layout      = "wide",
    initial_sidebar_state = "collapsed"
)

st.markdown("""
<style>
    .main { padding: 1rem 1.5rem; }
    .metric-card {
        background: #ffffff;
        border: 0.5px solid #e5e7eb;
        border-radius: 10px;
        padding: 1rem 1.2rem;
        margin-bottom: 0.5rem;
    }
    .metric-label { font-size: 12px; color: #6b7280; margin-bottom: 4px; }
    .metric-value { font-size: 22px; font-weight: 500; color: #111827; }
    .metric-sub   { font-size: 11px; color: #9ca3af; margin-top: 2px; }
    .pos { color: #15803d; }
    .neg { color: #b91c1c; }
    .section-title {
        font-size: 11px; font-weight: 500; color: #6b7280;
        text-transform: uppercase; letter-spacing: 0.05em;
        margin-bottom: 10px;
    }
    .trade-card {
        background: #f9fafb;
        border: 0.5px solid #e5e7eb;
        border-radius: 8px;
        padding: 10px 14px;
        margin-bottom: 8px;
    }
    .badge {
        display: inline-block;
        font-size: 11px;
        padding: 2px 8px;
        border-radius: 20px;
        font-weight: 500;
    }
    .buy-badge  { background: #dcfce7; color: #15803d; }
    .sell-badge { background: #fee2e2; color: #b91c1c; }
    .hold-badge { background: #fef3c7; color: #92400e; }
    .news-item  { padding: 6px 0; border-bottom: 0.5px solid #f3f4f6; }
    .news-title { font-size: 13px; color: #111827; line-height: 1.4; }
    .news-meta  { font-size: 11px; color: #9ca3af; margin-top: 2px; }
    .ai-card {
        background: #f9fafb;
        border: 0.5px solid #e5e7eb;
        border-radius: 8px;
        padding: 10px 14px;
        margin-bottom: 8px;
    }
    .kill-btn {
        background: #fee2e2 !important;
        color: #b91c1c !important;
        border: 1px solid #fca5a5 !important;
    }
    div[data-testid="stMetric"] {
        background: #f9fafb;
        border: 0.5px solid #e5e7eb;
        border-radius: 10px;
        padding: 12px 16px;
    }
</style>
""", unsafe_allow_html=True)


def get_db_connection():
    if not DB_PATH.exists():
        return None
    return sqlite3.connect(DB_PATH)


def get_account_data():
    try:
        from broker.oanda import get_account_summary, get_price
        account = get_account_summary()
        price   = get_price("EUR_USD")
        return account, price
    except Exception as e:
        return None, None


def get_open_trades_data():
    try:
        from broker.oanda import get_open_trades
        return get_open_trades()
    except:
        return []


def get_trade_history():
    conn = get_db_connection()
    if not conn:
        return pd.DataFrame()
    try:
        df = pd.read_sql_query("""
            SELECT trade_id, instrument, direction, entry_price,
                   exit_price, pnl, pnl_pips, outcome,
                   duration_minutes, open_time, close_time,
                   ai_confidence, ai_reasoning
            FROM trades ORDER BY id DESC LIMIT 50
        """, conn)
        conn.close()
        return df
    except:
        conn.close()
        return pd.DataFrame()


def get_stats():
    conn = get_db_connection()
    if not conn:
        return {}
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN outcome='WIN'  THEN 1 ELSE 0 END) as wins,
                   SUM(CASE WHEN outcome='LOSS' THEN 1 ELSE 0 END) as losses,
                   SUM(pnl) as total_pnl,
                   AVG(pnl) as avg_pnl,
                   MAX(pnl) as best,
                   MIN(pnl) as worst
            FROM trades WHERE status='CLOSED'
        """)
        row = cur.fetchone()
        conn.close()
        if row and row[0]:
            return {
                "total": row[0] or 0,
                "wins":  row[1] or 0,
                "losses":row[2] or 0,
                "total_pnl": row[3] or 0,
                "avg_pnl":   row[4] or 0,
                "best":      row[5] or 0,
                "worst":     row[6] or 0,
                "win_rate":  round((row[1] or 0) / row[0] * 100, 1) if row[0] else 0
            }
    except:
        pass
    return {}


def get_strategy_rules():
    conn = get_db_connection()
    if not conn:
        return []
    try:
        cur = conn.cursor()
        cur.execute("SELECT rule, created_at FROM strategy_rules WHERE active=1 ORDER BY id DESC")
        rows = cur.fetchall()
        conn.close()
        return rows
    except:
        return []


# ── TOP BAR ──
col_title, col_time, col_kill = st.columns([3, 2, 1])
with col_title:
    st.markdown("### Trading AI Dashboard")
with col_time:
    st.markdown(
        f"<p style='text-align:right; color:#6b7280; font-size:13px; margin-top:8px;'>"
        f"{datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}</p>",
        unsafe_allow_html=True
    )
with col_kill:
    if st.button("KILL SWITCH", type="secondary", use_container_width=True):
        try:
            from broker.orders import close_all_trades
            close_all_trades()
            st.error("All trades closed. AI stopped.")
        except Exception as e:
            st.error(f"Error: {e}")

st.divider()

# ── ACCOUNT METRICS ──
account, current_price = get_account_data()

balance      = float(account["balance"])       if account else 100000
open_count   = int(account["openTradeCount"])  if account else 0
unrealized   = float(account["unrealizedPL"])  if account else 0
stats        = get_stats()
win_rate     = stats.get("win_rate", 0)
total_pnl    = stats.get("total_pnl", 0)

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Account Balance",  f"${balance:,.2f}")
m2.metric("Unrealized P&L",   f"${unrealized:,.2f}", delta=f"{unrealized:+.2f}")
m3.metric("Open Trades",      f"{open_count} / 3")
m4.metric("Win Rate",         f"{win_rate}%")
m5.metric("Total P&L",        f"${total_pnl:,.2f}", delta=f"{total_pnl:+.2f}")

st.divider()

# ── MAIN CONTENT ──
left, right = st.columns([3, 2])

df_trades = get_trade_history()

with left:
    # Price chart
    st.markdown('<div class="section-title">EUR/USD Live Price</div>', unsafe_allow_html=True)
    try:
        from data.price_feed import get_candles
        df_chart = get_candles("EUR_USD", "H1", 50)
        if df_chart is not None and not df_chart.empty:
            fig = go.Figure(data=[go.Candlestick(
                x     = df_chart.index,
                open  = df_chart["open"],
                high  = df_chart["high"],
                low   = df_chart["low"],
                close = df_chart["close"],
                increasing_line_color = "#15803d",
                decreasing_line_color = "#b91c1c",
            )])
            fig.update_layout(
                height          = 280,
                margin          = dict(l=0, r=0, t=0, b=0),
                xaxis_rangeslider_visible = False,
                plot_bgcolor    = "white",
                paper_bgcolor   = "white",
                xaxis           = dict(gridcolor="#f3f4f6"),
                yaxis           = dict(gridcolor="#f3f4f6"),
            )
            st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        st.info(f"Chart loading... ({e})")

    # Trade history
    st.markdown('<div class="section-title">Trade History</div>', unsafe_allow_html=True)
    if not df_trades.empty:
        display = df_trades[["trade_id","instrument","direction",
                              "entry_price","exit_price","pnl",
                              "pnl_pips","outcome","duration_minutes"]].copy()
        display.columns = ["ID","Pair","Dir","Entry","Exit",
                           "P&L","Pips","Result","Duration(min)"]
        display["P&L"]  = display["P&L"].apply(
            lambda x: f"+${x:,.2f}" if x and x >= 0 else f"-${abs(x):,.2f}" if x else "-"
        )
        st.dataframe(display, use_container_width=True, height=200)
    else:
        st.info("No trades yet.")

    # P&L chart
    if not df_trades.empty and "pnl" in df_trades.columns:
        closed = df_trades[df_trades["outcome"].notna()].copy()
        if not closed.empty:
            closed["cumulative_pnl"] = closed["pnl"].fillna(0).iloc[::-1].cumsum().iloc[::-1]
            st.markdown('<div class="section-title">Cumulative P&L</div>', unsafe_allow_html=True)
            fig2 = px.area(
                closed.iloc[::-1], y="cumulative_pnl",
                color_discrete_sequence=["#15803d"]
            )
            fig2.update_layout(
                height        = 150,
                margin        = dict(l=0, r=0, t=0, b=0),
                plot_bgcolor  = "white",
                paper_bgcolor = "white",
                xaxis_visible = False,
                yaxis_title   = "P&L ($)"
            )
            st.plotly_chart(fig2, use_container_width=True)

with right:
    # Open positions
    st.markdown('<div class="section-title">Open Positions</div>', unsafe_allow_html=True)
    open_trades = get_open_trades_data()
    if open_trades:
        for t in open_trades:
            pl     = float(t.get("unrealizedPL", 0))
            units  = float(t.get("currentUnits", 0))
            pl_col = "#15803d" if pl >= 0 else "#b91c1c"
            badge  = "buy-badge" if units > 0 else "sell-badge"
            direc  = "BUY" if units > 0 else "SELL"
            st.markdown(f"""
            <div class="trade-card">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <div>
                        <span style="font-weight:500; font-size:14px;">{t.get('instrument','')}</span>
                        &nbsp;<span class="badge {badge}">{direc}</span>
                    </div>
                    <span style="font-weight:500; color:{pl_col};">${pl:,.2f}</span>
                </div>
                <div style="font-size:11px; color:#9ca3af; margin-top:4px;">
                    Units: {abs(units):,.0f} · ID: {t.get('id','')}
                </div>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.info("No open positions.")

    # AI decisions
    st.markdown('<div class="section-title">AI Brain — Recent Decisions</div>', unsafe_allow_html=True)
    if not df_trades.empty:
        recent = df_trades.head(3)
        for _, row in recent.iterrows():
            reasoning = str(row.get("ai_reasoning",""))[:150] if row.get("ai_reasoning") else "No reasoning logged."
            conf      = row.get("ai_confidence","")
            st.markdown(f"""
            <div class="ai-card">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
                    <span style="font-size:13px; font-weight:500;">{row.get('instrument','EUR_USD')}</span>
                    <span class="badge buy-badge">{row.get('direction','')}</span>
                </div>
                <div style="font-size:11px; color:#6b7280;">Confidence: {conf}%</div>
                <div style="font-size:11px; color:#374151; margin-top:4px; line-height:1.5;">{reasoning}...</div>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.info("No AI decisions yet.")

    # Strategy rules
    st.markdown('<div class="section-title">Learned Strategy Rules</div>', unsafe_allow_html=True)
    rules = get_strategy_rules()
    if rules:
        for i, (rule, created) in enumerate(rules, 1):
            st.markdown(f"""
            <div style="padding:6px 0; border-bottom:0.5px solid #f3f4f6; font-size:12px;">
                <span style="color:#6b7280; margin-right:6px;">{i}.</span>
                <span style="color:#111827;">{rule}</span>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.info("No learned rules yet.")

    # Performance stats
    st.markdown('<div class="section-title">Performance Stats</div>', unsafe_allow_html=True)
    if stats:
        s1, s2 = st.columns(2)
        s1.metric("Total Trades", stats.get("total", 0))
        s2.metric("Win Rate",     f"{stats.get('win_rate',0)}%")
        s3, s4 = st.columns(2)
        s3.metric("Best Trade",  f"${stats.get('best',0):,.2f}")
        s4.metric("Worst Trade", f"${stats.get('worst',0):,.2f}")

st.divider()
st.markdown(
    f"<p style='text-align:center; font-size:11px; color:#9ca3af;'>"
    f"Trading AI · Running autonomously · Refreshes every 30 seconds</p>",
    unsafe_allow_html=True
)

time.sleep(30)
st.rerun()
