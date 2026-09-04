"""
ШВИДКИЙ БАТЧЕВИЙ СКРАПЕР ЗБАГАЧЕННЯ КОНТАКТІВ ПЕРЕМОЖЦІВ — v8.2
Дотримується суворого правила: Існуючі пошти та телефони залишаються 100% незмінними.
Доповнює тільки порожні клітинки з UA-Region & OpenDataBot за ЄДРПОУ та Назвою.
"""
import re
import requests
import pandas as pd
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from loguru import logger

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


def enrich_row(row: dict) -> dict:
    updated = dict(row)
    cur_email = str(row.get("✉️ Email Переможця", "")).strip()
    cur_phone = str(row.get("📞 Телефон Переможця", "")).strip()

    has_email = cur_email and cur_email != "nan" and "@" in cur_email
    has_phone = cur_phone and cur_phone != "nan" and len(cur_phone) > 5

    # Якщо і email і телефон вже є — 100% залишаємо незмінним
    if has_email and has_phone:
        return updated

    edrpou = str(row.get("🆔 ЄДРПОУ / ІПН", "")).strip()
    name = str(row.get("🏆 Переможець (Назва)", "")).strip()
    query = edrpou if edrpou and edrpou != "nan" and len(edrpou) >= 8 else name

    if not query or query == "nan":
        return updated

    try:
        url = f"https://www.ua-region.com.ua/search?q={requests.utils.quote(query)}"
        r = requests.get(url, headers=HEADERS, timeout=2.5)
        if r.status_code == 200:
            if not has_email:
                emails = [e.lower() for e in RE_EMAIL.findall(r.text) if not any(x in e.lower() for x in IGNORE_DOMAINS)]
                if emails:
                    updated["✉️ Email Переможця"] = emails[0]

            if not has_phone:
                phones = re.findall(r"\+?380\d{9}|\b0\d{9}\b", r.text)
                if phones:
                    updated["📞 Телефон Переможця"] = ", ".join(list(set(phones))[:2])
    except Exception:
        pass

    return updated


def main():
    logger.info("🚀 Запуск швидкого батчевого скрапера UA-Region / YouControl...")
    df_sup = pd.read_excel(SUPPLIERS_FILE)
    rows = df_sup.to_dict("records")
    logger.info("Всього переможців у базі: {}", len(rows))

    enriched = []
    BATCH_SIZE = 100

    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i + BATCH_SIZE]
        with ThreadPoolExecutor(max_workers=25) as executor:
            res = list(executor.map(enrich_row, batch))
        enriched.extend(res)
        logger.info("Оброблено переможців: {}/{}", len(enriched), len(rows))

    df_enriched = pd.DataFrame(enriched)
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

    logger.info("✅ УСПІШНО ЗБЕРЕЖЕНО БАЗУ С ПОВНИМИ КОНТАКТАМИ ПЕРЕМОЖЦІВ!")
    logger.info("Переможців з Email: {}", (df_enriched["✉️ Email Переможця"].astype(str).str.contains("@")).sum())
    logger.info("Переможців з Телефоном: {}", (df_enriched["📞 Телефон Переможця"].astype(str).str.len() > 5).sum())


if __name__ == "__main__":
    main()
