"""
FastAPI backend for Payroll Balancer.
Accepts TCP + Accrual uploads, runs balancer, returns per-employee data for React.
"""
import io
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

from src.loaders import load_tcp_export, load_accrual_report
from src.leave_check import run_leave_check, RebalanceAction
from src.lwop_calc import apply_lwop_rules, get_emp_ids_with_lwop
from src.new_world_totals import compute_totals
from src.sick_check import apply_sick_rules

app = FastAPI(title="Payroll Balancer API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def run_balancer(tcp_bytes: bytes, accrual_bytes: bytes):
    """Run full balancer pipeline, return suggested df + metadata."""
    tcp = load_tcp_export(io.BytesIO(tcp_bytes))
    accrual = load_accrual_report(io.BytesIO(accrual_bytes))

    actions = []
    suggested, sick_actions = apply_sick_rules(tcp)
    for a in sick_actions:
        actions.append(RebalanceAction(emp_id=a.emp_id, original_code=a.original_code, original_hrs=a.original_hrs, date=a.date, proposed_code=a.proposed_code, proposed_hrs=a.proposed_hrs, reason=a.reason, bank=None))

    suggested, results, leave_actions, skipped = run_leave_check(tcp_df=suggested, accrual_df=accrual)
    actions.extend(leave_actions)

    emp_with_lwop = get_emp_ids_with_lwop(suggested)
    if emp_with_lwop:
        suggested, lwop_actions = apply_lwop_rules(suggested, emp_with_lwop)
        for a in lwop_actions:
            actions.append(RebalanceAction(emp_id=a.emp_id, original_code=a.original_code, original_hrs=a.original_hrs, date=a.date, proposed_code=a.proposed_code, proposed_hrs=a.proposed_hrs, reason=a.reason, bank=None))

    suggested["date_str"] = suggested["date"].apply(lambda x: f"{x.month}/{x.day}/{x.year}")
    suggested["day"] = suggested["date"].apply(lambda x: DAY_NAMES[x.weekday()])
    totals = compute_totals(suggested)

    return suggested, totals, results, skipped, actions


def pivot_employee_to_grid(emp_df):
    """
    Convert emp rows (emp_id, date, hrs, code) to grid: rows=days, columns=hour codes.
    Returns: {days: [{date, day, cells: {code: hrs}}], codes: [code list]}
    """
    codes = sorted(emp_df["code"].unique().tolist())
    days_data = []
    for (date_str, day), grp in emp_df.groupby(["date_str", "day"]):
        cells = {row["code"]: float(row["hrs"]) for _, row in grp.iterrows()}
        days_data.append({"date": date_str, "day": day, "cells": cells})
    days_data.sort(key=lambda x: x["date"])
    return {"days": days_data, "codes": codes}


@app.post("/api/run")
async def run(file_tcp: UploadFile = File(...), file_accrual: UploadFile = File(...)):
    if not file_tcp.filename.endswith(('.csv', '.txt')) or not file_accrual.filename.lower().endswith(('.xlsx', '.xls')):
        raise HTTPException(400, "Need TCP CSV and Accrual Excel")
    tcp_bytes = await file_tcp.read()
    accrual_bytes = await file_accrual.read()
    try:
        suggested, totals, results, skipped, actions = run_balancer(tcp_bytes, accrual_bytes)
    except Exception as e:
        raise HTTPException(500, str(e))

    date_range = f"{suggested['date'].min().strftime('%m/%d/%Y')} – {suggested['date'].max().strftime('%m/%d/%Y')}"

    employees = []
    name_lookup = {}
    try:
        accrual_df = load_accrual_report(io.BytesIO(accrual_bytes))
        name_lookup = dict(zip(accrual_df["emp_id"].astype(int), accrual_df["name"].astype(str)))
    except Exception:
        pass

    for emp_id in sorted(suggested["emp_id"].unique()):
        emp_df = suggested[suggested["emp_id"] == emp_id][["date_str", "day", "hrs", "code"]]
        grid = pivot_employee_to_grid(emp_df)
        tot_row = totals[totals["emp_id"] == emp_id].iloc[0] if len(totals[totals["emp_id"] == emp_id]) else None
        emp_actions = [a for a in actions if a.emp_id == emp_id]
        employees.append({
            "emp_id": int(emp_id),
            "name": name_lookup.get(emp_id, str(emp_id)),
            "totals": {"reg": float(tot_row["reg_hrs"]), "ot": float(tot_row["ot_hrs"]), "lwop": float(tot_row["lwop_hrs"]), "reg_plus_ot": float(tot_row["reg_plus_ot"])} if tot_row is not None else {},
            "grid": grid,
            "actions": [{"original_code": a.original_code, "original_hrs": a.original_hrs, "proposed_code": a.proposed_code, "reason": a.reason} for a in emp_actions],
        })

    all_codes = sorted(set(c for e in employees for c in e["grid"]["codes"]))
    return {
        "dateRange": date_range,
        "skipped": [int(x) for x in skipped],
        "employees": employees,
        "allCodes": all_codes,
    }


@app.get("/api/health")
def health():
    return {"ok": True}
