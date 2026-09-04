"""
Senior-Level Production School Portal Scraper.
Combines SeniorRequester, ProxyRotator, CheckpointManager, HtmlCacheManager,
and precise Parsers (ZnayshovParser & OsvitaUaParser).
"""

from __future__ import annotations

import json
import random
import sys
import time
from pathlib import Path

import bs4
from loguru import logger

from school_scrapers import OBLASTS, OsvitaUaParser, ZnayshovParser
from school_scraper_engine import (
    CheckpointManager,
    SeniorRequester,
)

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "data" / "raw" / "school_portals"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def scrape_znayshov(requester: SeniorRequester, checkpoint: CheckpointManager, max_pages_per_oblast: int = 100):
    out_file = OUTPUT_DIR / "znayshov_schools.jsonl"
    count = 0
    
    with open(out_file, "a", encoding="utf-8") as f_out:
        for obl_id, obl_name in OBLASTS.items():
            state_key = f"znayshov_oblast_{obl_id}"
            last_page = checkpoint.state.get("processed_pages", {}).get(state_key, 0)
            logger.info("Scraping znayshov.com region: {} (resuming from page {})", obl_name, last_page)
            
            page = last_page
            while page < max_pages_per_oblast:
                html = requester.post(
                    "https://znayshov.com/Schools/Search",
                    data={"pageIndex": str(page), "searchstring": "", "oblastId": obl_id},
                )
                if not html:
                    break
                    
                soup = bs4.BeautifulSoup(html, "html.parser")
                links = [a["href"] for a in soup.find_all("a", href=True) if "/Schools/Details/" in a["href"]]
                if not links:
                    break
                    
                new_links = 0
                for link in links:
                    full_url = "https://znayshov.com" + link
                    if checkpoint.is_visited(full_url):
                        continue
                        
                    det_html = requester.get(full_url)
                    if det_html:
                        rec = ZnayshovParser.parse_page(full_url, det_html)
                        if rec:
                            f_out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                            f_out.flush()
                            count += 1
                    checkpoint.mark_visited(full_url)
                    new_links += 1

                # Save checkpoint state after page
                checkpoint.state.setdefault("processed_pages", {})[state_key] = page + 1
                checkpoint.save()

                if new_links == 0:
                    break
                page += 1

    logger.info("Znayshov scrape complete. Saved records: {}", count)


def main():
    logger.info("Starting Senior-Level Production School Scraper Pipeline...")
    checkpoint = CheckpointManager()
    requester = SeniorRequester(use_cache=True)
    
    scrape_znayshov(requester, checkpoint, max_pages_per_oblast=100)


if __name__ == "__main__":
    main()
