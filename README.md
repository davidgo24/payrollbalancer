# Payroll Balancer

Pre-validation layer for transit payroll: run before importing TimeClockPlus data into New World.

**What it does:**
- Proposes **suggested rebalancing** based on your rules (not just flags)
- Outputs a **workable table** you can review and manually tweak before New World
- Keeps you accurate and abstracts the mental energy of "what should I change?"

## Quick start

**React app (recommended) — one employee at a time, like New World:**
```bash
# Terminal 1: API
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn api.main:app --reload --port 8000

# Terminal 2: React frontend
cd frontend && npm install && npm run dev
```
Open http://localhost:5173 → drag & drop files, review one employee at a time, edit inline.

**Streamlit (legacy):**
```bash
streamlit run app.py
```

**CLI:**
```bash
python run_balancer.py \
  --tcp /path/to/2.22-2.28.26.csv \
  --accrual /path/to/AccrualBalanceReport.xlsx \
  --out-dir ./output
```

## Outputs

| File | Purpose |
|------|---------|
| `suggested_rebalancing.csv` | Same format as TCP export — proposed changes applied. Review and use for New World import. |
| `new_world_totals.csv` | **REG vs OT per employee** — matches New World (OT+CTE→Premium, REG+leave→Regular). Use to spot REG↔OT redistribution needs. |
| `change_log.txt` | What changed and why |
| `exception_summary.txt` | Quick scan: who had insufficient leave, who was skipped |

## Rules (in order)

1. **Sick check** — When sick is used: OT 1.5 → OT 1.0 (match sick hours).
2. **Leave check** — When leave used > accrual balance: try fallback banks first:
   - SICK exhausted → VAC → COMP → AL → LWOP
   - VAC exhausted → SICK → COMP → AL → LWOP
   - (same pattern for AL, COMP)
3. **LWOP rule** — For LWOP employees: **Guarantee → LWOP** (40 stays, unpaid), OT → REG (no OT when LWOP).

Admin Leave employees are skipped (finance handles).

## Data format

- **TCP export:** `emp_id, hrs, code, date` (no header)
- **AccrualBalanceReport.xlsx:** Emp ID in column A, banks in SICK, VAC, AL, COMP, HOLIDAY columns

See `GAMEPLAN.md` for full details.
