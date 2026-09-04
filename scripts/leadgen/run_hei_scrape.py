"""
Official Registry Higher Education KVED Scraper Pipeline.

KVEDs:
  - 85.42: Вища освіта (Університети, Академії, Інститути)
  - 85.41: Фахова передвища освіта (Коледжі, Технікуми)
  - 85.32: Професійно-технічна освіта (ПТУ, Професійні ліцеї)

Target Segment:
  - Maps, History & Geography Educational Posters Offer
"""

from __future__ import annotations

import csv
import json
import os
import sys
from pathlib import Path

import pandas as pd
from loguru import logger

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import atlas_bootstrap  # noqa: F401,E402  корінь repo + atlas-maps
from importers.ua_region_scraper import UARegionScraper

RAW_DIR = ROOT / "data" / "raw" / "ua_region_hei"
OUTPUT_DIR = ROOT / "output"
RAW_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

HEI_KVEDS = ["85.42", "85.41", "85.32"]


def scrape_hei_kveds():
    logger.info("Starting ua-region Higher Education scrape for KVEDs: {}", HEI_KVEDS)
    scraper = UARegionScraper(kveds=HEI_KVEDS, output_dir=str(RAW_DIR))
    scraper.run()
    logger.info("HEI KVED scrape completed successfully.")


def consolidate_hei_data() -> pd.DataFrame:
    records: list[dict] = []
    
    for jsonl_file in sorted(RAW_DIR.glob("*.jsonl")):
        logger.info("Reading {}", jsonl_file.name)
        with open(jsonl_file, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                    records.append(data)
                except Exception:
                    continue

    df = pd.DataFrame(records)
    if df.empty:
        logger.warning("No records found in HEI KVED jsonl files.")
        return df

    logger.info("Total raw HEI KVED records: {}", len(df))
    return df


if __name__ == "__main__":
    scrape_hei_kveds()
    consolidate_hei_data()
