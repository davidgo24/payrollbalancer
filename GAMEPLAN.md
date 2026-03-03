# Payroll Balancer — Gameplan

## The Problem (Summary)

You use **TimeClockPlus** to record hours, then import into **New World** for payroll. The bottleneck:

1. **TimeClockPlus has no accrual rules** — you can't see who has leave (SICK, VAC, AL, etc.) until you hit New World.
2. **Errors surface late** — New World rejects entries when leave banks are exhausted, with no prior warning.
3. **Manual reallocation is heavy** — when errors hit, you must:
   - Look up each employee's accrual balances manually
   - Convert leave → LWOP when banks are exhausted
   - For LWOP cases: convert Guarantees → LWOP, OT → REG, add LWOP to reach 40
   - For SICK used: convert OT 1.5 → OT 1.0 (matching sick hours)
   - Holiday rules add more cases

**Your core goal:** Review that everyone is at 40 + whatever OT they had — but LWOP, sick, and leave issues slow you down.

---

## Proposed Solution: Pre-Validation Layer ("Payroll Balancer")

Run validation **before** (or alongside) the New World import, using the data you already have:

| Input | Purpose |
|-------|---------|
| TCP export (e.g. `2.22-2.28.26.csv`) | emp_id, hrs, code, date |
| AccrualBalanceReport.xlsx | Leave bank balances (SICK, VAC, AL, HOLIDAY, etc.) |
| Job Code List | Maps codes (1020→REG FT, 2003→AL SICK PAY, etc.) |

**Output:**  
A **pre-validated / pre-adjusted** view plus an **exception report** so you can:
- Fix issues once in a spreadsheet or script
- Import cleaner data into New World
- Or at least know exactly who needs LWOP, OT 1.0 conversion, etc., before you open New World

---

## Phase 1: Foundation (1–2 weeks)

### 1.1 Data ingestion and mapping

**Tasks:**
- [ ] Parse TCP export format: `emp_id, hrs, code, date`
- [ ] Parse AccrualBalanceReport (employee → SICK, VAC, AL, HOLIDAY, COMP)
- [ ] Build **employee ID ↔ name** mapping (Accrual uses names; TCP uses IDs — need lookup)
- [ ] Use Job Code List to map TCP codes → New World codes (AL PAY, SICK PAY, VAC PAY, etc.)

**Leave code mapping (from your notes):**

| TCP Code | New World Code | Bank |
|----------|----------------|------|
| 2001 | AL PAY | AL |
| 3003 | CT PAY 1.0 | COMP |
| 3006 | HOL PAYOUT | OT |
| 3007 | HOL PAY | REG |
| 2003, 2024, 3009 | AL SICK PAY, FMLA SICK, SICK PAY | SICK |
| 2025, 3008 | FMLA VAC, VAC PAY | VAC |

### 1.2 Employee linkage

**Confirmed:** AccrualBalanceReport has Employee ID in **Column A** (below "Primary Department") and Employee Name in Column B. Direct match with TCP emp_id.

### 1.3 Accrual columns and skips

**Use:** AL, COMP, HOLIDAY, SICK, VAC (skip ADMIN LV — finance handles admin leave).

**Skip employees entirely** if they have ADMIN LEAVE PAY (3010) in their TCP segments — finance handles those.

**Bank mapping (code → bank):**
- **SICK:** FMLA SICK, SICK PAY, AL SICK PAY, HEALTHY SICK variants
- **VAC:** FMLA VAC, VAC PAY
- **AL:** AL PAY, FMLA AL, etc. (but skip ADMIN LEAVE PAY employees)
- **COMP:** CT PAY 1.0, FMLA CT PAY, CT SAL PAY, etc.

---

## Phase 2: Rule engine (2–3 weeks)

### 2.1 Leave balance validation

**Logic:**
1. Sum leave used per employee per bank (SICK, VAC, AL, etc.) from TCP export.
2. Look up balance in AccrualBalanceReport.
3. **Flag** when `used > balance`.

**Suggested alternatives (from your notes):**
- Suggest other banks with available balance (prioritize: SICK→VAC→AL→…)
- If nothing available → suggest LWOP

### 2.2 LWOP rule (no leave left)

**When:** Employee has leave-coded hours but no leave balance.

**Actions:**
1. Convert leave hours → LWOP.
2. Convert Guarantee hours → LWOP where needed.
3. Convert OT → REG until REG + LWOP = 40.
4. Add LWOP to reach 40 paid hours.  
   *No OT when LWOP — only REG until 40 + LWOP.*

### 2.3 Sick-used rule (OT 1.5 → OT 1.0)

