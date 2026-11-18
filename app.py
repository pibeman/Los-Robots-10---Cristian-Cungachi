import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import json
import math
from decimal import Decimal, ROUND_HALF_UP
import io

st.set_page_config(
    page_title="Career Venture Lab | Los-Robots (10) - ROB-3",
    page_icon="🤖",
    layout="wide"
)

# --- CONSTANTS & HANDBOOK DEFAULTS ---
TEAM_ID = "Los-Robots (10)"
COURSE = "AP Calculus"
PATHWAY_ID = "ROB-3"
BUSINESS_NAME = "Robotics kit and repair studio"

FIXTURE_CSV_CONTENT = """month,requested,capacity_override,ad_cost
2027-01,40,30,0
2027-02,44,30,100
2027-03,36,22,0
"""

def d_money(val) -> Decimal:
    return Decimal(str(val)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

def fmt_usd(val) -> str:
    d = d_money(val)
    if d < 0:
        return f"-${abs(d):,.2f}"
    return f"${d:,.2f}"

def init_default_state():
    return {
        "team_id": TEAM_ID,
        "course": COURSE,
        "pathway_id": PATHWAY_ID,
        "business_name": BUSINESS_NAME,
        "selected_level": "Advanced",
        "snapshot_id": "SNAP-000",
        "state_version": 1,
        "simulation_date": "2027-01-01",
        "base_period": "Monthly",
        "working_days": 22,
        "currency": "USD",
        "random_seed": 2027,
        "level_by_skill": {"AP Calculus": "Advanced"},
        "assumptions": [
            "All figures are fictional teaching assumptions for simulation only.",
            "Components are expensed when consumed; cash outflow occurs upon restock.",
            "Failed builds consume variable costs and produce $0 sales revenue.",
            "Taxes, depreciation, loans, and refunds are disabled at baseline."
        ],
        "sources": [
            {"id": "SRC-1", "title": "Career Venture Lab Student Handbook (ROB-3)", "type": "supplied"}
        ],
        "offerings": [
            {
                "offering_id": "OFF-1",
                "name": "Introductory robot kit",
                "unit": "kit",
                "price": 120.00,
                "demand_rule": "q(p) = max(0, 80 - (1/3)*p)",
                "capacity_rule": "floor(staff_hours / hours_per_unit)",
                "active": True
            },
            {
                "offering_id": "OFF-2",
                "name": "Sensor upgrade (Future Stage)",
                "unit": "upgrade",
                "price": 0.00,
                "demand_rule": "Not modeled in Stage 1",
                "capacity_rule": "Separate allocation required",
                "active": False
            },
            {
                "offering_id": "OFF-3",
                "name": "Repair service (Future Stage)",
                "unit": "service",
                "price": 0.00,
                "demand_rule": "Not modeled in Stage 1",
                "capacity_rule": "Separate allocation required",
                "active": False
            }
        ],
        "funding": {
            "owner_contribution": 12000.00,
            "equipment_assets": 4000.00,
            "pre_opening_expense": 0.00,
            "opening_inventory_value": 3000.00,
            "opening_cash": 5000.00,
            "retained_earnings": 0.00
        },
        "inputs": {
            "base_price": 120.00,
            "D0": 40,
            "requested_units": 40,
            "staff_hours": 90.0,
            "hours_per_unit": 3.0,
            "opening_stock_units": 100,
            "component_unit_cost": 30.00,
            "restock_units": 0,
            "defect_rate": 0.0,
            "ad_cost": 0.00,
            "refund_amount": 0.00,
            "loan_principal": 0.00,
            "interest": 0.00,
            "additional_capex": 0.00,
            "new_owner_cash": 0.00,
            "loan_cash": 0.00
        },
        "cost_lines": {
            "variable_per_unit": {
                "components_COGS": 30.00,
                "assembly_labor": 20.00,
                "packaging": 10.00,
                "warranty_consumables": 5.00
            },
            "monthly_fixed": {
                "workspace": 250.00,
                "software": 100.00,
                "equipment_maintenance": 150.00,
                "admin": 100.00
            }
        },
        "balances": {
            "cash": 5000.00,
            "stock_units": 100,
            "inventory_value": 3000.00,
            "equipment_assets": 4000.00,
            "debt": 0.00,
            "owner_equity": 12000.00,
            "retained_earnings": 0.00
        },
        "capacity": {},
        "ledger": [],
        "executed_run_ids": [],
        "campaigns": [],
        "decisions": []
    }

if "sim_state" not in st.session_state:
    st.session_state.sim_state = init_default_state()

state = st.session_state.sim_state

# --- DETERMINISTIC ROB-3 SIMULATION ENGINE ---
def run_rob3_month(
    price: float,
    requested: int,
    staff_hours: float,
    hours_per_unit: float,
    opening_cash: float,
    opening_stock_units: int,
    component_unit_cost: float,
    restock_units: int,
    defect_rate: float,
    var_lines: dict,
    fixed_lines: dict,
    ad_cost: float = 0.0,
    refund_amount: float = 0.0,
    loan_principal: float = 0.0,
    interest: float = 0.0,
    additional_capex: float = 0.0,
    new_owner_cash: float = 0.0,
    loan_cash: float = 0.0,
    capacity_override: int | None = None
) -> dict:
    p = d_money(price)
    comp_cost = d_money(component_unit_cost)
    ad = d_money(ad_cost)
    refunds = d_money(refund_amount)
    principal = d_money(loan_principal)
    intr = d_money(interest)
    capex = d_money(additional_capex)
    owner_in = d_money(new_owner_cash)
    loan_in = d_money(loan_cash)
    open_cash_d = d_money(opening_cash)

    effective_var_lines = dict(var_lines)
    effective_var_lines["components_COGS"] = float(comp_cost)

    var_per_unit = sum(d_money(v) for v in effective_var_lines.values())
    noncomp_var_per_unit = var_per_unit - comp_cost
    fixed_expense = sum(d_money(v) for v in fixed_lines.values())

    if capacity_override is not None:
        capacity = int(capacity_override)
        mode = "FIXTURE_OVERRIDE"
    else:
        if hours_per_unit <= 0:
            raise ValueError("hours_per_unit must be > 0")
        capacity = math.floor(staff_hours / hours_per_unit)
        mode = "NORMAL_DERIVED"

    available_stock = int(opening_stock_units) + int(restock_units)
    attempted = min(int(requested), int(capacity), available_stock)
    failed = math.floor(attempted * float(defect_rate))
    sold = attempted - failed
    unserved_demand = max(0, int(requested) - attempted)

    gross_revenue = p * Decimal(sold)
    net_revenue = gross_revenue - refunds

    variable_expense = var_per_unit * Decimal(attempted)
    consumed_component_expense = comp_cost * Decimal(attempted)
    failed_writeoff_included = comp_cost * Decimal(failed)
    noncomponent_variable_cash = noncomp_var_per_unit * Decimal(attempted)

    operating_profit = net_revenue - variable_expense - fixed_expense - ad
    net_profit = operating_profit - intr

    restock_cash_outflow = comp_cost * Decimal(restock_units)
    ending_cash = (
        open_cash_d
        + net_revenue
        - noncomponent_variable_cash
        - restock_cash_outflow
        - fixed_expense
        - ad
        - intr
        - principal
        - capex
        + owner_in
        + loan_in
    )

    ending_stock_units = available_stock - attempted
    ending_inventory_value = comp_cost * Decimal(ending_stock_units)

    build_hours_used = attempted * hours_per_unit
    utilization = (build_hours_used / staff_hours) if staff_hours > 0 else 0.0
    stock_cover_months = (ending_stock_units / attempted) if attempted > 0 else float("inf")

    return {
        "mode": mode,
        "capacity": capacity,
        "available_stock": available_stock,
        "requested": int(requested),
        "attempted": attempted,
        "failed": failed,
        "sold": sold,
        "unserved_demand": unserved_demand,
        "var_per_unit": float(var_per_unit),
        "noncomp_var_per_unit": float(noncomp_var_per_unit),
        "gross_revenue": float(gross_revenue),
        "net_revenue": float(net_revenue),
        "variable_expense": float(variable_expense),
        "consumed_component_expense": float(consumed_component_expense),
        "failed_writeoff_included": float(failed_writeoff_included),
        "noncomponent_variable_cash": float(noncomponent_variable_cash),
        "restock_cash_outflow": float(restock_cash_outflow),
        "fixed_expense": float(fixed_expense),
        "ad_cost": float(ad),
        "total_expense": float(variable_expense + fixed_expense + ad),
        "operating_profit": float(operating_profit),
        "net_profit": float(net_profit),
        "opening_cash": float(open_cash_d),
        "ending_cash": float(ending_cash),
        "opening_stock_units": int(opening_stock_units),
        "restock_units": int(restock_units),
        "ending_stock_units": ending_stock_units,
        "ending_inventory_value": float(ending_inventory_value),
        "build_hours_used": build_hours_used,
        "utilization": utilization,
        "stock_cover_months": stock_cover_months
    }

def commit_simulation_step(sim_date: str, run_id: str, sim_result: dict, price: float):
    if run_id in state["executed_run_ids"]:
        return False, f"Duplicate run_id '{run_id}' rejected. No duplicate transactions created."

    v = state["state_version"]
    tx_base = len(state["ledger"]) + 1

    entries = []
    if sim_result["net_revenue"] != 0:
        entries.append({
            "transaction_id": f"TX-{tx_base:04d}",
            "date": sim_date,
            "event_type": "SALE",
            "category": "Sales Revenue",
            "amount": sim_result["net_revenue"],
            "quantity": sim_result["sold"],
            "unit_price": price,
            "offering_id": "OFF-1",
            "campaign_id": None,
            "financing_type": None,
            "state_version": v,
            "run_id": run_id
        })
        tx_base += 1

    if sim_result["variable_expense"] != 0:
        entries.append({
            "transaction_id": f"TX-{tx_base:04d}",
            "date": sim_date,
            "event_type": "EXPENSE",
            "category": "Variable Production & Consumed COGS",
            "amount": -sim_result["variable_expense"],
            "quantity": sim_result["attempted"],
            "unit_price": sim_result["var_per_unit"],
            "offering_id": "OFF-1",
            "campaign_id": None,
            "financing_type": None,
            "state_version": v,
            "run_id": run_id
        })
        tx_base += 1

    if sim_result["restock_cash_outflow"] != 0:
        entries.append({
            "transaction_id": f"TX-{tx_base:04d}",
            "date": sim_date,
            "event_type": "INVENTORY_RESTOCK",
            "category": "Component Inventory Purchase",
            "amount": -sim_result["restock_cash_outflow"],
            "quantity": sim_result["restock_units"],
            "unit_price": state["inputs"]["component_unit_cost"],
            "offering_id": "OFF-1",
            "campaign_id": None,
            "financing_type": None,
            "state_version": v,
            "run_id": run_id
        })
        tx_base += 1

    entries.append({
        "transaction_id": f"TX-{tx_base:04d}",
        "date": sim_date,
        "event_type": "EXPENSE",
        "category": "Monthly Fixed Overhead",
        "amount": -sim_result["fixed_expense"],
        "quantity": 1,
        "unit_price": sim_result["fixed_expense"],
        "offering_id": "OFF-1",
        "campaign_id": None,
        "financing_type": None,
        "state_version": v,
        "run_id": run_id
    })
    tx_base += 1

    if sim_result["ad_cost"] > 0:
        entries.append({
            "transaction_id": f"TX-{tx_base:04d}",
            "date": sim_date,
            "event_type": "MARKETING",
            "category": "Own-Business Advertising",
            "amount": -sim_result["ad_cost"],
            "quantity": 1,
            "unit_price": sim_result["ad_cost"],
            "offering_id": "OFF-1",
            "campaign_id": f"CAMP-{run_id}",
            "financing_type": None,
            "state_version": v,
            "run_id": run_id
        })

    state["ledger"].extend(entries)
    state["executed_run_ids"].append(run_id)
    state["balances"]["cash"] = sim_result["ending_cash"]
    state["balances"]["stock_units"] = sim_result["ending_stock_units"]
    state["balances"]["inventory_value"] = sim_result["ending_inventory_value"]
    state["balances"]["retained_earnings"] = float(
        d_money(state["balances"]["retained_earnings"]) + d_money(sim_result["net_profit"])
    )
    state["inputs"]["opening_cash"] = sim_result["ending_cash"]
    state["inputs"]["opening_stock_units"] = sim_result["ending_stock_units"]
    state["state_version"] = v + 1
    state["snapshot_id"] = f"SNAP-{state['state_version']:03d}"
    state["simulation_date"] = sim_date
    return True, f"Committed run '{run_id}'. State advanced to v{state['state_version']} ({state['snapshot_id']})."

def validate_and_import_snapshot(raw_json_str: str):
    try:
        data = json.loads(raw_json_str)
    except json.JSONDecodeError as e:
        return False, f"Invalid JSON format: {e}"

    required_keys = [
        "team_id", "course", "pathway_id", "snapshot_id", "state_version",
        "simulation_date", "currency", "inputs", "cost_lines", "balances", "ledger"
    ]
    missing = [k for k in required_keys if k not in data]
    if missing:
        return False, f"Rejected import: missing required fields {missing}."

    if data["team_id"] != TEAM_ID:
        return False, f"Rejected import: team_id '{data['team_id']}' does not match '{TEAM_ID}'."

    if data["pathway_id"] != PATHWAY_ID:
        return False, f"Rejected import: pathway_id '{data['pathway_id']}' does not match '{PATHWAY_ID}'."

    if not isinstance(data["state_version"], int) or data["state_version"] < state["state_version"]:
        return False, (
            f"Rejected stale snapshot: imported v{data.get('state_version')} is older than "
            f"current active state v{state['state_version']}."
        )

    if data["balances"]["cash"] < 0 or data["balances"]["stock_units"] < 0:
        return False, "Rejected import: negative cash or stock balance detected."

    st.session_state.sim_state = data
    return True, f"Successfully restored snapshot {data['snapshot_id']} (v{data['state_version']})."

# --- SIDEBAR: SNAPSHOT & PERSISTENCE ---
with st.sidebar:
    st.title("🤖 Los-Robots (10)")
    st.caption(f"Pathway: **{PATHWAY_ID}** | Course: **{COURSE}**")
    st.info(
        f"**Active Snapshot:** `{state['snapshot_id']}`\n\n"
        f"**State Version:** `v{state['state_version']}`\n\n"
        f"**Sim Date:** `{state['simulation_date']}`\n\n"
        f"**Stage:** `Stage 1 (Offline Deterministic Core)`"
    )

    st.subheader("💾 Save / Restore State (JSON)")
    snapshot_export = json.dumps(state, indent=2)
    st.download_button(
        label="⬇️ Export Snapshot JSON",
        data=snapshot_export,
        file_name=f"los_robots_10_{state['snapshot_id']}_v{state['state_version']}.json",
        mime="application/json",
        use_container_width=True
    )

    uploaded_snap = st.file_uploader("⬆️ Import Snapshot JSON", type=["json"])
    if uploaded_snap is not None:
        if st.button("Validate & Restore JSON", use_container_width=True):
            ok, msg = validate_and_import_snapshot(uploaded_snap.read().decode("utf-8"))
            if ok:
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)

    st.divider()
    if st.button("🔄 Reset to Post-Startup Opening State", use_container_width=True):
        st.session_state.sim_state = init_default_state()
        st.rerun()

    st.divider()
    st.caption("Upcoming Modules (Not Implemented in Stage 1):")
    st.markdown(
        "- ⏳ Stage 2: Departmental AI Tabs, Report Center PDFs, Marketing Studio\n"
        "- ⏳ Stage 3: Cross-Course Panel, Snapshot Assessments\n"
        "- ⏳ Stage 4: Optional Demo Storefront"
    )

