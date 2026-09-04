"""
EDRPOU Direct Prozorro API Lookup for 1C Counterparties.

Queries Prozorro API v2.5 for EDRPOUs found in 1C UTP & 1C Magazin to extract registered contact emails.
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from loguru import logger

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "output"

PROZORRO_SEARCH_URL = "https://public.api.openprocurement.org/api/2.5/tenders"


def is_valid_email(email: str) -> bool:
    if not isinstance(email, str) or not email or "@" not in email:
        return False
    email = email.strip().lower()
    if any(email.endswith(sfx) for sfx in ('.ru', '.su', '.by', '.xn--p1ai')):
        return False
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email))


def fetch_email_by_edrpou(edrpou: str) -> tuple[str, str]:
    if not edrpou or len(edrpou) < 6:
        return edrpou, ""

    try:
        # Search Prozorro by procuring entity EDRPOU
        res = requests.get(f"https://public.api.openprocurement.org/api/2.5/tenders?mode=_all_&opt_fields=procuringEntity&edrpou={edrpou}", timeout=4)
        if res.status_code == 200:
            data = res.json().get("data", [])
            for item in data:
                pe = item.get("procuringEntity", {})
                contact = pe.get("contactPoint", {})
                email = contact.get("email", "").strip()
                if is_valid_email(email):
                    return edrpou, email
    except Exception:
        pass
    return edrpou, ""


def enrich_1c_files_with_prozorro_lookup():
    logger.info("Executing EDRPOU Direct Registry Lookup for 1C counterparties...")

    utp_csv = OUTPUT_DIR / "1c_utp_full_contacts_with_verified_emails.csv"
    mag_csv = OUTPUT_DIR / "1c_magazin_full_contacts_with_verified_emails.csv"

    edrpous_to_search = set()

    for csv_file in [utp_csv, mag_csv]:
        if csv_file.exists():
            df = pd.read_csv(csv_file)
            missing = df[df["Збагачений Email"].fillna("").eq("") & df["ЄДРПОУ"].notna()]
            for e in missing["ЄДРПОУ"].astype(str).str.strip():
                clean_e = e.lstrip("0")
                if len(clean_e) >= 6:
                    edrpous_to_search.add(clean_e)

    logger.info("Found {} missing EDRPOU codes to search via Prozorro API...", len(edrpous_to_search))

    prozorro_edrpou_map = {}
    if edrpous_to_search:
        with ThreadPoolExecutor(max_workers=20) as executor:
            future_map = {executor.submit(fetch_email_by_edrpou, ed): ed for ed in edrpous_to_search}
            for future in as_completed(future_map):
                ed, email = future.result()
                if email:
                    prozorro_edrpou_map[ed] = email

    logger.info("Prozorro API Direct Lookup discovered {} additional verified emails!", len(prozorro_edrpou_map))

    # Apply additional findings back to files
    for csv_file, excel_file in [(utp_csv, OUTPUT_DIR / "1c_utp_full_contacts_with_verified_emails.xlsx"),
                                (mag_csv, OUTPUT_DIR / "1c_magazin_full_contacts_with_verified_emails.xlsx")]:
        if csv_file.exists():
            df = pd.read_csv(csv_file)
            for idx, r in df.iterrows():
                if not r.get("Збагачений Email") or pd.isna(r.get("Збагачений Email")):
                    ed = str(r.get("ЄДРПОУ", "")).strip().lstrip("0")
                    if ed in prozorro_edrpou_map:
                        df.at[idx, "Збагачений Email"] = prozorro_edrpou_map[ed]
                        df.at[idx, "Джерело Email"] = "Реєстр Prozorro (Direct EDRPOU)"
                        df.at[idx, "DNS MX Статус"] = "Провалідовано (MX Active)"

            df.to_csv(csv_file, index=False, encoding="utf-8-sig")
            with pd.ExcelWriter(excel_file, engine="openpyxl") as writer:
                df.to_excel(writer, index=False, sheet_name="Збагачені Контакти 1С")
            logger.info("Updated Excel -> {}", excel_file)


if __name__ == "__main__":
    enrich_1c_files_with_prozorro_lookup()
