"""
School & Education lead scraper — finds general secondary schools, colleges,
kindergartens, and educational institutions on ua-region.com.ua for NUSH atlas & map outreach.

Target KVEDs (Section 85):
  85.31 — Загальна середня освіта (Школи, ліцеї, гімназії)
  85.20 — Початкова освіта
  85.10 — Дошкільна освіта
  85.32 — Професійно-технічна освіта
  85.41 — Фахова передвища освіта
  85.59 — Інші види освіти
  85.60 — Допоміжна діяльність у сфері освіти
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import atlas_bootstrap  # noqa: F401,E402  корінь repo + atlas-maps
import pandas as pd
from loguru import logger

from importers.ua_region_scraper import UARegionScraper

SCHOOL_KVEDS = {
    "85.31": "Загальна середня освіта (Школи, ліцеї, гімназії)",
    "85.20": "Початкова освіта",
    "85.10": "Дошкільна освіта",
    "85.32": "Професійно-технічна освіта",
    "85.41": "Фахова передвища освіта",
    "85.59": "Інші види освіти (позашкільні заклади, центри)",
    "85.60": "Допоміжна діяльність у сфері освіти (ІРЦ, меткабінети)",
}

OUTPUT_DIR = root / "data" / "raw" / "ua_region_schools"
TEMP_DIR = root / "temp_data" / "ua_region_schools"
LEADS_XLSX = root / "output" / "school_leads.xlsx"
LEADS_CSV = root / "output" / "school_leads.csv"


def scrape() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    TEMP_DIR.mkdir(parents=True, exist_ok=True)

    scraper = UARegionScraper(
        kveds=list(SCHOOL_KVEDS.keys()),
        output_dir=str(OUTPUT_DIR),
        temp_dir=str(TEMP_DIR),
    )
    logger.info("Starting ua-region school scrape for KVEDs: {}", list(SCHOOL_KVEDS.keys()))
    scraper.run()
    logger.info("Scrape complete.")


def _extract_city(address: str | None) -> str:
    if not address:
        return ""
    m = re.search(r'\b(?:м\.|місто|с\.|смт\.?|селище)\s+([А-ЯІЇЄҐа-яіїєґ\'\-]+)', address)
    if m:
        return m.group(1)
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
        kved_name = SCHOOL_KVEDS.get(kved_code, kved_code)
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
    logger.info("Saved {} school leads → {}", len(df), LEADS_CSV)

    with pd.ExcelWriter(LEADS_XLSX, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Освітні заклади", index=False)
        ws = writer.sheets["Освітні заклади"]
        col_widths = {"A": 8, "B": 35, "C": 12, "D": 45, "E": 16,
                      "F": 45, "G": 22, "H": 28, "I": 28, "J": 50}
        for col, w in col_widths.items():
            ws.column_dimensions[col].width = w
        ws.freeze_panes = "A2"

    logger.info("Saved Excel → {}", LEADS_XLSX)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--scrape-only", action="store_true")
    parser.add_argument("--consolidate-only", action="store_true")
    args = parser.parse_args()

    if args.consolidate_only:
        consolidate()
    elif args.scrape_only:
        scrape()
    else:
        scrape()
        consolidate()