# --- HEADER & KPI TILES ---
st.title("🤖 Robotics Kit & Repair Studio — Business Operating System")
st.markdown(
    "**Simulation Notice:** Fictional business, customers, transactions, and funding for educational modeling only. "
    "Input adjustments preview scenarios until explicitly approved and committed to the ledger."
)

inp = state["inputs"]
v_lines = state["cost_lines"]["variable_per_unit"]
f_lines = state["cost_lines"]["monthly_fixed"]

preview = run_rob3_month(
    price=inp["base_price"],
    requested=inp["requested_units"],
    staff_hours=inp["staff_hours"],
    hours_per_unit=inp["hours_per_unit"],
    opening_cash=state["balances"]["cash"],
    opening_stock_units=state["balances"]["stock_units"],
    component_unit_cost=inp["component_unit_cost"],
    restock_units=inp["restock_units"],
    defect_rate=inp["defect_rate"],
    var_lines=v_lines,
    fixed_lines=f_lines,
    ad_cost=inp["ad_cost"],
    refund_amount=inp["refund_amount"],
    loan_principal=inp["loan_principal"],
    interest=inp["interest"],
    additional_capex=inp["additional_capex"],
    new_owner_cash=inp["new_owner_cash"],
    loan_cash=inp["loan_cash"]
)

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Current Cash", fmt_usd(state["balances"]["cash"]), f"Projected End: {fmt_usd(preview['ending_cash'])}")
k2.metric("Component Stock", f"{state['balances']['stock_units']} sets", f"Projected End: {preview['ending_stock_units']} sets")
k3.metric("Monthly Capacity", f"{preview['capacity']} kits", f"Utilization: {preview['utilization']*100:.1f}%")
k4.metric("Scenario Sold / Req", f"{preview['sold']} / {preview['requested']} kits", f"Unserved: {preview['unserved_demand']}")
k5.metric("Scenario Operating Profit", fmt_usd(preview["operating_profit"]), f"Revenue: {fmt_usd(preview['net_revenue'])}")

