"""
dashboard/app.py — VerdictAI Dashboard (Layer 6)
Run: streamlit run dashboard/app.py
"""

import os
import sqlite3
import pandas as pd
import streamlit as st
import plotly.express as px
from datetime import datetime

DB_PATH = os.getenv("SENTINEL_DB", "memory/sentinel.db")

st.set_page_config(
    page_title="VerdictAI",
    page_icon="⚖️",
    layout="wide",
)

# ── helpers ──────────────────────────────────────────────────────────────────

def _get_conn():
    return sqlite3.connect(DB_PATH)


def load_data() -> pd.DataFrame:
    try:
        with _get_conn() as conn:
            df = pd.read_sql_query(
                "SELECT * FROM results ORDER BY run_timestamp DESC", conn
            )
        return df
    except Exception:
        return pd.DataFrame()


# ── load ─────────────────────────────────────────────────────────────────────

df = load_data()

# ── header ───────────────────────────────────────────────────────────────────

st.title("⚖️ VerdictAI — LLM Eval Dashboard")
st.caption("Powered by Groq · SQLite · LangChain")

if df.empty:
    st.warning("No results found. Run a suite first: `python -m runner.main`")
    st.stop()

# ── sidebar filters ───────────────────────────────────────────────────────────

st.sidebar.header("Filters")

suites = ["All"] + sorted(df["suite_name"].unique().tolist())
selected_suite = st.sidebar.selectbox("Suite", suites)

if selected_suite != "All":
    df = df[df["suite_name"] == selected_suite]

verdicts = ["All", "PASS", "FAIL"]
selected_verdict = st.sidebar.selectbox("Verdict", verdicts)

if selected_verdict != "All":
    df = df[df["verdict"] == selected_verdict]

st.sidebar.markdown("---")
st.sidebar.metric("Total records", len(df))

# ── summary cards ─────────────────────────────────────────────────────────────

latest_run = df["run_timestamp"].max()
latest_df = df[df["run_timestamp"] == latest_run]

total  = len(latest_df)
passed = len(latest_df[latest_df["verdict"] == "PASS"])
failed = total - passed
avg_score = latest_df["score"].mean()

st.subheader("Latest Run Summary")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Total",  total)
c2.metric("✅ Passed", passed)
c3.metric("❌ Failed", failed)
c4.metric("Avg Score", f"{avg_score:.0f}" if not pd.isna(avg_score) else "N/A")

st.markdown("---")

# ── trend chart ───────────────────────────────────────────────────────────────

st.subheader("Pass / Fail Trend")

trend_df = (
    df.groupby(["run_timestamp", "verdict"])
    .size()
    .reset_index(name="count")
)

if not trend_df.empty:
    fig = px.bar(
        trend_df,
        x="run_timestamp",
        y="count",
        color="verdict",
        color_discrete_map={"PASS": "#22c55e", "FAIL": "#ef4444"},
        labels={"run_timestamp": "Run", "count": "Tests"},
        barmode="group",
    )
    fig.update_layout(
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        xaxis_tickangle=-30,
        legend_title="Verdict",
    )
    st.plotly_chart(fig, use_container_width=True)

st.markdown("---")

# ── score trend per test ──────────────────────────────────────────────────────

st.subheader("Score Trend by Test")

score_df = df.dropna(subset=["score"]).copy()
if not score_df.empty:
    fig2 = px.line(
        score_df.sort_values("run_timestamp"),
        x="run_timestamp",
        y="score",
        color="test_id",
        markers=True,
        labels={"run_timestamp": "Run", "score": "Judge Score"},
    )
    fig2.update_layout(
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        yaxis_range=[0, 105],
    )
    st.plotly_chart(fig2, use_container_width=True)

st.markdown("---")

# ── results table ─────────────────────────────────────────────────────────────

st.subheader("Test Results")

display_cols = ["run_timestamp", "suite_name", "test_id", "verdict", "score", "reason", "latency_ms"]
display_df = df[display_cols].copy()
display_df["run_timestamp"] = pd.to_datetime(display_df["run_timestamp"]).dt.strftime("%Y-%m-%d %H:%M:%S")

def _color_verdict(val):
    return "color: #22c55e" if val == "PASS" else "color: #ef4444"

st.dataframe(
    display_df.style.map(_color_verdict, subset=["verdict"]),
    use_container_width=True,
    height=400,
)

# ── export ────────────────────────────────────────────────────────────────────

csv = display_df.to_csv(index=False).encode("utf-8")
st.download_button(
    label="⬇️ Export as CSV",
    data=csv,
    file_name=f"verdictai_results_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv",
    mime="text/csv",
)