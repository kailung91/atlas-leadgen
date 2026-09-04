"""
Senior-Level Email Finder, Enrichment & DNS MX Verification Pipeline for 1C Databases.

Enriches 1C UTP (IPT) and 1C Magazin counterparties with valid, deliverable emails:
  1. Cross-matching with Schools (31,688), HEIs (1,479), Prozorro Entities (828), and Ukrmaps (487).
  2. DNS MX deliverability verification.
  3. Hostile domain filtering (.ru, .su, .by, mail.ru, yandex).
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import socket
import dns.resolver
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


def build_reference_email_maps():
    logger.info("Building reference email lookup maps across all master datasets...")

    edrpou_map: dict[str, str] = {}
    phone_map: dict[str, str] = {}

    # 1. School Master Dataset
    school_csv = OUTPUT_DIR / "school_leads_filtered.csv"
    if school_csv.exists():
        df_sch = pd.read_csv(school_csv)
        for _, r in df_sch.iterrows():
            email = str(r.get("Email", "")).strip()
            edrpou = str(r.get("ЄДРПОУ", "")).strip().lstrip("0")
            phone = str(r.get("Телефон", "")).strip()
            if is_valid_email_format(email):
                if edrpou and edrpou != "nan":
                    edrpou_map[edrpou] = email
                if phone and phone != "nan":
                    clean_p = re.sub(r"\D", "", phone)
                    if len(clean_p) >= 9:
                        phone_map[clean_p[-9:]] = email

    # 2. HEI Master Dataset
    hei_csv = OUTPUT_DIR / "hei_leads_filtered.csv"
    if hei_csv.exists():
        df_hei = pd.read_csv(hei_csv)
        for _, r in df_hei.iterrows():
            email = str(r.get("Email", "")).strip()
            edrpou = str(r.get("ЄДРПОУ", "")).strip().lstrip("0")
            phone = str(r.get("Телефон", "")).strip()
            if is_valid_email_format(email):
                if edrpou and edrpou != "nan":
                    edrpou_map[edrpou] = email
                if phone and phone != "nan":
                    clean_p = re.sub(r"\D", "", phone)
                    if len(clean_p) >= 9:
                        phone_map[clean_p[-9:]] = email

    # 3. Prozorro Entities
    for fname in ["prozorro_school_buyers.csv", "prozorro_school_winners.csv", "prozorro_school_bidders.csv"]:
        pz_csv = OUTPUT_DIR / fname
        if pz_csv.exists():
            df_pz = pd.read_csv(pz_csv)
            for _, r in df_pz.iterrows():
                email = str(r.get("Email", "")).strip()
                edrpou = str(r.get("ЄДРПОУ", "")).strip().lstrip("0")
                phone = str(r.get("Телефон", "")).strip()
                if is_valid_email_format(email):
                    if edrpou and edrpou != "nan":
                        edrpou_map[edrpou] = email
                    if phone and phone != "nan":
                        clean_p = re.sub(r"\D", "", phone)
                        if len(clean_p) >= 9:
                            phone_map[clean_p[-9:]] = email

    # 4. Ukrmaps Customers
    ukr_csv = OUTPUT_DIR / "ukrmaps_ecommerce_customers.csv"
    if ukr_csv.exists():
        df_ukr = pd.read_csv(ukr_csv)
        for _, r in df_ukr.iterrows():
            email = str(r.get("Email", "")).strip()
            phone = str(r.get("Телефон", "")).strip()
            if is_valid_email_format(email) and phone and phone != "nan":
                clean_p = re.sub(r"\D", "", phone)
                if len(clean_p) >= 9:
                    phone_map[clean_p[-9:]] = email

    logger.info("Reference Email Lookup Maps ready: {} EDRPOU keys, {} Phone keys!", len(edrpou_map), len(phone_map))
    return edrpou_map, phone_map


def enrich_1c_dataset(input_file: Path, output_file: Path, edrpou_map: dict, phone_map: dict, base_name: str, header_color: str):
    if not input_file.exists():
        logger.warning("Input file does not exist: {}", input_file)
        return

    df = pd.read_excel(input_file)
    logger.info("Enriching 1C [{}] contacts: {} rows...", base_name, len(df))

    found_emails = []
    email_sources = []

    for _, r in df.iterrows():
        existing_email = str(r.get("Email", "")).strip()
        edrpou = str(r.get("ЄДРПОУ", "")).strip().lstrip("0")
        phone = str(r.get("Телефони", "")).strip()

        # Check existing
        if is_valid_email_format(existing_email):
            found_emails.append(existing_email)
            email_sources.append("1С Запис")
            continue

        # Match by EDRPOU
        if edrpou and edrpou != "nan" and edrpou in edrpou_map:
            found_emails.append(edrpou_map[edrpou])
            email_sources.append("Збагачено через ЄДРПОУ")
            continue

        # Match by Phone
        matched_phone_email = ""
        if phone and phone != "nan":
            for p_chunk in re.split(r"[;,/]", phone):
                clean_p = re.sub(r"\D", "", p_chunk)
                if len(clean_p) >= 9 and clean_p[-9:] in phone_map:
                    matched_phone_email = phone_map[clean_p[-9:]]
                    break

        if matched_phone_email:
            found_emails.append(matched_phone_email)
            email_sources.append("Збагачено через Телефон")
        else:
            found_emails.append("")
            email_sources.append("")

    df["Збагачений Email"] = found_emails
    df["Джерело Email"] = email_sources

    # DNS MX Verification on all found emails
    all_emails = [e for e in found_emails if e]
    mx_results = verify_email_list_mx(all_emails)

    df["DNS MX Статус"] = df["Збагачений Email"].map(lambda e: "Провалідовано (MX Active)" if mx_results.get(e, False) else ("Недійсний" if e else ""))

    # Save outputs
    out_csv = output_file.with_suffix(".csv")
    df.to_csv(out_csv, index=False, encoding="utf-8-sig")

    with pd.ExcelWriter(output_file, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=f"Контакти {base_name}")
        format_excel_sheet(writer.sheets[f"Контакти {base_name}"], df, header_color=header_color)

    verified_count = df["DNS MX Статус"].eq("Провалідовано (MX Active)").sum()
    logger.info("Successfully Enriched 1C [{}]: {} total emails found, {} DNS MX verified -> {}", base_name, len(all_emails), verified_count, output_file)


def main():
    edrpou_map, phone_map = build_reference_email_maps()

    utp_file = OUTPUT_DIR / "1c_utp_full_contacts.xlsx"
    utp_out = OUTPUT_DIR / "1c_utp_full_contacts_with_verified_emails.xlsx"
    enrich_1c_dataset(utp_file, utp_out, edrpou_map, phone_map, "1С UTP", "1F4E78")

    mag_file = OUTPUT_DIR / "1c_magazin_full_contacts.xlsx"
    mag_out = OUTPUT_DIR / "1c_magazin_full_contacts_with_verified_emails.xlsx"
    enrich_1c_dataset(mag_file, mag_out, edrpou_map, phone_map, "1С Магазин", "2E75B6")


if __name__ == "__main__":
    main()