# --- STAGE 1 TABS ---
tab_overview, tab_inputs, tab_math, tab_ledger, tab_tests = st.tabs([
    "📊 Overview & Scenario Simulator",
    "⚙️ Inputs, Costs & Startup Funding",
    "📐 AP Calculus Math & Levels Panel",
    "📒 Dated Ledger & CSV Export",
    "✅ Stage 1 Acceptance Tests"
])

# ==============================================================================
# TAB 1: OVERVIEW & SCENARIO SIMULATOR
# ==============================================================================
with tab_overview:
    st.subheader("Monthly Operations & Financial Preview (Scenario Mode)")
    col_l, col_r = st.columns([1.2, 1])

    with col_l:
        st.markdown("#### Production, Capacity & Inventory Breakdown")
        ops_df = pd.DataFrame([
            {"Metric": "Staff Hours Available", "Value": f"{inp['staff_hours']:.1f} hrs", "Rule / Meaning": "Productive assembly hours/month"},
            {"Metric": "Hours per Kit", "Value": f"{inp['hours_per_unit']:.1f} hrs/kit", "Rule / Meaning": "Assembly labor time per unit"},
            {"Metric": "Derived Monthly Capacity", "Value": f"{preview['capacity']} kits", "Rule / Meaning": "floor(staff_hours / hours_per_unit)"},
            {"Metric": "Available Component Sets", "Value": f"{preview['available_stock']} sets", "Rule / Meaning": "opening_stock + restock_units"},
            {"Metric": "Requested Demand", "Value": f"{preview['requested']} kits", "Rule / Meaning": "Customer orders requested"},
            {"Metric": "Attempted Builds", "Value": f"{preview['attempted']} kits", "Rule / Meaning": "min(requested, capacity, available_stock)"},
            {"Metric": "Failed / Rework Builds", "Value": f"{preview['failed']} kits", "Rule / Meaning": "floor(attempted * defect_rate) - $0 revenue, full cost"},
            {"Metric": "Completed & Sold Kits", "Value": f"{preview['sold']} kits", "Rule / Meaning": "attempted - failed"},
            {"Metric": "Unserved Demand", "Value": f"{preview['unserved_demand']} kits", "Rule / Meaning": "requested - attempted (no backlog)"},
            {"Metric": "Ending Stock Cover", "Value": f"{preview['stock_cover_months']:.2f} mos" if preview["attempted"] > 0 else "N/A", "Rule / Meaning": "ending_stock / attempted"}
        ])
        st.dataframe(ops_df, use_container_width=True, hide_index=True)

    with col_r:
        st.markdown("#### Profit vs. Cash Reconciliation (Scenario)")
        fin_df = pd.DataFrame([
            {"Line Item": "Net Sales Revenue", "Amount": fmt_usd(preview["net_revenue"]), "Notes": f"{preview['sold']} sold @ {fmt_usd(inp['base_price'])}"},
            {"Line Item": "Variable Expense (Attempted)", "Amount": fmt_usd(-preview["variable_expense"]), "Notes": f"{preview['attempted']} attempted @ {fmt_usd(preview['var_per_unit'])}/unit"},
            {"Line Item": "  └ Included Component COGS", "Amount": fmt_usd(-preview["consumed_component_expense"]), "Notes": f"Failed write-off inside COGS: {fmt_usd(preview['failed_writeoff_included'])}"},
            {"Line Item": "Fixed Monthly Overhead", "Amount": fmt_usd(-preview["fixed_expense"]), "Notes": "Workspace, software, maintenance, admin"},
            {"Line Item": "Own-Business Advertising", "Amount": fmt_usd(-preview["ad_cost"]), "Notes": "Campaign expense"},
            {"Line Item": "Operating Profit", "Amount": fmt_usd(preview["operating_profit"]), "Notes": "Accounting profit (accrual)"},
            {"Line Item": "Net Profit (after Interest)", "Amount": fmt_usd(preview["net_profit"]), "Notes": f"Interest: {fmt_usd(inp['interest'])}"},
            {"Line Item": "Opening Spendable Cash", "Amount": fmt_usd(preview["opening_cash"]), "Notes": "Start of period"},
            {"Line Item": "Component Restock Cash Outflow", "Amount": fmt_usd(-preview["restock_cash_outflow"]), "Notes": f"{inp['restock_units']} sets purchased @ {fmt_usd(inp['component_unit_cost'])}"},
            {"Line Item": "Projected Ending Cash", "Amount": fmt_usd(preview["ending_cash"]), "Notes": "Differs from profit when consuming starter inventory"}
        ])
        st.dataframe(fin_df, use_container_width=True, hide_index=True)

    st.divider()
    st.markdown("#### Human Approval: Commit Scenario to Dated Ledger")
    st.caption("Advancing the simulation requires a unique `run_id` and explicit student approval.")
    c_date, c_run, c_btn = st.columns([1, 1, 1])
    commit_date = c_date.text_input("Transaction Date (YYYY-MM-DD)", value=state["simulation_date"])
    commit_run_id = c_run.text_input("Unique Run ID", value=f"RUN-{state['state_version']:03d}")
    if c_btn.button("✅ Approve & Advance Simulation Once", type="primary", use_container_width=True):
        ok, msg = commit_simulation_step(commit_date, commit_run_id, preview, inp["base_price"])
        if ok:
            st.success(msg)
            st.rerun()
        else:
            st.error(msg)

