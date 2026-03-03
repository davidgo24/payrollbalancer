"""
LWOP Calculator: For employees with LWOP (from leave conversion).
Rule: No OT when LWOP. Convert Guarantee→LWOP, OT→REG.
Optionally add LWOP to reach 40 REG + LWOP.
"""
from __future__ import annotations

import pandas as pd
from dataclasses import dataclass
from typing import Optional

from config.bank_mapping import LWOP_CODE, REG_CODE, OT_15_CODE, OT_10_CODE, GUARANTEE_CODE

# Codes we convert when employee has LWOP
GUARANTEE_CODES = {GUARANTEE_CODE, "GUARANTEE"}
OT_CODES = {OT_15_CODE, "OT 1.5", OT_10_CODE, "OT 1.0", "CT EARN 1.5", "CT EARN 1.0"}


@dataclass
class LWOPAction:
    emp_id: int
    original_code: str
    original_hrs: float
    date: str
    proposed_code: str
    proposed_hrs: float
    reason: str


def apply_lwop_rules(df: pd.DataFrame, emp_ids_with_lwop: set[int]) -> tuple[pd.DataFrame, list[LWOPAction]]:
    """
    For employees in emp_ids_with_lwop, apply:
    1. Guarantee → LWOP
    2. OT 1.5 / OT 1.0 / CT EARN → REG FT (no OT when LWOP)
    """
    suggested = df.copy()
    actions: list[LWOPAction] = []

    for emp_id in emp_ids_with_lwop:
        mask = suggested["emp_id"] == emp_id
        emp_df = suggested[mask]

        for idx, row in emp_df.iterrows():
            code = str(row["code"]).strip().upper()
            hrs = float(row["hrs"])

            if code in GUARANTEE_CODES and hrs > 0:
                suggested.loc[idx, "code"] = LWOP_CODE
                actions.append(LWOPAction(
                    emp_id=emp_id,
                    original_code=row["code"],
                    original_hrs=hrs,
                    date=str(row["date"].date() if hasattr(row["date"], "date") else row["date"]),
                    proposed_code=LWOP_CODE,
                    proposed_hrs=hrs,
                    reason="LWOP rule: Guarantee → LWOP when employee has LWOP",
                ))
            elif code in OT_CODES or "OT" in code or "CT EARN" in code:
                # Convert OT/CT to REG
                suggested.loc[idx, "code"] = REG_CODE
                actions.append(LWOPAction(
                    emp_id=emp_id,
                    original_code=row["code"],
                    original_hrs=hrs,
                    date=str(row["date"].date() if hasattr(row["date"], "date") else row["date"]),
                    proposed_code=REG_CODE,
                    proposed_hrs=hrs,
                    reason="LWOP rule: OT → REG when employee has LWOP (no OT over 40)",
                ))

    return suggested, actions


def get_emp_ids_with_lwop(df: pd.DataFrame) -> set[int]:
    """Return emp_ids that have any LWOP in the dataframe."""
    lwop = df[df["code"].str.upper().str.strip() == LWOP_CODE]
    return set(lwop["emp_id"].unique().astype(int))
