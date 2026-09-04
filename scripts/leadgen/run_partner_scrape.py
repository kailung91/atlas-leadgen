"""
Partner lead scraper — finds bookstores, stationery shops, book wholesalers
and agents on ua-region.com.ua for atlas & outline-map distribution outreach.

Target KVEDs:
  47.61 — Роздрібна торгівля книгами
  47.62 — Роздрібна торгівля газетами та канцтоварами
  46.18 — Агенти: папір, книги, канцтовари
  46.49 — Оптова торгівля іншими товарами домашнього вжитку (книги, карти)

Output:
  data/raw/ua_region_partners/kved_*.jsonl   — raw records
  output/partner_leads.xlsx                  — ready-to-send outreach list
  output/partner_leads.csv                   — same, CSV fallback
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import atlas_bootstrap  # noqa: F401,E402  корінь repo + atlas-maps
import pandas as pd
from loguru import logger

from importers.ua_region_scraper import UARegionScraper

PARTNER_KVEDS = {
    "47.61": "Роздрібна торгівля книгами",
    "47.62": "Роздрібна торгівля газетами та канцтоварами",
    "46.18": "Агенти: папір, книги, канцтовари",
    "46.49": "Оптова торгівля іншими товарами домашнього вжитку",
    "47.91": "Інтернет-магазини (Yakaboo, BookClub тощо)",
    "58.11": "Видання книг (видавці з власними мережами)",
}

OUTPUT_DIR = root / "data" / "raw" / "ua_region_partners"
TEMP_DIR = root / "temp_data" / "ua_region_partners"
LEADS_XLSX = root / "output" / "partner_leads.xlsx"
LEADS_CSV = root / "output" / "partner_leads.csv"


def scrape() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    TEMP_DIR.mkdir(parents=True, exist_ok=True)

    scraper = UARegionScraper(
        kveds=list(PARTNER_KVEDS.keys()),
        output_dir=str(OUTPUT_DIR),
        temp_dir=str(TEMP_DIR),
    )
    logger.info("Starting ua-region partner scrape for KVEDs: {}", list(PARTNER_KVEDS.keys()))
    scraper.run()
    logger.info("Scrape complete.")


def _extract_city(address: str | None) -> str:
    if not address:
        return ""
    import re
    # ua-region addresses often start with "м. Київ, ..." or "с. Foo, ..."
    m = re.search(r'\b(?:м\.|місто|с\.|смт\.?|селище)\s+([А-ЯІЇЄҐа-яіїєґ\'\-]+)', address)
    if m:
        return m.group(1)
    # fallback: first comma-separated token
    parts = [p.strip() for p in address.split(",")]
    return parts[0] if parts else ""


def _priority(row: dict) -> int:
    has_email = bool(row.get("email"))
    has_phone = bool(row.get("phones"))
    has_web = bool(row.get("website"))
    if has_email and has_phone:
        return 1
    if has_email or has_phone:
        return 2
    if has_web:
        return 3
    return 4


def consolidate() -> None:
    records: list[dict] = []
    seen_edrpou: set[str] = set()

    for jsonl in sorted(OUTPUT_DIR.glob("kved_*.jsonl")):
        kved_code = jsonl.stem.replace("kved_", "").replace("_", ".")
        kved_name = PARTNER_KVEDS.get(kved_code, kved_code)
        with open(jsonl, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                edrpou = rec.get("edrpou") or ""
                if edrpou and edrpou in seen_edrpou:
                    continue
                if edrpou:
                    seen_edrpou.add(edrpou)
                records.append({
                    "КVED": kved_code,
                    "Сфера": kved_name,
                    "ЄДРПОУ": edrpou,
                    "Назва": rec.get("name", ""),
                    "Місто": _extract_city(rec.get("address")),
                    "Адреса": rec.get("address", ""),
                    "Телефони": rec.get("phones", ""),
                    "Email": rec.get("email", ""),
                    "Сайт": rec.get("website", ""),
                    "Продукція/послуги": rec.get("products_services", ""),
                    "_priority": _priority(rec),
                })

    if not records:
        logger.warning("No records found — check that scrape completed successfully.")
        return

    df = pd.DataFrame(records)
    df = df.sort_values(["_priority", "Місто", "Назва"]).drop(columns=["_priority"])
    df = df.reset_index(drop=True)

    (root / "output").mkdir(parents=True, exist_ok=True)

    df.to_csv(LEADS_CSV, index=False, encoding="utf-8-sig")
    logger.info("Saved {} leads → {}", len(df), LEADS_CSV)

    with pd.ExcelWriter(LEADS_XLSX, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Партнери", index=False)
        ws = writer.sheets["Партнери"]
        # column widths
        col_widths = {"A": 8, "B": 30, "C": 12, "D": 45, "E": 16,
                      "F": 45, "G": 22, "H": 28, "I": 28, "J": 50}
        for col, w in col_widths.items():
            ws.column_dimensions[col].width = w
        # freeze header
        ws.freeze_panes = "A2"

    logger.info("Saved Excel → {}", LEADS_XLSX)
    logger.info(
        "Priority breakdown: P1(email+phone)={} P2(one contact)={} P3(web only)={} P4(none)={}",
        (df["Email"].notna() & df["Email"].ne("") & df["Телефони"].notna() & df["Телефони"].ne("")).sum(),
        ((df["Email"].notna() & df["Email"].ne("")) ^ (df["Телефони"].notna() & df["Телефони"].ne(""))).sum(),
        (df["Email"].eq("") & df["Телефони"].eq("") & df["Сайт"].notna() & df["Сайт"].ne("")).sum(),
        (df["Email"].eq("") & df["Телефони"].eq("") & df["Сайт"].eq("")).sum(),
    )


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--scrape-only", action="store_true", help="Only scrape, skip consolidation")
    parser.add_argument("--consolidate-only", action="store_true", help="Only consolidate existing JSONL")
    args = parser.parse_args()

    if args.consolidate_only:
        consolidate()
    elif args.scrape_only:
        scrape()
    else:
        scrape()
        consolidate()