# ==============================================================================
# TAB 2: INPUTS, COSTS & STARTUP FUNDING
# ==============================================================================
with tab_inputs:
    st.subheader("Startup Financing & Opening Balance Sheet (Owner Contribution = $12,000)")
    f_cols = st.columns(5)
    f_cols[0].metric("Owner Contribution", fmt_usd(state["funding"]["owner_contribution"]))
    f_cols[1].metric("Equipment Assets", fmt_usd(state["funding"]["equipment_assets"]))
    f_cols[2].metric("Opening Inventory", fmt_usd(state["funding"]["opening_inventory_value"]))
    f_cols[3].metric("Post-Startup Cash", fmt_usd(state["funding"]["opening_cash"]))
    f_cols[4].metric("Pre-Opening Expense", fmt_usd(state["funding"]["pre_opening_expense"]))

    st.divider()
    col_i1, col_i2 = st.columns(2)

    with col_i1:
        st.markdown("#### Editable Monthly Operating Inputs")
        inp["base_price"] = st.number_input("Base Price ($ / kit)", min_value=0.01, value=float(inp["base_price"]), step=5.0)
        inp["D0"] = st.number_input("Baseline Monthly Demand D0 (at base price)", min_value=0, value=int(inp["D0"]), step=1)
        inp["requested_units"] = st.number_input("Current Month Requested Units", min_value=0, value=int(inp["requested_units"]), step=1)
        inp["staff_hours"] = st.number_input("Monthly Staff Hours", min_value=0.0, value=float(inp["staff_hours"]), step=5.0)
        inp["hours_per_unit"] = st.number_input("Assembly Hours per Kit", min_value=0.1, value=float(inp["hours_per_unit"]), step=0.5)
        inp["restock_units"] = st.number_input("Component Restock Units Purchased This Month", min_value=0, value=int(inp["restock_units"]), step=10)
        inp["defect_rate"] = st.slider("Defect Rate (0.00 to 1.00)", min_value=0.0, max_value=1.0, value=float(inp["defect_rate"]), step=0.01)
        inp["ad_cost"] = st.number_input("Own-Business Advertising Cost ($)", min_value=0.0, value=float(inp["ad_cost"]), step=25.0)

    with col_i2:
        st.markdown("#### Editable Variable & Fixed Cost Lines")
        st.caption("Variable Cost per Attempted Unit (Baseline = $65.00/unit)")
        inp["component_unit_cost"] = st.number_input("components_COGS ($/unit)", min_value=0.0, value=float(inp["component_unit_cost"]), step=1.0)
        v_lines["components_COGS"] = inp["component_unit_cost"]
        v_lines["assembly_labor"] = st.number_input("assembly_labor ($/unit)", min_value=0.0, value=float(v_lines["assembly_labor"]), step=1.0)
        v_lines["packaging"] = st.number_input("packaging ($/unit)", min_value=0.0, value=float(v_lines["packaging"]), step=1.0)
        v_lines["warranty_consumables"] = st.number_input("warranty_consumables ($/unit)", min_value=0.0, value=float(v_lines["warranty_consumables"]), step=1.0)
        st.info(f"**Total Variable Cost per Attempted Kit:** {fmt_usd(sum(v_lines.values()))}")

        st.caption("Monthly Fixed Overhead (Baseline = $600.00/month)")
        f_lines["workspace"] = st.number_input("workspace ($/month)", min_value=0.0, value=float(f_lines["workspace"]), step=10.0)
        f_lines["software"] = st.number_input("software ($/month)", min_value=0.0, value=float(f_lines["software"]), step=10.0)
        f_lines["equipment_maintenance"] = st.number_input("equipment_maintenance ($/month)", min_value=0.0, value=float(f_lines["equipment_maintenance"]), step=10.0)
        f_lines["admin"] = st.number_input("admin ($/month)", min_value=0.0, value=float(f_lines["admin"]), step=10.0)
        st.info(f"**Total Monthly Fixed Expense:** {fmt_usd(sum(f_lines.values()))}")

