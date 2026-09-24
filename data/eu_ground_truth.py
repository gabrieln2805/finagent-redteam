"""
Loader for the real EU ground-truth cache (built by
scripts/build_eu_ground_truth.py from real data fetched by
scripts/fetch_eu_data.sh -- see data/raw/eu/ and the source cited in the
cache file itself).

This replaces the earlier synthetic SF-based hallucination ground truth
with data from two real EU sources:
  1. Romania's ERDF/ESF beneficiary registry, 2007-2013 programme period
     (region totals + individual project records, in RON).
  2. The European Commission's Financial Transparency System, 2015
     (country totals + individual beneficiary records, in EUR).
"""
import json
import os

_CACHE_PATH = os.path.join(os.path.dirname(__file__), "eu_ground_truth_cache.json")

with open(_CACHE_PATH, encoding="utf-8") as _f:
    _CACHE = json.load(_f)


def lookup_ro_region_total(region: str):
    """Real total ERDF/ESF funding (RON) for a Romanian NUTS2 region, 2007-2013."""
    return _CACHE["ro_erdf_esf_2007_2013_region_totals_ron"].get(region)


def lookup_ro_project_total(smis_code: str):
    """Real total amount (RON) for a specific Romanian ERDF/ESF project by its Cod SMIS."""
    row = _CACHE["ro_erdf_esf_2007_2013_projects"].get(str(smis_code))
    return row["total_amount_ron"] if row else None


def lookup_fts_country_total_2015(country: str):
    """Real total EU Financial Transparency System commitments (EUR) for a country, 2015."""
    return _CACHE["fts_2015_country_totals_eur"].get(country)


def lookup_fts_beneficiary_total(commitment_key: str):
    """Real total amount (EUR) for a specific FTS 2015 beneficiary commitment."""
    row = _CACHE["fts_2015_beneficiaries_eur"].get(commitment_key)
    return row["total_amount_eur"] if row else None
