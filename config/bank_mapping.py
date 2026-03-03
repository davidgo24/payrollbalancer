"""
Bank mapping: TCP code descriptions → leave bank.
Used to sum leave used per bank and compare to AccrualBalanceReport.
"""

# Codes that draw from SICK bank (FMLA SICK, SICK PAY, AL SICK PAY, etc.)
SICK_CODES = {
    "AL SICK PAY",
    "FMLA SICK",
    "SICK PAY",
    "HEALTHY SICK PAY",
    "HEALTHY SICK PT",
    "HEALTHY LMTD PT",
}

# Codes that draw from VAC bank
VAC_CODES = {"FMLA VAC", "VAC PAY"}

# Codes that draw from AL (Annual Leave) - EXCLUDE ADMIN LEAVE
AL_CODES = {
    "AL PAY",
    "AL PT PAY",
    "FMLA AL",
    "AL SAL PAY",
    "ADMIN SAL PAY",
    "ADMIN DIS",
    "BEREAVEMENT",
}

# Codes that draw from COMP bank (CT Pay, etc.)
COMP_CODES = {
    "CT PAY 1.0",
    "CT PAY 1J",  # if used
    "FMLA CT PAY",
    "CT SAL PAY",
    "CT SAL PAY 1.0",
}

# Skip these employees entirely - finance handles
SKIP_CODES = {"ADMIN LEAVE PAY"}

# LWOP - used when converting from leave when no balance
LWOP_CODE = "LWOP"

# REG for 40-hr rule conversions
REG_CODE = "REG FT"  # primary regular code

# OT conversions
OT_15_CODE = "OT 1.5"
OT_10_CODE = "OT 1.0"
GUARANTEE_CODE = "GUARANTEE"

# Fallback order when a bank is exhausted (try these before LWOP)
BANK_FALLBACK = {
    "SICK": ["VAC", "COMP", "AL"],   # Sick exhausted → try VAC, then COMP, then AL
    "VAC": ["SICK", "COMP", "AL"],   # VAC exhausted → try SICK, then COMP, then AL
    "AL": ["SICK", "VAC", "COMP"],   # AL exhausted → try SICK, then VAC, then COMP
    "COMP": ["SICK", "VAC", "AL"],   # COMP exhausted → try SICK, then VAC, then AL
}

# Bank → primary New World code (for reallocation)
BANK_TO_CODE = {
    "SICK": "SICK PAY",
    "VAC": "VAC PAY",
    "AL": "AL PAY",
    "COMP": "CT PAY 1.0",
}

# New World totals: REG-type (Regular Hours) vs OT-type (Premium/OT Hours)
# Per screenshot: OT + CTE go to Premium; REG + paid leave go to Regular
REG_TYPE_CODES = {
    "REG FT", "REG PT", "REG SAL", "REG PT LMTD", "REG PT OTHER",
    "GUARANTEE", "NON PROD LUNCH", "RECOVERY 1.5", "HOL PAY", "HOL UTU", "HOL UTU SAL",
    "SICK PAY", "FMLA SICK", "AL SICK PAY", "HEALTHY SICK PAY", "HEALTHY SICK PT", "HEALTHY LMTD PT",
    "VAC PAY", "FMLA VAC", "AL PAY", "FMLA AL", "BEREAVEMENT",
    "CT PAY 1.0", "FMLA CT PAY", "CT SAL PAY", "CT SAL PAY 1.0",  # CT Pay counts as paid = REG
}
OT_TYPE_CODES = {
    "OT 1.5", "OT 1.0", "OT 1.5 PT BUS", "OT PT", "OT PT-LMTD",
    "CT EARN 1.5", "CT EARN 1.0",  # CT Earn = premium
    "HOL 1.5", "HOL 1.0", "HOL 1.0 CTE", "HOL PAYOUT",
}


def get_bank_for_code(description: str) -> str | None:
    """Return bank (SICK, VAC, AL, COMP) or None if not a leave code."""
    d = description.strip().upper()
    if d in SICK_CODES:
        return "SICK"
    if d in VAC_CODES:
        return "VAC"
    if d in AL_CODES:
        return "AL"
    if d in COMP_CODES:
        return "COMP"
    return None


def is_skip_employee(codes_used: set[str]) -> bool:
    """True if employee should be skipped (admin leave - finance handles)."""
    return bool(SKIP_CODES & {c.strip().upper() for c in codes_used})


def get_code_type_for_new_world(description: str) -> str | None:
    """Return 'REG' or 'OT' for New World Regular vs Premium totals. None if OTHER (e.g. LWOP)."""
    d = description.strip().upper()
    if d in REG_TYPE_CODES:
        return "REG"
    if d in OT_TYPE_CODES:
        return "OT"
    return None
