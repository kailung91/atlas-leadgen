"""
ПРОФЕСІЙНИЙ СКРАПЕР ЗБАГАЧЕННЯ ВІДСУТНІХ КОНТАКТІВ ПЕРЕМОЖЦІВ — v8.1
Суворе правило: ІСНУЮЧІ КОНТАКТИ НЕ ЧІПАТИ. Доповнювати ТІЛЬКИ відсутні (NaN/порожні).
"""
import sys
import re
import socket
import requests
import pandas as pd
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from loguru import logger
import dns.resolver

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "output"

SUPPLIERS_FILE = OUTPUT_DIR / "PROZORRO_WINNING_SUPPLIERS_FULL_CONTACTS.xlsx"
MASTER_FILE = OUTPUT_DIR / "MASTER_EMAIL_OUTREACH_CAMPAIGN_FINAL.xlsx"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
    "Accept-Language": "uk-UA,uk;q=0.9,en-US;q=0.8,en;q=0.7",
}

RE_EMAIL = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
IGNORE_DOMAINS = {"ua-region", "youcontrol", "opendatabot", "clarity", "w3.org", "schema", "example", "domain"}


def lookup_uaregion(row: dict) -> dict:
    updated = dict(row)
    
    current_email = str(row.get("✉️ Email Переможця", "")).strip()
    current_phone = str(row.get("📞 Телефон Переможця", "")).strip()

    # СУВОРЕ ПРАВИЛО: Якщо і email і телефон вже є — пропускаємо!
    has_email = current_email and current_email != "nan" and "@" in current_email
    has_phone = current_phone and current_phone != "nan" and len(current_phone) > 5

    if has_email and has_phone:
        return updated

    edrpou = str(row.get("🆔 ЄДРПОУ / ІПН", "")).strip()
    name = str(row.get("🏆 Переможець (Назва)", "")).strip()

    query = edrpou if edrpou and edrpou != "nan" and len(edrpou) >= 8 else name
    if not query or query == "nan":
        return updated

    try:
        url = f"https://www.ua-region.com.ua/search?q={requests.utils.quote(query)}"
        r = requests.get(url, headers=HEADERS, timeout=4)
        if r.status_code == 200:
            if not has_email:
                emails = [e.lower() for e in RE_EMAIL.findall(r.text) if not any(x in e.lower() for x in IGNORE_DOMAINS)]
                if emails:
                    updated["✉️ Email Переможця"] = emails[0]
                    updated["Джерело Емаіл"] = "UA-Region"

            if not has_phone:
                phones = re.findall(r"\+?380\d{9}|\b0\d{9}\b", r.text)
                if phones:
                    updated["📞 Телефон Переможця"] = ", ".join(list(set(phones))[:2])
    except Exception:
        pass

    return updated


def main():
    logger.info("🚀 Збагачення відсутніх контактів Переможців (Суворе збереження існуючих)...")

    if not SUPPLIERS_FILE.exists():
        logger.error("Файл {} не знайдено!", SUPPLIERS_FILE)
        return

    df_sup = pd.read_excel(SUPPLIERS_FILE)
    rows = df_sup.to_dict("records")
    logger.info("Всього записів у базі: {} | Обробка відсутніх пошт/телефонів...", len(rows))

    with ThreadPoolExecutor(max_workers=20) as executor:
        enriched_rows = list(executor.map(lookup_uaregion, rows))

    df_enriched = pd.DataFrame(enriched_rows)

    emails_count = (df_enriched["✉️ Email Переможця"].astype(str).str.contains("@")).sum()
    phones_count = (df_enriched["📞 Телефон Переможця"].astype(str).str.len() > 5).sum()

    logger.info("Підсумок збагачення: Переможців з Email = {}, з телефоном = {}", emails_count, phones_count)

    df_enriched.to_excel(SUPPLIERS_FILE, index=False)
    df_enriched.to_csv(OUTPUT_DIR / "PROZORRO_WINNING_SUPPLIERS_FULL_CONTACTS.csv", index=False, encoding="utf-8-sig")

    df_master = pd.read_excel(MASTER_FILE, sheet_name="1. Замовники (Master Email)")
    df_pz = pd.read_excel(MASTER_FILE, sheet_name="2. Prozorro Замовники")
    df_p1 = pd.read_excel(MASTER_FILE, sheet_name="4. Школи P1 Top")

    with pd.ExcelWriter(MASTER_FILE, engine="openpyxl") as writer:
        df_master.to_excel(writer, index=False, sheet_name="1. Замовники (Master Email)")
        df_pz.to_excel(writer, index=False, sheet_name="2. Prozorro Замовники")
        df_enriched.to_excel(writer, index=False, sheet_name="3. Переможці (Контакти Enriched)")
        df_p1.to_excel(writer, index=False, sheet_name="4. Школи P1 Top")

    logger.info("✅ УСПІШНО ЗБЕРЕЖЕНО ОНОВЛЕНІ БАЗИ!")


if __name__ == "__main__":
    main()
