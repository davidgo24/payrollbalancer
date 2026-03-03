"""
New World totals: REG vs OT per employee.
Per New World screenshot: OT hrs + CTE hrs → Premium; REG + paid leave → Regular.
Helps you see who needs REG↔OT redistribution.
"""
from __future__ import annotations

import pandas as pd
from config.bank_mapping import get_code_type_for_new_world, REG_TYPE_CODES, OT_TYPE_CODES


def compute_totals(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute per-employee REG, OT, LWOP totals (matching New World display).
    Returns DataFrame with emp_id, reg_hrs, ot_hrs, lwop_hrs, other_hrs, total_hrs.
    """
    rows = []
    for emp_id in df["emp_id"].unique():
        emp = df[df["emp_id"] == emp_id]
        reg = ot = lwop = other = 0.0
        for _, row in emp.iterrows():
            code = str(row["code"]).strip().upper()
            hrs = float(row["hrs"])
            if code == "LWOP":
                lwop += hrs
            elif code in REG_TYPE_CODES:
                reg += hrs
            elif code in OT_TYPE_CODES:
                ot += hrs
            else:
                other += hrs
        rows.append({
            "emp_id": emp_id,
            "reg_hrs": round(reg, 4),
            "ot_hrs": round(ot, 4),
            "lwop_hrs": round(lwop, 4),
            "other_hrs": round(other, 4),
            "total_hrs": round(reg + ot + lwop + other, 4),
            "reg_plus_ot": round(reg + ot, 4),
        })
    return pd.DataFrame(rows)


def format_totals_summary(totals_df: pd.DataFrame) -> str:
    """Human-readable summary for quick scan."""
    lines = [
        "=== NEW WORLD TOTALS (REG vs OT) ===",
        "Use this to see who needs REG↔OT redistribution. REG + OT = Regular + Premium.",
        "",
        f"{'Emp ID':<10} {'REG':>10} {'OT':>10} {'LWOP':>10} {'Reg+OT':>10}",
        "-" * 52,
    ]
    for _, row in totals_df.iterrows():
        lines.append(f"{int(row['emp_id']):<10} {row['reg_hrs']:>10.2f} {row['ot_hrs']:>10.2f} {row['lwop_hrs']:>10.2f} {row['reg_plus_ot']:>10.2f}")
    return "\n".join(lines)
