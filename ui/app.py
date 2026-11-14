"""Streamlit control tower for the synthetic production schedule."""

from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path

import pandas as pd
import plotly.express as px
import requests
import streamlit as st

DATA_DIR = Path(os.getenv("SCHEDULING_DATA_DIR", "data"))
API_URL = os.getenv("SCHEDULING_API_URL", "http://127.0.0.1:8000")
EPOCH = pd.Timestamp("2026-01-01T00:00:00Z")
EPOCH_DATE = dt.date(2026, 1, 1)

st.set_page_config(page_title="Hackathon", layout="wide", initial_sidebar_state="auto")

# Shared colors keep the dashboard consistent; breakpoints adapt columns and text to smaller screens.
st.markdown(
    """<style>
    .stApp{background:#f3f6fb;color:#17243b}
    [data-testid="stMainBlockContainer"]{max-width:100%;padding:1.5rem}
    [data-testid="stSidebar"]{background:linear-gradient(175deg,#10243b,#142e4b 55%,#17615f)}
    [data-testid="stSidebar"] *{color:#eef5ff}
    [data-testid="stSidebar"] [data-baseweb="popover"] *,[data-testid="stSidebar"] [data-baseweb="select"] *,
    [data-testid="stSidebar"] [role="combobox"],[data-testid="stSidebar"] input{color:#17243b!important}
    [data-testid="stSidebar"] input::placeholder{color:#718096!important;opacity:1}
    [data-testid="stSidebar"] .status-pill{color:#087b61!important}
    [data-testid="stSidebar"] [data-testid="stMetric"]{background:#fff}
    [data-testid="stSidebar"] [data-testid="stMetricLabel"],[data-testid="stSidebar"] [data-testid="stMetricValue"]{color:#17243b!important}
    [data-testid="stSidebar"] [data-baseweb="tag"]{background:#258f86}
    [data-testid="stMetric"]{background:#fff;border:1px solid #e3e9f2;border-left:4px solid #12a594;border-radius:12px;padding:12px 15px;box-shadow:0 5px 18px #142c4b0d}
    .status-pill{display:inline-block;padding:5px 11px;border-radius:99px;background:#d8f6ec;color:#087b61;font-size:.78rem;font-weight:700}
    div.stButton>button[kind="primary"]{background:linear-gradient(110deg,#128e84,#2879c7);border:0;color:white}
    [data-testid="stTabs"] [role="tablist"]{overflow-x:auto;flex-wrap:nowrap}
    @media(max-width:768px){
      [data-testid="stHorizontalBlock"]{flex-wrap:wrap!important;gap:.5rem}
      [data-testid="stHorizontalBlock"]>[data-testid="column"]{flex:1 1 48%!important;width:48%!important;min-width:48%!important}
      [data-testid="stMainBlockContainer"]{padding:.75rem}
    }
    @media(max-width:480px){
      [data-testid="stHorizontalBlock"]>[data-testid="column"]{flex-basis:100%!important;width:100%!important;min-width:100%!important}
    }
    </style>""",
    unsafe_allow_html=True,
)

# Cache data reads because Streamlit reruns this file when a widget changes.
@st.cache_data(show_spinner=False)
def load_dataset(root: str) -> tuple[dict, dict[str, pd.DataFrame]]:
    folder = Path(root) / "clean"
    summary = json.loads((folder / "validation_summary.json").read_text(encoding="utf-8"))
    files = {
        "schedule": "operation_schedules.csv", "operations": "operations.csv",
        "orders": "production_orders.csv", "machines": "machines.csv",
    }
    return summary, {name: pd.read_csv(folder / file) for name, file in files.items()}