**When:** Sick bank (SICK PAY, FMLA SICK, AL SICK PAY, etc.) is used in the period.

**Actions:**
1. Sum sick hours used in the week.
2. Convert OT 1.5 → OT 1.0 for that week until converted hours = sick hours used.
3. Track which days/entries to change.

### 2.4 40‑hour rule

**Principle:** OT applies only to hours beyond 40 REG (and qualifying paid leave).

- If REG + paid leave &lt; 40, adjust so that:
  - REG + leave + LWOP = 40, and
  - OT is only hours above that base.

### 2.5 Holiday rules (future)

- HOLIDAY BANKED
- HOLIDAY PAYOUT
- Holiday used to make up hours → similar OT treatment as sick
- Worked holiday + payout but needed hrs moved to another day → special case

---

## Phase 3: Workflow integration (1–2 weeks)

### 3.1 Run sequence

1. **Monday (Week 1):** Run balancer on Week 1 TCP export.
2. **Thursday (Week 2):** Run balancer on Week 2 TCP export (including projected Thu/Fri/Sat).
3. Review exception report and pre-adjusted output.
4. Import into New World — ideally with most corrections already done.

### 3.2 Outputs

| Output | Content |
|--------|---------|
| **Suggested Rebalancing Table** | Same format as TCP export (emp_id, hrs, code, date) but with *proposed* code/hr changes applied. A **workable table** you can review and manually tweak before New World — not just flags. |
| **Change log / Summary** | Per-employee: what changed, why (e.g. "Emp 1025: 9.03 FMLA VAC → LWOP — insufficient VAC balance") |
| **Exception report** | Emps with insufficient leave, suggested LWOP, OT 1.0 conversions — for quick scan |

**Design goal:** The system proposes and keeps you accurate; you stay in control and can manually override. Abstracts the mental energy of "what should I change?" so you can focus on reviewing.

### 3.3 New World compatibility

- Match New World’s expected import format (rows/columns).
- Or output a “review checklist” that mirrors the Quick Entry / Hours Code Entry layout.

---

## Phase 4: Tooling and UX (1 week)

### Options

| Option | Pros | Cons |
|--------|------|------|
| **Python script + Excel** | Quick, editable, no deployment | Manual steps, some copy‑paste |
| **Streamlit / simple web app** | Nice UI, upload files, see results | Needs Python env |
| **Excel + Power Query / VBA** | Stays in Excel | Maintenance can get messy |
| **Google Sheets + Apps Script** | Shareable, no install | Limited for large datasets |

**Recommendation:** Start with a **Python script** that:
1. Reads TCP CSV, Accrual Excel, Job Code List.
2. Applies rules and produces exception report + adjusted CSV.
3. Optionally: Streamlit wrapper for drag‑and‑drop uploads.

---

## MVP build order

1. **Leave check** — Validate leave used vs balance; when insufficient, propose reallocation (other banks or LWOP).
2. **LWOP calculator** — For leave-exhausted employees: propose GUARANTEE→LWOP, OT→REG, add LWOP to reach 40.
3. **Sick check** — When sick used: propose OT 1.5→OT 1.0 (matching sick hours).

**Backburner (post-MVP):** Holiday hrs check, labor union duties.

---

## Data you’ll need (checklist)

- [ ] TCP export format confirmed (e.g. `emp_id, hrs, code, date`)
- [ ] AccrualBalanceReport structure (columns, any filters)
- [ ] Employee ID ↔ name mapping source
- [ ] New World import format (columns, codes, required fields)
- [ ] Exact leave bank prioritization (e.g. SICK before VAC before AL)
- [ ] Any CT EARN / CT PAY rules that interact with OT/leave

---

## Next steps

1. **Confirm:** Employee ID ↔ name mapping (where does it live?).
2. **Confirm:** AccrualBalanceReport columns/format (we inferred from shared strings).
3. **Prioritize:** Which rule to implement first (leave check, sick→OT 1.0, or LWOP)?
4. **Scope:** Start with Python script vs. build UI first.

---

## Appendix: Rules reference (from LEAVE_CODE_MAPPING_TCP.txt)

- **Leave mapping:** Use Accrual sheet to map hours to correct banks (SICK, VAC, AL).
- **Insufficient leave:** Flag and suggest alternative banks or LWOP.
- **Sick used:** Flag for OT 1.5 → OT 1.0 conversion (match sick hours).
- **LWOP used:** Convert Guarantee → LWOP, OT → REG, add LWOP to reach 40. No OT when LWOP.
- **Holiday:** Banked, payout, makeup rules; special case for worked holiday + payout.
