"""
Leave Check: Validate leave used vs accrual balance.
When insufficient, try fallback banks (SICK→VAC→COMP→AL, VAC→SICK→COMP→AL, etc.)
before converting to LWOP.
"""
from __future__ import annotations

import pandas as pd
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

from config.bank_mapping import (
    get_bank_for_code,
    LWOP_CODE,
    BANK_FALLBACK,
    BANK_TO_CODE,
)
from src.loaders import (
    load_tcp_export,
    load_accrual_report,
    get_employees_to_skip,
)


@dataclass
class RebalanceAction:
    """A proposed change to a single row."""
    emp_id: int
    original_code: str
    original_hrs: float
    date: str
    proposed_code: str
    proposed_hrs: float
    reason: str
    bank: Optional[str] = None


@dataclass
class EmployeeLeaveResult:
    """Result of leave check for one employee."""
    emp_id: int
    passed: bool
    shortfalls: dict[str, float] = field(default_factory=dict)
    actions: list[RebalanceAction] = field(default_factory=list)


def _try_fallback(bal: dict, original_bank: str, needed: float) -> tuple[str | None, float]:
    """
    Try fallback banks for 'needed' hours. Return (fallback_bank, hrs_allocated) or (None, 0).
    """
    for fb in BANK_FALLBACK.get(original_bank, []):
        avail = float(bal.get(fb, 0))
        if avail >= needed:
            return (fb, needed)
        if avail > 0:
            return (fb, avail)
    return (None, 0)


def run_leave_check(
    tcp_path: str | Path | None = None,
    accrual_path: str | Path | None = None,
    tcp_df: pd.DataFrame | None = None,
    accrual_df: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, list[EmployeeLeaveResult], list[RebalanceAction], list[int]]:
    """
    Run leave check with bank fallback. When insufficient:
    - SICK exhausted → try VAC, then COMP, then AL, then LWOP
    - VAC exhausted → try SICK, then COMP, then AL, then LWOP
    - etc.
    """
    if tcp_df is not None and accrual_df is not None:
        tcp = tcp_df.copy()
        accrual = accrual_df.copy()
    elif tcp_path and accrual_path:
        tcp = load_tcp_export(tcp_path)
        accrual = load_accrual_report(accrual_path)
    else:
        raise ValueError("Provide either (tcp_path, accrual_path) or (tcp_df, accrual_df)")

    accrual_by_emp = accrual.set_index("emp_id").to_dict("index")
    skip_emp_ids = get_employees_to_skip(tcp)
    tcp_filtered = tcp[~tcp["emp_id"].isin(skip_emp_ids)].copy()

    results: list[EmployeeLeaveResult] = []
    all_actions: list[RebalanceAction] = []
    row_proposals: dict[int, tuple[str, float]] = {}

    for emp_id in tcp_filtered["emp_id"].unique():
        emp_rows = tcp_filtered[tcp_filtered["emp_id"] == emp_id]
        bal = accrual_by_emp.get(emp_id, {})
        if not bal:
            results.append(EmployeeLeaveResult(emp_id=emp_id, passed=True))
            continue

        shortfalls = {}
        emp_actions = []
        bal_remaining = {k: float(v) for k, v in bal.items() if k in ("SICK", "VAC", "AL", "COMP", "HOLIDAY")}

        for idx, row in emp_rows.iterrows():
            bank = get_bank_for_code(row["code"])
            if bank is None:
                continue

            used = float(row["hrs"])
            available = float(bal.get(bank, 0))

            if used <= available:
                bal_remaining[bank] = bal_remaining.get(bank, 0) - used
                continue

            excess = used - available
            shortfalls[bank] = shortfalls.get(bank, 0) + excess

            # Use what we can from original bank, rest from fallbacks or LWOP
            hrs_from_orig = min(used, available)
            hrs_needed = used - hrs_from_orig
            if hrs_from_orig > 0:
                bal_remaining[bank] = bal_remaining.get(bank, 0) - hrs_from_orig

            # Try fallbacks: use first bank that has >= hrs_needed for the full amount
            fallback_bank = None
            for fb in BANK_FALLBACK.get(bank, []):
                avail = bal_remaining.get(fb, 0)
                if avail >= hrs_needed:
                    fallback_bank = fb
                    bal_remaining[fb] = bal_remaining.get(fb, 0) - hrs_needed
                    break

            if fallback_bank is not None:
                new_code = BANK_TO_CODE.get(fallback_bank, row["code"])
                row_proposals[idx] = (new_code, used)
                emp_actions.append(RebalanceAction(
                    emp_id=emp_id,
                    original_code=row["code"],
                    original_hrs=used,
                    date=str(row["date"].date() if hasattr(row["date"], "date") else row["date"]),
                    proposed_code=new_code,
                    proposed_hrs=used,
                    reason=f"Insufficient {bank} → reallocated to {fallback_bank}",
                    bank=bank,
                ))
            else:
                # Some or all must go to LWOP
                row_proposals[idx] = (LWOP_CODE, used)
                emp_actions.append(RebalanceAction(
                    emp_id=emp_id,
                    original_code=row["code"],
                    original_hrs=used,
                    date=str(row["date"].date() if hasattr(row["date"], "date") else row["date"]),
                    proposed_code=LWOP_CODE,
                    proposed_hrs=used,
                    reason=f"Insufficient {bank} balance ({available:.2f}); tried fallbacks, remainder→LWOP",
                    bank=bank,
                ))

        results.append(EmployeeLeaveResult(
            emp_id=emp_id,
            passed=len(shortfalls) == 0,
            shortfalls=shortfalls,
            actions=emp_actions,
        ))
        all_actions.extend(emp_actions)

    suggested = tcp_filtered.copy()
    for idx, (prop_code, prop_hrs) in row_proposals.items():
        if idx in suggested.index:
            suggested.loc[idx, "code"] = prop_code
            suggested.loc[idx, "hrs"] = prop_hrs

    return suggested, results, all_actions, list(skip_emp_ids)


def format_change_log(actions: list[RebalanceAction]) -> str:
    """Human-readable change log."""
    lines = []
    for a in actions:
        lines.append(
            f"Emp {a.emp_id} | {a.original_hrs:.2f} {a.original_code} → {a.proposed_code} | {a.reason}"
        )
    return "\n".join(lines) if lines else "No changes proposed."
