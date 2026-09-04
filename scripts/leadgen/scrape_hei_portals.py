"""
Higher Education Institutions (HEIs / ЗВО) Scraper Pipeline for Osvita.ua & Znayshov.

Target:
  - Universities, Academies, Institutes, Colleges (Університети, Академії, Інститути, Коледжі)
  - Focus: Geography & History Wall Posters & Maps Offer (Географія, Історія, Карти, Навчальні Плакати)
"""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.parse
from pathlib import Path

import bs4
from loguru import logger

# Add scripts directory to path
ROOT = Path(__file__).resolve().parents[2]
# `school_scraper_engine` лежить поруч, у scripts/leadgen/ — після переїзду
# 2026-09-04 шлях указував на scripts/, де його вже немає.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from school_scraper_engine import SeniorRequester, CheckpointManager, HtmlCacheManager

RAW_DIR = ROOT / "data" / "raw" / "hei_portals"
RAW_DIR.mkdir(parents=True, exist_ok=True)

TARGET_KEYWORDS = [
    "географ", "істор", "природнич", "педагогіч", "гуманітарн",
    "краєзнав", "картограф", "геодез", "туризм", "еколог"
]


def extract_osvita_vnz_details(requester: SeniorRequester, vnz_url: str) -> dict | None:
    html = requester.get(vnz_url)
    if not html:
        return None

    soup = bs4.BeautifulSoup(html, "html.parser")
    
    # Extract title
    h1 = soup.find("h1") or soup.find("title")
    raw_title = h1.text.strip() if h1 else ""
    title = re.sub(r"\s*-\s*вузи України.*$", "", raw_title).strip()

    # Extract obfuscated mailto email
    email = ""
    for script in soup.find_all("script"):
        stext = script.text or ""
        if "unescape" in stext or "eval" in stext:
            matches = re.findall(r"unescape\(['\"]([^'\"]+)['\"]\)", stext)
            for m in matches:
                decoded = urllib.parse.unquote(m)
                em_match = re.search(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", decoded)
                if em_match:
                    email = em_match.group(0)
                    break
        if email:
            break

    if not email:
        em_match = re.search(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", html)
        if em_match:
            email = em_match.group(0)

    # Extract phone, address, website
    phone = ""
    address = ""
    website = ""

    # Parse contact div / text
    text_content = soup.get_text()
    phone_match = re.search(r"\(0\d{2,4}\)\s*[\d\s\-]{5,10}", text_content)
    if phone_match:
        phone = phone_match.group(0).strip()

    web_match = re.search(r"https?://[a-zA-Z0-9.-]+\.(?:edu\.ua|org\.ua|com\.ua|net\.ua|ua)", html)
    if web_match and "osvita.ua" not in web_match.group(0):
        website = web_match.group(0)

    addr_match = re.search(r"м\.\s*[А-ЯІЇЄҐa-zA-Z0-9\s.,\-]+,\s*(?:вул\.|просп\.|пл\.|пров\.)[А-ЯІЇЄҐa-zA-Z0-9\s.,\-]+", text_content)
    if addr_match:
        address = addr_match.group(0).strip()

    # Identify relevance to Geography & History
    is_target_spec = any(k in text_content.lower() for k in TARGET_KEYWORDS)

    return {
        "source": "osvita.ua/vnz",
        "name": title,
        "email": email,
        "phone": phone,
        "website": website,
        "address": address,
        "url": vnz_url,
        "target_profile": "Географія / Історія / Картографія" if is_target_spec else "Загальний ЗВО",
    }


def scrape_osvita_vnz(requester: SeniorRequester, checkpoint: CheckpointManager) -> list[dict]:
    results = []
    base_url = "https://osvita.ua/vnz/guide/"
    logger.info("Scraping osvita.ua Higher Education directory...")

    # Main catalog pages (25 VNZ per page, up to ~40 pages)
    page_urls = [base_url] + [f"https://osvita.ua/vnz/guide/list/{p}/" for p in range(25, 1000, 25)]

    for page_url in page_urls:
        if checkpoint.is_visited(page_url):
            continue

        html = requester.get(page_url)
        checkpoint.mark_visited(page_url)
        if not html:
            break

        soup = bs4.BeautifulSoup(html, "html.parser")
        vnz_links = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if re.match(r"^/vnz/guide/\d+/\s*$", href) or re.match(r"^https://osvita\.ua/vnz/guide/\d+/\s*$", href):
                full_url = href if href.startswith("http") else f"https://osvita.ua{href}"
                vnz_links.append(full_url)

        vnz_links = list(dict.fromkeys(vnz_links))
        if not vnz_links:
            logger.info("No more VNZ links found on page {}. Complete.", page_url)
            break

        logger.info("Found {} HEIs (ЗВО) on page {}", len(vnz_links), page_url)
        for vnz_url in vnz_links:
            if checkpoint.is_visited(vnz_url):
                continue

            detail = extract_osvita_vnz_details(requester, vnz_url)
            checkpoint.mark_visited(vnz_url)
            if detail:
                results.append(detail)

    out_file = RAW_DIR / "osvita_vnz.jsonl"
    with open(out_file, "a", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    logger.info("Saved {} HEI (ЗВО) records -> {}", len(results), out_file)
    return results


def main():
    logger.info("Starting Senior Higher Education Institutions (ЗВО) Scraper...")
    requester = SeniorRequester(use_cache=True, use_proxies=False)
    checkpoint = CheckpointManager(state_file=RAW_DIR / "hei_scraper_state.json")

    scrape_osvita_vnz(requester, checkpoint)
    logger.info("Higher Education Scraper finished successfully!")


if __name__ == "__main__":
    main()