def prepare_views(tables: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Join once so schedule, order, and capacity charts share consistent records."""
    activity = tables["schedule"].merge(
        tables["operations"][["operation_id", "order_id", "step_no", "duration_min"]],
        on="operation_id", validate="one_to_one",
    ).merge(
        tables["orders"][["order_id", "sku", "due_min", "priority", "urgent"]], on="order_id"
    ).merge(tables["machines"][["machine_id", "name"]], on="machine_id", how="left")
    activity["machine_name"] = activity["name"].fillna("Unassigned")
    activity["priority"] = pd.to_numeric(activity["priority"], errors="coerce").fillna(0).astype(int)
    activity[["start_min", "end_min", "setup_start_min"]] = activity[
        ["start_min", "end_min", "setup_start_min"]
    ].apply(pd.to_numeric, errors="coerce")
    scheduled = activity[activity["status"] == "scheduled"].copy()
    scheduled["occupied_min"] = (
        scheduled["end_min"] - scheduled["setup_start_min"].fillna(scheduled["start_min"])
    ).clip(lower=0)
    finishes = scheduled.groupby("order_id", as_index=False)["end_min"].max().rename(columns={"end_min": "completed_min"})
    orders = tables["orders"].merge(finishes, on="order_id", how="left")
    orders["lateness_min"] = (orders["completed_min"] - orders["due_min"]).clip(lower=0).fillna(0)
    orders["state"] = orders["completed_min"].notna().map({True: "On time", False: "Infeasible"})
    orders.loc[orders["lateness_min"] > 0, "state"] = "Late"
    load = scheduled.groupby("machine_id", as_index=False).agg(
        occupied_min=("occupied_min", "sum"), operations=("operation_id", "count"))
    load = tables["machines"][["machine_id", "name"]].merge(load, on="machine_id", how="left")
    load[["occupied_min", "operations"]] = load[["occupied_min", "operations"]].fillna(0)
    load["occupied_hr"] = load["occupied_min"] / 60
    return activity, orders, load


def load_scenarios() -> dict[str, dict]:
    """Use validator reports as evidence; never load the separate ground-truth labels."""
    root = DATA_DIR / "mutated"
    if not root.exists():
        return {}
    return {
        folder.name: json.loads((folder / "validation_summary.json").read_text(encoding="utf-8"))
        for folder in sorted(root.iterdir())
        if folder.is_dir() and (folder / "validation_summary.json").exists()
    }

def style_chart(fig, height: int = 340):
    """Give each Plotly chart the same lightweight grid, font, and spacing."""
    fig.update_layout(
        height=height, margin=dict(l=12, r=16, t=24, b=12),
        paper_bgcolor="rgba(255,255,255,0)", plot_bgcolor="rgba(255,255,255,0)",
        font=dict(family="Segoe UI, sans-serif", color="#26364d"),
        xaxis=dict(showgrid=True, gridcolor="#e8edf4", zeroline=False),
        yaxis=dict(showgrid=False, zeroline=False),
        legend=dict(orientation="h", y=1.02, x=1, xanchor="right"),
    )
    return fig

def post_json(path: str, payload: dict, timeout: int = 90) -> dict:
    """Send interactive actions to the API, which owns schedule persistence."""
    response = requests.post(f"{API_URL}{path}", json=payload, timeout=timeout)
    response.raise_for_status()
    return response.json()

try:
    report, tables = load_dataset(str(DATA_DIR.resolve()))
except (FileNotFoundError, json.JSONDecodeError) as error:
    st.error(f"Could not load generated data: {error}")
    st.info("Run `python -m src.cli generate` from the project root first.")
    st.stop()

activity, orders, machine_load = prepare_views(tables)
scenarios = load_scenarios()
metrics = report["metrics"]
order_total = len(orders)
on_time = int((orders["state"] == "On time").sum())
on_time_rate = 100 * on_time / order_total if order_total else 0
scheduled_count = int((activity["status"] == "scheduled").sum())

# The sidebar shows baseline health and filters used by the schedule board.
with st.sidebar:
    st.markdown("## 🏭 PLANT / CONTROL")
    st.caption("PRODUCTION INTELLIGENCE · 2026")
    st.markdown("### Baseline schedule")
    if report["valid"]:
        st.markdown(f'<span class="status-pill">{report["schedule_id"]} · VALID</span>', unsafe_allow_html=True)
    else:
        st.error(f"{report['schedule_id']} · REVIEW REQUIRED")
    st.markdown("---")
    machine_filter = st.selectbox("Machine", ["All machines"] + sorted(tables["machines"]["machine_id"]))
    horizon = st.selectbox("Schedule window", ["First 7 days", "First 30 days", "Full horizon"])

# The KPI row give planners an at-a-glance schedule health summary.
for col, label, value, note in zip(
    st.columns(4),
    ("On-time", "Late orders", "Makespan", "Scheduled ops"),
    (f"{on_time_rate:.1f}%", f"{metrics['late_orders']:,}",
     f"{metrics['makespan_min'] / 1440:.1f} d", f"{scheduled_count:,}"),
    ("Completed by due date", f"{on_time:,} orders on time",
     f"{metrics['makespan_min']:,} minutes", f"{metrics['infeasible_operations']:,} infeasible"),
):
    col.metric(label, value, help=note)

overview, schedule_tab, exceptions, what_if, analyst = st.tabs(["Overview", "Schedule", "Exceptions", "What-if", "Analyst"])

# Overview charts compare delivery and machine workload for quick triage.
with overview:
    left, right = st.columns([1, 1.35], gap="large")
    with left:
        st.markdown("### Delivery status")
        status = orders["state"].value_counts().reindex(
            ["On time", "Late", "Infeasible"], fill_value=0
        ).rename_axis("Status").reset_index(name="Orders")
        fig = px.pie(
            status, names="Status", values="Orders", hole=.68, color="Status",
            color_discrete_map={"On time": "#12a594", "Late": "#e7a12d", "Infeasible": "#d95565"},
        )
        fig.update_traces(textinfo="percent", marker=dict(line=dict(color="white", width=3)))
        fig.update_layout(annotations=[dict(text=f"{order_total}<br>orders", x=.5, y=.5, showarrow=False)])
        st.plotly_chart(style_chart(fig), width="stretch", config={"displayModeBar": False})
    with right:
        st.markdown("### Machine workload")
        busiest = machine_load.nlargest(12, "occupied_hr").sort_values("occupied_hr")
        fig = px.bar(
            busiest, x="occupied_hr", y="name", orientation="h", color="operations",
            color_continuous_scale=["#c9e8e4", "#46b7a5", "#2879c7"],
            labels={"name": "Machine", "occupied_hr": "Occupied hours", "operations": "Operations"},
            hover_data={"occupied_min": ":,", "operations": True},
        )
        fig.update_coloraxes(showscale=False)
        st.plotly_chart(style_chart(fig), width="stretch", config={"displayModeBar": False})

    st.markdown("### Orders with the most lateness")
    late = orders.loc[orders["lateness_min"] > 0].nlargest(10, "lateness_min")
    st.dataframe(late[["order_id", "sku", "priority", "urgent", "lateness_min"]], hide_index=True, width="stretch")

# The schedule board reuses sidebar filters and exposes operation details on hover.
with schedule_tab:
    board = activity[activity["status"] == "scheduled"].copy()
    if machine_filter != "All machines":
        board = board[board["machine_id"] == machine_filter]
    days = {"First 7 days": 7, "First 30 days": 30, "Full horizon": None}[horizon]
    if not board.empty and days:
        board = board[board["start_min"] < board["start_min"].min() + days * 1440]
    if board.empty:
        st.info("No operations match the selected schedule filters.")
    else:
        board["start_at"] = EPOCH + pd.to_timedelta(board["start_min"], unit="m")
        board["end_at"] = EPOCH + pd.to_timedelta(board["end_min"], unit="m")
        board["Priority"] = board["priority"].map(lambda value: f"P{value}")
        fig = px.timeline(
            board, x_start="start_at", x_end="end_at", y="machine_name", color="Priority",
            hover_data=["operation_id", "order_id", "sku", "step_no", "setup_min", "tooling_id"],
            color_discrete_sequence=["#d95565", "#ef9b42", "#e7c84a", "#48a99b", "#4b82cf"],
        )
        fig.update_yaxes(autorange="reversed", title=None)
        fig.update_xaxes(title="Schedule time (UTC)", tickformat="%b %d · %H:%M")
        st.plotly_chart(style_chart(fig, max(430, min(720, 24 * board["machine_name"].nunique()))), width="stretch")

# Exceptions come from each scenario's validator report, not from ground truth.
with exceptions:
    st.markdown("### Baseline and injected scenarios")
    st.success("Baseline passes hard-constraint validation.") if report["valid"] else st.error("Baseline needs review.")
    if not scenarios:
        st.info("No injected reports found. Generate the dataset to create scenario evidence.")
    else:
        name = st.selectbox("Scenario evidence", sorted(scenarios))
        scenario = scenarios[name]
        findings = scenario.get("issues", [])
        st.metric("Validator findings", len(findings))
        if findings:
            st.dataframe(pd.DataFrame(findings), hide_index=True, width="stretch")
            kind = st.selectbox("Explain finding", sorted({row["issue_type"] for row in findings}))
            if st.button("Explain with evidence", type="primary"):
                try:
                    st.json(post_json("/api/explain", {"schedule_id": scenario["schedule_id"], "issue_type": kind}))
                except requests.RequestException as error:
                    st.error(f"Explanation request failed: {error}")
        else:
            st.info("No findings.")
        st.caption(f"Schedule version: {scenario.get('schedule_id', 'unknown')}")

# What-if runs through the API, which saves a new version without changing the baseline.
with what_if:
    st.markdown("### Maintenance what-if")
    st.caption("Add downtime, re-run dispatch, and compare the results with the baseline.")
    machines = tables["machines"].sort_values("machine_id")
    names = dict(zip(machines["machine_id"], machines["name"]))
    with st.form("what_if_form"):
        left, middle, right = st.columns(3)
        machine_id = left.selectbox(
            "Machine affected", machines["machine_id"].tolist(),
            format_func=lambda value: f"{value} · {names[value]}",
        )
        outage_date = left.date_input("Outage date (08:00 UTC)", value=dt.date(2026, 2, 1))
        duration = middle.slider("Duration (hours)", 1, 168, 8)
        right.caption("Each run creates a traceable schedule version.")
        run = right.form_submit_button("Run what-if", type="primary", use_container_width=True)
    if run:
        start = dt.datetime.combine(outage_date, dt.time(8, 0))
        start_min = int((start - dt.datetime.combine(EPOCH_DATE, dt.time())).total_seconds() // 60)
        try:
            st.session_state["what_if"] = post_json(
                "/api/what-if",
                {"machine_id": machine_id, "start_min": start_min, "duration_min": duration * 60},
                timeout=120,
            )
        except requests.RequestException as error:
            st.error(f"What-if request failed: {error}")
    result = st.session_state.get("what_if")
    if result:
        st.markdown(f"#### Results · {result['schedule_id']}")
        changed, delta = result["what_if"], result["delta"]
        for col, key, label in zip(
            st.columns(3),
            ("makespan_min", "late_orders", "total_lateness_min"),
            ("Makespan Δ", "Late orders Δ", "Total lateness Δ"),
        ):
            col.metric(label, f"{delta[key]:+,}", delta=f"Scenario total: {changed[key]:,}", delta_color="off")

# Optional AI actions use the guarded API, and any provider/API errors stay visible.
with analyst:
    st.markdown("### Ask the schedule")
    with st.form("sql_form"):
        question = st.text_area("Question", placeholder="Which urgent orders finish late?")
        ask = st.form_submit_button("Ask analyst", type="primary")
    if ask and question.strip():
        try:
            st.json(post_json("/api/ask-sql", {"question": question.strip()}))
        except requests.RequestException as error:
            st.error(f"Analyst request failed: {error}")
    st.caption("Requires a compatible LLM provider configured on the API.")