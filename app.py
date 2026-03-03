"""
Payroll Balancer — Web App
Upload TCP CSV + Accrual Excel, run balancer, download results.
"""
import streamlit as st
import pandas as pd
from pathlib import Path
import io

from src.loaders import load_tcp_export, load_accrual_report
from src.leave_check import run_leave_check, format_change_log, RebalanceAction
from src.lwop_calc import apply_lwop_rules, get_emp_ids_with_lwop
from src.new_world_totals import compute_totals
from src.sick_check import apply_sick_rules

st.set_page_config(page_title="Payroll Balancer", page_icon="⚖️", layout="wide")

st.title("⚖️ Payroll Balancer")
st.caption("Pre-validate TCP hours before New World import")

with st.sidebar:
    st.header("Upload files")
    tcp_file = st.file_uploader("TCP Export (CSV)", type=["csv"])
    accrual_file = st.file_uploader("Accrual Balance Report (Excel)", type=["xlsx", "xls"])

if tcp_file and accrual_file:
    try:
        with st.spinner("Loading..."):
            tcp = load_tcp_export(io.BytesIO(tcp_file.getvalue()))
            accrual = load_accrual_report(io.BytesIO(accrual_file.getvalue()))

        with st.spinner("Running balancer..."):
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

        st.success(f"Done. {len(actions)} proposed change(s).")

        # Tabs
        tab1, tab2, tab3, tab4, tab5 = st.tabs(["Suggested Table", "REG/OT Totals", "Change Log", "Exceptions", "Downloads"])

        with tab1:
            st.subheader("Suggested Rebalancing (review before New World)")
            suggested["date"] = suggested["date"].apply(lambda x: f"{x.month}/{x.day}/{x.year}")
            st.dataframe(suggested[["emp_id", "hrs", "code", "date"]], use_container_width=True, height=400)

        with tab2:
            st.subheader("New World Totals (REG vs OT)")
            st.caption("REG + OT = Regular + Premium. Use to spot REG↔OT redistribution needs.")
            totals = compute_totals(suggested)
            st.dataframe(totals, use_container_width=True)

        with tab3:
            st.subheader("Change Log")
            st.text(format_change_log(actions))

        with tab4:
            failed = [r for r in results if not r.passed]
            st.subheader("Exceptions")
            st.write(f"Skipped (Admin Leave): {len(skipped)} employees — {list(sorted(int(x) for x in skipped)[:15])}")
            st.write(f"Leave insufficient: {len(failed)} employees")
            for r in failed:
                short = ", ".join(f"{b}: {h:.2f} over" for b, h in r.shortfalls.items())
                st.write(f"  Emp {r.emp_id}: {short}")

        with tab5:
            st.subheader("Download Results")
            suggested_csv = suggested[["emp_id", "hrs", "code", "date"]].to_csv(index=False, header=False)
            st.download_button("Download suggested_rebalancing.csv", suggested_csv, "suggested_rebalancing.csv", "text/csv")

            totals_csv = totals.to_csv(index=False)
            st.download_button("Download new_world_totals.csv", totals_csv, "new_world_totals.csv", "text/csv")

            log_txt = format_change_log(actions)
            st.download_button("Download change_log.txt", log_txt, "change_log.txt", "text/plain")

    except Exception as e:
        st.error(f"Error: {e}")
        raise
else:
    st.info("Upload TCP CSV and Accrual Excel in the sidebar to run the balancer.")
