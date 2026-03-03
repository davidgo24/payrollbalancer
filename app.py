"""
Payroll Balancer — Web App
Upload TCP CSV + Accrual Excel, run balancer, edit results inline, download.
"""
import streamlit as st
import pandas as pd
import io
from datetime import datetime

from config.bank_mapping import HOURS_CODES
from src.loaders import load_tcp_export, load_accrual_report
from src.leave_check import run_leave_check, format_change_log, RebalanceAction
from src.lwop_calc import apply_lwop_rules, get_emp_ids_with_lwop
from src.new_world_totals import compute_totals
from src.sick_check import apply_sick_rules

DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

st.set_page_config(page_title="Payroll Balancer", page_icon="⚖️", layout="wide", initial_sidebar_state="expanded")

st.title("⚖️ Payroll Balancer")
st.caption("Pre-validate TCP hours before New World · Drag & drop files, edit inline, download")

# Sidebar
with st.sidebar:
    st.header("📁 Upload files")
    st.caption("Drag and drop or click to browse")
    tcp_file = st.file_uploader("TCP Export (CSV)", type=["csv"], key="tcp")
    accrual_file = st.file_uploader("Accrual Balance Report (Excel)", type=["xlsx", "xls"], key="accrual")

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

        # Format for display
        suggested["date_str"] = suggested["date"].apply(lambda x: f"{x.month}/{x.day}/{x.year}")
        suggested["day"] = suggested["date"].apply(lambda x: DAY_NAMES[x.weekday()])
        date_range = f"{suggested['date'].min().strftime('%m/%d/%Y')} – {suggested['date'].max().strftime('%m/%d/%Y')}"

        # Reset edited state when input files change
        run_key = hash((tcp_file.getvalue()[:500], accrual_file.getvalue()[:500]))
        if st.session_state.get("run_key") != run_key or "edited_df" not in st.session_state:
            st.session_state.run_key = run_key
            st.session_state.edited_df = suggested[["emp_id", "day", "date_str", "hrs", "code"]].copy()

        st.success(f"✓ {len(actions)} proposed change(s) · Week: {date_range}")

        # Employee filter (narrows table; edits apply to full set when filter cleared)
        all_emps = sorted(suggested["emp_id"].unique())
        emp_filter = st.sidebar.multiselect("Filter employee (optional)", all_emps, default=[], key="emp_filter")
        disp_df = st.session_state.edited_df
        if emp_filter:
            disp_df = disp_df[disp_df["emp_id"].isin(emp_filter)]
            st.sidebar.caption("Clear filter to edit all employees")

        # Tabs
        tab1, tab2, tab3, tab4, tab5 = st.tabs(["✏️ Edit hours", "📊 REG/OT totals", "📋 Change log", "⚠️ Exceptions", "⬇️ Download"])

        with tab1:
            st.subheader("Suggested rebalancing — edit hrs and code inline")
            st.caption(f"Mon–Sun · Dates: {date_range} · Edit Hours or Code (dropdown)")
            edited = st.data_editor(
                disp_df.sort_values(["emp_id", "date_str", "code"]).reset_index(drop=True),
                column_config={
                    "emp_id": st.column_config.NumberColumn("Emp ID", disabled=True, format="%d"),
                    "day": st.column_config.TextColumn("Day", disabled=True),
                    "date_str": st.column_config.TextColumn("Date", disabled=True),
                    "hrs": st.column_config.NumberColumn("Hours", min_value=0.0, max_value=24.0, step=0.01, format="%.2f"),
                    "code": st.column_config.SelectboxColumn("Code", options=HOURS_CODES, required=True),
                },
                use_container_width=True,
                height=500,
                key="hours_editor",
            )
            if not emp_filter:
                st.session_state.edited_df = edited.copy()
            else:
                seen = {}
                for _, row in edited.iterrows():
                    key = (int(row["emp_id"]), row["date_str"])
                    matches = st.session_state.edited_df[
                        (st.session_state.edited_df["emp_id"] == row["emp_id"]) &
                        (st.session_state.edited_df["date_str"] == row["date_str"])
                    ]
                    pos = seen.get(key, 0)
                    if pos < len(matches):
                        idx = matches.index[pos]
                        st.session_state.edited_df.loc[idx, "hrs"] = row["hrs"]
                        st.session_state.edited_df.loc[idx, "code"] = row["code"]
                        seen[key] = pos + 1

        with tab2:
            st.subheader("New World totals (REG vs OT)")
            st.caption("REG + OT = Regular + Premium")
            # Recompute from edited if needed
            tot_df = st.session_state.edited_df.rename(columns={"date_str": "date"})
            totals = compute_totals(tot_df)
            st.dataframe(totals, use_container_width=True)

        with tab3:
            st.subheader("Change log")
            st.text_area("", format_change_log(actions), height=300, disabled=True)

        with tab4:
            failed = [r for r in results if not r.passed]
            st.subheader("Exceptions")
            st.write(f"**Skipped (Admin Leave):** {len(skipped)} employees — {list(sorted(int(x) for x in skipped)[:15])}")
            st.write(f"**Leave insufficient:** {len(failed)} employees")
            for r in failed:
                short = ", ".join(f"{b}: {h:.2f} over" for b, h in r.shortfalls.items())
                st.write(f"  Emp {r.emp_id}: {short}")

        with tab5:
            st.subheader("Download results")
            out_df = st.session_state.edited_df[["emp_id", "hrs", "code", "date_str"]].rename(columns={"date_str": "date"})
            suggested_csv = out_df.to_csv(index=False, header=False)
            st.download_button("📥 suggested_rebalancing.csv", suggested_csv, "suggested_rebalancing.csv", "text/csv")

            tot_df = st.session_state.edited_df.rename(columns={"date_str": "date"})
            totals = compute_totals(tot_df)
            totals_csv = totals.to_csv(index=False)
            st.download_button("📥 new_world_totals.csv", totals_csv, "new_world_totals.csv", "text/csv")

            log_txt = format_change_log(actions)
            st.download_button("📥 change_log.txt", log_txt, "change_log.txt", "text/plain")

    except Exception as e:
        st.error(f"Error: {e}")
        import traceback
        st.code(traceback.format_exc())
else:
    st.info("👈 **Upload TCP CSV and Accrual Excel** in the sidebar to run the balancer.")
    st.markdown("""
    **Workflow:**
    1. Drag & drop your TCP export (CSV) and Accrual Balance Report (Excel)
    2. Review the suggested rebalancing — **edit hrs and codes inline** in the table
    3. Check REG/OT totals to spot redistribution needs
    4. Download the final CSV for New World import
    """)
