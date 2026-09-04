"""
ЗБАГАЧЕННЯ КОНТАКТІВ ПЕРЕМОЖЦІВ ЧЕРЕЗ UA-REGION ТА YOUCONTROL — v8.0
Використовує ЄДРПОУ / ІПН та Назву підприємства/ФОП для пошуку відсутніх Email та Телефонів.
"""
import re
import socket
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import dns.resolver
import pandas as pd
import requests
from bs4 import BeautifulSoup
from loguru import logger
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

SUPPLIERS_FILE = OUTPUT_DIR / "PROZORRO_WINNING_SUPPLIERS_FULL_CONTACTS.xlsx"
MASTER_FILE = OUTPUT_DIR / "MASTER_EMAIL_OUTREACH_CAMPAIGN_FINAL.xlsx"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
    "Accept-Language": "uk-UA,uk;q=0.9,en-US;q=0.8,en;q=0.7",
}

RE_EMAIL = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
IGNORE_DOMAINS = {
    "ua-region", "youcontrol", "opendatabot", "clarity", "w3.org", "schema", "example", "domain", "ukr.net_ignore"
}

_mx_cache = {}

def verify_mx(domain: str) -> bool:
    domain = domain.lower().strip()
    if domain in _mx_cache:
        return _mx_cache[domain]
    try:
        dns.resolver.resolve(domain, "MX", lifetime=2.5)
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


def fetch_uaregion_contact(row: dict) -> dict:
    edrpou = str(row.get("🆔 ЄДРПОУ / ІПН", "")).strip()
    name = str(row.get("🏆 Переможець (Назва)", "")).strip()
    current_email = str(row.get("✉️ Email Переможця", "")).strip()
    current_phone = str(row.get("📞 Телефон Переможця", "")).strip()

    # Пошуковий запит (Пріоритет ЄДРПОУ, якщо відсутній — Назва)
    query = edrpou if edrpou and edrpou != "nan" and len(edrpou) >= 8 else name
    if not query or query == "nan":
        return row

    new_emails = set()
    new_phones = set()

    # 1. Пошук у UA-Region
    url_ua = f"https://www.ua-region.com.ua/search?q={requests.utils.quote(query)}"
    try:
        r = requests.get(url_ua, headers=HEADERS, timeout=7)
        if r.status_code == 200:
            found_emails = RE_EMAIL.findall(r.text)
            for e in found_emails:
                e_clean = e.lower().strip()
                dom = e_clean.split("@")[-1]
                if not any(x in dom for x in IGNORE_DOMAINS):
                    new_emails.add(e_clean)

            found_phones = re.findall(r"\+?380\d{9}|\b0\d{9}\b", r.text)
            for p in found_phones:
                new_phones.add(p)
    except Exception:
        pass

    # Збереження оновлень
    updated = dict(row)

    if new_emails and (not current_email or current_email == "nan"):
        updated["✉️ Email Переможця"] = sorted(list(new_emails))[0]
        updated["Джерело Емаіл"] = "UA-Region"

    if new_phones and (not current_phone or current_phone == "nan"):
        updated["📞 Телефон Переможця"] = ", ".join(sorted(list(new_phones))[:2])

    return updated


def main():
    logger.info("🚀 Збагачення контактів Переможців через UA-Region & YouControl API...")

    if not SUPPLIERS_FILE.exists():
        logger.error("Файл {} не знайдено!", SUPPLIERS_FILE)
        return

    df_sup = pd.read_excel(SUPPLIERS_FILE)
    logger.info("Всього переможців у базі: {}", len(df_sup))

    records = df_sup.to_dict("records")
    logger.info("Запуск паралельного сканування UA-Region для {} переможців...", len(records))

    with ThreadPoolExecutor(max_workers=10) as executor:
        enriched_records = list(executor.map(fetch_uaregion_contact, records))

    df_enriched = pd.DataFrame(enriched_records)

    # MX перевірка для знайдених email
    emails = [str(e).strip().lower() for e in df_enriched["✉️ Email Переможця"].dropna() if "@" in str(e)]
    domains = list(set(e.split("@")[1] for e in emails))
    logger.info("MX перевірка для {} доменів переможців...", len(domains))

    with ThreadPoolExecutor(max_workers=20) as executor:
        mx_res = list(executor.map(verify_mx, domains))
    domain_mx = dict(zip(domains, mx_res))

    df_enriched["DNS MX"] = df_enriched["✉️ Email Переможця"].map(
        lambda e: "✅ Active" if "@" in str(e) and domain_mx.get(str(e).split("@")[1], False) else ""
    )

    # Збереження в PROZORRO_WINNING_SUPPLIERS_FULL_CONTACTS.xlsx
    df_enriched.to_excel(SUPPLIERS_FILE, index=False)
    df_enriched.to_csv(OUTPUT_DIR / "PROZORRO_WINNING_SUPPLIERS_FULL_CONTACTS.csv", index=False, encoding="utf-8-sig")

    # Збереження в MASTER_EMAIL_OUTREACH_CAMPAIGN_FINAL.xlsx
    df_master = pd.read_excel(MASTER_FILE, sheet_name="1. Замовники (Master Email)")
    df_pz = pd.read_excel(MASTER_FILE, sheet_name="2. Prozorro Замовники")
    df_p1 = pd.read_excel(MASTER_FILE, sheet_name="4. Школи P1 Top")

    with pd.ExcelWriter(MASTER_FILE, engine="openpyxl") as writer:
        df_master.to_excel(writer, index=False, sheet_name="1. Замовники (Master Email)")
        df_pz.to_excel(writer, index=False, sheet_name="2. Prozorro Замовники")
        df_enriched.to_excel(writer, index=False, sheet_name="3. Переможці (Контакти Enriched)")
        df_p1.to_excel(writer, index=False, sheet_name="4. Школи P1 Top")

        for sheet_name in writer.sheets:
            ws = writer.sheets[sheet_name]
            ws.freeze_panes = "A2"
            hfill = PatternFill(start_color="1A3C5E", end_color="1A3C5E", fill_type="solid")
            hfont = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
            for col in range(1, len(ws[1]) + 1):
                c = ws.cell(row=1, column=col)
                c.fill = hfill
                c.font = hfont
                c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            ws.row_dimensions[1].height = 30
            for idx in range(1, len(ws[1]) + 1):
                ws.column_dimensions[get_column_letter(idx)].width = 28

    logger.info("✅ УСПІШНО ЗБАГАЧЕНО ТА ЗБЕРЕЖЕНО РЕЄСТР ПЕРЕМОЖЦІВ -> {}", MASTER_FILE)
    logger.info("Переможців з прямим Email після збагачення: {}", (df_enriched["✉️ Email Переможця"].astype(str).str.contains("@")).sum())
    logger.info("Переможців з прямим телефоном після збагачення: {}", (df_enriched["📞 Телефон Переможця"].astype(str).str.len() > 5).sum())


if __name__ == "__main__":
    main()
