"""
Sick Check: When sick bank is used, convert OT 1.5 → OT 1.0 for that week
until converted hours = sick hours used.
"""
from __future__ import annotations

import pandas as pd
from dataclasses import dataclass
from typing import Optional

from config.bank_mapping import OT_15_CODE, OT_10_CODE

SICK_CODES = {"SICK PAY", "FMLA SICK", "AL SICK PAY", "HEALTHY SICK PAY", "HEALTHY SICK PT", "HEALTHY LMTD PT"}


@dataclass
class SickAction:
    emp_id: int
    original_code: str
    original_hrs: float
    date: str
    proposed_code: str
    proposed_hrs: float
    reason: str


def apply_sick_rules(df: pd.DataFrame) -> tuple[pd.DataFrame, list[SickAction]]:
    """
    For each employee who used SICK this period:
    - Sum sick hours used
    - Convert OT 1.5 → OT 1.0, up to that amount (FIFO by date)
    """
    suggested = df.copy()
    actions: list[SickAction] = []

    for emp_id in df["emp_id"].unique():
        emp_df = df[df["emp_id"] == emp_id]
        sick_used = sum(
            float(row["hrs"]) for _, row in emp_df.iterrows()
            if str(row["code"]).strip().upper() in SICK_CODES
        )
        if sick_used <= 0:
            continue

        # Get OT 1.5 rows for this emp, sorted by date (FIFO)
        ot_rows = emp_df[
            emp_df["code"].str.upper().str.strip().isin([OT_15_CODE, "OT 1.5"])
        ].sort_values("date")

        hrs_to_convert = sick_used
        for idx, row in ot_rows.iterrows():
            if hrs_to_convert <= 0:
                break
            hrs = float(row["hrs"])
            convert_this = min(hrs, hrs_to_convert)

            if convert_this <= 0:
                continue

            if convert_this >= hrs:
                suggested.loc[idx, "code"] = OT_10_CODE
            else:
                suggested.loc[idx, "hrs"] = hrs - convert_this
                extra = suggested.loc[[idx]].copy()
                extra["code"] = OT_10_CODE
                extra["hrs"] = convert_this
                suggested = pd.concat([suggested, extra], ignore_index=True)

            hrs_to_convert -= convert_this
            actions.append(SickAction(
                emp_id=emp_id,
                original_code=row["code"],
                original_hrs=hrs,
                date=str(row["date"].date() if hasattr(row["date"], "date") else row["date"]),
                proposed_code=OT_10_CODE,
                proposed_hrs=convert_this,
                reason=f"Sick rule: OT 1.5 → 1.0 when sick used ({sick_used:.2f} hrs sick this period)",
            ))

    return suggested, actions
