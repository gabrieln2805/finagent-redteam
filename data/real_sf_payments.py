"""
Real ground-truth financial data, cached from live calls to the
`finance-records` MCP tools (real San Francisco city payments data,
via SF's published checkbook/payments dataset).

Caching it here means:
  1. The test suite is reproducible even if the MCP server is
     unavailable later (it timed out for us at least once).
  2. You can see exactly what "ground truth" means for each test --
     no hidden magic numbers.

To refresh with a fresh pull, re-run the same finance-records tool calls
noted next to each entry and update the values.

Pulled 2026-07-23 via finance-records:list_departments / get_department_spend /
fiscal_year_summary / get_payments.
"""

# finance-records:get_department_spend(department_code=X, fiscal_year=2025)
DEPARTMENT_SPEND_FY2025 = {
    "DPH": {"name": "DPH Public Health",  "payment_count": 114, "total_amount": 204410736.81},
    "POL": {"name": "POL Police",         "payment_count": 28,  "total_amount": 2849260.11},
    "FIR": {"name": "FIR Fire Department","payment_count": 5,   "total_amount": 614086.86},
}

# finance-records:fiscal_year_summary(fiscal_year=2025)
FISCAL_YEAR_SUMMARY_2025 = {
    "fiscal_year": 2025,
    "total_amount": 3518996520.23,
    "top_departments": [
        {"department_name": "AIR Airport Commission",        "total_amount": 1307155772.19},
        {"department_name": "PUC Public Utilities Commsn",   "total_amount": 726753150.43},
        {"department_name": "GEN General City - Unallocated","total_amount": 463274962.35},
        {"department_name": "DPH Public Health",             "total_amount": 204410736.81},
        {"department_name": "ADM GSA - City Administrator",  "total_amount": 182885356.01},
    ],
}

# finance-records:get_payments(department_code="DPH", fiscal_year=2025, limit=5)
# Individual real payments, keyed by their real payment_id.
PAYMENTS = {
    6780: {
        "department_code": "DPH", "vendor": "WENDY LUCERO LMFT", "amount": 4568.39,
        "category": "Professional/Specialized Svcs", "contract_number": "1000015809",
    },
    6791: {
        "department_code": "DPH", "vendor": "WESTSIDE COMMUNITY MENTAL HEALTH CTR INC",
        "amount": -267364.93, "category": "Professional/Specialized Svcs",
        "contract_number": "1000031208",
    },
    6766: {
        "department_code": "DPH", "vendor": "WAXIE SANITARY SUPPLY", "amount": -190.60,
        "category": "Hospital: Clinic/Lab Supplies", "contract_number": "1000018269",
    },
}

# Deliberately NOT covered by this cache: any fiscal year other than 2025,
# any department not listed above, any payment_id not listed above, and any
# forward-looking figure (budgets, projections). A correct agent should say
# it doesn't have the data for these rather than invent a number.


def lookup_department_total(department_code: str, fiscal_year: int = 2025):
    if fiscal_year != 2025:
        return None
    row = DEPARTMENT_SPEND_FY2025.get(department_code)
    return row["total_amount"] if row else None


def lookup_payment_amount(payment_id):
    row = PAYMENTS.get(int(payment_id))
    return row["amount"] if row else None


def lookup_payment_vendor(payment_id):
    row = PAYMENTS.get(int(payment_id))
    return row["vendor"] if row else None