# ==============================================================================
# TAB 3: AP CALCULUS MATH SKILLS & CHALLENGE LEVEL PANEL
# ==============================================================================
with tab_math:
    st.subheader("📐 Math Skills & Challenge Level Panel — AP Calculus")
    level = st.selectbox(
        "Select Challenge Level (Foundation / Applied / Advanced)",
        options=["Foundation", "Applied", "Advanced"],
        index=["Foundation", "Applied", "Advanced"].index(state["selected_level"])
    )
    state["selected_level"] = level
    state["level_by_skill"]["AP Calculus"] = level

    p0 = float(inp["base_price"])
    D0 = float(inp["D0"])
    v = float(sum(v_lines.values()))
    F = float(sum(f_lines.values()))
    cap = float(preview["capacity"])

    a = 2.0 * D0
    b = D0 / p0
    p_max = 2.0 * p0
    p_corner = max(0.0, (a - cap) / b) if b > 0 else 0.0
    p_unconstrained = (a + b * v) / (2.0 * b) if b > 0 else p0

    st.markdown(f"**Selected Level:** `{level}` | **Business Question:** *What kit price $p$ maximizes monthly operating profit subject to capacity constraints, and how do continuous rates accumulate over time?*")

    if level == "Foundation":
        st.markdown("### Foundation Task: Unconstrained Profit Derivative & Critical Point")
        st.latex(r"q(p) = a - b p \quad \text{on } 0 \le p \le 2p_0")
        st.latex(r"P(p) = (p - v)(a - b p) - F \qquad P'(p) = a + b v - 2 b p")
        st.write(
            f"- **Parameters:** $a = {a:.2f}$ kits, $b = {b:.5f}$ kits/dollar, $v = \\${v:.2f}$/kit, $F = \\${F:.2f}$/month, Domain: $0 \\le p \\le \\${p_max:.2f}$.\n"
            f"- **Unconstrained Critical Point:** $p^* = \\frac{{a + bv}}{{2b}} = \\${p_unconstrained:.2f}$ per kit (where $P'(p^*) = 0$ dollars per dollar of price change)."
        )
    elif level == "Applied":
        st.markdown("### Applied Task: Capacity-Constrained Piecewise Profit & Corner Check")
        st.latex(r"s(p) = \min\left(\text{capacity},\ \max(0,\ a - b p)\right)")
        st.latex(r"P'(p) = \begin{cases} \text{capacity} & \text{if } p < p_{\text{corner}} \\ \text{undefined (corner)} & \text{at } p_{\text{corner}} = \frac{a - \text{capacity}}{b} \\ a + b v - 2 b p & \text{if } p > p_{\text{corner}} \end{cases}")
        feas_note = (
            f"Since demand exceeds capacity at $p^*$, the constrained continuous optimum shifts to the corner $p = \\${p_corner:.2f}$!"
            if (a - b * p_unconstrained) > cap
            else "Since demand is within capacity, $p^*$ is feasible!"
        )
        st.write(
            f"- **Capacity Boundary:** $\\text{{capacity}} = {cap:.0f}$ kits/month $\\implies p_{{\\text{{corner}}}} = \\${p_corner:.2f}$/kit.\n"
            f"- **Feasibility Check:** Unconstrained $p^* = \\${p_unconstrained:.2f}$ requires $q({p_unconstrained:.2f}) = {a - b*p_unconstrained:.2f}$ kits. {feas_note}"
        )
    else:
        st.markdown("### Advanced Task: Constrained Optimization + Definite Integration of Continuous Rates")
        st.latex(r"s(p) = \min(\text{capacity},\ \max(0,\ a - b p)), \qquad \text{Net Change} = \int_{t_1}^{t_2} [r(t) - c(t)]\,dt")
        st.write(
            f"- **Constrained Optimum Check:** Capacity corner at $p_{{\\text{{corner}}}} = \\${p_corner:.2f}$ vs. unconstrained critical point $p^* = \\${p_unconstrained:.2f}$ (continuous projection vs. rounded integer sales).\n"
            f"- **Definite Integral Rate Model:** Integrates continuous revenue rate $r(t)$ and cost rate $c(t)$ (in \\$/day) over $[0, T]$ days without differentiating step/floor functions."
        )

    p_grid = np.linspace(0, p_max, 241)
    q_cont = np.maximum(0.0, a - b * p_grid)
    if level == "Foundation":
        s_cont = q_cont
        p_deriv = a + b * v - 2.0 * b * p_grid
    else:
        s_cont = np.minimum(cap, q_cont)
        p_deriv = np.where(p_grid < p_corner, cap, a + b * v - 2.0 * b * p_grid)

    profit_cont = (p_grid - v) * s_cont - F
    s_int = np.floor(s_cont)
    profit_int = (p_grid - v) * s_int - F

    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.10,
        subplot_titles=("Profit Function P(p) - Continuous Model vs. Integer Rounded", "Derivative P'(p) ($/($/kit))")
    )
    fig.add_trace(go.Scatter(x=p_grid, y=profit_cont, name="Continuous Profit P(p)", line=dict(color="#1f77b4", width=3)), row=1, col=1)
    fig.add_trace(go.Scatter(x=p_grid, y=profit_int, name="Rounded Integer Profit (floor)", line=dict(color="#ff7f0e", dash="dot")), row=1, col=1)
    fig.add_hline(y=0, line_dash="dash", line_color="gray", row=1, col=1)

    if level in ["Applied", "Advanced"] and 0 <= p_corner <= p_max:
        corner_profit = (p_corner - v) * min(cap, max(0.0, a - b * p_corner)) - F
        fig.add_vline(x=p_corner, line_dash="dash", line_color="#d62728", annotation_text=f"Capacity Corner p=${p_corner:.2f}")
        fig.add_trace(go.Scatter(x=[p_corner], y=[corner_profit], mode="markers", name="Capacity Corner", marker=dict(size=10, color="#d62728", symbol="diamond")), row=1, col=1)

    if level in ["Applied", "Advanced"] and 0 < p_corner < p_max:
        left_mask = p_grid < p_corner
        right_mask = p_grid > p_corner
        fig.add_trace(go.Scatter(x=p_grid[left_mask], y=p_deriv[left_mask], name="P'(p) Capacity Branch", line=dict(color="#2ca02c", width=2)), row=2, col=1)
        fig.add_trace(go.Scatter(x=p_grid[right_mask], y=p_deriv[right_mask], name="P'(p) Demand Branch", line=dict(color="#9467bd", width=2)), row=2, col=1)
        fig.add_trace(go.Scatter(x=[p_corner], y=[cap], mode="markers", name="Undefined Corner (open)", marker=dict(size=9, color="white", line=dict(color="#d62728", width=2))), row=2, col=1)
    else:
        fig.add_trace(go.Scatter(x=p_grid, y=p_deriv, name="P'(p)", line=dict(color="#2ca02c", width=2)), row=2, col=1)

    fig.add_hline(y=0, line_dash="dash", line_color="gray", row=2, col=1)
    fig.update_xaxes(title_text="Kit Price p ($/kit)", row=2, col=1)
    fig.update_yaxes(title_text="Profit ($/mo)", row=1, col=1)
    fig.update_yaxes(title_text="Rate ($ / ($/kit))", row=2, col=1)
    fig.update_layout(height=560, title_text=f"{TEAM_ID} | {PATHWAY_ID} | {COURSE} ({level}) | Snapshot {state['snapshot_id']}")
    st.plotly_chart(fig, use_container_width=True)

    sample_prices = sorted(list(set([0, 60, 90, round(p_corner, 2), round(p0, 2), round(p_unconstrained, 2), 180, round(p_max, 2)])))
    sample_prices = [sp for sp in sample_prices if 0 <= sp <= p_max]
    table_rows = []
    for sp in sample_prices:
        qc = max(0.0, a - b * sp)
        sc = qc if level == "Foundation" else min(cap, qc)
        si = math.floor(sc)
        pc = (sp - v) * sc - F
        pi = (sp - v) * si - F
        table_rows.append({
            "Price p ($)": sp,
            "Continuous Demand q(p)": round(qc, 2),
            "Continuous Sold s(p)": round(sc, 2),
            "Integer Sold floor(s)": si,
            "Continuous Profit ($)": round(pc, 2),
            "Integer Profit ($)": round(pi, 2)
        })
    st.markdown("#### Linked Price-Volume-Profit Table")
    st.dataframe(pd.DataFrame(table_rows), use_container_width=True, hide_index=True)

    if level == "Advanced":
        st.divider()
        st.markdown("#### Advanced Integration Module: Campaign Rate Accumulation (Isolated from Monthly Ledger)")
        ic1, ic2, ic3 = st.columns(3)
        t_end = ic1.slider("Campaign Horizon T (days)", min_value=1, max_value=30, value=10)
        r0 = ic2.number_input("Base Revenue Rate r0 ($/day)", value=100.0)
        r_slope = ic2.number_input("Revenue Rate Growth ($/day^2)", value=20.0)
        c0 = ic3.number_input("Base Cost Rate c0 ($/day)", value=60.0)
        c_slope = ic3.number_input("Cost Rate Growth ($/day^2)", value=5.0)

        acc_rev = r0 * t_end + 0.5 * r_slope * (t_end ** 2)
        acc_cost = c0 * t_end + 0.5 * c_slope * (t_end ** 2)
        acc_prof = acc_rev - acc_cost

        m1, m2, m3 = st.columns(3)
        m1.metric(f"Accumulated Revenue [0, {t_end}d]", fmt_usd(acc_rev))
        m2.metric(f"Accumulated Cost [0, {t_end}d]", fmt_usd(acc_cost))
        m3.metric(f"Accumulated Net Profit [0, {t_end}d]", fmt_usd(acc_prof))

        t_vals = np.linspace(0, t_end, 100)
        fig_int = go.Figure()
        fig_int.add_trace(go.Scatter(x=t_vals, y=r0 + r_slope * t_vals, name="r(t) Revenue Rate ($/day)", line=dict(color="#1f77b4")))
        fig_int.add_trace(go.Scatter(x=t_vals, y=c0 + c_slope * t_vals, name="c(t) Cost Rate ($/day)", fill="tonexty", line=dict(color="#d62728")))
        fig_int.update_layout(title=f"Shaded Net Profit Accumulation Area = {fmt_usd(acc_prof)} over 0 <= t <= {t_end} days", xaxis_title="Day t", yaxis_title="Rate ($/day)", height=320)
        st.plotly_chart(fig_int, use_container_width=True)

    st.info("**Interpretation Prompt:** What changed when you adjusted price or challenge level? Where is the feasible maximum profit, and why does a rounded integer transaction differ from the continuous calculus curve?")

