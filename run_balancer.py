#!/usr/bin/env python3
"""
Payroll Balancer - Run leave check and output suggested rebalancing.

Usage:
  python run_balancer.py --tcp <tcp.csv> --accrual <AccrualBalanceReport.xlsx> [--out-dir <dir>]

Outputs:
  - suggested_rebalancing.csv  (workable table for manual review/import)
  - change_log.txt             (what changed and why)
  - exception_summary.txt      (quick scan of who had issues)
"""
import argparse
from pathlib import Path

from src.leave_check import run_leave_check, format_change_log, RebalanceAction
from src.loaders import load_tcp_export, load_accrual_report
from src.lwop_calc import apply_lwop_rules, get_emp_ids_with_lwop
from src.new_world_totals import compute_totals, format_totals_summary
from src.sick_check import apply_sick_rules


def main():
    parser = argparse.ArgumentParser(description="Payroll Balancer - Leave check & suggested rebalancing")
    parser.add_argument("--tcp", required=True, help="Path to TCP export CSV (emp_id, hrs, code, date)")
    parser.add_argument("--accrual", required=True, help="Path to AccrualBalanceReport.xlsx")
    parser.add_argument("--out-dir", default=".", help="Output directory for results")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print("Loading data...")
    tcp = load_tcp_export(args.tcp)
    accrual = load_accrual_report(args.accrual)

    # Step 1: Sick check — OT 1.5 → 1.0 for employees who used sick (run on original data)
    suggested, sick_actions = apply_sick_rules(tcp)
    actions = []
    for a in sick_actions:
        actions.append(RebalanceAction(emp_id=a.emp_id, original_code=a.original_code, original_hrs=a.original_hrs, date=a.date, proposed_code=a.proposed_code, proposed_hrs=a.proposed_hrs, reason=a.reason, bank=None))

    # Step 2: Leave check — insufficient leave → LWOP
    suggested, results, leave_actions, skipped = run_leave_check(tcp_df=suggested, accrual_df=accrual)
    actions.extend(leave_actions)

    # Step 3: LWOP calculator — for employees who now have LWOP, convert Guarantee→LWOP, OT→REG
    emp_with_lwop = get_emp_ids_with_lwop(suggested)
    if emp_with_lwop:
        suggested, lwop_actions = apply_lwop_rules(suggested, emp_with_lwop)
        # Merge into change log format
        for a in lwop_actions:
            actions.append(RebalanceAction(emp_id=a.emp_id, original_code=a.original_code, original_hrs=a.original_hrs, date=a.date, proposed_code=a.proposed_code, proposed_hrs=a.proposed_hrs, reason=a.reason, bank=None))

    # Save suggested rebalancing table (same format as TCP: emp_id, hrs, code, date)
    out_csv = out_dir / "suggested_rebalancing.csv"
    out_df = suggested[["emp_id", "hrs", "code", "date"]].copy()
    out_df["date"] = out_df["date"].apply(lambda x: f"{x.month}/{x.day}/{x.year}")
    out_df.to_csv(out_csv, index=False, header=False)
    print(f"Suggested rebalancing table: {out_csv}")

    # Change log
    log_text = format_change_log(actions)
    out_log = out_dir / "change_log.txt"
    out_log.write_text(log_text, encoding="utf-8")
    print(f"Change log: {out_log}")

    # Exception summary
    failed = [r for r in results if not r.passed]
    summary_lines = [
        "=== PAYROLL BALANCER - EXCEPTION SUMMARY ===",
        "",
        f"Skipped (Admin Leave - finance handles): {len(skipped)} employees: {sorted(int(x) for x in skipped)[:10]}{'...' if len(skipped) > 10 else ''}",
        "",
        f"Leave insufficient: {len(failed)} employees",
        "",
    ]
    for r in failed:
        short = ", ".join(f"{b}: {h:.2f} over" for b, h in r.shortfalls.items())
        summary_lines.append(f"  Emp {r.emp_id}: {short}")
    out_summary = out_dir / "exception_summary.txt"
    out_summary.write_text("\n".join(summary_lines), encoding="utf-8")
    print(f"Exception summary: {out_summary}")

    # New World totals (REG vs OT) for redistribution review
    totals_df = compute_totals(suggested)
    totals_df.to_csv(out_dir / "new_world_totals.csv", index=False)
    totals_txt = format_totals_summary(totals_df)
    (out_dir / "new_world_totals.txt").write_text(totals_txt, encoding="utf-8")
    print(f"New World totals (REG/OT): {out_dir / 'new_world_totals.csv'}")

    print("")
    print(f"Done. {len(actions)} proposed change(s). Review suggested_rebalancing.csv before importing to New World.")


if __name__ == "__main__":
    main()
