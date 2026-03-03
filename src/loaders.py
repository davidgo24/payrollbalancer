"""
Data loaders for TCP export, AccrualBalanceReport, and Job Code List.
"""
import pandas as pd
from pathlib import Path

from config.bank_mapping import get_bank_for_code, is_skip_employee


def load_tcp_export(path: str | Path) -> pd.DataFrame:
    """Load TCP export CSV. Columns: emp_id, hrs, code, date."""
    df = pd.read_csv(path, header=None, names=["emp_id", "hrs", "code", "date"])
    df["emp_id"] = df["emp_id"].astype(int)
    df["hrs"] = pd.to_numeric(df["hrs"], errors="coerce").fillna(0)
    df["date"] = pd.to_datetime(df["date"], format="mixed", errors="coerce")
    df["code"] = df["code"].astype(str).str.strip()
    return df.dropna(subset=["date"]).reset_index(drop=True)


def load_accrual_report(path: str | Path) -> pd.DataFrame:
    """
    Load AccrualBalanceReport.xlsx.
    Known structure (City of Montebello): Row 2 = dept header, Row 3+ = data.
    Col 0 = emp_id, Col 1 = name, Col 3 = AL, Col 6 = COMP,
    Col 7 = HOLIDAY, Col 8 = SICK, Col 9 = VAC. (Col 2 = ADMIN LV, skip.)
    """
    df = pd.read_excel(path, header=None)
    # Data starts row 3; row 2 is "Primary Department" header
    data = df.iloc[3:].copy()
    result = pd.DataFrame()
    result["emp_id"] = pd.to_numeric(data.iloc[:, 0], errors="coerce")
    result["name"] = data.iloc[:, 1].astype(str)
    result["AL"] = pd.to_numeric(data.iloc[:, 3], errors="coerce").fillna(0)
    result["COMP"] = pd.to_numeric(data.iloc[:, 6], errors="coerce").fillna(0)
    result["HOLIDAY"] = pd.to_numeric(data.iloc[:, 7], errors="coerce").fillna(0)
    result["SICK"] = pd.to_numeric(data.iloc[:, 8], errors="coerce").fillna(0)
    result["VAC"] = pd.to_numeric(data.iloc[:, 9], errors="coerce").fillna(0)
    result = result.dropna(subset=["emp_id"])
    result["emp_id"] = result["emp_id"].astype(int)
    return result


def get_employees_to_skip(tcp_df: pd.DataFrame) -> set[int]:
    """Employees with ADMIN LEAVE PAY - skip entirely."""
    admin = tcp_df[tcp_df["code"].str.upper() == "ADMIN LEAVE PAY"]
    return set(admin["emp_id"].unique().astype(int))


def get_leave_used_by_employee(tcp_df: pd.DataFrame) -> dict[int, dict[str, float]]:
    """
    Sum leave hours used per employee per bank.
    Returns: {emp_id: {bank: hours}}
    """
    out = {}
    for _, row in tcp_df.iterrows():
        bank = get_bank_for_code(row["code"])
        if bank is None:
            continue
        eid = int(row["emp_id"])
        if eid not in out:
            out[eid] = {"SICK": 0.0, "VAC": 0.0, "AL": 0.0, "COMP": 0.0, "HOLIDAY": 0.0}
        out[eid][bank] = out[eid].get(bank, 0) + float(row["hrs"])
    return out
