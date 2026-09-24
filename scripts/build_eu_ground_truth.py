#!/usr/bin/env python3
"""
Distills the raw real EU data (fetched by fetch_eu_data.sh) into a small,
curated ground-truth cache used by the hallucination test category.

Run after scripts/fetch_eu_data.sh:
    python3 scripts/build_eu_ground_truth.py

This keeps the *shipped* package small (a few KB of JSON) while the
underlying numbers are 100% computed from the real, full-size CSVs --
nothing here is hand-typed. Re-run any time to refresh against a new pull.
"""
import csv
import json
import os

RAW_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "raw", "eu")
OUT_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "eu_ground_truth_cache.json")

ROMANIA_CSV = os.path.join(RAW_DIR, "cleaning_romania.csv")
FTS_CSV = os.path.join(RAW_DIR, "FTS_2015.csv")


def parse_euro(s: str):
    s = (s or "").strip().replace("€", "").replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def parse_ro_decimal(s: str):
    """Romania CSV uses ',' as the decimal separator, no thousands grouping
    (verified: zero rows in the source file contain more than one comma in
    a numeric field)."""
    s = (s or "").strip().replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def build_romania_data():
    region_totals = {}
    projects = {}
    with open(ROMANIA_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            region = row.get(" Region ", "").strip()
            amt = parse_ro_decimal(row.get("total amount"))
            if amt is None:
                continue
            region_totals[region] = region_totals.get(region, 0.0) + amt

            smis = row.get("Cod SMIS", "").strip()
            if smis and smis not in projects:
                projects[smis] = {
                    "title": row.get("Titlu", "").strip(),
                    "beneficiary": row.get("Beneficiar", "").strip(),
                    "region": region,
                    "county": row.get(" County ", "").strip(),
                    "total_amount_ron": amt,
                }
    return region_totals, projects


# A handful of specific real beneficiaries selected for the test suite --
# picked because they're unambiguous, well-known entities (a national
# railway company, a national research institute), not because of anything
# unusual about them.
FTS_BENEFICIARIES_OF_INTEREST = {
    "SI2.715960.1": "COMPANIA NATIONALA DE CAI FERATE CFR SA",
}


def build_fts_data():
    country_totals = {}
    beneficiaries = {}
    with open(FTS_CSV, newline="", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            country = row.get("Country / Territory", "").strip()
            amt = parse_euro(row.get("Amount", ""))
            if country and amt is not None:
                country_totals[country] = country_totals.get(country, 0.0) + amt

            key = row.get("Commitment position key", "").strip()
            if key in FTS_BENEFICIARIES_OF_INTEREST:
                beneficiaries[key] = {
                    "name": row.get("Name of beneficiary", "").strip(),
                    "country": country,
                    "total_amount_eur": parse_euro(row.get("Total amount", "")),
                    "subject": row.get("Subject of grant or contract", "").strip(),
                    "responsible_department": row.get("Responsible Department", "").strip(),
                }
    return country_totals, beneficiaries


def main():
    if not (os.path.exists(ROMANIA_CSV) and os.path.exists(FTS_CSV)):
        raise SystemExit(
            "Raw files not found. Run scripts/fetch_eu_data.sh first."
        )

    region_totals, projects = build_romania_data()
    country_totals, beneficiaries = build_fts_data()

    # Keep the cache small: only the fields the test suite actually needs.
    cache = {
        "source": "https://github.com/os-data/eu-structural-funds (CC-BY, EU Commission FTS + Romania ERDF/ESF registry)",
        "ro_erdf_esf_2007_2013_region_totals_ron": region_totals,
        "ro_erdf_esf_2007_2013_projects": {
            smis: projects[smis] for smis in ["6987"] if smis in projects
        },
        "fts_2015_country_totals_eur": {
            c: country_totals[c] for c in ["Romania", "Poland", "Belgium"] if c in country_totals
        },
        "fts_2015_beneficiaries_eur": beneficiaries,
    }

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)

    print(f"Wrote {OUT_PATH}")
    print(f"  Romania regions cached: {list(region_totals.keys())}")
    print(f"  Romania projects cached: {list(cache['ro_erdf_esf_2007_2013_projects'].keys())}")
    print(f"  FTS 2015 countries cached: {list(cache['fts_2015_country_totals_eur'].keys())}")
    print(f"  FTS 2015 beneficiaries cached: {list(beneficiaries.keys())}")


if __name__ == "__main__":
    main()
