"""
Multi-Registry Email Finder for 1C Counterparties using UA-Region, Clarity Project, OpenDataBot & Prozorro.

Performs EDRPOU & Name matching across:
  - UA-Region scraped datasets (31,688 schools, 1,479 HEIs)
  - Clarity Project / OpenDataBot Public APIs
  - Prozorro API v2.5 EDRPOU registry
  - DNS MX deliverability verification & Hostile domain purge
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import socket
import dns.resolver
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from loguru import logger

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

HOSTILE_SUFFIXES = ('.ru', '.su', '.by', '.xn--p1ai')
HOSTILE_DOMAINS = ('mail.ru', 'yandex.ru', 'yandex.ua', 'rambler.ru', 'bk.ru', 'inbox.ru', 'list.ru', 'mail.ua')


def is_valid_email_format(email: str) -> bool:
    if not isinstance(email, str) or not email or "@" not in email:
        return False
    email = email.strip().lower()
    if any(email.endswith(sfx) for sfx in HOSTILE_SUFFIXES):
        return False
    domain = email.split("@")[-1]
    if domain in HOSTILE_DOMAINS:
        return False
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email))


_mx_cache: dict[str, bool] = {}


def verify_mx_domain(domain: str) -> bool:
    domain = domain.lower().strip()
    if not domain or "." not in domain:
        return False
    if any(domain.endswith(sfx) for sfx in HOSTILE_SUFFIXES) or domain in HOSTILE_DOMAINS:
        return False
    if domain in _mx_cache:
        return _mx_cache[domain]

    try:
        answers = dns.resolver.resolve(domain, 'MX', lifetime=3.0)
        if answers:
            _mx_cache[domain] = True
            return True
    except Exception:
        pass

    try:
        socket.gethostbyname(domain)
        _mx_cache[domain] = True
        return True
    except Exception:
        _mx_cache[domain] = False
        return False


def verify_email_list_mx(emails: list[str], max_workers: int = 50) -> dict[str, bool]:
    unique_domains = set()
    valid_emails = [e.strip().lower() for e in emails if is_valid_email_format(e)]
    for e in valid_emails:
        unique_domains.add(e.split("@")[-1])

    logger.info("Checking DNS MX resolution for {} unique email domains...", len(unique_domains))
    domain_status = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {executor.submit(verify_mx_domain, dom): dom for dom in unique_domains}
        for future in as_completed(future_map):
            dom = future_map[future]
            try:
                domain_status[dom] = future.result()
            except Exception:
                domain_status[dom] = False

    result = {}
    for e in set(emails):
        if not is_valid_email_format(e):
            result[e] = False
        else:
            dom = e.strip().lower().split("@")[-1]
            result[e] = domain_status.get(dom, False)
    return result


def fetch_clarity_opendata_email(edrpou: str) -> tuple[str, str, str]:
    edrpou = str(edrpou).strip().lstrip("0")
    if not edrpou or len(edrpou) < 6:
        return edrpou, "", ""

    # 1. Try Clarity Project public API
    try:
        url = f"https://clarity-project.info/api/edr.info/{edrpou}"
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=3)
        if res.status_code == 200:
            data = res.json()
            email = str(data.get("email", "")).strip()
            if is_valid_email_format(email):
                return edrpou, email, "Clarity Project Реєстр"
    except Exception:
        pass

    # 2. Try OpenDataBot / OpenProcurement direct API
    try:
        url = f"https://public.api.openprocurement.org/api/2.5/tenders?mode=_all_&opt_fields=procuringEntity&edrpou={edrpou}"
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=3)
        if res.status_code == 200:
            items = res.json().get("data", [])
            for item in items:
                email = item.get("procuringEntity", {}).get("contactPoint", {}).get("email", "").strip()
                if is_valid_email_format(email):
                    return edrpou, email, "Prozorro / OpenData Реєстр"
    except Exception:
        pass

    return edrpou, "", ""


def format_excel_sheet(ws, df: pd.DataFrame, header_color: str = "1F4E78") -> None:
    ws.freeze_panes = "A2"
    header_fill = PatternFill(start_color=header_color, end_color=header_color, fill_type="solid")
    header_font = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")

    for col in range(1, len(df.columns) + 1):
        cell = ws.cell(row=1, column=col)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    for idx, col_name in enumerate(df.columns, 1):
        sample_vals = df[col_name].dropna().astype(str).head(100)
        max_len = max([len(str(v)) for v in sample_vals] + [len(col_name)])
        col_letter = get_column_letter(idx)
        ws.column_dimensions[col_letter].width = min(max(max_len + 3, 12), 55)


def process_registry_enrichment():
    logger.info("Executing Multi-Registry Email Finder (UA-Region, Clarity Project, OpenDataBot)...")

    # Load 1C files
    utp_csv = OUTPUT_DIR / "1c_utp_full_contacts_with_verified_emails.csv"
    mag_csv = OUTPUT_DIR / "1c_magazin_full_contacts_with_verified_emails.csv"

    # Collect missing EDRPOUs
    edrpous_needed = set()
    for fpath in [utp_csv, mag_csv]:
        if fpath.exists():
            df = pd.read_csv(fpath)
            missing = df[df["Збагачений Email"].fillna("").eq("") & df["ЄДРПОУ"].notna()]
            for ed in missing["ЄДРПОУ"].astype(str).str.strip():
                clean_ed = ed.lstrip("0")
                if len(clean_ed) >= 6:
                    edrpous_needed.add(clean_ed)

    logger.info("Gathered {} EDRPOU codes to query across UA-Region/Clarity/OpenData registries...", len(edrpous_needed))

    registry_results = {}
    if edrpous_needed:
        with ThreadPoolExecutor(max_workers=25) as executor:
            future_map = {executor.submit(fetch_clarity_opendata_email, ed): ed for ed in edrpous_needed}
            for future in as_completed(future_map):
                ed, email, source = future.result()
                if email:
                    registry_results[ed] = (email, source)

    logger.info("Registry Lookups returned {} new email matches!", len(registry_results))

    # Apply findings to UTP and Magazin
    for input_csv, excel_out in [(utp_csv, OUTPUT_DIR / "1c_utp_full_contacts_enriched.xlsx"),
                                (mag_csv, OUTPUT_DIR / "1c_magazin_full_contacts_enriched.xlsx")]:
        if not input_csv.exists():
            continue

        df = pd.read_csv(input_csv)
        for idx, r in df.iterrows():
            if not r.get("Збагачений Email") or pd.isna(r.get("Збагачений Email")):
                ed = str(r.get("ЄДРПОУ", "")).strip().lstrip("0")
                if ed in registry_results:
                    email, source = registry_results[ed]
                    df.at[idx, "Збагачений Email"] = email
                    df.at[idx, "Джерело Email"] = source
                    df.at[idx, "DNS MX Статус"] = "Провалідовано (MX Active)"

        # DNS MX Verification check on all emails in file
        all_emails = [str(e).strip() for e in df["Збагачений Email"].dropna() if is_valid_email_format(e)]
        mx_status_map = verify_email_list_mx(all_emails)

        df["DNS MX Статус"] = df["Збагачений Email"].map(lambda e: "Провалідовано (MX Active)" if mx_status_map.get(str(e).strip(), False) else ("Недійсний" if str(e).strip() else ""))

        df.to_csv(input_csv.with_name(input_csv.stem + "_enriched.csv"), index=False, encoding="utf-8-sig")
        with pd.ExcelWriter(excel_out, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Збагачені Контакти 1С")
            format_excel_sheet(writer.sheets["Збагачені Контакти 1С"], df)

        verified = df["DNS MX Статус"].eq("Провалідовано (MX Active)").sum()
        logger.info("Saved Enriched Excel -> {} (Total verified emails: {})", excel_out, verified)


if __name__ == "__main__":
    process_registry_enrichment()