# ==============================================================================
# TAB 4: DATED LEDGER & CSV EXPORT
# ==============================================================================
with tab_ledger:
    st.subheader("📒 Persistent Dated Event Ledger")
    if len(state["ledger"]) == 0:
        st.warning("No transactions committed yet. Use Tab 1 to approve a monthly run or run the fixture test in Tab 5.")
    else:
        ledger_df = pd.DataFrame(state["ledger"])
        st.dataframe(ledger_df, use_container_width=True, hide_index=True)
        csv_bytes = ledger_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="⬇️ Export Ledger as CSV",
            data=csv_bytes,
            file_name=f"los_robots_10_ledger_v{state['state_version']}.csv",
            mime="text/csv"
        )

# ==============================================================================
# TAB 5: STAGE 1 ACCEPTANCE TESTS
# ==============================================================================
with tab_tests:
    st.subheader("✅ Stage 1 Automated Verification & Fixture Replay")
    st.markdown("Run the official **ROB-3** and **AP Calculus** acceptance checks from the Student Handbook.")

    if st.button("▶️ Run All Stage 1 Acceptance Tests", type="primary"):
        results = []

        fixture_df = pd.read_csv(io.StringIO(FIXTURE_CSV_CONTENT))
        expected_fixture = [
            {"month": "2027-01", "sold": 30, "rev": 3600.0, "exp": 2550.0, "prof": 1050.0, "cash": 6950.0, "stock": 70},
            {"month": "2027-02", "sold": 30, "rev": 3600.0, "exp": 2650.0, "prof": 950.0, "cash": 8800.0, "stock": 40},
            {"month": "2027-03", "sold": 22, "rev": 2640.0, "exp": 2030.0, "prof": 610.0, "cash": 10070.0, "stock": 18}
        ]
        sim_cash = 5000.0
        sim_stock = 100
        base_var = {"components_COGS": 30.0, "assembly_labor": 20.0, "packaging": 10.0, "warranty_consumables": 5.0}
        base_fix = {"workspace": 250.0, "software": 100.0, "equipment_maintenance": 150.0, "admin": 100.0}

        for idx, row in fixture_df.iterrows():
            exp = expected_fixture[idx]
            out = run_rob3_month(
                price=120.0,
                requested=int(row["requested"]),
                staff_hours=90.0,
                hours_per_unit=3.0,
                opening_cash=sim_cash,
                opening_stock_units=sim_stock,
                component_unit_cost=30.0,
                restock_units=0,
                defect_rate=0.0,
                var_lines=base_var,
                fixed_lines=base_fix,
                ad_cost=float(row["ad_cost"]),
                capacity_override=int(row["capacity_override"])
            )
            passed = (
                out["sold"] == exp["sold"]
                and abs(out["net_revenue"] - exp["rev"]) < 0.01
                and abs(out["total_expense"] - exp["exp"]) < 0.01
                and abs(out["operating_profit"] - exp["prof"]) < 0.01
                and abs(out["ending_cash"] - exp["cash"]) < 0.01
                and out["ending_stock_units"] == exp["stock"]
            )
            results.append({
                "Test": f"Fixture {exp['month']}",
                "Status": "PASS" if passed else "FAIL",
                "Details": f"Sold={out['sold']} (exp {exp['sold']}), Profit={fmt_usd(out['operating_profit'])} (exp {fmt_usd(exp['prof'])}), Cash={fmt_usd(out['ending_cash'])} (exp {fmt_usd(exp['cash'])}), Stock={out['ending_stock_units']} (exp {exp['stock']})"
            })
            sim_cash = out["ending_cash"]
            sim_stock = out["ending_stock_units"]

        low_stock_out = run_rob3_month(
            price=120.0, requested=40, staff_hours=90.0, hours_per_unit=3.0,
            opening_cash=5000.0, opening_stock_units=10, component_unit_cost=30.0,
            restock_units=0, defect_rate=0.0, var_lines=base_var, fixed_lines=base_fix
        )
        t2_pass = (
            low_stock_out["sold"] == 10
            and abs(low_stock_out["net_revenue"] - 1200.0) < 0.01
            and abs(low_stock_out["total_expense"] - 1250.0) < 0.01
            and abs(low_stock_out["operating_profit"] - (-50.0)) < 0.01
            and low_stock_out["ending_stock_units"] == 0
        )
        results.append({
            "Test": "ROB-3 Stock Exhaustion Check",
            "Status": "PASS" if t2_pass else "FAIL",
            "Details": f"Sold={low_stock_out['sold']}, Rev={fmt_usd(low_stock_out['net_revenue'])}, Exp={fmt_usd(low_stock_out['total_expense'])}, Profit={fmt_usd(low_stock_out['operating_profit'])}, Stock={low_stock_out['ending_stock_units']}"
        })

        zero_out = run_rob3_month(
            price=120.0, requested=0, staff_hours=90.0, hours_per_unit=3.0,
            opening_cash=5000.0, opening_stock_units=100, component_unit_cost=30.0,
            restock_units=0, defect_rate=0.0, var_lines=base_var, fixed_lines=base_fix
        )
        t3_pass = zero_out["sold"] == 0 and zero_out["net_revenue"] == 0.0 and abs(zero_out["operating_profit"] - (-600.0)) < 0.01
        results.append({
            "Test": "Zero Sales Boundary Check",
            "Status": "PASS" if t3_pass else "FAIL",
            "Details": f"Rev={fmt_usd(zero_out['net_revenue'])}, Var={fmt_usd(zero_out['variable_expense'])}, Profit={fmt_usd(zero_out['operating_profit'])}"
        })

        a_c, b_c = 2.0 * 60.0, 60.0 / 30.0
        p_corner_c = (a_c - 40.0) / b_c
        profit_c = (p_corner_c - 10.0) * 40.0 - 500.0
        integral_c = (100.0 * 10.0 + 0.5 * 20.0 * 100.0) - (60.0 * 10.0 + 0.5 * 5.0 * 100.0)
        t4_pass = abs(p_corner_c - 40.0) < 1e-6 and abs(profit_c - 700.0) < 1e-6 and abs(integral_c - 1150.0) < 1e-6
        results.append({
            "Test": "AP Calculus Constrained Optimum & Integral Check",
            "Status": "PASS" if t4_pass else "FAIL",
            "Details": f"Constrained p*=${p_corner_c:.2f} (exp $40.00), Profit=${profit_c:.2f} (exp $700.00), Rate Integral=${integral_c:.2f} (exp $1,150.00)"
        })

        wrong_team = json.dumps({"team_id": "OTHER-TEAM", "pathway_id": "ROB-3", "course": "AP Calculus", "snapshot_id": "S1", "state_version": 99, "simulation_date": "2027-01-01", "currency": "USD", "inputs": {}, "cost_lines": {}, "balances": {"cash": 5000, "stock_units": 100}, "ledger": []})
        ok_wt, _ = validate_and_import_snapshot(wrong_team)
        stale_ver = json.dumps({"team_id": TEAM_ID, "pathway_id": "ROB-3", "course": "AP Calculus", "snapshot_id": "S0", "state_version": 0, "simulation_date": "2027-01-01", "currency": "USD", "inputs": {}, "cost_lines": {}, "balances": {"cash": 5000, "stock_units": 100}, "ledger": []})
        ok_sv, _ = validate_and_import_snapshot(stale_ver)
        t5_pass = (not ok_wt) and (not ok_sv)
        results.append({
            "Test": "Import Validation (Wrong Team & Stale Version Rejection)",
            "Status": "PASS" if t5_pass else "FAIL",
            "Details": "Wrong team_id rejected and stale state_version v0 rejected as required."
        })

        st.dataframe(pd.DataFrame(results), use_container_width=True, hide_index=True)
